import json
import sys
from pathlib import Path
from typing import Any, Dict, List


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = ROOT_DIR / "reports" / "summary.json"
BENCHMARK_RESULTS_PATH = ROOT_DIR / "reports" / "benchmark_results.json"
FAILURE_ANALYSIS_PATH = ROOT_DIR / "analysis" / "failure_analysis.md"
REFLECTIONS_DIR = ROOT_DIR / "analysis" / "reflections"


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def expect_keys(payload: Dict[str, Any], required_keys: List[str], label: str, errors: List[str]) -> None:
    missing = [key for key in required_keys if key not in payload]
    if missing:
        errors.append(f"{label} is missing keys: {', '.join(missing)}")


def validate_summary(payload: Dict[str, Any], errors: List[str]) -> None:
    expect_keys(
        payload,
        ["schema_version", "generated_at", "metadata", "metrics", "versions", "regression", "release_gate"],
        "reports/summary.json",
        errors,
    )
    if errors:
        return

    metadata = payload.get("metadata", {})
    metrics = payload.get("metrics", {})
    versions = payload.get("versions", {})
    release_gate = payload.get("release_gate", {})

    expect_keys(
        metadata,
        [
            "version",
            "baseline_version",
            "candidate_version",
            "dataset_path",
            "dataset_size",
            "scored_retrieval_cases",
            "skipped_retrieval_cases",
            "pass_threshold",
            "batch_size",
            "judge_model",
            "dataset_profile",
        ],
        "summary.metadata",
        errors,
    )
    expect_keys(
        metrics,
        [
            "avg_score",
            "hit_rate",
            "avg_hit_rate",
            "avg_mrr",
            "agreement_rate",
            "avg_latency_ms",
            "avg_tokens_used",
            "avg_estimated_cost",
            "pass_rate",
            "error_rate",
        ],
        "summary.metrics",
        errors,
    )
    expect_keys(versions, ["v1", "v2"], "summary.versions", errors)
    expect_keys(
        release_gate,
        ["decision", "passed", "checks", "failed_checks", "thresholds"],
        "summary.release_gate",
        errors,
    )

    for version_key in ("v1", "v2"):
        version_payload = versions.get(version_key, {})
        expect_keys(
            version_payload,
            [
                "agent_version",
                "runtime_version",
                "judge_model",
                "total_cases",
                "scored_retrieval_cases",
                "skipped_retrieval_cases",
                "status_counts",
                "metrics",
                "wall_clock_seconds",
                "judge_issue_counts",
                "breakdown",
            ],
            f"summary.versions.{version_key}",
            errors,
        )


def validate_case_result(case_result: Dict[str, Any], label: str, errors: List[str]) -> None:
    expect_keys(
        case_result,
        [
            "case_id",
            "question",
            "expected_answer",
            "expected_retrieval_ids",
            "metadata",
            "answer",
            "contexts",
            "retrieved_ids",
            "version",
            "tokens_used",
            "estimated_cost",
            "latency_ms",
            "retrieval",
            "judge",
            "status",
            "passed",
        ],
        label,
        errors,
    )
    retrieval = case_result.get("retrieval", {})
    judge = case_result.get("judge", {})
    expect_keys(
        retrieval,
        ["hit_rate", "mrr", "top_k", "is_scored", "skip_reason"],
        f"{label}.retrieval",
        errors,
    )
    expect_keys(
        judge,
        ["final_score", "agreement_rate", "individual_scores", "reasoning", "conflict_note"],
        f"{label}.judge",
        errors,
    )


