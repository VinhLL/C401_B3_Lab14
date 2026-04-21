# Báo cáo cá nhân - Bùi Quang Vinh

## Vai trò phụ trách
**DATA OWNER**

## 1. Phạm vi công việc đã sở hữu
Trong Lab 14, tôi phụ trách phần dữ liệu đầu vào cho toàn bộ pipeline đánh giá. Phạm vi chính của tôi gồm:

- Chốt domain cuối cùng cùng cả nhóm.
- Tạo corpus nguồn có ID ổn định để phục vụ retrieval.
- Sửa script sinh golden dataset để tạo được từ 50 test cases trở lên.
- Đảm bảo mỗi test case có `expected_retrieval_ids` để tính Hit Rate và MRR.
- Đảm bảo dữ liệu có phân bố theo `difficulty` và `type` để hỗ trợ phân tích lỗi.
- Chuẩn bị dữ liệu sạch, nhất quán cho bước tạo database retrieval.

## 2. Domain cuối cùng đã chốt
Nhóm thống nhất chọn domain:

- **BLDS 2015 - Bảo đảm thực hiện nghĩa vụ dân sự**
- Mã domain trong dữ liệu: `civil_law_security_obligations_vi`

Lý do chọn domain này:

- Nội dung đủ hẹp để kiểm soát chất lượng dữ liệu.
- Có cấu trúc pháp lý rõ ràng, thuận lợi cho retrieval theo điều luật/chủ đề.
- Có đủ các tình huống so sánh, quy tắc, quy trình và các đoạn khó để sinh test case nhiều mức độ.

## 3. File tôi sở hữu
- **Thêm:** `data/domain_corpus.jsonl`
- **Sửa:** `data/synthetic_gen.py`

## 4. Công việc đã thực hiện

### 4.1. Xây dựng corpus nguồn có ID ổn định
Tôi xây dựng file `data/domain_corpus.jsonl` theo định dạng JSONL, mỗi dòng là một chunk độc lập của tài liệu. Mỗi record đều có các trường phục vụ retrieval và trace ngược về nguồn, trong đó quan trọng nhất là:

- `doc_id`
- `chunk_id`
- `chunk_index`
- `domain`
- `title`
- `text`
- `summary`
- `article_refs`

Quy ước ID được giữ ổn định theo hướng:

- `doc_id`: đại diện cho tài liệu nguồn
- `chunk_id`: đại diện cho từng chunk, ví dụ `blds2015_bao_dam_nghia_vu_chunk_009`

Nhờ cách đặt ID này, các thành phần retrieval, benchmark và phân tích lỗi có thể tham chiếu cùng một đơn vị dữ liệu mà không bị lệch mapping.

### 4.2. Sửa script sinh golden dataset
Tôi chỉnh `data/synthetic_gen.py` để script không còn sinh dữ liệu ngẫu nhiên đơn giản mà chọn case trực tiếp từ corpus theo rule-based heuristic. Các điểm chính gồm:

- Lọc ra các chunk đủ thông tin để làm test case.
- Phân loại case theo `difficulty`: `easy`, `medium`, `hard`.
- Phân loại case theo `type`: `comparison`, `rule_interpretation`, `scenario_analysis`, `article_rule`, `procedure`, `topic_summary`.
- Tạo `question` bám sát nội dung thực tế của chunk.
- Sinh `expected_answer` từ ngữ cảnh gốc.
- Gắn `expected_retrieval_ids` bằng chính `chunk_id` mong đợi.
- Với các case tình huống kéo dài qua nhiều đoạn, mở rộng `expected_retrieval_ids` sang chunk kế tiếp để đánh giá retrieval công bằng hơn.

### 4.3. Đảm bảo dữ liệu phục vụ tính Hit Rate và MRR
Mỗi dòng trong `data/golden_set.jsonl` đều có:

- `expected_answer`
- `expected_retrieval_ids`

Đây là điều kiện bắt buộc để engine có thể:

- So sánh câu trả lời với ground truth.
- Tính Hit Rate.
- Tính MRR.
- Phân tích retrieval miss theo từng case.

### 4.4. Phân bố difficulty/type để phục vụ failure analysis
Tôi chủ động thiết kế script để không sinh dữ liệu lệch về một kiểu câu hỏi duy nhất. Kết quả hiện tại của bộ golden set:

- **Số lượng case:** 60
- **Difficulty distribution:** `easy = 20`, `medium = 25`, `hard = 15`
- **Type distribution:** `comparison = 16`, `rule_interpretation = 12`, `scenario_analysis = 15`, `article_rule = 11`, `procedure = 4`, `topic_summary = 2`

Phân bố này giúp benchmark có giá trị hơn vì có thể quan sát lỗi retrieval/generation theo từng loại ca thay vì chỉ nhìn một điểm trung bình chung.

### 4.5. Phần tạo database
Ngoài corpus và golden dataset, tôi cũng phụ trách chuẩn hóa dữ liệu đầu vào cho bước tạo database retrieval. Cụ thể:

