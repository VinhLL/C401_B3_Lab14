# Báo cáo cá nhân - Ngô Quang Phúc

## Thông tin học viên
- **Họ và tên:** Ngô Quang Phúc
- **Mã học viên:** 2A202600477
- **Vai trò trong nhóm:** Người 6 - Orchestrator / Release Gate Owner

## 1. Phạm vi công việc đã sở hữu
Trong Lab Day 14, tôi phụ trách phần orchestration cuối của toàn bộ benchmark pipeline. Mục tiêu của phần việc này là ghép các module của nhóm thành một luồng chạy hoàn chỉnh, sinh artifact báo cáo ổn định, tính regression giữa hai phiên bản agent và đưa ra quyết định release/block dựa trên số liệu.

Các đầu việc chính tôi chịu trách nhiệm gồm:

- hoàn thiện `main.py` để chạy benchmark cho cả `V1` và `V2`
- định nghĩa và áp dụng release gate dựa trên `avg_score`, `hit_rate`, `agreement_rate`, `latency`, `cost`
- chuẩn hóa schema cho `reports/summary.json` và `reports/benchmark_results.json`
- cập nhật `check_lab.py` để validate đúng các key bắt buộc trong report
- điền `analysis/failure_analysis.md` bằng số liệu benchmark thật
- tạo thư mục `analysis/reflections/` và quy ước đặt tên file reflection cho từng thành viên

Các file tôi trực tiếp sở hữu và chỉnh sửa là:

- `main.py`
- `check_lab.py`
- `analysis/failure_analysis.md`
- `analysis/reflections/reflection_NgoQuangPhuc.md`

## 2. Quyết định kỹ thuật chính

### 2.1. Tổ chức lại `main.py` theo hướng orchestration thật sự
Thay vì chỉ chạy benchmark một cách tối giản rồi dump kết quả thô, tôi tổ chức lại `main.py` theo các bước rõ ràng:

- nạp dataset từ `data/golden_set.jsonl`
- chạy lần lượt `Agent_V1_Base` và `Agent_V2_Optimized`
- tổng hợp kết quả theo từng version
- tính regression summary giữa V1 và V2
- áp dụng release gate
- ghi ra hai file report chuẩn hóa

Cách làm này giúp `main.py` trở thành entrypoint chính của bài lab đúng như README yêu cầu, không còn là script demo đơn giản.

### 2.2. Chuẩn hóa schema report để dễ kiểm tra và dễ phân tích
Tôi thiết kế lại `reports/summary.json` theo hướng vừa đủ cho chấm điểm, vừa đủ cho phân tích sau benchmark. File này hiện có:

- `schema_version`
- `generated_at`
- `metadata`
- `metrics`
- `versions.v1`
- `versions.v2`
- `regression`
- `release_gate`

Song song với đó, `reports/benchmark_results.json` được chuẩn hóa để chứa:

- metadata chung của benchmark
- kết quả chi tiết theo từng version
- so sánh per-case giữa V1 và V2

Việc khóa schema theo kiểu này giúp `check_lab.py` có thể validate ổn định, đồng thời hỗ trợ failure analysis vì dữ liệu không còn rời rạc.

### 2.3. Thiết kế release gate theo nhiều chiều, không chỉ nhìn mỗi score
Tôi không dùng logic kiểu “delta score > 0 thì release”, mà định nghĩa release gate theo nhiều tiêu chí:

- quality floor: `avg_score`, `hit_rate`, `agreement_rate`
- performance/cost ceiling: `avg_latency_ms`, `avg_estimated_cost`
- regression guard: delta giữa V2 và V1 cho score, hit rate, latency, cost

Lý do là trong benchmark hệ thống, một bản candidate có thể nhanh hơn nhưng retrieval tệ hơn, hoặc chất lượng không tăng nhưng cost phình mạnh. Nếu chỉ nhìn một chỉ số đơn lẻ thì quyết định release sẽ thiếu an toàn.

### 2.4. Gắn validation thành một bước riêng trong `check_lab.py`
Tôi viết lại `check_lab.py` để nó không chỉ kiểm tra “có file hay không”, mà còn validate:

