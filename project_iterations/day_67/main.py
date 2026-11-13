"""Day 67 平台启动入口：技术八股题库与模拟笔试自动评分演示 (v1.0.0-day67)。"""

from __future__ import annotations

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.interview_bank import (
    ExamSession,
    get_question_bank,
    list_questions,
)


def main() -> None:
    """运行 5 道跨维度模拟笔试并输出逐题得分与薄弱维度诊断报告。"""
    print("=" * 72)
    print("🎯 智枢企业级智能体平台 v1.0.0-day67 · 技术八股与模拟笔试系统")
    print("=" * 72)

    bank = get_question_bank()
    print(f"\n[1/3] 内置题库加载完成：共 {len(bank)} 道高频面试题，覆盖 5 大核心技术维度。")

    # 精选 5 大维度各 1 题组成模拟笔试卷
    exam_questions = [
        list_questions(category="Transformer")[0],  # TF-001
        list_questions(category="RAG")[0],          # RAG-001
        list_questions(category="Agent")[1],        # AGT-002
        list_questions(category="Python")[0],       # PY-001
        list_questions(category="Engineering")[0],  # ENG-001
    ]

    session = ExamSession(
        questions=exam_questions,
        candidate_name="陈默（模拟冲刺版）",
        session_id="EXAM-DAY67-DEMO",
    )

    # 模拟候选人不同熟练度的真实作答（包含高分回答、部分命中、空答/薄弱项）
    simulated_answers = {
        "TF-001": (
            "因为当 d_k 较大时，Q 和 K 点积的方差会随 d_k 线性增大，"
            "点积过大容易把 Softmax 推入梯度饱和区导致梯度消失。"
            "除以 sqrt(d_k) 可以把方差稳定拉回 1，保证反向传播稳定。"
        ),
        "RAG-001": (
            "Dense 向量擅长语义匹配但对专有名词不敏感，BM25 擅长关键词精确匹配。"
            "两者结合后用 RRF 按排名倒数融合，无需对两路分数做归一化。"
        ),
        "AGT-002": (
            "使用 Pydantic 和 JSON Schema 对工具参数进行严格校验，"
            "并设置 max_iterations 防止死循环。"
        ),
        "PY-001": (
            "在 async def 里用 requests 会阻塞事件循环，导致并发能力下降，"
            "可以换成 httpx 或使用 asyncio.to_thread。"
        ),
        "ENG-001": "",  # 故意留空，模拟薄弱项/未作答场景
    }

    print("\n[2/3] 开始逐题作答与自动评分（共 5 题）：")
    for idx, q in enumerate(session.questions, start=1):
        ans = simulated_answers[q.id]
        result = session.submit_answer(q.id, ans)
        status = "✅ 优秀" if result.score >= 85 else ("⚠️ 及格/待补全" if result.score >= 60 else "❌ 薄弱")
        print(f"\n  Q{idx}. [{q.category} | {q.difficulty}] {q.question}")
        print(f"      得分: {result.score:.1f}/100 ({status}) | 要点覆盖率: {result.coverage_ratio * 100:.0f}%")
        print(f"      命中要点: {', '.join(result.matched_points) if result.matched_points else '无'}")
        print(f"      缺失要点: {', '.join(result.missing_points) if result.missing_points else '无'}")
        print(f"      评语: {result.feedback}")

    report = session.finish_exam(weak_threshold=70.0)
    print("\n" + "=" * 72)
    print("[3/3] 模拟笔试综合诊断报告")
    print("=" * 72)
    print(f"候选人: {report.candidate_name} | 作答: {report.answered_count}/{report.total_questions}")
    print(f"综合均分: {report.average_score:.1f} / 100 | 综合评级: {report.grade_level}")
    print(f"各维度得分: {report.category_scores}")
    print(f"薄弱维度诊断 (< 70分): {report.weak_categories}")

    if report.study_plan:
        print("\n📌 针对性复习计划：")
        for plan in report.study_plan:
            print(f"  - [{plan.priority}] {plan.category} (均分 {plan.average_score:.1f}): {plan.action_plan}")


if __name__ == "__main__":
    main()
