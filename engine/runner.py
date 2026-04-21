import asyncio
import inspect
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


class BenchmarkRunner:
    def __init__(
        self,
        agent: Any,
        evaluator: Any,
        judge: Any,
        *,
        pass_threshold: float = 3.0,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.75,
        max_concurrency: Optional[int] = None,
    ) -> None:
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge
        self.pass_threshold = float(pass_threshold)
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.max_concurrency = max_concurrency

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _call_with_retry(
        self,
        label: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Tuple[Any, int]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                result = func(*args, **kwargs)
                return await self._maybe_await(result), attempt
            except Exception as exc:  # pragma: no cover - depends on runtime integrations
                last_error = exc
                if attempt >= self.retry_attempts:
                    break
                await asyncio.sleep(self.retry_backoff_seconds * attempt)

        assert last_error is not None
        raise RuntimeError(
            f"{label} failed after {self.retry_attempts} attempts: {last_error}"
        ) from last_error

    def _as_list(self, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _resolve_case_top_k(self, test_case: Dict[str, Any], response: Dict[str, Any]) -> Optional[int]:
        metadata = self._as_dict(test_case.get("metadata"))
        candidate = (
            test_case.get("top_k")
            or metadata.get("top_k")
            or response.get("top_k")
            or getattr(self.agent, "top_k", None)
        )
        try:
            return int(candidate) if candidate is not None else None
        except (TypeError, ValueError):
            return None

    def _default_retrieval_result(
        self,
        test_case: Dict[str, Any],
        response: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        response = response or {}
        retrieved_ids = self._as_list(response.get("retrieved_ids"))
        expected_ids = self._as_list(test_case.get("expected_retrieval_ids"))
        top_k = self._resolve_case_top_k(test_case, response)

        if not expected_ids:
            skip_reason = "empty_expected_retrieval_ids"
            hit_rate = 0.0
            mrr = 0.0
            is_scored = False
        else:
            first_rank = None
            for index, doc_id in enumerate(retrieved_ids, start=1):
                if doc_id in expected_ids:
                    first_rank = index
                    break
            limit = top_k if top_k is not None else len(retrieved_ids)
            top_retrieved = retrieved_ids[: max(0, limit)]
            hit_rate = 1.0 if any(doc_id in expected_ids for doc_id in top_retrieved) else 0.0
            mrr = (1.0 / first_rank) if first_rank else 0.0
            skip_reason = None
            is_scored = True

        result = {
            "hit_rate": hit_rate,
            "mrr": mrr,
            "top_k": top_k if top_k is not None else len(retrieved_ids),
            "expected_count": len(expected_ids),
            "retrieved_count": len(retrieved_ids),
            "matched_expected_ids": [doc_id for doc_id in retrieved_ids if doc_id in expected_ids],
            "first_relevant_rank": next(
                (index for index, doc_id in enumerate(retrieved_ids, start=1) if doc_id in expected_ids),
                None,
            ),
            "is_scored": is_scored,
            "skip_reason": skip_reason,
        }

        if error_message:
            result["error"] = error_message
        return result

    async def _extract_retrieval_result(
        self,
        test_case: Dict[str, Any],
        response: Dict[str, Any],
        ragas_scores: Dict[str, Any],
    ) -> Dict[str, Any]:
        embedded = ragas_scores.get("retrieval")
        if isinstance(embedded, dict):
            return embedded

        if hasattr(self.evaluator, "evaluate_case"):
            result = self.evaluator.evaluate_case(
                expected_ids=test_case.get("expected_retrieval_ids"),
                retrieved_ids=response.get("retrieved_ids"),
                top_k=self._resolve_case_top_k(test_case, response),
                case=test_case,
            )
            return self._as_dict(await self._maybe_await(result)) or self._default_retrieval_result(test_case, response)

        retrieval_evaluator = getattr(self.evaluator, "retrieval_evaluator", None)
        if retrieval_evaluator and hasattr(retrieval_evaluator, "evaluate_case"):
            result = retrieval_evaluator.evaluate_case(
                expected_ids=test_case.get("expected_retrieval_ids"),
                retrieved_ids=response.get("retrieved_ids"),
                top_k=self._resolve_case_top_k(test_case, response),
                case=test_case,
            )
            return self._as_dict(await self._maybe_await(result)) or self._default_retrieval_result(test_case, response)

        return self._default_retrieval_result(test_case, response)

    async def _score_response(
        self,
        test_case: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], int]:
        if hasattr(self.evaluator, "score"):
            ragas_scores, attempts = await self._call_with_retry(
                "evaluator.score",
                self.evaluator.score,
                test_case,
                response,
            )
            ragas = self._as_dict(ragas_scores)
        else:
            ragas = {}
            attempts = 0

        retrieval_result = await self._extract_retrieval_result(test_case, response, ragas)
        ragas["retrieval"] = retrieval_result
        return ragas, attempts

    def _default_judge_result(self, error_message: Optional[str] = None) -> Dict[str, Any]:
        return {
            "final_score": 0.0,
            "agreement_rate": 0.0,
            "individual_scores": {},
            "reasoning": error_message or "Judge evaluation was skipped.",
            "conflict_note": error_message or "Judge evaluation was skipped.",
        }

    def _build_error_result(
        self,
        test_case: Dict[str, Any],
        error_message: str,
        *,
        started_at: float,
        agent_attempts: int = 0,
        evaluator_attempts: int = 0,
        judge_attempts: int = 0,
        partial_response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = partial_response or {}
        total_latency_seconds = time.perf_counter() - started_at
        retrieval_result = self._default_retrieval_result(
            test_case,
            response=response,
            error_message=error_message,
        )
        ragas_scores = {"retrieval": retrieval_result, "error": error_message}

        return {
            "case_id": test_case.get("case_id"),
            "question": test_case.get("question", ""),
            "expected_answer": test_case.get("expected_answer", ""),
            "expected_retrieval_ids": self._as_list(test_case.get("expected_retrieval_ids")),
            "metadata": self._as_dict(test_case.get("metadata")),
            "answer": response.get("answer", ""),
            "agent_response": response.get("answer", ""),
            "contexts": self._as_list(response.get("contexts")),
            "retrieved_ids": self._as_list(response.get("retrieved_ids")),
            "version": response.get("version") or getattr(self.agent, "version", None),
            "tokens_used": self._safe_float(response.get("tokens_used"), 0.0),
            "estimated_cost": self._safe_float(response.get("estimated_cost"), 0.0),
            "latency": round(total_latency_seconds, 6),
            "latency_ms": round(total_latency_seconds * 1000, 2),
            "agent_latency_ms": None,
            "ragas": ragas_scores,
            "retrieval": retrieval_result,
            "judge": self._default_judge_result(error_message),
            "status": "error",
            "passed": False,
            "error": error_message,
            "attempts": {
                "agent": agent_attempts,
                "evaluator": evaluator_attempts,
                "judge": judge_attempts,
            },
        }

    async def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        started_at = time.perf_counter()
        question = test_case.get("question", "")

        if not question:
            return self._build_error_result(
                test_case,
                "Test case is missing a question.",
                started_at=started_at,
            )

        try:
            agent_started_at = time.perf_counter()
            response, agent_attempts = await self._call_with_retry(
                "agent.query",
                self.agent.query,
                question,
            )
            agent_latency_ms = (time.perf_counter() - agent_started_at) * 1000
            response = self._as_dict(response)
        except Exception as exc:
            return self._build_error_result(
                test_case,
                str(exc),
                started_at=started_at,
            )

        try:
            ragas_scores, evaluator_attempts = await self._score_response(test_case, response)
        except Exception as exc:
            return self._build_error_result(
                test_case,
                str(exc),
                started_at=started_at,
                agent_attempts=agent_attempts,
                partial_response=response,
            )

        retrieval_result = self._as_dict(ragas_scores.get("retrieval"))

        try:
            judge_result, judge_attempts = await self._call_with_retry(
                "judge.evaluate_multi_judge",
                self.judge.evaluate_multi_judge,
                question,
                response.get("answer", ""),
                test_case.get("expected_answer", ""),
            )
            judge_result = self._as_dict(judge_result)
        except Exception as exc:
            error_message = str(exc)
            judge_result = self._default_judge_result(error_message)
            judge_attempts = self.retry_attempts
            ragas_scores["judge_error"] = error_message

        total_latency_seconds = time.perf_counter() - started_at
        final_score = self._safe_float(judge_result.get("final_score"), 0.0)
        status = "pass" if final_score >= self.pass_threshold else "fail"

        return {
            "case_id": test_case.get("case_id"),
            "question": question,
            "expected_answer": test_case.get("expected_answer", ""),
            "expected_retrieval_ids": self._as_list(test_case.get("expected_retrieval_ids")),
            "metadata": self._as_dict(test_case.get("metadata")),
            "answer": response.get("answer", ""),
            "agent_response": response.get("answer", ""),
            "contexts": self._as_list(response.get("contexts")),
            "retrieved_ids": self._as_list(response.get("retrieved_ids")),
            "version": response.get("version") or getattr(self.agent, "version", None),
            "tokens_used": self._safe_float(response.get("tokens_used"), 0.0),
            "estimated_cost": self._safe_float(response.get("estimated_cost"), 0.0),
            "latency": round(total_latency_seconds, 6),
            "latency_ms": round(total_latency_seconds * 1000, 2),
            "agent_latency_ms": round(agent_latency_ms, 2),
            "ragas": ragas_scores,
            "retrieval": retrieval_result,
            "judge": judge_result,
            "status": status,
            "passed": status == "pass",
            "error": None,
            "attempts": {
                "agent": agent_attempts,
                "evaluator": evaluator_attempts,
                "judge": judge_attempts,
            },
        }

    async def _run_with_semaphore(
        self,
        test_case: Dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        async with semaphore:
            started_at = time.perf_counter()
            try:
                return await self.run_single_test(test_case)
            except Exception as exc:  # pragma: no cover - last-resort safety net
                return self._build_error_result(
                    test_case,
                    f"Unhandled runner error: {exc}",
                    started_at=started_at,
                )

    async def run_all(self, dataset: List[Dict[str, Any]], batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        Run the full benchmark pipeline asynchronously in bounded batches.
        """
        if not dataset:
            return []

        normalized_batch_size = max(1, int(batch_size))
        concurrency = self.max_concurrency or normalized_batch_size
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        results: List[Dict[str, Any]] = []
        for offset in range(0, len(dataset), normalized_batch_size):
            batch = dataset[offset : offset + normalized_batch_size]
            tasks = [self._run_with_semaphore(case, semaphore) for case in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

        return results

    def summarize_results(self, results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        results_list = list(results)
        total_cases = len(results_list)
        if total_cases == 0:
            return {
                "total_cases": 0,
                "pass_cases": 0,
                "fail_cases": 0,
                "error_cases": 0,
                "avg_latency_ms": 0.0,
                "avg_tokens_used": 0.0,
                "avg_estimated_cost": 0.0,
                "avg_judge_score": 0.0,
                "avg_hit_rate": 0.0,
                "avg_mrr": 0.0,
                "agreement_rate": 0.0,
            }

        pass_cases = sum(1 for result in results_list if result.get("status") == "pass")
        fail_cases = sum(1 for result in results_list if result.get("status") == "fail")
        error_cases = sum(1 for result in results_list if result.get("status") == "error")

        scored_retrieval = [
            result
            for result in results_list
            if self._as_dict(result.get("retrieval")).get("is_scored")
        ]

        return {
            "total_cases": total_cases,
            "pass_cases": pass_cases,
            "fail_cases": fail_cases,
            "error_cases": error_cases,
            "avg_latency_ms": sum(self._safe_float(result.get("latency_ms")) for result in results_list) / total_cases,
            "avg_tokens_used": sum(self._safe_float(result.get("tokens_used")) for result in results_list) / total_cases,
            "avg_estimated_cost": sum(self._safe_float(result.get("estimated_cost")) for result in results_list) / total_cases,
            "avg_judge_score": sum(
                self._safe_float(self._as_dict(result.get("judge")).get("final_score"))
                for result in results_list
            ) / total_cases,
            "avg_hit_rate": (
                sum(self._safe_float(self._as_dict(result.get("retrieval")).get("hit_rate")) for result in scored_retrieval)
                / len(scored_retrieval)
                if scored_retrieval
                else 0.0
            ),
            "avg_mrr": (
                sum(self._safe_float(self._as_dict(result.get("retrieval")).get("mrr")) for result in scored_retrieval)
                / len(scored_retrieval)
                if scored_retrieval
                else 0.0
            ),
            "agreement_rate": sum(
                self._safe_float(self._as_dict(result.get("judge")).get("agreement_rate"))
                for result in results_list
            ) / total_cases,
        }