- Corpus được giữ `doc_id` và `chunk_id` ổn định để index vào vector database không bị lệch khóa.
- Dữ liệu được chuẩn hóa theo chunk để mỗi vector tương ứng đúng một đơn vị retrieval.
- Repo hiện có `data/chroma_manifest.json`, trong đó manifest ghi nhận collection `blds2015_legal_corpus` với **177 documents** được index từ `data/domain_corpus.jsonl`.

Với cách tổ chức này, pipeline retrieval có thể:

- Truy vấn theo embedding ở mức chunk.
- Trả về `retrieved_ids` cùng hệ quy chiếu với `expected_retrieval_ids`.
- Đo được chất lượng retrieval một cách nhất quán.

## 5. Kết quả đối chiếu với Definition of Done

### 5.1. Có 1 file corpus có `doc_id` / `chunk_id` ổn định
Đã hoàn thành.

- File: `data/domain_corpus.jsonl`
- Quy mô hiện tại: **177 chunks**
- ID ổn định theo quy ước thống nhất giữa corpus, retrieval và benchmark

### 5.2. `python data/synthetic_gen.py` sinh ra `data/golden_set.jsonl` >= 50 dòng
Đã hoàn thành.

- Kết quả thực tế: **60 dòng**

### 5.3. Mỗi dòng có `expected_answer` và `expected_retrieval_ids`
Đã hoàn thành.

- Kết quả kiểm tra: không có dòng nào thiếu hai trường này

### 5.4. Có phân bố difficulty/type để phục vụ phân tích lỗi
Đã hoàn thành.

- Bộ test có phân tầng rõ theo độ khó và loại câu hỏi

### 5.5. Có dữ liệu sẵn sàng cho phần tạo database
Đã hoàn thành ở mức dữ liệu và index mapping.

- Corpus đã tương thích với bước build database
- `chunk_id` trong database và `expected_retrieval_ids` dùng cùng hệ quy chiếu

## 6. Quyết định kỹ thuật chính
- Chọn **JSONL** thay vì một file JSON lớn để dễ stream, dễ kiểm tra từng dòng và thuận tiện cho pipeline benchmark.
- Giữ **stable ID** ở cấp document và chunk để không phá vỡ các phép đo retrieval khi cập nhật script hoặc benchmark lại.
- Dùng **rule-based case generation** thay vì sinh câu hỏi ngẫu nhiên để kiểm soát chất lượng và độ phủ.
- Gắn **metadata difficulty/type** ngay trong golden set để hỗ trợ failure clustering và root-cause analysis.
- Với các hard case nhiều đoạn, cho phép **nhiều expected chunk IDs** để phản ánh đúng thực tế retrieval pháp lý.

## 7. Khó khăn gặp phải và cách xử lý

### Khó khăn 1: Văn bản pháp lý dài, cấu trúc không đồng đều
Một số chunk có tiêu đề kém rõ nghĩa hoặc chứa nhiều nội dung nối tiếp nhau, khó sinh câu hỏi tốt nếu chỉ lấy nguyên văn.

**Cách xử lý:**  
Tôi bổ sung logic suy ra topic từ `title`, câu đầu và các pattern pháp lý để tạo câu hỏi hợp lý hơn.

### Khó khăn 2: Một số tình huống trải qua nhiều chunk
Nếu chỉ gắn 1 chunk làm ground truth thì retrieval có thể bị đánh giá thiếu công bằng.

**Cách xử lý:**  
Tôi cho script kiểm tra chunk kế tiếp trong các case tình huống và thêm vào `expected_retrieval_ids` khi cần.

### Khó khăn 3: Cần vừa đủ số lượng vừa đảm bảo độ đa dạng
Nếu chỉ lấy các chunk dài nhất hoặc dễ nhất thì bộ benchmark không có giá trị phân tích lỗi.

**Cách xử lý:**  
Tôi đặt quota theo difficulty và giữ thêm phân loại type để đảm bảo độ phủ.

## 8. Bài học rút ra
- Với bài toán RAG, chất lượng benchmark phụ thuộc rất mạnh vào chất lượng corpus và ground truth retrieval.
- Stable ID là điều bắt buộc nếu muốn theo dõi regression giữa các lần chạy benchmark.
- Failure analysis chỉ thực sự có ý nghĩa khi golden set có phân tầng theo độ khó và kiểu câu hỏi.
- Phần tạo database không nên làm tách rời với bước thiết kế corpus; nếu ID không ổn định thì toàn bộ phép đo retrieval sẽ mất giá trị.

## 9. Tự đánh giá đóng góp
Tôi đã hoàn thành đúng phần việc của một Data Owner:

- Chốt domain cuối cùng cùng nhóm.
- Xây dựng corpus nguồn có ID ổn định.
- Sửa script để sinh được golden dataset đạt yêu cầu.
- Đảm bảo đủ trường dữ liệu để tính các chỉ số retrieval.
- Chuẩn bị dữ liệu nhất quán cho bước tạo database và benchmark.

Phần việc này là nền tảng cho các nhóm Retrieval, Judge và Failure Analysis chạy đúng và cho ra kết quả có thể tin cậy.