- key bắt buộc trong `summary.json`
- key bắt buộc trong `benchmark_results.json`
- cấu trúc per-case result
- sự tồn tại của `analysis/failure_analysis.md`
- sự tồn tại của thư mục `analysis/reflections/`

Điều này giúp repo có một bước pre-submit check rõ ràng, giảm rủi ro nộp bài với artifact bị thiếu field.

### 2.5. Xử lý tương thích runtime cho ChromaDB ở tầng orchestration
Trong môi trường chạy thực tế, `chromadb` bị lỗi import do mismatch với `opentelemetry`. Tôi không sửa file agent của người khác, mà xử lý tương thích ở `main.py` bằng compatibility shim trước khi import agent.

Cách tiếp cận này phù hợp với phạm vi Người 6:

- giữ nguyên code ownership của Người 2
- vẫn làm cho pipeline benchmark chạy được end-to-end
- hạn chế đụng chạm sang phần implementation retrieval

## 3. Kết quả đạt được
Sau khi hoàn thiện orchestration, hệ thống đã chạy được theo đúng flow yêu cầu:

- `python main.py` sinh thành công:
  - `reports/summary.json`
  - `reports/benchmark_results.json`
- `python check_lab.py` chạy pass
- `analysis/failure_analysis.md` đã được điền bằng số liệu benchmark thật thay vì template trống

Kết quả benchmark thực tế hiện tại:

- **Dataset size:** `60` cases
- **V1 avg_score:** `2.5000`
- **V2 avg_score:** `2.5000`
- **V1 hit_rate:** `0.0833`
- **V2 hit_rate:** `0.1167`
- **V1 avg_mrr:** `0.0667`
- **V2 avg_mrr:** `0.0733`
- **V1 avg_latency_ms:** `470.62`
- **V2 avg_latency_ms:** `367.94`
- **V1 avg_estimated_cost:** `0.058730`
- **V2 avg_estimated_cost:** `0.091957`
- **Release gate decision:** `BLOCK`

Như vậy, definition of done của phần tôi phụ trách đã đạt ở mức orchestration và artifact:

- benchmark chạy được cho `V1` và `V2`
- có summary/report ổn định
- có logic delta và release gate
- có bước validation trước khi nộp
- có failure analysis thật sự dựa trên số liệu

## 4. Vấn đề gặp phải và cách xử lý

### 4.1. `main.py` ban đầu chưa đủ vai trò của một orchestrator
Phiên bản ban đầu của `main.py` chỉ chạy benchmark ở mức cơ bản, ghi ra report rất mỏng và chưa có schema đủ chặt cho chấm điểm cũng như phân tích regression.

Tôi xử lý bằng cách:

- tách các bước load dataset, run version, summarize version, compare version, build release gate
- ghi report theo schema rõ ràng
- làm cho `summary.json` trở thành artifact trung tâm của pipeline

### 4.2. Runtime bị lỗi import `chromadb`
Khi chạy benchmark, pipeline bị dừng sớm vì `chromadb` không import được do mismatch với `opentelemetry`.

Tôi xử lý bằng cách:

- chẩn đoán package version trong môi trường
- vá compatibility ở mức import trong `main.py`
- tránh sửa `agent/main_agent.py` để không đụng vào phần ownership của Người 2

Nhờ vậy, benchmark vẫn chạy được mà không phá ranh giới phần việc của các thành viên khác.

### 4.3. Judge backend lỗi làm score không phản ánh đúng chất lượng thật
Trong lần benchmark hiện tại, toàn bộ `60` case đều bị `invalid_api_key` ở judge backend. Điều này dẫn đến:

- `agreement_rate = 0.0`
- mọi case dùng fallback judge score
- `avg_score` đứng yên ở `2.5`

Tôi không sửa `engine/llm_judge.py` vì đó không thuộc file sở hữu của tôi. Thay vào đó, tôi làm hai việc trong phạm vi Người 6:

- phản ánh rõ lỗi này vào report và failure analysis
- để release gate block đúng theo dữ liệu thật thay vì che lỗi đi

### 4.4. Cần phân biệt artifact để chấm với artifact để phân tích
Nếu chỉ lưu summary ngắn thì dễ chấm nhưng khó debug. Nếu chỉ lưu per-case raw result thì khó nhìn tổng thể.

