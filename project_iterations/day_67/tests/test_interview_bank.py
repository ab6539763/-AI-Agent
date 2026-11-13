"""Day 67 单元测试：技术八股题库筛选、要点覆盖评分、空答处理、薄弱维度诊断与报告导出。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.interview_bank import (
    VALID_CATEGORIES,
    ExamSession,
    get_question_bank,
    grade_answer,
    list_questions,
)


def test_question_bank_completeness_and_filtering() -> None:
    """题库应至少包含 15 题并覆盖全部 5 大技术维度，且支持按维度与难度筛选。"""
    bank = get_question_bank()
    assert len(bank) >= 15

    categories_present = {q.category for q in bank}
    assert categories_present == set(VALID_CATEGORIES)

    for cat in VALID_CATEGORIES:
        cat_qs = list_questions(category=cat)
        assert len(cat_qs) >= 3
        assert all(q.category == cat for q in cat_qs)

    hard_qs = list_questions(difficulty="Hard")
    assert len(hard_qs) >= 3
    assert all(q.difficulty == "Hard" for q in hard_qs)

    with pytest.raises(ValueError):
        list_questions(category="InvalidCategory")  # type: ignore[arg-type]


def test_grade_answer_keyword_coverage_scoring() -> None:
    """高覆盖回答应得高分，部分命中应得中等分并准确列出缺失要点。"""
    tf_q = list_questions(category="Transformer")[0]  # TF-001

    strong_ans = (
        "点积 Q·K^T 的方差随 d_k 线性增大，过大会让 Softmax 进入梯度饱和区导致梯度消失，"
        "除以 sqrt(d_k) 后方差恢复为 1，从而稳定反向传播。"
    )
    strong_res = grade_answer(tf_q, strong_ans)
    assert strong_res.score >= 95.0
    assert strong_res.coverage_ratio == 1.0
    assert strong_res.missing_points == []
    assert not strong_res.is_empty

    partial_ans = "因为点积太大了会导致 softmax 饱和、梯度消失。"
    partial_res = grade_answer(tf_q, partial_ans)
    assert 30.0 <= partial_res.score < 70.0
    assert len(partial_res.matched_points) == 1
    assert len(partial_res.missing_points) == 2


def test_empty_answer_handling() -> None:
    """空字符串或纯空白回答应返回 0 分、is_empty=True 且全部要点标记为缺失。"""
    rag_q = list_questions(category="RAG")[0]
    for raw in ("", "   \n\t  "):
        res = grade_answer(rag_q, raw)
        assert res.score == 0.0
        assert res.coverage_ratio == 0.0
        assert res.is_empty is True
        assert res.matched_points == []
        assert len(res.missing_points) == len(rag_q.key_points)
        assert "未检测到有效作答" in res.feedback


def test_exam_session_weak_category_diagnosis_and_study_plan() -> None:
    """ExamSession 应能识别低于阈值的薄弱维度并生成对应优先级的复习计划。"""
    selected = [
        list_questions(category="Transformer")[0],
        list_questions(category="RAG")[0],
        list_questions(category="Agent")[0],
        list_questions(category="Python")[0],
        list_questions(category="Engineering")[0],
    ]
    session = ExamSession(questions=selected, candidate_name="李婷", session_id="TEST-001")

    # Transformer、RAG 给高分作答；Agent、Python 给空答/低分；Engineering 给满分作答
    session.submit_answer(
        selected[0].id,
        "方差随 d_k 线性增大，防止 Softmax 饱和梯度消失，缩放后方差为1稳定反向传播。",
    )
    session.submit_answer(
        selected[1].id,
        "Dense 向量对专有名词弱，BM25 擅长关键词精确匹配，RRF 基于排名倒数融合无需归一化。",
    )
    session.submit_answer(selected[2].id, "")  # 0 分 -> High priority
    session.submit_answer(selected[3].id, "会阻塞事件循环。")  # 部分命中 -> Medium/High
    session.submit_answer(
        selected[4].id,
        "隔离 System 与用户输入边界，网关层做 PII 脱敏护栏，工具执行坚持最小权限与 HITL 审批。",
    )

    report = session.finish_exam(weak_threshold=70.0)
    assert report.total_questions == 5
    assert report.answered_count == 4
    assert "Agent" in report.weak_categories
    assert "Python" in report.weak_categories
    assert "Transformer" not in report.weak_categories
    assert report.weak_categories[0] == "Agent"  # 0 分排在最前

    plan_cats = {item.category: item for item in report.study_plan}
    assert "Agent" in plan_cats
    assert plan_cats["Agent"].priority == "High"
    assert len(plan_cats["Agent"].focus_topics) >= 1


def test_exam_report_export_markdown_and_json() -> None:
    """ExamReport 应支持导出结构化字典、合法 JSON 与完整 Markdown 报告。"""
    qs = ExamSession.select_questions(n=5, seed=42)
    assert len(qs) == 5
    assert len({q.category for q in qs}) == 5

    session = ExamSession(questions=qs, candidate_name="张工", session_id="EXPORT-001")
    for q in qs:
        session.submit_answer(q.id, q.model_answer)

    report = session.finish_exam()
    assert report.average_score >= 85.0
    assert report.weak_categories == []

    md = report.to_markdown()
    assert "# 智枢模拟笔试诊断报告 (EXPORT-001)" in md
    assert "张工" in md
    assert "各维度得分" in md

    parsed = json.loads(report.to_json())
    assert parsed["session_id"] == "EXPORT-001"
    assert parsed["total_questions"] == 5
    assert len(parsed["results"]) == 5
