#!/usr/bin/env python3
"""
DEMO: Multi-Judge Consensus Engine
===================================
Demonstrating the LLMJudge with 3 specialized judges:
1. Accuracy Judge - Kiểm tra độ chính xác
2. Groundedness Judge - Kiểm tra hallucination
3. Tone/Safety Judge - Kiểm tra chuyên nghiệp & an toàn
"""

import asyncio
import json
from engine.llm_judge import LLMJudge


async def demo_basic_evaluation():
    """Demo cơ bản: evaluate một câu trả lời"""
    print("=" * 80)
    print("📊 DEMO 1: Basic Multi-Judge Evaluation")
    print("=" * 80)
    
    judge = LLMJudge(model="gpt-4o")
    
    question = "Cô Hồng có bao nhiêu con?"
    ground_truth = "Cô Hồng có 2 con: một con trai và một con gái, các con đều đã vào đại học."
    
    # Giả lập 3 câu trả lời khác nhau
    answers = [
        "Cô Hồng có 2 con, một trai một gái. Các con đã vào đại học.",  # Tốt
        "Cô Hồng có 3 con, nhưng tôi không chắc chắn.",  # Sai
        "Cô Hồng có con nhưng tôi không biết chính xác bao nhiêu.",  # Mơ hồ
    ]
    
    for idx, answer in enumerate(answers, 1):
        print(f"\n--- Câu trả lời #{idx} ---")
        print(f"Answer: {answer}\n")
        
        try:
            result = await judge.evaluate_multi_judge(question, answer, ground_truth)
            
            print(f"FINAL SCORE: {result['final_score']}/5.0")
            print(f"AGREEMENT RATE: {result['agreement_rate']}")
            print(f"INDIVIDUAL SCORES: {result['individual_scores']}")
            print(f"\nREASONING:\n{result['reasoning']}")
            
            if result.get('conflict_note'):
                print(f"\n⚠️ CONFLICT NOTE: {result['conflict_note']}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "-" * 80)


async def demo_position_bias():
    """Demo: Position Bias Detection"""
    print("\n" + "=" * 80)
    print("🔄 DEMO 2: Position Bias Detection")
    print("=" * 80)
    
    judge = LLMJudge(model="gpt-4o")
    
    question = "Hãy so sánh Python và Java"
    
    response_a = """
    Python là một ngôn ngữ lập trình có cú pháp đơn giản, dễ học, 
    và được sử dụng rộng rãi trong AI/ML. Tuy nhiên, nó chậm hơn Java 
    và không phù hợp cho các ứng dụng yêu cầu hiệu năng cao.
    """
    
    response_b = """
    Java là một ngôn ngữ mạnh mẽ với hiệu năng cao, thích hợp cho 
    các ứng dụng enterprise lớn. Tuy nhiên, cú pháp phức tạp hơn Python 
    và không được ưa chuộng trong lĩnh vực AI/ML.
    """
    
    print(f"Question: {question}\n")
    print(f"Response A (First): {response_a}\n")
    print(f"Response B (Second): {response_b}\n")
    
    try:
        bias_result = await judge.check_position_bias(response_a, response_b, question)
        
        print("Position Bias Check Results:")
        print(f"  Bias Detected: {bias_result.get('position_bias_detected')}")
        print(f"  First Evaluation (A,B): {bias_result.get('first_evaluation')}")
        print(f"  Second Evaluation Swapped (B,A): {bias_result.get('second_evaluation_swapped')}")
        print(f"  Explanation: {bias_result.get('explanation')}")
        
        if 'error' in bias_result:
            print(f"  ⚠️ Error: {bias_result['error']}")
    
    except Exception as e:
        print(f"❌ Error in position bias check: {e}")
    
    print("\n" + "=" * 80)


async def demo_conflict_resolution():
    """Demo: Conflict Resolution Logic"""
    print("\n" + "=" * 80)
    print("⚖️ DEMO 3: Conflict Resolution Logic")
    print("=" * 80)
    
    judge = LLMJudge(model="gpt-4o")
    
    # Scenario where judges might disagree
    question = "AI có thể thay thế con người không?"
    ground_truth = """
    AI có thể thay thế con người trong một số công việc cụ thể như xử lý dữ liệu, 
    phát hiện lỗi trong code, v.v. Tuy nhiên, AI vẫn thiếu sáng tạo, cảm xúc 
    và khả năng suy luận phức tạp của con người. Nó nên được xem là công cụ 
    hỗ trợ chứ không phải thay thế.
    """
    
    answer = """
    AI có thể làm nhiều việc mà con người làm, nhưng nó vẫn có hạn chế. 
    AI không có ý thức hay suy luận như con người.
    """
    
    print(f"Question: {question}")
    print(f"Ground Truth: {ground_truth}")
    print(f"Answer: {answer}\n")
    
    try:
        result = await judge.evaluate_multi_judge(question, answer, ground_truth)
        
        print("Conflict Resolution Analysis:")
        print(f"  Individual Scores: {result['individual_scores']}")
        print(f"  Agreement Rate: {result['agreement_rate']}")
        print(f"  Final Score: {result['final_score']}")
        print(f"  Conflict Note: {result['conflict_note']}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "=" * 80)


async def main():
    print("\n🎯 MULTI-JUDGE CONSENSUS ENGINE - DEMO\n")
    
    # Run all demos
    await demo_basic_evaluation()
    await demo_position_bias()
    await demo_conflict_resolution()
    
    print("\n✅ All demos completed!")
    print("\nNote: Thực tế khi chạy, bạn sẽ cần:")
    print("  1. Thiết lập OPENAI_API_KEY environment variable")
    print("  2. Đảm bảo có quyền truy cập vào gpt-4o model")
    print("  3. Dữ liệu sẽ được lưu trong reports/summary.json sau khi chạy main.py")


if __name__ == "__main__":
    asyncio.run(main())
