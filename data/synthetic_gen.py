import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


DATA_DIR = Path(__file__).resolve().parent
CORPUS_PATH = DATA_DIR / "domain_corpus.jsonl"
OUTPUT_PATH = DATA_DIR / "golden_set.jsonl"

TARGET_CASES = 60
DIFFICULTY_TARGETS = {"easy": 20, "medium": 25, "hard": 15}

ARTICLE_LABEL = "\u0110i\u1ec1u"

SCENARIO_MARKERS = (
    "Tình huống",
    "Ví dụ",
    "Bản án",
    "QUYẾT ĐỊNH",
    "Hướng xử lý",
)
COMPARISON_MARKERS = (
    "so với BLDS 2005",
    "điểm mới",
    "khác với",
    "sửa đổi",
    "bổ sung",
)
PROCEDURE_MARKERS = (
    "thông báo",
    "định giá",
    "bán đấu giá",
    "phương thức xử lý",
    "hồ sơ",
)
RULE_MARKERS = (
    "hiệu lực đối kháng",
    "thứ tự ưu tiên",
    "đăng ký",
    "xử lý tài sản",
    "phạm vi nghĩa vụ",
    "tài sản bảo đảm",
)
IGNORE_TITLE_PREFIXES = ("Chunk", "PGS", "ThS", "TS", "Trường")


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> List[str]:
    cleaned = clean_spaces(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def truncate_answer(text: str, min_chars: int = 180, max_chars: int = 460) -> str:
    sentences = split_sentences(text)
    if not sentences:
        clipped = clean_spaces(text)[:max_chars].strip()
        return clipped.rstrip(".") + "." if clipped and not clipped.endswith(".") else clipped

    picked: List[str] = []
    current_len = 0
    for sentence in sentences:
        candidate_len = current_len + len(sentence) + (1 if picked else 0)
        if picked and candidate_len > max_chars:
            break
        picked.append(sentence)
        current_len = candidate_len
        if current_len >= min_chars and len(picked) >= 2:
            break

    answer = " ".join(picked).strip()
    if len(answer) <= max_chars:
        return answer

    clipped = answer[:max_chars].rsplit(" ", 1)[0].strip()
    return clipped + "..."


def load_corpus() -> List[Dict]:
    if not CORPUS_PATH.exists():
        raise FileNotFoundError(f"Missing corpus file: {CORPUS_PATH}")

    with CORPUS_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def contains_any(text: str, markers: Tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def is_informative(entry: Dict) -> bool:
    text = entry.get("text", "")
    if len(text) < 260:
        return False
    if text.upper() == text and len(text) < 180:
        return False
    return True


def is_valid_title(title: str) -> bool:
    if not title:
        return False
    if any(title.startswith(prefix) for prefix in IGNORE_TITLE_PREFIXES):
        return False
    if len(title) < 8 or len(title) > 120:
        return False
    return True


def derive_topic(entry: Dict) -> str:
    title = clean_spaces(entry.get("title", ""))
    if is_valid_title(title):
        return title.rstrip(".:")

    text = entry.get("text", "")
    sentences = split_sentences(text)
    first_sentence = sentences[0] if sentences else clean_spaces(text)

    if ":" in first_sentence:
        candidate = clean_spaces(first_sentence.split(":", 1)[0])
        if 8 <= len(candidate) <= 120 and not candidate.startswith(("Theo", "Thứ", ARTICLE_LABEL)):
            return candidate.rstrip(".:")

    for pattern in (r"quy định về ([^.;:]+)", r"về ([^.;:]+)"):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = clean_spaces(match.group(1))
            if 8 <= len(candidate) <= 90:
                return candidate.rstrip(".:")

    return clean_spaces(first_sentence[:90]).rstrip(".:")


def normalize_topic(topic: str) -> str:
    cleaned = clean_spaces(topic).strip(" :.;,")
    cleaned = re.sub(r"^(Thứ\s+\w+,\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(rf"^{ARTICLE_LABEL}\s+\d+\s+BLDS\s+2015\s+quy\s+định\s+về\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Theo\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^về\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^quy định về\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("“", "").replace("”", "").replace('"', "")
    cleaned = clean_spaces(cleaned)
    if len(cleaned) > 95:
        cleaned = cleaned[:95].rsplit(" ", 1)[0]
    return cleaned.rstrip(".:")


def should_use_topic(topic: str) -> bool:
    normalized = normalize_topic(topic)
    if len(normalized) < 8 or len(normalized) > 55:
        return False

    lowered = normalized.lower()
    blocked_prefixes = (
        "blds 2015",
        "điều ",
        "khoản ",
        "nội dung,",
        "theo đó",
    )
    blocked_fragments = (
        "(",
        "với nội dung",
        "đều có quyền",
        "khá chi tiết khi quy định",
    )
    return not lowered.startswith(blocked_prefixes) and not any(fragment in lowered for fragment in blocked_fragments)


def classify_case(entry: Dict) -> Tuple[str, str]:
    text = entry.get("text", "")
    article_refs = entry.get("article_refs", [])

    if contains_any(text, SCENARIO_MARKERS):
        return "hard", "scenario_analysis"
    if contains_any(text, COMPARISON_MARKERS):
        return "medium", "comparison"
    if contains_any(text, PROCEDURE_MARKERS):
        return "medium", "procedure"
    if contains_any(text, RULE_MARKERS):
        return ("medium" if article_refs else "easy"), "rule_interpretation"
    if article_refs:
        return "easy", "article_rule"
    return "easy", "topic_summary"


def score_entry(entry: Dict, difficulty: str, case_type: str) -> int:
    text = entry.get("text", "")
    article_refs = entry.get("article_refs", [])

    score = len(text)
    if article_refs:
        score += 250
    if case_type == "scenario_analysis":
        score += 300
    if case_type == "comparison":
        score += 200
    if case_type == "procedure":
        score += 120
    if difficulty == "hard":
        score += 100
    return score


def select_entries(corpus: List[Dict]) -> List[Tuple[Dict, str, str]]:
    prepared: List[Tuple[int, Dict, str, str]] = []
    for entry in corpus:
        if not is_informative(entry):
            continue
        difficulty, case_type = classify_case(entry)
        prepared.append((score_entry(entry, difficulty, case_type), entry, difficulty, case_type))

    if not prepared:
        raise ValueError("No informative corpus entries found to generate golden set.")

    by_difficulty = {"easy": [], "medium": [], "hard": []}
    for item in prepared:
        by_difficulty[item[2]].append(item)

    for difficulty in by_difficulty:
        by_difficulty[difficulty].sort(key=lambda row: (-row[0], row[1]["chunk_index"]))

    all_sorted = sorted(prepared, key=lambda row: (-row[0], row[1]["chunk_index"]))
    selected: List[Tuple[Dict, str, str]] = []
    used_chunk_ids = set()

    for difficulty, quota in DIFFICULTY_TARGETS.items():
        count = 0
        for _, entry, entry_difficulty, case_type in by_difficulty[difficulty]:
            chunk_id = entry["chunk_id"]
            if chunk_id in used_chunk_ids:
                continue
            selected.append((entry, entry_difficulty, case_type))
            used_chunk_ids.add(chunk_id)
            count += 1
            if count >= quota:
                break

    for _, entry, difficulty, case_type in all_sorted:
        if len(selected) >= TARGET_CASES:
            break
        chunk_id = entry["chunk_id"]
        if chunk_id in used_chunk_ids:
            continue
        selected.append((entry, difficulty, case_type))
        used_chunk_ids.add(chunk_id)

    selected.sort(key=lambda row: row[0]["chunk_index"])
    return selected[:TARGET_CASES]


def build_question(entry: Dict, case_type: str, topic: str) -> str:
    article_refs = entry.get("article_refs", [])
    source_label = article_refs[0] if article_refs else "tài liệu"
    topic_fragment = f"về {topic}" if should_use_topic(topic) else "trong đoạn tài liệu này"

    if case_type == "scenario_analysis":
        if "Hướng xử lý" in entry.get("text", "") or "QUYẾT ĐỊNH" in entry.get("text", ""):
            return f"Trong tình huống được nêu trong {source_label}, hướng xử lý chính {topic_fragment} là gì?"
        return f"Trong tình huống được nêu trong {source_label}, vấn đề pháp lý chính {topic_fragment} là gì?"
    if case_type == "comparison":
        return f"Theo {source_label}, điểm mới hoặc điểm khác đáng chú ý {topic_fragment} là gì?"
    if case_type == "procedure":
        return f"Theo {source_label}, quy trình hoặc yêu cầu chính {topic_fragment} là gì?"
    if case_type == "rule_interpretation":
        return f"Theo {source_label}, quy tắc chính {topic_fragment} được nêu như thế nào?"
    if case_type == "article_rule":
        return f"Theo {source_label}, tài liệu quy định gì {topic_fragment}?"
    return f"Nội dung pháp lý chính {topic_fragment} là gì?"


def collect_expected_ids_and_context(entry: Dict, case_type: str, by_index: Dict[int, Dict]) -> Tuple[List[str], str]:
    expected_ids = [entry["chunk_id"]]
    combined_context = entry["text"]
    next_entry = by_index.get(entry["chunk_index"] + 1)

    if not next_entry:
        return expected_ids, combined_context

    next_text = next_entry.get("text", "")
    if case_type == "scenario_analysis" and any(marker in next_text for marker in ("Hướng xử lý", "QUYẾT ĐỊNH")):
        expected_ids.append(next_entry["chunk_id"])
        combined_context = f"{combined_context} {next_text}"

    return expected_ids, combined_context


def build_expected_answer(case_type: str, combined_context: str) -> str:
    context = combined_context
    if case_type == "scenario_analysis":
        if "Hướng xử lý:" in context:
            context = context.split("Hướng xử lý:", 1)[1]
        elif "QUYẾT ĐỊNH" in context:
            context = context.split("QUYẾT ĐỊNH", 1)[1]
    return truncate_answer(context)


def generate_cases(corpus: List[Dict]) -> List[Dict]:
    selected_entries = select_entries(corpus)
    by_index = {entry["chunk_index"]: entry for entry in corpus}
    cases: List[Dict] = []

    for idx, (entry, difficulty, case_type) in enumerate(selected_entries, start=1):
        topic = normalize_topic(derive_topic(entry))
        expected_ids, combined_context = collect_expected_ids_and_context(entry, case_type, by_index)
        cases.append(
            {
                "case_id": f"blds2015_case_{idx:03d}",
                "question": build_question(entry, case_type, topic),
                "expected_answer": build_expected_answer(case_type, combined_context),
                "expected_retrieval_ids": expected_ids,
                "metadata": {
                    "difficulty": difficulty,
                    "type": case_type,
                    "source_domain": entry.get("domain"),
                    "source_doc_id": entry.get("doc_id"),
                    "source_chunk_ids": expected_ids,
                    "source_chunk_index": entry.get("chunk_index"),
                    "topic": topic,
                    "article_refs": entry.get("article_refs", []),
                },
            }
        )

    return cases


def save_cases(cases: List[Dict]) -> None:
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")


def print_summary(cases: List[Dict]) -> None:
    difficulty_counts = Counter(case["metadata"]["difficulty"] for case in cases)
    type_counts = Counter(case["metadata"]["type"] for case in cases)

    print(f"Saved {len(cases)} cases to {OUTPUT_PATH}")
    print(f"Difficulty distribution: {dict(difficulty_counts)}")
    print(f"Type distribution: {dict(type_counts)}")


def main() -> None:
    corpus = load_corpus()
    cases = generate_cases(corpus)
    if len(cases) < 50:
        raise ValueError(f"Expected at least 50 cases, generated only {len(cases)}")
    save_cases(cases)
    print_summary(cases)


if __name__ == "__main__":
    main()
