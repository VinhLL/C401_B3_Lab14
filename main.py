import asyncio
import json
import os
import re
import sys
import time
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from engine.llm_judge import LLMJudge
from engine.retrieval_eval import RetrievalEvaluator
from engine.runner import BenchmarkRunner


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

warnings.filterwarnings(
    "ignore",
    message=r"coroutine 'LLMJudge\._judge_.*' was never awaited",
    category=RuntimeWarning,
)


ROOT_DIR = Path(__file__).resolve().parent
DATASET_PATH = ROOT_DIR / "data" / "golden_set.jsonl"
REPORTS_DIR = ROOT_DIR / "reports"
SUMMARY_PATH = REPORTS_DIR / "summary.json"
BENCHMARK_RESULTS_PATH = REPORTS_DIR / "benchmark_results.json"

SUMMARY_SCHEMA_VERSION = "lab14.summary.v2"
RESULTS_SCHEMA_VERSION = "lab14.results.v2"
BASELINE_LABEL = "Agent_V1_Base"
CANDIDATE_LABEL = "Agent_V2_Optimized"
PASS_THRESHOLD = 3.0
BATCH_SIZE = 5
JUDGE_MODEL = os.getenv("LLM_JUDGE_MODEL", "gpt-4o")

RELEASE_THRESHOLDS = {
    "min_avg_score": 3.0,
    "min_hit_rate": 0.30,
    "min_agreement_rate": 0.50,
    "max_avg_latency_ms": 2500.0,
    "max_avg_estimated_cost": 0.12,
    "min_score_delta": 0.0,
    "min_hit_rate_delta": -0.05,
    "max_latency_delta_ms": 400.0,
    "max_cost_ratio": 1.50,
}

CHROMADB_COMPAT_STATE = {
    "checked": False,
    "applied": False,
    "aliases": [],
    "error": None,
}


class ExpertEvaluator:
    def __init__(self) -> None:
        self.retrieval_evaluator = RetrievalEvaluator()

    async def score(self, case: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        retrieval = self.retrieval_evaluator.evaluate_case(
            expected_ids=case.get("expected_retrieval_ids"),
            retrieved_ids=response.get("retrieved_ids"),
            top_k=case.get("top_k"),
            case=case,
        )
        return {
            "faithfulness": 0.9,
            "relevancy": 0.8,
            "retrieval": retrieval,
        }


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def average(values: Iterable[float]) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return sum(values_list) / len(values_list)


def round_metric(value: float, digits: int = 4) -> float:
    return round(safe_float(value), digits)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_agent_runtime_version(agent_version: str) -> str:
    return "v2" if "V2" in agent_version.upper() else "v1"


def apply_chromadb_compat_shim() -> Dict[str, Any]:
    if CHROMADB_COMPAT_STATE["checked"]:
        return CHROMADB_COMPAT_STATE

    CHROMADB_COMPAT_STATE["checked"] = True

    try:
        import opentelemetry.sdk._logs as logs
        import opentelemetry.sdk._logs.export as export

        if not hasattr(logs, "ReadableLogRecord") and hasattr(logs, "LogData"):
            logs.ReadableLogRecord = logs.LogData
            CHROMADB_COMPAT_STATE["aliases"].append(
                "opentelemetry.sdk._logs.ReadableLogRecord -> LogData"
            )

        if not hasattr(export, "LogRecordExportResult") and hasattr(export, "LogExportResult"):
            export.LogRecordExportResult = export.LogExportResult
            CHROMADB_COMPAT_STATE["aliases"].append(
                "opentelemetry.sdk._logs.export.LogRecordExportResult -> LogExportResult"
            )
    except Exception as exc:  # pragma: no cover - depends on local site-packages
        CHROMADB_COMPAT_STATE["error"] = str(exc)

    CHROMADB_COMPAT_STATE["applied"] = bool(CHROMADB_COMPAT_STATE["aliases"])
    return CHROMADB_COMPAT_STATE


def build_agent(agent_version: str) -> Any:
    apply_chromadb_compat_shim()
    from agent.main_agent import MainAgent

    return MainAgent(version=normalize_agent_runtime_version(agent_version))


def load_dataset() -> List[Dict[str, Any]]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            "Missing data/golden_set.jsonl. Run `python data/synthetic_gen.py` first."
        )

    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        dataset = [json.loads(line) for line in handle if line.strip()]

    if not dataset:
        raise ValueError("data/golden_set.jsonl is empty.")
    return dataset


