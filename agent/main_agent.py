import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from typing import List, Dict
import chromadb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "blds2015_legal_corpus"
EMBED_DIM = 256

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

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

class MainAgent:
    def __init__(self, version: str = "v1"):
        self.version = version
        self.name = f"LegalAgent-{version}"
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_collection(name=COLLECTION_NAME)
        self.top_k = 3 if version == "v1" else 5

    async def query(self, question: str) -> Dict:
        query_embedding = deterministic_embed(normalize_text(question))
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k,
            include=["metadatas", "documents", "distances"]
        )
        retrieved_ids = results.get("ids", [[]])[0]
        contexts = results.get("documents", [[]])[0]
        
        answer_parts = [f"Tôi tìm thấy {len(contexts)} đoạn tài liệu liên quan:\n"]
        for i, (ctx, cid) in enumerate(zip(contexts, retrieved_ids), start=1):
            answer_parts.append(f"{i}. [{cid}] {ctx[:200]}...\n")
        answer = "".join(answer_parts).strip()
        
        tokens_used = len(question.split()) + sum(len(ctx.split()) for ctx in contexts)
        estimated_cost = 0.0001 * tokens_used
        
        return {
            "answer": answer,
            "contexts": contexts,
            "retrieved_ids": retrieved_ids,
            "tokens_used": tokens_used,
            "estimated_cost": estimated_cost,
            "version": self.version
        }

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    async def test():
        agent_v1 = MainAgent("v1")
        resp_v1 = await agent_v1.query("Theo Điều 297 BLDS 2015, hiệu lực đối kháng với người thứ ba phát sinh khi nào?")
        print("=== V1 Response ===")
        print(json.dumps(resp_v1, ensure_ascii=False, indent=2))
        
        agent_v2 = MainAgent("v2")
        resp_v2 = await agent_v2.query("Theo Điều 297 BLDS 2015, hiệu lực đối kháng với người thứ ba phát sinh khi nào?")
        print("\n=== V2 Response ===")
        print(json.dumps(resp_v2, ensure_ascii=False, indent=2))
    asyncio.run(test())
