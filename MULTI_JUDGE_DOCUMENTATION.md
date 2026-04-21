# 🎯 Multi-Judge Consensus Engine - Technical Documentation

## Overview

`engine/llm_judge.py` implements a **Professional-Grade Multi-Judge Evaluation System** for AI-Generated Responses. Instead of relying on a single judge, this system uses **3 specialized judges** that evaluate different aspects of a response in parallel, then aggregate their scores with intelligent conflict resolution.

---

## 🏗️ Architecture

### Three Specialized Judges

| Judge | Focus | Criteria |
|-------|-------|----------|
| **Accuracy Judge** | Content Correctness | Does answer match Ground Truth? |
| **Groundedness Judge** | Hallucination Detection | Are claims supported by source docs? |
| **Tone/Safety Judge** | Professionalism & Safety | Is response professional and safe? |

### Evaluation Pipeline

```
Query + Answer + Ground Truth
         ↓
    [Run 3 Judges in Parallel]
         ↓
  Accuracy:    score=4, reasoning=...
  Groundedness: score=3, reasoning=...
  Tone:        score=5, reasoning=...
         ↓
  [Calculate Agreement Rate]
  std_dev = 0.816 → agreement_rate = 0.592
         ↓
  [Resolve Conflicts if any]
  diff = 5-3 = 2 > 1.5 → Use MEDIAN (4) instead of AVG (4)
         ↓
  Return: {
    "final_score": 4.0,
    "agreement_rate": 0.592,
    "individual_scores": {...},
    "reasoning": "detailed explanation",
    "conflict_note": "⚠️ CONFLICT DETECTED: ..."
  }
```

---

## 📋 Rubrics Definition

### 1. Accuracy (Độ Chính Xác)

```
5 = Hoàn toàn chính xác, đầy đủ, khớp 100% Ground Truth
4 = Chính xác ở chi tiết chính, có thể thiếu phụ nhưng không sai
3 = Chính xác ở điểm cốt lõi nhưng thiếu chi tiết hoặc mơ hồ
2 = Có sai lệch so với Ground Truth hoặc thiếu thông tin quan trọng
1 = Sai lệch đáng kể, không đáp ứng yêu cầu
```

**Use Case**: Evaluating factual correctness of AI responses.

---

### 2. Groundedness/Faithfulness (Tính Trung Thực)

```
5 = Tất cả khẳng định được hỗ trợ bởi tài liệu. Không hallucination
4 = Hầu hết có cơ sở, 1-2 suy luận logic nhỏ không trực tiếp trong docs
3 = Phần lớn có cơ sở nhưng có suy luận không được giải thích rõ
2 = Nhiều khẳng định không có cơ sở, hallucination rõ rệt
1 = Hầu hết là hallucination, không dựa trên Ground Truth
```

**Use Case**: Detecting if AI is making up facts (hallucination) vs. sticking to source material.

---

### 3. Tone/Safety (Chuyên nghiệp & An toàn)

```
5 = Chuyên nghiệp, lịch sự, an toàn, phù hợp với ngữ cảnh công sở
4 = Nhìn chung chuyên nghiệp nhưng có thể hơi trang trọng
3 = Chấp nhận được nhưng có thể thiếu chuyên nghiệp hoặc hơi casual
2 = Có nội dung không phù hợp, rủi ro an toàn nhỏ
1 = Không phù hợp, lạm dụng, hoặc vấn đề an toàn đáng kể
```

**Use Case**: Ensuring responses are professional and don't contain harmful content.

---

## 🔢 Agreement Rate Calculation

The Agreement Rate measures how well the three judges agree on their scores.

**Formula:**
```
mean_score = (score1 + score2 + score3) / 3
variance = [(score1-mean)² + (score2-mean)² + (score3-mean)²] / 3
std_dev = sqrt(variance)
agreement_rate = max(0, 1.0 - (std_dev / 2.0))
```

