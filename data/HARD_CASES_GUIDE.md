# Hướng dẫn thiết kế Hard Cases cho Retrieval Benchmark

Tài liệu này chuẩn hóa hard cases theo đúng schema hiện tại của `data/golden_set.jsonl` để benchmark retrieval có giá trị và chấm được bằng code.

## 1. Schema bắt buộc của mỗi test case

Mỗi dòng trong `data/golden_set.jsonl` phải có tối thiểu các trường sau:

- `case_id`: ID duy nhất của case.
- `question`: câu hỏi benchmark.
- `expected_answer`: đáp án chuẩn cho judge.
- `expected_retrieval_ids`: danh sách `chunk_id` đúng mà retrieval cần tìm ra.
- `metadata.difficulty`: một trong `easy`, `medium`, `hard`.
- `metadata.type`: loại case, hiện dùng các giá trị như `article_rule`, `rule_interpretation`, `procedure`, `comparison`, `scenario_analysis`.

## 2. Contract giữa expected_retrieval_ids và retrieved_ids

- `expected_retrieval_ids` phải dùng đúng giá trị `chunk_id` trong corpus.
- Agent phải trả về `retrieved_ids` là danh sách ID theo đúng format đó.
- Retrieval evaluator sẽ so sánh trực tiếp `expected_retrieval_ids` với `retrieved_ids`, không map theo `doc_id` hay `title`.
- `expected_retrieval_ids` có thể chứa nhiều hơn 1 ID nếu câu trả lời đúng cần ghép nhiều chunk liên tiếp.
- Nếu `expected_retrieval_ids` rỗng, case đó không được tính vào `avg_hit_rate` và `avg_mrr` vì không có ground truth retrieval.

## 3. Định nghĩa hard case trong dataset hiện tại

Trong generator hiện tại, hard case phải khớp với contract sau:

- `metadata.difficulty = "hard"`
- `metadata.type = "scenario_analysis"`
- Nội dung chứa tình huống pháp lý, ví dụ thực tế, hướng xử lý hoặc quyết định áp dụng luật.
- Câu trả lời thường không nằm trọn trong một câu ngắn, mà cần đọc đúng chunk tình huống và đôi khi cần thêm chunk kế tiếp.

Một case không được gắn `hard` chỉ vì câu hỏi dài hoặc văn phong khó. Nó phải khó ở mặt retrieval hoặc reasoning trên ngữ cảnh gốc.

## 4. Quota difficulty để benchmark có giá trị

Quota đang dùng trong generator là:

- `easy`: 20 cases
- `medium`: 25 cases
- `hard`: 15 cases

Tổng cộng `60` cases. Tỷ lệ hard case là `15/60 = 25%`.

Hard quota này phải được giữ ổn định để:

- so sánh V1 và V2 công bằng
- tránh benchmark quá dễ
- buộc retrieval phải xử lý các tình huống có nhiều nhiễu và nhiều chi tiết pháp lý gần nhau

## 5. Cách gán expected_retrieval_ids cho hard cases

- Mặc định gán chunk chứa tình huống chính vào `expected_retrieval_ids`.
- Nếu chunk kế tiếp chứa phần `Hướng xử lý` hoặc `QUYẾT ĐỊNH` cần thiết để trả lời đúng, thêm chunk kế tiếp vào cùng danh sách.
- Chỉ thêm các chunk thực sự cần cho đáp án. Không thêm quá rộng vì sẽ làm hit rate mất ý nghĩa.
- Không dùng các ID tổng quát như `doc_id`; chỉ dùng `chunk_id`.

Ví dụ:

```json
{
  "case_id": "blds2015_case_041",
  "expected_retrieval_ids": [
    "blds2015_bao_dam_nghia_vu_chunk_070",
    "blds2015_bao_dam_nghia_vu_chunk_071"
  ],
  "metadata": {
    "difficulty": "hard",
    "type": "scenario_analysis"
  }
}
```

## 6. Mapping type theo difficulty

- `easy`: chủ yếu là `article_rule`, `topic_summary`
- `medium`: chủ yếu là `rule_interpretation`, `procedure`, `comparison`
- `hard`: hiện chuẩn hóa là `scenario_analysis`

Nếu sau này thêm loại hard mới, phải cập nhật cả generator và guide này cùng lúc.

## 7. Quy ước top_k khi chấm retrieval

- Agent hiện có thể trả số lượng kết quả khác nhau theo version.
- V1 đang dùng `top_k = 3`.
- V2 đang dùng `top_k = 5`.
- Hit rate được tính trên top-k thực tế của case hoặc của agent version.
- MRR được tính trên toàn bộ danh sách `retrieved_ids` theo thứ tự rank.

Vì vậy, khi so sánh phiên bản, cần giữ nguyên dataset nhưng cho phép evaluator đọc `top_k` động thay vì hard-code một giá trị duy nhất.

## 8. Checklist trước khi thêm hard case mới

- Case có `expected_retrieval_ids` hợp lệ và không rỗng.
- Các ID đều tồn tại trong corpus.
- `metadata.difficulty` và `metadata.type` khớp định nghĩa ở trên.
- Hard case thực sự là tình huống pháp lý hoặc phân tích ngữ cảnh, không chỉ là câu hỏi dài.
- Số lượng hard cases sau khi thêm vẫn giữ đúng quota benchmark.
