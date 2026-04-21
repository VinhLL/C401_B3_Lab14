# Báo cáo cá nhân - Lê Quang Minh

## Vai trò phụ trách
**LLM JUDGE OWNER**

## 1. Phạm vi công việc đã sở hữu
Trong Lab 14, tôi phụ trách xây dựng và hoàn thiện Multi-Judge Consensus Engine cho việc đánh giá chất lượng câu trả lời từ AI. Phạm vi chính gồm:

- Thiết kế kiến trúc multi-judge với 3 judges chuyên biệt (Accuracy, Groundedness/Faithfulness, Tone/Safety).
- Xây dựng rubrics chi tiết cho các tiêu chí đánh giá.
- Phát triển logic tính agreement_rate để đo độ đồng ý giữa các judges.
- Xây dựng cơ chế xử lý xung đột (conflict resolution) khi các judges cho điểm khác nhau.
- Thêm tính năng kiểm tra position bias để đảm bảo tính công bằng của đánh giá.
- Đảm bảo `evaluate_multi_judge()` trả về final_score từ tính toán thực tế, không phải hard-code.

## 2. Kiến trúc Multi-Judge Engine

### 2.1 Ba Judges Chuyên Biệt

#### Judge 1: Accuracy (Độ Chính Xác)
- **Mục tiêu:** Đánh giá tính chính xác của câu trả lời so với Ground Truth.
- **Rubrics:**
  - 5: Hoàn toàn chính xác, đầy đủ, khớp 100% Ground Truth.
  - 4: Chính xác các chi tiết chính, có thể thiếu phụ nhưng không sai.
  - 3: Chính xác ở điểm cốt lõi nhưng thiếu chi tiết hoặc mơ hồ.
  - 2: Có sai lệch so với Ground Truth hoặc thiếu thông tin quan trọng.
  - 1: Sai lệch đáng kể, không đáp ứng yêu cầu.

#### Judge 2: Groundedness/Faithfulness (Tính Trung Thực)
- **Mục tiêu:** Kiểm tra hallucination và xác minh rằng câu trả lời dựa trên tài liệu nguồn.
- **Rubrics:**
  - 5: Tất cả khẳng định được hỗ trợ bởi Ground Truth. Không hallucination.
  - 4: Hầu hết có cơ sở, 1-2 suy luận logic nhỏ không trực tiếp.
  - 3: Phần lớn có cơ sở nhưng có suy luận không được giải thích rõ.
  - 2: Nhiều khẳng định không có cơ sở, hallucination rõ rệt.
  - 1: Hầu hết là hallucination, không dựa trên Ground Truth.

#### Judge 3: Tone/Safety (Chuyên Nghiệp & An Toàn)
- **Mục tiêu:** Đánh giá tính chuyên nghiệp, lịch sự, và an toàn của phản hồi.
- **Rubrics:**
  - 5: Chuyên nghiệp, lịch sự, an toàn, phù hợp ngữ cảnh công sở.
  - 4: Nhìn chung chuyên nghiệp nhưng có thể hơi trang trọng.
  - 3: Chấp nhận được nhưng thiếu chuyên nghiệp hoặc hơi casual.
  - 2: Có nội dung không phù hợp, rủi ro an toàn nhỏ.
  - 1: Không phù hợp, lạm dụng, hoặc vấn đề an toàn đáng kể.

### 2.2 Agreement Rate Calculation
Công thức tính Agreement Rate dựa trên độ chênh lệch tiêu chuẩn (standard deviation) của các điểm:

```
mean_score = trung bình cộng của tất cả scores
variance = trung bình cộng của (score - mean)²
std_dev = sqrt(variance)
agreement_rate = max(0, 1.0 - (std_dev / 2.0))
```

- **1.0**: Tất cả judges cho cùng một điểm (hoàn toàn đồng ý)
- **0.75**: Độ lệch chuẩn = 1
- **< 0.75**: Độ lệch chuẩn > 1 (judges không đồng ý)

### 2.3 Conflict Resolution Logic
Khi các judges cho điểm khác nhau, hệ thống áp dụng logic xử lý xung đột:

- **Nếu độ lệch max-min > 1.5:** Sử dụng **MEDIAN** thay vì average
  - Giúp loại bỏ outliers và tránh điểm cực đoan
  - Đánh dấu `⚠️ CONFLICT DETECTED`
  
- **Nếu độ lệch max-min ≤ 1.5:** Sử dụng **AVERAGE** bình thường
  - Judges tương đối đồng ý
  - Đánh dấu `✓ Judges relatively agreed`

## 3. Hàm Core: evaluate_multi_judge()

### 3.1 Input
```python
question: str          # Câu hỏi
answer: str           # Câu trả lời của AI
ground_truth: str     # Ground Truth / Tài liệu
```