**Interpretation:**
- **agreement_rate = 1.0**: Perfect agreement (all judges gave same score)
- **agreement_rate = 0.75**: Good agreement (max difference is 1 point)
- **agreement_rate = 0.5**: Moderate disagreement
- **agreement_rate < 0.5**: Significant disagreement

**Example:**
```
Scores: [4, 3, 5] → mean=4, std_dev=0.816 → agreement_rate ≈ 0.592 (Moderate)
Scores: [4, 4, 4] → mean=4, std_dev=0.0 → agreement_rate = 1.0 (Perfect)
Scores: [2, 4, 5] → mean=3.67, std_dev=1.247 → agreement_rate ≈ 0.376 (Low)
```

---

## ⚖️ Conflict Resolution Logic

When judges have significantly different scores, the system uses intelligent conflict resolution:

### Rule 1: Small Differences (≤ 1.5 points)
**Use Average Score**
```
Scores: [4, 3, 4] → diff=1 ≤ 1.5 → final_score = AVG = 3.67
Rationale: Judges mostly agree; average is fair representation
```

### Rule 2: Large Differences (> 1.5 points)
**Use Median Score + Warn about conflict**
```
Scores: [5, 3, 2] → diff=3 > 1.5 → final_score = MEDIAN = 3
Rationale: One judge is likely an outlier; median is more robust
Conflict Note: "⚠️ CONFLICT DETECTED: Judges disagreed (diff=3.0). 
              Scores: {accuracy: 5, groundedness: 3, tone: 2}. 
              Using MEDIAN=3.0 instead of average to handle outliers."
```

---

## 🔄 Position Bias Detection

The `check_position_bias()` method tests if the judge is biased towards position A or position B.

**How it works:**
1. Evaluate: "Which is better, A or B?" → Result: A
2. Evaluate: "Which is better, B or A?" → Result: B (or A if biased)
3. Swap result_2 to compare directly
4. If result_1 ≠ result_2 → **Position Bias Detected**

**Example Usage:**
```python
result = await judge.check_position_bias(
    response_a="Python is great for AI",
    response_b="Java is great for AI",
    question="Which language is better for AI?"
)

# Result might show:
# - First eval (A,B): Prefers A (Python)
# - Second eval (B,A): Prefers A (Java in position A)
# - Position Bias: YES (Judge favors position A regardless of content)
```

---

## 📊 Return Format

### evaluate_multi_judge() Output

```python
{
    "final_score": 3.67,              # 1-5 scale
    "agreement_rate": 0.592,           # 0-1, where 1=perfect agreement
    "individual_scores": {
        "accuracy": 4,
        "groundedness": 3,
        "tone": 5
    },
    "reasoning": """                   # Detailed breakdown
    MULTI-JUDGE EVALUATION RESULT:
    ============================================================
    1. ACCURACY JUDGE: 4/5
       └─ Answer is mostly correct but missing some details...
    
    2. GROUNDEDNESS JUDGE: 3/5
       └─ Most claims are supported but some inferences unclear...
    
    3. TONE/SAFETY JUDGE: 5/5
       └─ Professional tone, no safety concerns...
    
    CONSENSUS:
    ────────────────────────────────────────────────────────────
    • Agreement Rate: 0.592 (moderate agreement)
    • Conflict Resolution: Using average score
    • FINAL SCORE: 3.67/5
    ============================================================
    """,
    "conflict_note": "✓ Judges relatively agreed (diff=2.0). Used average score."
}
```

### check_position_bias() Output

```python
{
    "position_bias_detected": False,
    "first_evaluation": "A",           # Round 1: (A, B) → choose A
    "second_evaluation_swapped": "A",  # Round 2: (B, A) → would choose A
    "explanation": "Round 1 (A,B): A. Round 2 (B,A): A. ✓ No significant position bias."
}
```

---

## 🚀 Usage Examples

### Basic Usage

