# Báo cáo cá nhân - Nguyễn Việt Hoàng

## Vai trò phụ trách

**AGENT OWNER**

## 1. Phạm vi công việc đã sở hữu

Trong Lab 14, tôi phụ trách thay thế agent giả lập bằng RAG thực tế cho toàn bộ pipeline đánh giá. Phạm vi chính của tôi gồm:

- Thay logic giả lập trong `agent/main_agent.py` bằng agent RAG thật trên domain đã chốt.
- Đảm bảo agent trả về đầy đủ schema đúng yêu cầu: `answer`, `contexts`, `retrieved_ids`, `tokens_used`, `estimated_cost`, `version`.
- Chuẩn bị cơ chế để `main.py` chạy được ít nhất 2 version agent: V1 base và V2 optimized.
- Tối ưu retrieval/generation ở mức có thể benchmark được.
- Phối hợp với Data Owner và Retrieval Eval Owner để chốt contract `expected_retrieval_ids` ↔ `retrieved_ids`.

## 2. Domain cuối cùng đã chốt

Nhóm thống nhất chọn domain:

- **BLDS 2015 - Bảo đảm thực hiện nghĩa vụ dân sự**
- Mã domain trong dữ liệu: `civil_law_security_obligations_vi`

## 3. File tôi sở hữu

- **Sửa:** `agent/main_agent.py`

## 4. Công việc đã thực hiện

### 4.1. Tích hợp với ChromaDB đã xây dựng trước đó

Tôi chỉnh sửa `agent/main_agent.py` để:

- Kết nối đến `data/chroma_db` với `collection_name = "blds2015_legal_corpus"`
- Sử dụng hàm `deterministic_embed` giống hệt như ở `data/build_chroma_db.py` để đảm bảo tính nhất quán giữa bước index và bước query
- Truy vấn vector DB và lấy về `chunk_id`, `documents`, `metadatas`, `distances`
- Lấy kết quả và trả về đúng schema

### 4.2. Trả về đúng schema đã khóa

Agent hiện trả về đầy đủ các trường theo yêu cầu:

```python
{
    "answer": "Tôi tìm thấy ...",        # Câu trả lời dựa trên các đoạn retrieved
    "contexts": [ "...", "..." ],          # Danh sách các đoạn văn bản retrieved
    "retrieved_ids": [ "chunk_001", ... ], # Danh sách chunk_id tương ứng
    "tokens_used": 123,                    # Ước tính số tokens sử dụng
    "estimated_cost": 0.0123,                # Ước tính chi phí
    "version": "v1"                         # Phiên bản agent
}
```

### 4.3. Cơ chế phân biệt V1 và V2

Tôi thiết kế để `MainAgent` nhận tham số `version` trong `__init__`:

- **V1 (base):** `top_k = 3` → trả về 3 kết quả
- **V2 (optimized):** `top_k = 5` → trả về 5 kết quả

Việc thay đổi `top_k` là cách đơn giản nhưng có thể đo được trong benchmark để đánh giá trade-off giữa retrieval và generation.

### 4.4. Contract ID đồng nhất với corpus và golden dataset

Agent trả về `retrieved_ids` bằng chính `chunk_id` trong `data/domain_corpus.jsonl`, giống hệt như `expected_retrieval_ids` trong golden set. Điều này đảm bảo evaluator có thể tính chính xác hit rate và MRR một cách nhất quán.

## 5. Kết quả đối chiếu với Definition of Done

### ✅ Requirement 1: Benchmark runner gọi agent không còn nhận dữ liệu stub

Đã hoàn thành. Agent hiện kết nối đến ChromaDB thật và trả về kết quả retrieval thực tế.

### ✅ Requirement 2: Agent response đúng schema đã khóa

Đã hoàn thành. Agent trả về đầy đủ 6 trường theo yêu cầu.

### ✅ Requirement 3: Có tham số/config để phân biệt V1 và V2

Đã hoàn thành. `MainAgent(version="v1")` hoặc `MainAgent(version="v2")`.

## 6. Quyết định kỹ thuật chính

- **Sử dụng embedding đồng nhất giữa index và query:** Dùng hàm `deterministic_embed` giống hệt `build_chroma_db.py` để không có mismatch khi thay đổi script.
- **Phân biệt V1/V2 qua `top_k`:** Thay đổi số lượng kết quả retrieval để dễ đo được trong benchmark.
- **Trả về `chunk_id` trực tiếp làm `retrieved_ids` để đồng nhất contract với Data Owner và Retrieval Eval Owner.**
- **Ước tính `tokens_used` và `estimated_cost` đơn giản để có thể đo được trade-off trong benchmark.**

## 7. Vấn đề gặp phải và cách xử lý

### Vấn đề 1: ChromaDB không cho include "ids" trong query

**Lỗi ban đầu:** `ValueError: Expected include item to be one of documents, embeddings, metadatas, distances, uris, data, got ids in query.`
**Cách xử lý:** Bỏ "ids" ra khỏi include, vì ChromaDB luôn trả về ids mặc định mà không cần include.

### Vấn đề 2: Encoding issue khi in tiếng Việt trên Windows

**Lỗi ban đầu:** `UnicodeEncodeError: 'charmap' codec can't encode character...`
**Cách xử lý:** Thay đổi stdout encoding sang utf-8 bằng cách dùng `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`.

### Vấn đề 3: Contract ID phải đồng nhất giữa các thành phần

**Cách xử lý:** Phối hợp với Data Owner và Retrieval Eval Owner để chốt rằng:

- Dùng `chunk_id` làm `expected_retrieval_ids` và `retrieved_ids`
- Không thay đổi định dạng ID để không phá vỡ phép đo benchmark

## 8. Bài học rút ra

- Với bài toán RAG benchmark, tính nhất quán giữa index và query là rất quan trọng. Nếu embedding không giống nhau thì phép đo retrieval sẽ không có nghĩa.
- Schema agent phải được khóa chặt giữa các thành viên (Data Owner, Agent Owner, Retrieval Eval Owner) để không có sai sót trong contract.
- Phân biệt V1/V2 nên dùng thay đổi đơn giản nhưng đo được trong benchmark (như thay đổi `top_k`) để dễ theo dõi regression.

## 9. Hướng cải tiến cho lần benchmark tiếp theo

Nếu làm tiếp vòng sau, tôi ưu tiên các hướng sau:

- Thêm reranking cho retrieval để cải thiện hit rate
- Thêm LLM generation thực tế (OpenAI/Gemini) thay vì answer chỉ đơn thuần liệt kê các đoạn retrieved
- Thêm hybrid retrieval (lexical + semantic)
- Thêm confidence score cho retrieval để hỗ trợ dynamic top_k
- Thêm caching cho retrieval để giảm latency và cost

## 10. Tự đánh giá đóng góp

Tôi đã hoàn thành đúng phần việc của Agent Owner:

- Thay thế agent giả lập bằng RAG thật
- Đảm bảo agent trả về đúng schema
- Có cơ chế phân biệt V1 và V2
- Phối hợp với nhóm chốt contract ID
- Chuẩn bị agent sẵn sàng cho benchmark
  Phần việc này là nền tảng cho benchmark runner chạy được và đo được chất lượng retrieval/generation.
