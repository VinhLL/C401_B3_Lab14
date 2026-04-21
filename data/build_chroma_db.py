import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List

import chromadb


DATA_DIR = Path(__file__).resolve().parent
CORPUS_PATH = DATA_DIR / "domain_corpus.jsonl"
CHROMA_DIR = DATA_DIR / "chroma_db"
MANIFEST_PATH = DATA_DIR / "chroma_manifest.json"
COLLECTION_NAME = "blds2015_legal_corpus"
EMBED_DIM = 256


def maybe_fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value
    if "Ã" not in value and "Ä" not in value and "á»" not in value:
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except (UnicodeError, LookupError):
        return value


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", maybe_fix_mojibake(text)).strip()


def normalize_entry(entry: Dict) -> Dict:
    normalized = dict(entry)
    for key in ("doc_id", "chunk_id", "domain", "domain_title", "doc_title", "title", "text", "summary"):
        if key in normalized and isinstance(normalized[key], str):
            normalized[key] = normalize_text(normalized[key])

    article_refs = normalized.get("article_refs", [])
    normalized["article_refs"] = [normalize_text(item) for item in article_refs if isinstance(item, str)]
    return normalized


def load_corpus() -> List[Dict]:
    if not CORPUS_PATH.exists():
        raise FileNotFoundError(f"Missing corpus file: {CORPUS_PATH}")

    with CORPUS_PATH.open("r", encoding="utf-8") as f:
        return [normalize_entry(json.loads(line)) for line in f if line.strip()]


def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def deterministic_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    vector = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def chunked(items: List[Dict], batch_size: int) -> Iterable[List[Dict]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def build_metadata(entry: Dict) -> Dict:
    return {
        "doc_id": entry["doc_id"],
        "chunk_index": int(entry["chunk_index"]),
        "domain": entry.get("domain", ""),
        "title": entry.get("title", ""),
        "article_refs": " | ".join(entry.get("article_refs", [])),
    }


def rebuild_chroma_db() -> Dict:
    corpus = load_corpus()
    if not corpus:
        raise ValueError("Corpus is empty; cannot build Chroma DB.")

    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "BLDS 2015 legal retrieval corpus for Lab14",
            "embedding_backend": "deterministic_hash_v1",
            "embedding_dimension": EMBED_DIM,
        },
    )

    for batch in chunked(corpus, batch_size=32):
        ids = [entry["chunk_id"] for entry in batch]
        documents = [entry["text"] for entry in batch]
        metadatas = [build_metadata(entry) for entry in batch]
        embeddings = [deterministic_embed(document) for document in documents]
        collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    probe_query = normalize_text(
        "Theo Dieu 297 BLDS 2015, hieu luc doi khang voi nguoi thu ba phat sinh khi nao?"
    )
    probe_results = collection.query(
        query_embeddings=[deterministic_embed(probe_query)],
        n_results=3,
        include=["metadatas", "documents", "distances"],
    )

    manifest = {
        "collection_name": COLLECTION_NAME,
        "persist_directory": str(CHROMA_DIR),
        "corpus_path": str(CORPUS_PATH),
        "document_count": collection.count(),
        "embedding_backend": "deterministic_hash_v1",
        "embedding_dimension": EMBED_DIM,
        "probe_query": probe_query,
        "probe_top_chunk_ids": probe_results.get("ids", [[]])[0],
    }

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


def main() -> None:
    manifest = rebuild_chroma_db()
    print(f"Built Chroma DB at: {manifest['persist_directory']}")
    print(f"Collection: {manifest['collection_name']}")
    print(f"Documents: {manifest['document_count']}")
    print(f"Probe top chunks: {manifest['probe_top_chunk_ids']}")


if __name__ == "__main__":
    main()