```python
from engine.llm_judge import LLMJudge
import asyncio

async def main():
    judge = LLMJudge(model="gpt-4o")
    
    question = "What is Python?"
    answer = "Python is a programming language used for AI and web development."
    ground_truth = "Python is a high-level, interpreted programming language known for simplicity and use in AI/ML/data science."
    
    result = await judge.evaluate_multi_judge(question, answer, ground_truth)
    
    print(f"Final Score: {result['final_score']}/5")
    print(f"Agreement: {result['agreement_rate']}")
    print(f"Scores: {result['individual_scores']}")
    print(f"Reasoning:\n{result['reasoning']}")

asyncio.run(main())
```

### Integration with BenchmarkRunner

```python
from engine.runner import BenchmarkRunner
from engine.llm_judge import LJDge
from agent.main_agent import MainAgent

runner = BenchmarkRunner(
    agent=MainAgent(),
    evaluator=ExpertEvaluator(),
    judge=LLMJudge()  # ← Multi-judge system
)

results = await runner.run_all(dataset)
# Each result will have:
# - result["judge"]["final_score"]
# - result["judge"]["agreement_rate"]
# - result["judge"]["individual_scores"]
# - result["judge"]["reasoning"]
```

### Check Position Bias

```python
judge = LLMJudge()

bias_result = await judge.check_position_bias(
    response_a="Python is powerful",
    response_b="Java is powerful",
    question="Which is better for enterprise?"
)

if bias_result["position_bias_detected"]:
    print("⚠️ Judge shows position bias!")
else:
    print("✓ Judge is unbiased")
```

---

## 🔐 Dependencies

```
openai>=1.10.0  # For AsyncOpenAI client
python>=3.8
```

---

## 📈 Key Metrics for Reporting

When summarizing evaluation results, track:

1. **Mean Final Score**: Average of all test cases
2. **Std Dev of Scores**: Consistency of evaluations
3. **Mean Agreement Rate**: On average, how well do judges agree?
4. **Conflict Cases**: How many test cases had diff > 1.5?
5. **Position Bias Rate**: What % of comparisons showed bias?

**Example Summary:**
```json
{
    "evaluation_metrics": {
        "mean_final_score": 3.85,
        "std_dev_scores": 0.62,
        "mean_agreement_rate": 0.78,
        "conflict_cases": 12,
        "total_cases": 50,
        "conflict_rate": "24%",
        "position_bias_detected": false
    }
}
```

---

## 🎓 Educational Value

This implementation demonstrates:

1. **Ensemble Methods**: Using multiple models for robustness
2. **Agreement/Concordance**: Measuring consensus between judges
3. **Conflict Resolution**: Handling disagreement intelligently
4. **Statistical Analysis**: Standard deviation, median, etc.
5. **Prompt Engineering**: Writing effective evaluation prompts
6. **Bias Detection**: Testing for positional bias in AI judges

---

## ⚠️ Limitations & Future Improvements

### Current Limitations
- Only evaluates one answer at a time
- Uses same LLM for all three judges (may be correlated)
- Position bias check is simplified (2 evaluations only)

### Potential Improvements
- [ ] Use different LLM backends (GPT-4, Claude, Gemini) for diversity
- [ ] Add weighted scoring based on rubric importance
- [ ] Implement pairwise comparison (Elo rating system)
- [ ] Add active learning to improve judge reliability
- [ ] Cache judge responses to reduce API costs
- [ ] Implement judge calibration (fine-tune on known good/bad examples)

---

## 📝 Version History

- **v1.0** (Initial): Basic multi-judge system with 3 judges
  - Accuracy, Groundedness, Tone evaluation
  - Agreement rate calculation
  - Conflict resolution logic
  - Position bias check
  - Detailed rubrics

---

## 👤 Author Notes

This system is designed to be:
- **Transparent**: Clear rubrics and reasoning
- **Robust**: Multiple judges prevent single-point failure
- **Extensible**: Easy to add more judges or modify rubrics
- **Production-Ready**: Error handling and fallbacks included

For questions or improvements, refer to the GRADING_RUBRIC.md for expert-level requirements.
