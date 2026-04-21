# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark
- **Dataset benchmark:** 60 cases.
- **Phân bố difficulty:** easy `20`, medium `25`, hard `15`.
- **Phân bố type:** article_rule `11`, comparison `16`, procedure `4`, rule_interpretation `12`, scenario_analysis `15`, topic_summary `2`.
- **Kết quả V1:** pass `0`, fail `60`, error `0`, avg_score `2.50/5`, hit_rate `0.0833`, avg_mrr `0.0667`, agreement_rate `0.0000`, avg_latency `470.62 ms`, avg_cost `0.058730`.
- **Kết quả V2:** pass `0`, fail `60`, error `0`, avg_score `2.50/5`, hit_rate `0.1167`, avg_mrr `0.0733`, agreement_rate `0.0000`, avg_latency `367.94 ms`, avg_cost `0.091957`.
- **Delta V2 - V1:** avg_score `+0.0000`, hit_rate `+0.0334`, avg_mrr `+0.0066`, agreement_rate `+0.0000`, latency `-102.68 ms`, avg_cost `+0.033227` (`+56.58%`).
- **Release gate:** `BLOCK`.
- **Các check bị fail:** `candidate_avg_score_floor`, `candidate_hit_rate_floor`, `candidate_agreement_rate_floor`, `cost_ratio_guard`.

## 2. Phân nhóm lỗi
| Nhóm lỗi | Số lượng | Bằng chứng từ benchmark | Nguyên nhân dự kiến |
|----------|----------|-------------------------|---------------------|
| Judge backend failure | 60/60 cases | `judge_issue_counts.invalid_api_key = 60`, `agreement_rate = 0.0` ở cả V1 và V2 | API key của OpenAI đang sai nên multi-judge rơi vào fallback và không tạo được tín hiệu chất lượng thật |
| Retrieval miss | 53/60 cases ở V2 | `hit_rate = 0` trên 53 cases; miss nhiều ở `comparison = 14`, `scenario_analysis = 13`, `rule_interpretation = 10` | Retrieval hiện tại dựa trên deterministic embedding đơn giản, chưa có article-aware matching, lexical boost hay reranking |
| Cost inflation không đổi chất lượng | 58/60 cases | V2 tăng cost nhưng `hit_rate_delta <= 0` ở 58 cases; chỉ 2 cases được lợi từ `top_k = 5` | V2 đang tăng `top_k` đồng loạt thay vì chọn lọc theo difficulty hoặc confidence |

Góc nhìn thêm theo difficulty của V2:
- `easy`: hit_rate `0.1000`
- `medium`: hit_rate `0.1200`
- `hard`: hit_rate `0.1333`

Nhận xét:
- V2 có cải thiện retrieval nhẹ so với V1 nhưng mức tăng chưa đủ qua ngưỡng release.
- Việc judge backend hỏng khiến toàn bộ score generation đứng yên ở `2.5`, che mất tín hiệu thật của các cải tiến retrieval.

## 3. Phân tích 5 Whys

Do judge backend fallback làm mọi case đều có `final_score = 2.5`, 3 case dưới đây được chọn theo **rủi ro vận hành** thay vì chỉ theo score: một case retrieval miss hoàn toàn, một case retrieval có cải thiện nhưng bị judge che khuất, và một case cost tăng mạnh mà chất lượng không đổi.

### Case #1: `blds2015_case_001` - miss hoàn toàn câu hỏi comparison theo Điều 318
1. **Symptom:** Cả V1 và V2 đều không lấy được `expected_retrieval_ids = ["blds2015_bao_dam_nghia_vu_chunk_005"]`; V2 chỉ thêm 2 chunk nhiễu và cost tăng từ `0.0440` lên `0.0677`.
2. **Why 1:** Query có neo pháp lý rất rõ (`Điều 318`, "điểm mới hoặc điểm khác") nhưng retrieved chunks lại là `141`, `033`, `028`, `062`, `137`, không khớp điều luật cần tìm.
3. **Why 2:** Retrieval hiện tại không ưu tiên match theo số điều, từ khóa pháp lý và intent dạng comparison.
4. **Why 3:** Agent chưa có hybrid retrieval hoặc reranking để kéo chunk chứa điều luật đúng lên top đầu.
5. **Why 4:** Bản V2 chỉ mở rộng `top_k` từ `3` lên `5`, nhưng không đổi chiến lược truy hồi.
6. **Root Cause:** Stack retrieval chưa "article-aware" cho câu hỏi comparison, nên tăng số lượng context không giải quyết được lỗi gốc.

### Case #2: `blds2015_case_024` - retrieval có cải thiện nhưng benchmark vẫn fail
1. **Symptom:** V1 miss hoàn toàn; V2 đã tìm được chunk đúng `078` ở rank `5` nên `hit_rate` tăng từ `0.0` lên `1.0` và `mrr` tăng lên `0.2`, nhưng `final_score` vẫn giữ `2.5`.
2. **Why 1:** Judge không chấm được câu trả lời thật vì mọi request tới OpenAI đều trả `invalid_api_key`.
3. **Why 2:** Pipeline benchmark không có preflight check cho judge backend trước khi chạy toàn bộ dataset.
4. **Why 3:** Khi judge fail, hệ thống dùng fallback score cố định nên phần generation quality không còn giá trị phân biệt.
5. **Why 4:** Release gate vẫn phải dựa vào `avg_score` và `agreement_rate`, nên candidate bị block dù retrieval có cải thiện cục bộ.
6. **Root Cause:** Môi trường chấm điểm bị misconfigure; lỗi cấu hình đã che khuất tác động tích cực của retrieval ở một số case.

### Case #3: `blds2015_case_032` - cost tăng mạnh nhưng không có gain
1. **Symptom:** V1 đã hit đúng chunk `092` ở rank `2` (`mrr = 0.5`), V2 vẫn giữ nguyên chất lượng retrieval nhưng cost tăng từ `0.0759` lên `0.1271` (`+67.5%`).
2. **Why 1:** V2 kéo thêm hai chunk `053` và `054` dù chunk liên quan đã xuất hiện ở rank cao.
3. **Why 2:** Logic tối ưu hiện tại đồng nhất "tốt hơn" với "lấy nhiều context hơn".
4. **Why 3:** Không có reranking, cutoff theo confidence, hay dynamic top_k theo loại case.
5. **Why 4:** Cost guard chỉ được kiểm ở cuối pipeline, chưa được phản ánh ngược lại ở chiến lược retrieval của agent.
6. **Root Cause:** V2 tối ưu theo hướng brute-force `top_k` thay vì tối ưu đa mục tiêu giữa quality, latency và cost.

## 4. Kế hoạch cải tiến (Action Plan)
- [ ] Sửa cấu hình judge trước khi benchmark lại: xác thực `OPENAI_API_KEY`, thêm preflight health check và fail-fast nếu judge backend không usable.
- [ ] Với query có mẫu `Điều`, `khoản`, `điểm mới`, `khác với`, thêm lexical/article boost hoặc hybrid retrieval để tăng precision cho `comparison` và `rule_interpretation`.
- [ ] Thay `top_k` cố định bằng `dynamic top_k`: giữ `top_k = 3` mặc định, chỉ mở rộng khi hard case hoặc khi score truy hồi thấp.
- [ ] Thêm reranking hoặc heuristic lọc context để giảm tình trạng V2 tăng cost trên 58/60 cases mà không tăng hit_rate.
- [ ] Benchmark lại sau khi judge backend hoạt động bình thường, rồi cập nhật lại `failure_analysis.md` bằng score thật thay vì fallback `2.5`.