Tôi xử lý bằng cách chia artifact ra làm hai lớp:

- `summary.json` cho tổng hợp, regression và release decision
- `benchmark_results.json` cho chi tiết từng case và so sánh per-case

Thiết kế này giúp cả người chấm lẫn nhóm phát triển đều có tài liệu phù hợp với nhu cầu của mình.

## 5. Phân tích cá nhân dựa trên kết quả benchmark

### 5.1. Release gate đang làm đúng vai trò chặn rủi ro
Kết quả hiện tại cho thấy V2 tuy có cải thiện nhẹ về retrieval và nhanh hơn V1, nhưng vẫn phải bị block vì:

- `avg_score` chưa đạt ngưỡng
- `hit_rate` chưa đạt ngưỡng
- `agreement_rate` bằng `0`
- cost tăng vượt guard

Điều này cho thấy release gate đã hoạt động đúng vai trò “cửa chặn cuối”, không để nhóm kết luận lạc quan dựa trên một vài tín hiệu cải thiện cục bộ.

### 5.2. Report tốt giúp failure analysis có cơ sở hơn
Nhờ schema report được tổ chức lại, `failure_analysis.md` có thể bám theo số liệu thật như:

- miss retrieval theo difficulty/type
- delta giữa V1 và V2
- cost inflation ở V2
- judge issue count

Nếu không có orchestration và report đủ chặt, phần phân tích thất bại rất dễ trở thành nhận xét cảm tính.

### 5.3. Hệ benchmark chỉ mạnh bằng mắt xích yếu nhất
Qua lần chạy này, tôi thấy rất rõ một điều: dù runner, retrieval eval và report đã nối được với nhau, toàn bộ signal chất lượng generation vẫn bị suy yếu chỉ vì judge backend hỏng.

Điều đó cho tôi bài học là phần orchestration không chỉ ghép module lại với nhau, mà còn phải làm lộ ra điểm nghẽn hệ thống một cách trung thực.

## 6. Bài học rút ra
Qua phần việc của mình, tôi rút ra các bài học chính:

- orchestration tốt không phải là “chạy được”, mà là “chạy được, có số liệu, có schema, có gate và có khả năng giải thích quyết định”
- release gate cần nhìn đa chỉ số thay vì chỉ dựa vào một metric trung bình
- validation trước khi nộp là bước bắt buộc nếu muốn artifact ổn định
- khi làm việc nhóm có ownership theo file, cần ưu tiên giải quyết vấn đề ở đúng ranh giới trách nhiệm của mình
- benchmark system phải phản ánh trung thực lỗi môi trường; không nên che lỗi chỉ để có kết quả đẹp

## 7. Hướng cải tiến cho lần benchmark tiếp theo
Nếu tiếp tục phát triển vòng sau, tôi muốn cải tiến phần Người 6 theo các hướng:

- thêm preflight check cho judge backend trước khi chạy toàn bộ benchmark
- đưa thêm breakdown metrics theo difficulty/type vào release gate để block chi tiết hơn
- bổ sung file schema documentation cho `summary.json` và `benchmark_results.json`
- thêm cờ cấu hình để đổi threshold release mà không phải sửa code
- lưu lịch sử benchmark theo nhiều lần chạy để so sánh trend thay vì chỉ một lần V1 vs V2

## 8. Tự đánh giá đóng góp
Tôi đánh giá phần đóng góp của mình là phần “đóng gói cuối” để biến các module rời rạc của nhóm thành một benchmark pipeline có thể chạy, có thể chấm và có thể phân tích.

Tôi không trực tiếp cải thiện retrieval hay judge model, nhưng tôi chịu trách nhiệm:

- đưa pipeline về trạng thái chạy end-to-end
- làm cho kết quả benchmark có cấu trúc rõ ràng
- thiết kế release gate để quyết định release/block dựa trên dữ liệu
- cung cấp failure analysis có số liệu thật thay vì template hình thức

Đây là phần việc quan trọng vì nếu không có orchestration đúng, những đóng góp kỹ thuật của các thành viên khác sẽ khó được tổng hợp thành kết quả benchmark hoàn chỉnh.