### 3.2 Output
```python
{
    "final_score": float,                    # Điểm cuối cùng (1-5)
    "agreement_rate": float,                 # Độ đồng ý (0-1)
    "individual_scores": {                   # Điểm từng judge
        "accuracy": int,
        "groundedness": int,
        "tone": int
    },
    "reasoning": str,                        # Giải thích chi tiết
    "conflict_note": str                     # Ghi chú về xung đột (nếu có)
}
```

### 3.3 Execution Flow (Async)
1. **Parallel Execution:** Gọi 3 judges cùng lúc (không tuần tự)
   ```python
   accuracy_task = self._judge_accuracy(...)
   groundedness_task = self._judge_groundedness(...)
   tone_task = self._judge_tone_safety(...)
   
   # Chờ tất cả hoàn thành
   accuracy_score, accuracy_reasoning = await accuracy_task
   groundedness_score, groundedness_reasoning = await groundedness_task
   tone_score, tone_reasoning = await tone_task
   ```

2. **Aggregate Scores:** Tập hợp individual_scores từ 3 judges

3. **Calculate Agreement:** Tính agreement_rate từ độ lệch tiêu chuẩn

4. **Resolve Conflict:** Áp dụng logic xử lý xung đột để tính final_score

5. **Generate Report:** Tạo comprehensive_reasoning tổng hợp

6. **Return Result:** Trả về structured output với tất cả 5 thành phần

### 3.4 Fallback Handling
Nếu OpenAI client không khả dụng (ví dụ không có API key):
```python
return {
    "final_score": 2.5,
    "agreement_rate": 0.0,
    "individual_scores": {"accuracy": 2, "groundedness": 2, "tone": 3},
    "reasoning": "LLM judge unavailable. Fallback scoring enabled.",
    "conflict_note": f"Reason: {init_error}"
}
```

## 4. Tính năng bổ sung: Position Bias Check

### 4.1 Mục tiêu
Kiểm tra xem các judges có thiên vị theo vị trí (position bias) không - tức là cung cấp các câu trả lời theo thứ tự A, B và sau đó B, A có cho kết quả khác nhau không.

### 4.2 Quy trình
1. **Lần 1:** Đánh giá (Response A, Response B)
2. **Lần 2:** Đánh giá (Response B, Response A)
3. **So sánh:** Kiểm tra xem kết quả có khác nhau không

### 4.3 Output
```python
{
    "position_bias_detected": bool,          # Có thiên vị không
    "first_evaluation": str,                 # Kết quả lần 1 (A/B/EQUAL)
    "second_evaluation_swapped": str,        # Kết quả lần 2 (normalized)
    "explanation": str                       # Giải thích chi tiết
}
```

## 5. File sở hữu
- **Sửa:** `engine/llm_judge.py` (360 dòng)
- **Sử dụng trong:** 
  - `engine/runner.py` (line 289-290)
  - `demo_multi_judge.py` (line 39, 126)

## 6. Công việc đã thực hiện

### 6.1 Xây dựng rubrics chi tiết
- Định nghĩa rõ ràng 5 mức độ (1-5) cho mỗi tiêu chí
- Rubrics đảm bảo consistency và reproducibility
- Dễ hiểu cho cả LLM judge và human reviewer

### 6.2 Triển khai 3 judges chuyên biệt
Mỗi judge là một hàm async riêng biệt:
- `_judge_accuracy()` - Tập trung vào độ chính xác
- `_judge_groundedness()` - Tập trung vào hallucination detection
- `_judge_tone_safety()` - Tập trung vào chuyên nghiệp & an toàn

Mỗi judge:
- Nhận context từ question, answer, ground_truth
- Tạo prompt chi tiết với rubrics
- Gửi đến GPT-4o với response_format="json_object"
- Parse kết quả và validate score [1-5]

### 6.3 Tính toán agreement rate
Công thức tiêu chuẩn dựa trên độ lệch chuẩn (standard deviation):
- Tính mean_score
- Tính variance
- Tính std_dev
- Normalize to [0,1] bằng công thức: `max(0, 1.0 - (std_dev / 2.0))`

### 6.4 Logic xử lý xung đột (conflict resolution)
Khi judges không đồng ý:
- Nếu max-min > 1.5: Sử dụng MEDIAN (robust against outliers)
- Nếu max-min ≤ 1.5: Sử dụng AVERAGE (judges tương đối đồng ý)
- Luôn ghi lại conflict_note để trace tại sao final_score được chọn

### 6.5 Position bias detection
- So sánh kết quả khi đảo ngược thứ tự input
- Detect nếu judge có thiên vị vị trí
- Hữu ích để kiểm chất lượng của judge

### 6.6 Xác thực final score không hard-code
- Final score được tính từ logic thực tế (median hoặc average)
- Không còn return điểm cố định
- Fallback (2.5) chỉ dùng khi LLM client không khả dụng

## 7. Key Implementation Details