def build_dataset_profile(dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    difficulty_counts = Counter()
    type_counts = Counter()
    scored_retrieval_cases = 0

    for case in dataset:
        metadata = case.get("metadata", {}) or {}
        difficulty_counts[metadata.get("difficulty", "unknown")] += 1
        type_counts[metadata.get("type", "unknown")] += 1
        if case.get("expected_retrieval_ids"):
            scored_retrieval_cases += 1

    return {
        "difficulty_distribution": dict(sorted(difficulty_counts.items())),
        "type_distribution": dict(sorted(type_counts.items())),
        "retrieval_scored_cases": scored_retrieval_cases,
        "retrieval_skipped_cases": len(dataset) - scored_retrieval_cases,
    }


def extract_judge_issue(judge_result: Dict[str, Any]) -> str | None:
    combined_text = " ".join(
        [
            str(judge_result.get("reasoning", "")),
            str(judge_result.get("conflict_note", "")),
        ]
    ).lower()

    if "invalid_api_key" in combined_text or "incorrect api key" in combined_text:
        return "invalid_api_key"
    if "llm judge unavailable" in combined_text:
        return "judge_unavailable"
    if "evaluation failed" in combined_text or "error in multi-judge evaluation" in combined_text:
        return "judge_runtime_error"
    return None


def summarize_group(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_cases = len(results)
    if total_cases == 0:
        return {
            "count": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "hit_rate": 0.0,
            "avg_mrr": 0.0,
        }

    scored_retrieval = [
        result for result in results if (result.get("retrieval") or {}).get("is_scored")
    ]
    return {
        "count": total_cases,
        "pass_rate": round_metric(
            sum(1 for result in results if result.get("status") == "pass") / total_cases
        ),
        "avg_score": round_metric(
            average(
                safe_float((result.get("judge") or {}).get("final_score")) for result in results
            )
        ),
        "hit_rate": round_metric(
            average(
                safe_float((result.get("retrieval") or {}).get("hit_rate"))
                for result in scored_retrieval
            )
        ),
        "avg_mrr": round_metric(
            average(
                safe_float((result.get("retrieval") or {}).get("mrr"))
                for result in scored_retrieval
            )
        ),
    }


def build_breakdown(results: List[Dict[str, Any]], metadata_key: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        metadata = result.get("metadata", {}) or {}
        group_name = str(metadata.get(metadata_key, "unknown"))
        grouped.setdefault(group_name, []).append(result)

    return {
        group_name: summarize_group(group_results)
        for group_name, group_results in sorted(grouped.items())
    }


def summarize_version_run(
    agent_label: str,
    runtime_version: str,
    results: List[Dict[str, Any]],
    runner: BenchmarkRunner,
    wall_clock_seconds: float,
) -> Dict[str, Any]:
    raw_summary = runner.summarize_results(results)
    total_cases = raw_summary["total_cases"]
    judge_issue_counts = Counter()

    for result in results:
        judge_issue = extract_judge_issue(result.get("judge", {}) or {})
        if judge_issue:
            judge_issue_counts[judge_issue] += 1

    metrics = {
        "avg_score": round_metric(raw_summary["avg_judge_score"]),
        "hit_rate": round_metric(raw_summary["avg_hit_rate"]),
        "avg_hit_rate": round_metric(raw_summary["avg_hit_rate"]),
        "avg_mrr": round_metric(raw_summary["avg_mrr"]),
        "agreement_rate": round_metric(raw_summary["agreement_rate"]),
        "avg_latency_ms": round(safe_float(raw_summary["avg_latency_ms"]), 2),
        "avg_tokens_used": round(safe_float(raw_summary["avg_tokens_used"]), 2),
        "avg_estimated_cost": round(safe_float(raw_summary["avg_estimated_cost"]), 6),
        "pass_rate": round_metric(raw_summary["pass_cases"] / total_cases if total_cases else 0.0),
        "error_rate": round_metric(raw_summary["error_cases"] / total_cases if total_cases else 0.0),
    }

    scored_retrieval_cases = sum(
        1 for result in results if (result.get("retrieval") or {}).get("is_scored")
    )

    return {
        "agent_version": agent_label,
        "runtime_version": runtime_version,
        "judge_model": JUDGE_MODEL,
        "total_cases": total_cases,
        "scored_retrieval_cases": scored_retrieval_cases,
        "skipped_retrieval_cases": total_cases - scored_retrieval_cases,
        "status_counts": {
            "pass": raw_summary["pass_cases"],
            "fail": raw_summary["fail_cases"],
            "error": raw_summary["error_cases"],
        },
        "metrics": metrics,
        "wall_clock_seconds": round(wall_clock_seconds, 2),
        "judge_issue_counts": dict(sorted(judge_issue_counts.items())),
        "breakdown": {
            "difficulty": build_breakdown(results, "difficulty"),
            "type": build_breakdown(results, "type"),
        },
    }


def build_case_comparisons(
    dataset: List[Dict[str, Any]],
    baseline_results: List[Dict[str, Any]],
    candidate_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    baseline_by_case = {result.get("case_id"): result for result in baseline_results}
    candidate_by_case = {result.get("case_id"): result for result in candidate_results}

    comparisons: List[Dict[str, Any]] = []
    for case in dataset:
        case_id = case.get("case_id")
        baseline = baseline_by_case.get(case_id, {})
        candidate = candidate_by_case.get(case_id, {})
        baseline_score = safe_float((baseline.get("judge") or {}).get("final_score"))
        candidate_score = safe_float((candidate.get("judge") or {}).get("final_score"))
        baseline_hit_rate = safe_float((baseline.get("retrieval") or {}).get("hit_rate"))
        candidate_hit_rate = safe_float((candidate.get("retrieval") or {}).get("hit_rate"))
        baseline_mrr = safe_float((baseline.get("retrieval") or {}).get("mrr"))
        candidate_mrr = safe_float((candidate.get("retrieval") or {}).get("mrr"))
        baseline_latency_ms = safe_float(baseline.get("latency_ms"))
        candidate_latency_ms = safe_float(candidate.get("latency_ms"))
        baseline_cost = safe_float(baseline.get("estimated_cost"))
        candidate_cost = safe_float(candidate.get("estimated_cost"))

        comparisons.append(
            {
                "case_id": case_id,
                "question": case.get("question", ""),
                "difficulty": (case.get("metadata", {}) or {}).get("difficulty", "unknown"),
                "type": (case.get("metadata", {}) or {}).get("type", "unknown"),
                "baseline_status": baseline.get("status"),
                "candidate_status": candidate.get("status"),
                "baseline_score": round_metric(baseline_score),
                "candidate_score": round_metric(candidate_score),
                "score_delta": round_metric(candidate_score - baseline_score),
                "baseline_hit_rate": round_metric(baseline_hit_rate),
                "candidate_hit_rate": round_metric(candidate_hit_rate),
                "hit_rate_delta": round_metric(candidate_hit_rate - baseline_hit_rate),
                "baseline_mrr": round_metric(baseline_mrr),
                "candidate_mrr": round_metric(candidate_mrr),
                "mrr_delta": round_metric(candidate_mrr - baseline_mrr),
                "baseline_latency_ms": round(baseline_latency_ms, 2),
                "candidate_latency_ms": round(candidate_latency_ms, 2),
                "latency_delta_ms": round(candidate_latency_ms - baseline_latency_ms, 2),
                "baseline_estimated_cost": round(baseline_cost, 6),
                "candidate_estimated_cost": round(candidate_cost, 6),
                "estimated_cost_delta": round(candidate_cost - baseline_cost, 6),
            }
        )

    return comparisons


def build_regression_summary(
    baseline_summary: Dict[str, Any],
    candidate_summary: Dict[str, Any],
    comparisons: List[Dict[str, Any]],
) -> Dict[str, Any]:
    baseline_metrics = baseline_summary["metrics"]
    candidate_metrics = candidate_summary["metrics"]
    delta = {
        "avg_score": round_metric(candidate_metrics["avg_score"] - baseline_metrics["avg_score"]),
        "hit_rate": round_metric(candidate_metrics["hit_rate"] - baseline_metrics["hit_rate"]),
        "avg_mrr": round_metric(candidate_metrics["avg_mrr"] - baseline_metrics["avg_mrr"]),
        "agreement_rate": round_metric(
            candidate_metrics["agreement_rate"] - baseline_metrics["agreement_rate"]
        ),
        "avg_latency_ms": round(
            candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"], 2
        ),
        "avg_estimated_cost": round(
            candidate_metrics["avg_estimated_cost"] - baseline_metrics["avg_estimated_cost"], 6
        ),
    }

    return {
        "baseline_version": baseline_summary["agent_version"],
        "candidate_version": candidate_summary["agent_version"],
        "delta": delta,
        "score_improved_cases": sum(1 for item in comparisons if item["score_delta"] > 0),
        "score_regressed_cases": sum(1 for item in comparisons if item["score_delta"] < 0),
        "score_unchanged_cases": sum(1 for item in comparisons if item["score_delta"] == 0),
        "retrieval_improved_cases": sum(1 for item in comparisons if item["hit_rate_delta"] > 0),
        "retrieval_regressed_cases": sum(1 for item in comparisons if item["hit_rate_delta"] < 0),
        "retrieval_unchanged_cases": sum(1 for item in comparisons if item["hit_rate_delta"] == 0),
    }


def build_release_gate(
    baseline_summary: Dict[str, Any],
    candidate_summary: Dict[str, Any],
) -> Dict[str, Any]:
    baseline_metrics = baseline_summary["metrics"]
    candidate_metrics = candidate_summary["metrics"]

    score_delta = candidate_metrics["avg_score"] - baseline_metrics["avg_score"]
    hit_rate_delta = candidate_metrics["hit_rate"] - baseline_metrics["hit_rate"]
    latency_delta_ms = candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"]
    baseline_cost = baseline_metrics["avg_estimated_cost"]
    candidate_cost = candidate_metrics["avg_estimated_cost"]
    if baseline_cost <= 0:
        cost_ratio = 0.0 if candidate_cost <= 0 else float("inf")
    else:
        cost_ratio = candidate_cost / baseline_cost

    checks = [
        {
            "name": "candidate_avg_score_floor",
            "metric": "avg_score",
            "operator": ">=",
            "threshold": RELEASE_THRESHOLDS["min_avg_score"],
            "baseline": baseline_metrics["avg_score"],
            "candidate": candidate_metrics["avg_score"],
            "passed": candidate_metrics["avg_score"] >= RELEASE_THRESHOLDS["min_avg_score"],
        },
        {
            "name": "candidate_hit_rate_floor",
            "metric": "hit_rate",
            "operator": ">=",
            "threshold": RELEASE_THRESHOLDS["min_hit_rate"],
            "baseline": baseline_metrics["hit_rate"],
            "candidate": candidate_metrics["hit_rate"],
            "passed": candidate_metrics["hit_rate"] >= RELEASE_THRESHOLDS["min_hit_rate"],
        },
        {
            "name": "candidate_agreement_rate_floor",
            "metric": "agreement_rate",
            "operator": ">=",
            "threshold": RELEASE_THRESHOLDS["min_agreement_rate"],
            "baseline": baseline_metrics["agreement_rate"],
            "candidate": candidate_metrics["agreement_rate"],
            "passed": (
                candidate_metrics["agreement_rate"] >= RELEASE_THRESHOLDS["min_agreement_rate"]
            ),
        },
        {
            "name": "candidate_latency_ceiling",
            "metric": "avg_latency_ms",
            "operator": "<=",
            "threshold": RELEASE_THRESHOLDS["max_avg_latency_ms"],
            "baseline": baseline_metrics["avg_latency_ms"],
            "candidate": candidate_metrics["avg_latency_ms"],
            "passed": candidate_metrics["avg_latency_ms"] <= RELEASE_THRESHOLDS["max_avg_latency_ms"],
        },
        {
            "name": "candidate_cost_ceiling",
            "metric": "avg_estimated_cost",
            "operator": "<=",
            "threshold": RELEASE_THRESHOLDS["max_avg_estimated_cost"],
            "baseline": baseline_metrics["avg_estimated_cost"],
            "candidate": candidate_metrics["avg_estimated_cost"],
            "passed": (
                candidate_metrics["avg_estimated_cost"]
                <= RELEASE_THRESHOLDS["max_avg_estimated_cost"]
            ),
        },
        {
            "name": "score_delta_guard",
            "metric": "avg_score_delta",
            "operator": ">=",
            "threshold": RELEASE_THRESHOLDS["min_score_delta"],
            "baseline": 0.0,
            "candidate": round_metric(score_delta),
            "passed": score_delta >= RELEASE_THRESHOLDS["min_score_delta"],
        },
        {
            "name": "hit_rate_delta_guard",
            "metric": "hit_rate_delta",
            "operator": ">=",
            "threshold": RELEASE_THRESHOLDS["min_hit_rate_delta"],
            "baseline": 0.0,
            "candidate": round_metric(hit_rate_delta),
            "passed": hit_rate_delta >= RELEASE_THRESHOLDS["min_hit_rate_delta"],
        },
        {
            "name": "latency_delta_guard",
            "metric": "latency_delta_ms",
            "operator": "<=",
            "threshold": RELEASE_THRESHOLDS["max_latency_delta_ms"],
            "baseline": 0.0,
            "candidate": round(latency_delta_ms, 2),
            "passed": latency_delta_ms <= RELEASE_THRESHOLDS["max_latency_delta_ms"],
        },
        {
            "name": "cost_ratio_guard",
            "metric": "cost_ratio",
            "operator": "<=",
            "threshold": RELEASE_THRESHOLDS["max_cost_ratio"],
            "baseline": 1.0,
            "candidate": round(cost_ratio, 4) if cost_ratio != float("inf") else "inf",
            "passed": cost_ratio <= RELEASE_THRESHOLDS["max_cost_ratio"],
        },
    ]

    failed_checks = [check["name"] for check in checks if not check["passed"]]
    return {
        "decision": "release" if not failed_checks else "block",
        "passed": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "thresholds": RELEASE_THRESHOLDS,
    }


def sanitize_text(value: str) -> str:
    if not isinstance(value, str):
        return value

    sanitized = re.sub(r"sk-[A-Za-z0-9_\-*/.]+", "sk-***REDACTED***", value)
    return sanitized


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


async def run_version(
    agent_label: str,
    dataset: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    runtime_version = normalize_agent_runtime_version(agent_label)
    runner = BenchmarkRunner(
        agent=build_agent(agent_label),
        evaluator=ExpertEvaluator(),
        judge=LLMJudge(model=JUDGE_MODEL),
        pass_threshold=PASS_THRESHOLD,
    )

    started_at = time.perf_counter()
    results = await runner.run_all(dataset, batch_size=BATCH_SIZE)
    wall_clock_seconds = time.perf_counter() - started_at
    summary = summarize_version_run(agent_label, runtime_version, results, runner, wall_clock_seconds)
    return results, summary


async def main() -> int:
    try:
        dataset = load_dataset()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    dataset_profile = build_dataset_profile(dataset)
    print(
        f"Running benchmark on {len(dataset)} cases "
        f"(V1={BASELINE_LABEL}, V2={CANDIDATE_LABEL}, batch_size={BATCH_SIZE})"
    )

    try:
        baseline_results, baseline_summary = await run_version(BASELINE_LABEL, dataset)
        candidate_results, candidate_summary = await run_version(CANDIDATE_LABEL, dataset)
    except Exception as exc:
        print(f"[ERROR] Benchmark execution failed: {exc}")
        return 1

    comparisons = build_case_comparisons(dataset, baseline_results, candidate_results)
    regression = build_regression_summary(baseline_summary, candidate_summary, comparisons)
    release_gate = build_release_gate(baseline_summary, candidate_summary)

    notes: List[str] = []
    if CHROMADB_COMPAT_STATE["applied"]:
        notes.append(
            "Applied local ChromaDB/OpenTelemetry compatibility aliases from main.py to avoid import failure."
        )
    if CHROMADB_COMPAT_STATE["error"]:
        notes.append(f"Compatibility shim warning: {CHROMADB_COMPAT_STATE['error']}")
    if candidate_summary["judge_issue_counts"]:
        notes.append(
            "Judge backend produced runtime issues during the candidate run; inspect judge_issue_counts for details."
        )

    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "metadata": {
            "version": CANDIDATE_LABEL,
            "baseline_version": BASELINE_LABEL,
            "candidate_version": CANDIDATE_LABEL,
            "dataset_path": str(DATASET_PATH.relative_to(ROOT_DIR)),
            "dataset_size": len(dataset),
            "total": len(dataset),
            "scored_retrieval_cases": candidate_summary["scored_retrieval_cases"],
            "skipped_retrieval_cases": candidate_summary["skipped_retrieval_cases"],
            "pass_threshold": PASS_THRESHOLD,
            "batch_size": BATCH_SIZE,
            "judge_model": JUDGE_MODEL,
            "dataset_profile": dataset_profile,
            "chromadb_compat": CHROMADB_COMPAT_STATE,
            "notes": notes,
        },
        "metrics": candidate_summary["metrics"],
        "versions": {
            "v1": baseline_summary,
            "v2": candidate_summary,
        },
        "regression": regression,
        "release_gate": release_gate,
    }

    benchmark_results_payload = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "metadata": {
            "baseline_version": BASELINE_LABEL,
            "candidate_version": CANDIDATE_LABEL,
            "dataset_size": len(dataset),
            "dataset_path": str(DATASET_PATH.relative_to(ROOT_DIR)),
            "judge_model": JUDGE_MODEL,
            "pass_threshold": PASS_THRESHOLD,
        },
        "versions": {
            "v1": {
                "agent_version": BASELINE_LABEL,
                "runtime_version": baseline_summary["runtime_version"],
                "total_cases": len(baseline_results),
                "results": baseline_results,
            },
            "v2": {
                "agent_version": CANDIDATE_LABEL,
                "runtime_version": candidate_summary["runtime_version"],
                "total_cases": len(candidate_results),
                "results": candidate_results,
            },
        },
        "comparisons": {
            "overview": regression,
            "by_case": comparisons,
        },
    }

    write_json(SUMMARY_PATH, sanitize_payload(summary_payload))
    write_json(BENCHMARK_RESULTS_PATH, sanitize_payload(benchmark_results_payload))

    decision = summary_payload["release_gate"]["decision"].upper()
    print(f"V1 avg_score: {baseline_summary['metrics']['avg_score']:.4f}")
    print(f"V2 avg_score: {candidate_summary['metrics']['avg_score']:.4f}")
    print(f"Delta avg_score: {regression['delta']['avg_score']:+.4f}")
    print(f"Decision: {decision}")
    print(f"Wrote: {SUMMARY_PATH.relative_to(ROOT_DIR)}")
    print(f"Wrote: {BENCHMARK_RESULTS_PATH.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