def validate_benchmark_results(payload: Dict[str, Any], errors: List[str]) -> None:
    expect_keys(
        payload,
        ["schema_version", "generated_at", "metadata", "versions", "comparisons"],
        "reports/benchmark_results.json",
        errors,
    )
    if errors:
        return

    metadata = payload.get("metadata", {})
    versions = payload.get("versions", {})
    comparisons = payload.get("comparisons", {})

    expect_keys(
        metadata,
        ["baseline_version", "candidate_version", "dataset_size", "dataset_path", "judge_model", "pass_threshold"],
        "benchmark_results.metadata",
        errors,
    )
    expect_keys(versions, ["v1", "v2"], "benchmark_results.versions", errors)
    expect_keys(comparisons, ["overview", "by_case"], "benchmark_results.comparisons", errors)

    for version_key in ("v1", "v2"):
        version_payload = versions.get(version_key, {})
        expect_keys(
            version_payload,
            ["agent_version", "runtime_version", "total_cases", "results"],
            f"benchmark_results.versions.{version_key}",
            errors,
        )
        results = version_payload.get("results", [])
        if not isinstance(results, list) or not results:
            errors.append(f"benchmark_results.versions.{version_key}.results must be a non-empty list")
            continue
        validate_case_result(results[0], f"benchmark_results.versions.{version_key}.results[0]", errors)

    by_case = comparisons.get("by_case", [])
    if not isinstance(by_case, list) or not by_case:
        errors.append("benchmark_results.comparisons.by_case must be a non-empty list")
    else:
        expect_keys(
            by_case[0],
            [
                "case_id",
                "question",
                "difficulty",
                "type",
                "baseline_status",
                "candidate_status",
                "score_delta",
                "hit_rate_delta",
                "mrr_delta",
                "latency_delta_ms",
                "estimated_cost_delta",
            ],
            "benchmark_results.comparisons.by_case[0]",
            errors,
        )


def validate_failure_analysis(errors: List[str]) -> None:
    if not FAILURE_ANALYSIS_PATH.exists():
        errors.append("Missing analysis/failure_analysis.md")
        return

    content = FAILURE_ANALYSIS_PATH.read_text(encoding="utf-8").strip()
    required_sections = [
        "## 1. Tổng quan Benchmark",
        "## 2. Phân nhóm lỗi",
        "## 3. Phân tích 5 Whys",
        "## 4. Kế hoạch cải tiến",
    ]
    for section in required_sections:
        if section not in content:
            errors.append(f"analysis/failure_analysis.md is missing section: {section}")


def validate_reflections_dir(errors: List[str]) -> None:
    if not REFLECTIONS_DIR.exists():
        errors.append("Missing analysis/reflections directory")


def validate_lab() -> int:
    print("Checking lab artifacts...")

    required_paths = [SUMMARY_PATH, BENCHMARK_RESULTS_PATH, FAILURE_ANALYSIS_PATH]
    errors: List[str] = []

    for path in required_paths:
        if path.exists():
            print(f"[OK] {path.relative_to(ROOT_DIR)}")
        else:
            errors.append(f"Missing required file: {path.relative_to(ROOT_DIR)}")

    validate_reflections_dir(errors)

    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        print("Validation failed.")
        return 1

    try:
        summary_payload = read_json(SUMMARY_PATH)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] reports/summary.json is not valid JSON: {exc}")
        return 1

    try:
        benchmark_results_payload = read_json(BENCHMARK_RESULTS_PATH)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] reports/benchmark_results.json is not valid JSON: {exc}")
        return 1

    validate_summary(summary_payload, errors)
    validate_benchmark_results(benchmark_results_payload, errors)
    validate_failure_analysis(errors)

    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        print("Validation failed.")
        return 1

    metrics = summary_payload["metrics"]
    release_gate = summary_payload["release_gate"]
    print("--- Quick Stats ---")
    print(f"Total cases: {summary_payload['metadata']['dataset_size']}")
    print(f"Candidate avg_score: {metrics['avg_score']:.4f}")
    print(f"Candidate hit_rate: {metrics['hit_rate']:.4f}")
    print(f"Candidate agreement_rate: {metrics['agreement_rate']:.4f}")
    print(f"Release gate decision: {release_gate['decision']}")
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate_lab())
