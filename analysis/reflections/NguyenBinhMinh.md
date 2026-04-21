# Báo cáo cá nhân - Nguyễn Bình Minh

## Vai trò phụ trách
**RUNNER OWNER**

## 1. Phạm vi công việc đã sở hữu
Tôi phụ trách tầng "chạy benchmark" - lớp gom nối Agent, Retrieval Evaluator và Multi-Judge thành một pipeline async chạy được trên toàn bộ golden set. Phạm vi chính gồm:

- Hoàn thiện [engine/runner.py](engine/runner.py) để điều phối 1 test case end-to-end: gọi agent → chấm retrieval → chấm judge → gom kết quả.
- Biến pipeline thành async và batched, tối ưu `batch_size` + `max_concurrency` để chạy đủ nhanh mà không vượt rate limit LLM.
- Thu thập đầy đủ `latency`, `tokens_used`, `estimated_cost`, `status` (pass/fail/error) theo từng case.
- Đảm bảo output mỗi case có đầy đủ thông tin để tầng orchestrator ghi `benchmark_results.json` và `summary.json` mà không phải suy diễn thêm.
- Chốt "result schema per-case" làm hợp đồng dữ liệu cho downstream tiêu thụ.

## 2. File sở hữu
- **Sửa:** [engine/runner.py](engine/runner.py)

## 3. Công việc đã thực hiện

### 3.1. Thiết kế `BenchmarkRunner` linh hoạt với nhiều contract

- Runner không bắt buộc evaluator phải có `evaluate_case` hay `score` - có thì gọi, không có thì fallback bằng một hàm `_default_retrieval_result()` tự tính hit_rate/MRR tại chỗ.
- Runner tự trích `retrieval` result từ nhiều nguồn theo thứ tự ưu tiên: embedded trong `ragas` scores → `evaluator.evaluate_case` → `evaluator.retrieval_evaluator.evaluate_case` → fallback mặc định.
- Với judge, nếu `evaluate_multi_judge` ném exception thì runner vẫn hoàn tất case đó bằng `_default_judge_result()` và ghi `judge_error` thay vì fail cả batch.

### 3.2. Async pipeline với `asyncio.Semaphore` và batching
`run_all()` được viết async, nhận `batch_size` và đẩy từng batch qua `asyncio.gather()` có semaphore giới hạn concurrency:

- `batch_size`: số case đẩy vào pool cùng lúc cho mỗi vòng lặp.
- `max_concurrency`: trần tuyệt đối cho số coroutine chạy song song, bảo vệ khỏi rate limit OpenAI.
- `_maybe_await()`: runner chấp nhận cả callable sync lẫn async để không ràng buộc chữ ký các component bên dưới.

Chọn semaphore thay vì chạy toàn bộ `gather` một lần vì golden set 60 case nếu fire cùng lúc sẽ bị OpenAI trả 429 và làm latency trung bình bị skew.

### 3.3. Retry có backoff tuyến tính
`_call_with_retry()` bọc mọi lời gọi ra ngoài (agent.query, evaluator.score, judge.evaluate_multi_judge) với:

- `retry_attempts` mặc định = 2.
- `retry_backoff_seconds * attempt`: backoff tăng dần theo lần thử.
- Ghi lại số lần thử vào `result["attempts"]` để failure analysis biết case nào flaky.

Retry được đặt ở tầng runner vì chỉ runner mới có bối cảnh đầy đủ để quyết định "lỗi này có nên retry hay không" - tầng dưới chỉ raise exception như bình thường.

### 3.4. Đo latency tách bạch
Mỗi case đo 2 loại latency để phục vụ phân tích hiệu năng:

- `agent_latency_ms`: chỉ thời gian agent xử lý (retrieval + generation).
- `latency_ms`: tổng thời gian 1 case, bao gồm cả judge và evaluator.

