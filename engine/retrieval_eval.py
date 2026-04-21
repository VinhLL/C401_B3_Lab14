from typing import Any, Dict, List, Optional

class RetrievalEvaluator:
    def __init__(self):
        pass

    def _normalize_ids(self, values: Optional[List[Any]]) -> List[str]:
        if not values:
            return []

        normalized: List[str] = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                normalized.append(text)
        return normalized

    def _resolve_top_k(
        self,
        top_k: Optional[int] = None,
        retrieved_ids: Optional[List[str]] = None,
        case: Optional[Dict[str, Any]] = None,
    ) -> int:
        case_top_k = None
        if case:
            metadata = case.get("metadata", {}) or {}
            case_top_k = case.get("top_k", metadata.get("top_k"))

        chosen_top_k = top_k if top_k is not None else case_top_k
        if chosen_top_k is None:
            return len(retrieved_ids or [])

        try:
            parsed_top_k = int(chosen_top_k)
        except (TypeError, ValueError):
            return len(retrieved_ids or [])

        return max(0, parsed_top_k)

    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3) -> float:
        """
        Tính hit rate cho một case.

        Quy ước:
        - expected_ids rỗng: không thể chấm retrieval, caller nên skip case này.
        - retrieved_ids rỗng: hit rate = 0.0 nếu expected_ids có dữ liệu.
        - top_k <= 0: coi như không có kết quả retrieval hợp lệ.
        """
        expected_ids = self._normalize_ids(expected_ids)
        retrieved_ids = self._normalize_ids(retrieved_ids)

        if not expected_ids or top_k <= 0:
            return 0.0

        top_retrieved = retrieved_ids[:top_k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Tìm vị trí đầu tiên của một expected_id trong retrieved_ids.
        MRR = 1 / position (vị trí 1-indexed). Nếu không thấy thì là 0.
        """
        expected_ids = self._normalize_ids(expected_ids)
        retrieved_ids = self._normalize_ids(retrieved_ids)

        if not expected_ids or not retrieved_ids:
            return 0.0

        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def evaluate_case(
        self,
        expected_ids: Optional[List[Any]],
        retrieved_ids: Optional[List[Any]],
        top_k: Optional[int] = None,
        case: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_expected_ids = self._normalize_ids(expected_ids)
        normalized_retrieved_ids = self._normalize_ids(retrieved_ids)
        resolved_top_k = self._resolve_top_k(top_k=top_k, retrieved_ids=normalized_retrieved_ids, case=case)

        if not normalized_expected_ids:
            return {
                "hit_rate": 0.0,
                "mrr": 0.0,
                "top_k": resolved_top_k,
                "expected_count": 0,
                "retrieved_count": len(normalized_retrieved_ids),
                "matched_expected_ids": [],
                "first_relevant_rank": None,
                "is_scored": False,
                "skip_reason": "empty_expected_retrieval_ids",
            }

        hit_rate = self.calculate_hit_rate(
            normalized_expected_ids,
            normalized_retrieved_ids,
            top_k=resolved_top_k,
        )
        mrr = self.calculate_mrr(normalized_expected_ids, normalized_retrieved_ids)

        matched_expected_ids = [
            doc_id for doc_id in normalized_retrieved_ids[:resolved_top_k] if doc_id in normalized_expected_ids
        ]
        first_relevant_rank = next(
            (index + 1 for index, doc_id in enumerate(normalized_retrieved_ids) if doc_id in normalized_expected_ids),
            None,
        )

        return {
            "hit_rate": hit_rate,
            "mrr": mrr,
            "top_k": resolved_top_k,
            "expected_count": len(normalized_expected_ids),
            "retrieved_count": len(normalized_retrieved_ids),
            "matched_expected_ids": matched_expected_ids,
            "first_relevant_rank": first_relevant_rank,
            "is_scored": True,
            "skip_reason": None,
        }

    async def evaluate_batch(self, dataset: List[Dict]) -> Dict:
        """
        Chạy eval cho toàn bộ bộ dữ liệu.
        Dataset cần có trường 'expected_retrieval_ids' và Agent trả về 'retrieved_ids'.
        """
        per_case: List[Dict[str, Any]] = []
        scored_cases = 0
        sum_hit_rate = 0.0
        sum_mrr = 0.0

        for item in dataset:
            case_result = self.evaluate_case(
                expected_ids=item.get("expected_retrieval_ids"),
                retrieved_ids=item.get("retrieved_ids"),
                top_k=item.get("top_k"),
                case=item,
            )
            case_result["case_id"] = item.get("case_id")
            per_case.append(case_result)

            if not case_result["is_scored"]:
                continue

            scored_cases += 1
            sum_hit_rate += case_result["hit_rate"]
            sum_mrr += case_result["mrr"]

        avg_hit_rate = sum_hit_rate / scored_cases if scored_cases else 0.0
        avg_mrr = sum_mrr / scored_cases if scored_cases else 0.0

        return {
            "avg_hit_rate": avg_hit_rate,
            "avg_mrr": avg_mrr,
            "total_cases": len(dataset),
            "scored_cases": scored_cases,
            "skipped_cases": len(dataset) - scored_cases,
            "per_case": per_case,
        }
