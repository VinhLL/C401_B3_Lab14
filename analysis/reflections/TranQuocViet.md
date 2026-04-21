# Báo cáo Cá Nhân - Trần Quốc Việt

## 1. Phạm vi công việc đã sở hữu

Trong bài lab này, phần tôi phụ trách là Retrieval Evaluation cho pipeline benchmark. Phạm vi chính gồm:

- hoàn thiện `engine/retrieval_eval.py` để tính metric retrieval theo từng case
- tổng hợp metric batch gồm `avg_hit_rate` và `avg_mrr`
- xử lý các edge cases của contract retrieval như `retrieved_ids` bị thiếu, `expected_retrieval_ids` rỗng, và `top_k` khác nhau giữa các phiên bản agent
- chuẩn hóa `data/HARD_CASES_GUIDE.md` để hard-case khớp với schema dataset thật và quota benchmark đang dùng
- phối hợp với các thành viên phụ trách agent và judge để chốt contract `expected_retrieval_ids` <-> `retrieved_ids`

Hai file tôi trực tiếp sở hữu và chỉnh sửa là:

- `engine/retrieval_eval.py`
- `data/HARD_CASES_GUIDE.md`

## 2. Quyết định kỹ thuật chính

### 2.1. Tách rõ metric theo từng case và metric tổng hợp batch

Trong `engine/retrieval_eval.py`, tôi không chỉ giữ các hàm tính `hit_rate` và `mrr`, mà bổ sung thêm logic `evaluate_case(...)` để mỗi test case trả về đầy đủ:

- `hit_rate`
- `mrr`
- `top_k` thực tế được dùng để chấm
- `matched_expected_ids`
- `first_relevant_rank`
- `is_scored`
- `skip_reason`

Cách làm này giúp debug retrieval dễ hơn rất nhiều so với chỉ có một con số trung bình ở cuối batch. Khi benchmark fail, nhóm có thể biết case nào miss hoàn toàn, case nào hit ở rank thấp, và case nào bị skip do thiếu ground truth retrieval.

### 2.2. Chuẩn hóa edge-case để metric không bị méo

Tôi áp dụng các quy ước sau:

- nếu `expected_retrieval_ids` rỗng thì case đó không được tính vào trung bình retrieval và phải có `skip_reason = "empty_expected_retrieval_ids"`
- nếu `retrieved_ids` thiếu hoặc rỗng nhưng `expected_retrieval_ids` có dữ liệu thì case vẫn được chấm với `hit_rate = 0.0`, `mrr = 0.0`
- `top_k` không bị hard-code duy nhất, mà được resolve động theo case hoặc theo output retrieval hiện có

Quy ước này quan trọng vì nếu không tách bạch `skip` với `miss`, trung bình retrieval sẽ phản ánh sai chất lượng hệ thống.

### 2.3. Đồng bộ contract với dataset và agent

Sau khi đối chiếu pipeline, tôi chốt contract như sau:

- dataset dùng `expected_retrieval_ids`
- agent trả `retrieved_ids`
- hai trường này phải cùng dùng `chunk_id`
- evaluator so sánh trực tiếp hai danh sách này, không map qua `doc_id`, `title` hay text matching

Đây là điểm quan trọng để tránh benchmark bị mơ hồ. Nếu không khóa contract ở mức ID, nhóm sẽ rất khó xác định retrieval thực sự đúng hay chỉ “na ná đúng”.

### 2.4. Chuẩn hóa hard-case theo schema thật thay vì mô tả chung chung

Trong `data/HARD_CASES_GUIDE.md`, tôi chuyển từ mô tả kiểu ý tưởng tổng quát sang guide bám sát dataset generator hiện tại. Cụ thể:

- nêu rõ schema bắt buộc của một case benchmark
- định nghĩa hard case hiện tại là `metadata.difficulty = "hard"` và trọng tâm là `scenario_analysis`
- chốt quota difficulty là `easy = 20`, `medium = 25`, `hard = 15`
- mô tả cách gán `expected_retrieval_ids` cho case cần 1 hoặc nhiều chunk
- nêu rõ quy ước `top_k` khi chấm retrieval cho V1 và V2

Mục tiêu của phần này là làm cho hard cases có giá trị benchmark thật sự, thay vì chỉ là danh sách ý tưởng khó nhưng không đo được bằng code.

## 3. Kết quả đạt được

Dựa trên benchmark trong `analysis/failure_analysis.md`, phần retrieval sau khi được đo đúng contract đã cho ra tín hiệu rõ ràng hơn:

- V1 có `hit_rate = 0.0833`, `avg_mrr = 0.0667`
- V2 có `hit_rate = 0.1167`, `avg_mrr = 0.0733`
- delta retrieval của V2 so với V1 là `+0.0334` hit rate và `+0.0066` MRR

Điều này cho thấy V2 có cải thiện retrieval nhẹ, dù chưa đủ để qua release gate. Quan trọng hơn, benchmark hiện đã đo được retrieval đúng theo từng case thay vì dùng số giả lập.

Tôi cũng đã kiểm tra các tình huống biên ở evaluator:

- case có overlap giữa `expected_retrieval_ids` và `retrieved_ids` cho metric đúng
- case thiếu `retrieved_ids` trả về miss hợp lệ
- case `expected_retrieval_ids` rỗng được skip khỏi trung bình

Như vậy, definition of done của phần tôi phụ trách đã đạt ở mức code và benchmark artifact:

- có hàm tính metric theo từng case
- có tổng hợp `avg_hit_rate`, `avg_mrr`
- hard-case guide khớp với dataset schema và benchmark quota

## 4. Vấn đề gặp phải và cách xử lý

### 4.1. Vấn đề ban đầu: retrieval evaluator chỉ là placeholder

Khi rà soát code, tôi thấy `evaluate_batch(...)` trong `engine/retrieval_eval.py` đang trả về số hard-code. Điều này làm cho benchmark nhìn như có retrieval metrics nhưng thực tế không đo gì cả.

Tôi xử lý bằng cách viết lại logic evaluator để:

- tính per-case trước
- chỉ aggregate trên các case có thể chấm
- trả thêm metadata phục vụ debug

### 4.2. Hard-case guide không khớp dataset đang generate

Guide cũ tập trung vào prompt injection, ambiguity, multi-turn và technical stress. Các ý tưởng này hữu ích về mặt tư duy test, nhưng không khớp với schema `difficulty/type` đang được SDG sinh ra.

Tôi xử lý bằng cách viết lại guide từ góc nhìn benchmark executable:

- hard case là gì theo schema hiện tại
- quota hard case là bao nhiêu
- mapping giữa loại câu hỏi và difficulty
- contract ID nào được dùng để chấm retrieval

### 4.3. Benchmark bị che tín hiệu bởi judge backend lỗi

Theo `failure_analysis.md`, toàn bộ pipeline generation đang bị che khuất vì judge backend fallback, dẫn tới `final_score = 2.5` cho mọi case. Điều này không thuộc phần tôi sở hữu trực tiếp, nhưng có ảnh hưởng đến việc diễn giải tác động của retrieval.

Trong bối cảnh đó, tôi tập trung đảm bảo retrieval metrics vẫn độc lập và đo được thật. Nhờ vậy, dù judge có lỗi, nhóm vẫn nhìn thấy V2 cải thiện retrieval ở một số case và vẫn có cơ sở để phân tích root cause.

## 5. Phân tích cá nhân dựa trên Failure Analysis

Từ `analysis/failure_analysis.md`, tôi rút ra ba điểm quan trọng liên quan trực tiếp đến phần retrieval:

### 5.1. Retrieval hiện tại có thể đo được, nhưng chiến lược truy hồi còn yếu

`hit_rate` của V2 chỉ đạt `0.1167`, nghĩa là retrieval vẫn miss 53/60 cases. Điều này cho thấy phần evaluator của tôi đã làm đúng nhiệm vụ: nó lộ ra chất lượng thật của retrieval thay vì che đi bằng số giả.

### 5.2. Hard cases hiện nay đang có giá trị benchmark thực tế

Do hard cases đã được gắn quota và schema rõ ràng, failure analysis có thể chỉ ra miss tập trung ở `comparison`, `scenario_analysis`, và `rule_interpretation`. Nếu không có guide chuẩn hóa và contract ID rõ ràng, nhóm sẽ khó xác định loại case nào đang kéo tụt retrieval.

### 5.3. Tăng `top_k` không đồng nghĩa với retrieval tốt hơn

Failure analysis chỉ ra V2 tăng cost mạnh nhưng chỉ cải thiện cục bộ. Điều này củng cố quyết định của tôi là evaluator phải support `top_k` động, để benchmark phản ánh đúng trade-off giữa chất lượng và cost theo từng phiên bản agent.

## 6. Bài học rút ra

Qua phần việc này, tôi rút ra các bài học kỹ thuật sau:

- trong benchmark system, metric code phải được kiểm chứng như production code; placeholder rất dễ tạo cảm giác “đã có metric” nhưng thực ra không đo gì
- retrieval benchmark chỉ có giá trị khi contract ground truth ID được khóa chặt giữa dataset, agent và evaluator
- hard-case guide phải gắn với schema executable, không nên chỉ dừng ở mô tả ý tưởng test
- cần phân biệt rõ `skip` với `miss`; đây là khác biệt nhỏ trong code nhưng ảnh hưởng lớn đến độ tin cậy của metric tổng hợp
- khi một tầng khác trong pipeline bị lỗi, retrieval metrics vẫn phải độc lập đủ để hỗ trợ failure analysis

## 7. Hướng cải tiến cho lần benchmark tiếp theo

Nếu làm tiếp vòng sau, tôi ưu tiên các hướng sau cho phần retrieval:

- thêm lexical/article-aware boosting cho query có mẫu như `Điều`, `khoản`, `điểm mới`, `khác với`
- áp dụng hybrid retrieval hoặc reranking cho các case `comparison` và `scenario_analysis`
- thay `top_k` cố định bằng `dynamic top_k` theo difficulty hoặc confidence score
- bổ sung breakdown retrieval theo `difficulty` và `metadata.type` ngay trong summary để failure analysis nhanh hơn
- thêm preflight validation để chặn benchmark sớm nếu dataset, contract fields hoặc judge backend chưa sẵn sàng

## 8. Tự đánh giá đóng góp

Tôi đánh giá phần đóng góp của mình là phần nền tảng cho tính đúng đắn của benchmark retrieval. Tôi không trực tiếp làm retrieval model tốt hơn, nhưng tôi chịu trách nhiệm làm cho hệ thống đo đúng, đo được theo từng case, và có tài liệu đủ rõ để cả nhóm dùng chung một contract. Đây là điều kiện bắt buộc để các cải tiến của những thành viên khác có thể được đánh giá công bằng và có cơ sở kỹ thuật.