### 3.5. Per-case result schema ổn định
Đây là phần tôi dành nhiều thời gian nhất vì đây là contract với downstream. Mỗi result có:

- Định danh: `case_id`, `question`, `expected_answer`, `expected_retrieval_ids`, `metadata`.
- Output agent: `answer`, `agent_response`, `contexts`, `retrieved_ids`, `version`, `tokens_used`, `estimated_cost`.
- Latency: `latency`, `latency_ms`, `agent_latency_ms`.
- Chấm điểm: `ragas`, `retrieval`, `judge`.
- Trạng thái: `status` (`pass` / `fail` / `error`), `passed`, `error`, `attempts`.

Runner cũng có `summarize_results()` để tổng hợp nhanh `avg_judge_score`, `avg_hit_rate`, `avg_mrr`, `agreement_rate`, `avg_latency_ms`, `avg_tokens_used`, `avg_estimated_cost`, phân loại pass/fail/error. Main.py có thể tận dụng trực tiếp hàm này mà không phải tự viết lại.

### 3.6. Error path không phá dữ liệu
Khi 1 case lỗi ở bất kỳ bước nào (thiếu question, agent throw, evaluator throw), `_build_error_result()` vẫn sinh ra 1 result đúng schema với `status = "error"`, `passed = False`, và retrieval metric mặc định. Nhờ vậy:

- `len(results) == len(dataset)` luôn đúng.
- Downstream `summarize_results` và `failure_analysis` không cần check None.
- Có thể đếm chính xác bao nhiêu case lỗi vì runtime, bao nhiêu case fail vì chất lượng trả lời.

## 4. Kết quả đối chiếu với Definition of Done

### 4.1. `run_all()` chạy được trên golden_set thật
Đã hoàn thành. Runner chạy được trên bộ 60 case, cho cả V1 và V2 agent mà không cần sửa gì thêm.

### 4.2. Mỗi result có đủ retrieval metric, judge metric, latency, status, metadata
Đã hoàn thành. Schema per-case cố định, được downstream tiêu thụ trực tiếp và `check_lab.py` pass.

### 4.3. Pipeline async, batched, ổn định
Đã hoàn thành. `batch_size` và `max_concurrency` có thể tuỳ chỉnh từ ngoài. Retry + semaphore đảm bảo không bị 429 khi chạy liên tiếp V1 rồi V2.

## 5. Quyết định kỹ thuật chính

- **Async + Semaphore thay vì threadpool**: agent và judge đều là I/O-bound (chờ LLM), async cho throughput tốt hơn mà không phải quản lý GIL.
- **Retry ở tầng runner, không ở tầng component**: tập trung policy về 1 chỗ, tầng dưới chỉ raise và không cần biết runner sẽ thử lại bao lần.
- **Fallback retrieval metric tại runner**: tránh coupling cứng với `RetrievalEvaluator`. Nếu interface đổi thì runner vẫn chạy được, chỉ là metric kém chính xác hơn - đây là trade-off có chủ đích để pipeline không bị block.
- **Error case vẫn ra đúng schema**: chọn "fail-soft per case" thay vì "fail-fast toàn batch" vì benchmark 60 case mà crash ở case thứ 7 thì coi như mất cả giờ LLM cost.
- **Tách `agent_latency_ms` khỏi `latency_ms`**: để release gate chẩn đoán được nguồn gây chậm là từ agent hay từ judge/evaluator.
- **`_maybe_await` cho cả sync lẫn async callable**: để các component bên dưới không bắt buộc phải viết async mới ghép được vào pipeline.

## 6. Khó khăn gặp phải và cách xử lý

### Khó khăn 1: Contract của evaluator còn đang thay đổi khi tôi cần ghép
Lúc tôi bắt đầu sửa runner, `RetrievalEvaluator` chưa chốt tên hàm (`evaluate_case` vs `score`) và chưa chốt nơi đặt kết quả retrieval (trong `ragas["retrieval"]` hay trả riêng).