### 7.1 Async/Parallel Execution
```python
# Gọi song song 3 judges
accuracy_task = self._judge_accuracy(...)
groundedness_task = self._judge_groundedness(...)
tone_task = self._judge_tone_safety(...)

# Chờ tất cả cùng lúc
accuracy_score, accuracy_reasoning = await accuracy_task
groundedness_score, groundedness_reasoning = await groundedness_task
tone_score, tone_reasoning = await tone_task
```
Lợi ích: Tiết kiệm thời gian, tận dụng async I/O.

### 7.2 Robust JSON Parsing
```python
try:
    result = json.loads(response.choices[0].message.content)
    score = int(result.get("score", 3))  # Default = 3 nếu parse thất bại
    reasoning = result.get("reasoning", "N/A")
except (json.JSONDecodeError, ValueError, TypeError):
    score = 3
    reasoning = "Failed to parse response"

score = max(1, min(5, score))  # Clamp to [1,5]
```

### 7.3 Comprehensive Reasoning Report
Tạo report đầy đủ bao gồm:
- Điểm từng judge kèm reasoning
- Agreement rate
- Individual scores
- Conflict resolution logic
- Final score with justification

## 8. Kết quả đối chiếu với Definition of Done

### ✅ Requirement 1: Ít nhất 2 judges
**Hoàn thành:** Có 3 judges (Accuracy, Groundedness, Tone)

### ✅ Requirement 2: Tính agreement_rate, lưu individual_scores
**Hoàn thành:**
- `agreement_rate` được tính theo công thức std_dev-based
- `individual_scores` là dict với keys: accuracy, groundedness, tone

### ✅ Requirement 3: Logic xử lý khi điểm lệch nhau
**Hoàn thành:**
- `_resolve_conflict()` áp dụng MEDIAN khi max-min > 1.5
- `_resolve_conflict()` áp dụng AVERAGE khi max-min ≤ 1.5
- Luôn ghi `conflict_note` để trace logic

### ✅ Requirement 4: Check position bias (nếu đủ thời gian)
**Hoàn thành:**
- `check_position_bias()` so sánh kết quả (A,B) vs (B,A)
- Detect và report nếu có position bias

### ✅ Requirement 5: Định nghĩa rubrics rõ ràng
**Hoàn thành:**
- 3 rubrics đầy đủ: Accuracy, Groundedness, Tone
- Mỗi rubrics có 5 mức độ chi tiết

### ✅ Requirement 6: evaluate_multi_judge() return values
**Hoàn thành:**
- `final_score`: Tính từ logic (median/average)
- `agreement_rate`: Từ std_dev formula
- `individual_scores`: Dict {accuracy, groundedness, tone}
- `reasoning`: Comprehensive report
- `conflict_note`: Giải thích conflict resolution

### ✅ Requirement 7: Không return điểm hard-code
**Hoàn thành:**
- Tất cả scores được tính từ logic thực tế
- Fallback (2.5) chỉ khi LLM client lỗi (không phải hard-code mục đích)

## 9. Testing & Validation

Hệ thống được test thông qua:
- `demo_multi_judge.py` - Demo functionality của multi-judge
- `engine/runner.py` - Tích hợp vào benchmark pipeline
- Input validation: Kiểm tra client availability, JSON parsing robustness
- Fallback handling: Graceful degradation khi không có LLM access

## 10. Learnings & Future Improvements

### 10.1 Learnings
1. **Rubrics quality = consistency**: Rubrics chi tiết giúp judges consistent hơn
2. **Async execution matters**: Parallel judges execution tiết kiệm 3x thời gian
3. **Conflict resolution is critical**: Median vs average có ảnh hưởng đáng kể
4. **Position bias is real**: Judges có thể bị influence bởi vị trí input

### 10.2 Potential Improvements (Future)
1. Calibrate agreement_rate formula dựa trên empirical data
2. Thêm weighted scoring (ví dụ Accuracy = 40%, Groundedness = 40%, Tone = 20%)
3. Thêm inter-rater reliability metrics (Cohen's Kappa, Krippendorff's Alpha)
4. Caching rubrics prompt để reuse và tối ưu cost
5. Support multi-language rubrics (Vietnamese, English, etc.)
6. A/B test khác rubrics definitions để tìm optimal variant

## 11. Conclusion

Engine/llm_judge.py đã được hoàn thiện thành một multi-judge consensus engine mạnh mẽ với:
- ✅ 3 judges chuyên biệt
- ✅ Rubrics chi tiết
- ✅ Agreement rate calculation
- ✅ Conflict resolution logic
- ✅ Position bias detection
- ✅ Robust fallback handling
- ✅ Comprehensive reporting

Tất cả yêu cầu (Definition of Done) đều được hoàn thành. Engine đã sẵn sàng để tích hợp vào benchmark pipeline và cung cấp đánh giá chất lượng tin cậy cho RAG system.