**Cách xử lý:** Tôi không đợi mà viết `_extract_retrieval_result()` với 4 nguồn fallback theo thứ tự ưu tiên. Sau khi contract được chốt thì code vẫn chạy đúng mà không phải đổi gì.

### Khó khăn 2: Judge hay timeout trên vài case dài
Một số case có `expected_answer` dài, multi-judge parallel đôi khi bị OpenAI trả timeout.

**Cách xử lý:** Bọc `judge.evaluate_multi_judge` trong try/except riêng, khi lỗi thì sinh `_default_judge_result` và vẫn ghi retrieval metric bình thường. Case đó sẽ bị đánh `status = "fail"` do `final_score = 0.0` nhưng toàn bộ pipeline không dừng. Failure analysis có thể filter các case có `ragas["judge_error"]` để biết đây là lỗi infra chứ không phải lỗi agent.

### Khó khăn 3: `top_k` không đồng nhất giữa case, agent, và evaluator
Trường `top_k` có thể nằm ở nhiều nơi: metadata của case, response của agent, hoặc config của evaluator.

**Cách xử lý:** Viết `_resolve_case_top_k()` với thứ tự ưu tiên rõ ràng: `case.top_k` → `case.metadata.top_k` → `response.top_k` → `agent.top_k`. Chốt thứ tự này trong code để tránh ambiguous.

### Khó khăn 4: Điều chỉnh `batch_size` cho phù hợp
Quá nhỏ thì chạy lâu, quá lớn thì bị 429.

**Cách xử lý:** Tách riêng `batch_size` (lô xử lý) và `max_concurrency` (trần song song). `batch_size` để tuỳ chỉnh từ ngoài, `max_concurrency` đặt mặc định = `batch_size` nhưng cho phép ghi đè. Khi test thực tế trên 60 case, `batch_size = 5` + `max_concurrency = 5` cho thời gian chạy chấp nhận được mà không dính rate limit.

## 7. Bài học rút ra

- **Runner là "tầng bảo hiểm"**: nó không tạo ra giá trị mới, nhưng là thứ bảo vệ toàn bộ pipeline khỏi sụp đổ khi 1 component lỗi. Mọi failure mode đều phải có default path.
- **Contract-first khi làm tầng giữa**: thay vì đợi contract chốt 100% mới bắt đầu, nên khai báo trước contract bằng fallback logic rồi sửa lại khi bên dưới chốt thật.
- **Per-case schema là tài sản chung quan trọng nhất của benchmark**: orchestrator, failure analysis, cả report đều tiêu thụ nó. Một lần chốt schema gọn gàng đổi lại rất nhiều công sửa lặt vặt về sau.
- **Tách latency theo tầng ngay từ đầu**: gộp là nhanh viết, nhưng khi debug release gate thì phải đo lại. Đo đúng từ đầu rẻ hơn đo lại.
- **Async không phải luôn nhanh hơn - cần semaphore**: fire toàn bộ cùng lúc sẽ bị rate limit và chậm hơn chạy tuần tự. Concurrency có trần mới là concurrency có ích.
- **Fail-soft per case, fail-fast per run**: với benchmark dài và tốn LLM cost, mỗi case lỗi nên được ghi nhận thay vì làm crash cả run.

## 8. Tự đánh giá đóng góp

Tôi đã hoàn thành đúng phần việc của một Runner Owner:

- Runner chạy async, batched, có retry, có semaphore, có fallback ở mọi failure mode.
- Per-case result schema ổn định, đã được orchestrator và `check_lab.py` tiêu thụ thành công.
- Cung cấp sẵn `summarize_results()` để tầng main tính `avg_score`, `hit_rate`, `agreement_rate` mà không phải tự viết lại.
- Pipeline chạy ổn định trên cả V1 và V2 agent, thu đủ `latency`, `tokens_used`, `estimated_cost`, `status` cho từng case để phục vụ phân tích downstream.
