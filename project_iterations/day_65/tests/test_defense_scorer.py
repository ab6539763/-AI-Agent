"""Day 65 单元测试：覆盖五维度加权评分、等级边界、评委问答匹配、权重校验与 Markdown 导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY65_DIR = Path(__file__).resolve().parents[1]
if str(DAY65_DIR) not in sys.path:
    sys.path.insert(0, str(DAY65_DIR))

from zhishu_agent.defense_scorer import (  # noqa: E402
    DefenseRubric,
    JudgeQuestionBank,
    RubricDimension,
    assign_grade,
    evaluate_defense,
    export_markdown_scorecard,
)


def test_weighted_rubric_scoring_single_and_multi_judge() -> None:
    """验证五维度加权计算精确性（20% / 30% / 20% / 15% / 15%）及多评委均值聚合。"""
    rubric = DefenseRubric()
    # 90*0.2 + 95*0.3 + 85*0.2 + 80*0.15 + 90*0.15 = 18 + 28.5 + 17 + 12 + 13.5 = 89.0
    single_scores = {
        "business_value": 90.0,
        "architecture_depth": 95.0,
        "engineering_quality": 85.0,
        "demo_fluency": 80.0,
        "qa_performance": 90.0,
    }
    res_single = evaluate_defense(single_scores, rubric=rubric)
    assert res_single.total_score == pytest.approx(89.0, abs=1e-2)
    assert res_single.grade == "A"
    assert res_single.dimension_contributions["architecture_depth"] == pytest.approx(28.5, abs=1e-2)

    # 多评委聚合：评委1总分 89.0，评委2全95总分 95.0 -> 均值 92.0 (S级)
    multi = [
        {"judge_name": "评委A", "judge_role": "CTO", "scores": single_scores},
        {
            "judge_name": "评委B",
            "judge_role": "安全总监",
            "scores": {k: 95.0 for k in single_scores},
        },
    ]
    res_multi = evaluate_defense(multi, rubric=rubric)
    assert len(res_multi.judge_scorecards) == 2
    assert res_multi.total_score == pytest.approx(92.0, abs=1e-2)
    assert res_multi.grade == "S"


def test_grade_boundaries() -> None:
    """验证 S / A / B / C 四档分数边界判定准确无误。"""
    assert assign_grade(100.0) == "S"
    assert assign_grade(90.0) == "S"
    assert assign_grade(89.99) == "A"
    assert assign_grade(80.0) == "A"
    assert assign_grade(79.99) == "B"
    assert assign_grade(70.0) == "B"
    assert assign_grade(69.99) == "C"
    assert assign_grade(0.0) == "C"

    # 端到端通过 evaluate_defense 验证边界
    for boundary_score, expected_grade in [(90.0, "S"), (80.0, "A"), (70.0, "B"), (69.5, "C")]:
        res = evaluate_defense(
            {
                "business_value": boundary_score,
                "architecture_depth": boundary_score,
                "engineering_quality": boundary_score,
                "demo_fluency": boundary_score,
                "qa_performance": boundary_score,
            }
        )
        assert res.total_score == pytest.approx(boundary_score, abs=1e-2)
        assert res.grade == expected_grade


def test_judge_question_bank_matching_and_answer_scoring() -> None:
    """验证评委题库覆盖 5 大企业硬核主题、关键词匹配与回答采分点评估。"""
    bank = JudgeQuestionBank()
    categories = {q.category for q in bank.list_questions()}
    assert {"幻觉治理", "高并发成本", "权限隔离", "HITL超时", "微调vs RAG选型"} <= categories

    # 匹配测试：权限隔离与提示词注入
    matches = bank.match_question("多租户向量库怎么做权限隔离和防Prompt注入？", top_k=2)
    assert len(matches) >= 1
    top_q, top_score = matches[0]
    assert top_q.category == "权限隔离"
    assert top_score > 0

    # 回答评分测试：高覆盖回答 vs 空回答
    good_ans = (
        "我们采用 BM25+向量+RRF 混合检索和重排，强制 Citation 原句溯源，"
        "低置信度触发拒答(Abstention)，并接入 Faithfulness 自动化评测门禁。"
    )
    eval_good = bank.score_answer("JQ-01", good_ans)
    assert eval_good["coverage_ratio"] >= 0.75
    assert eval_good["suggested_score"] >= 85.0

    eval_empty = bank.score_answer("JQ-01", "")
    assert eval_empty["suggested_score"] == 0.0


def test_invalid_weight_and_score_validation() -> None:
    """验证非法权重（总和不为1、负数权重）及越界/缺失分数的校验异常。"""
    bad_dims_sum = [
        RubricDimension(key="a", name="维度A", weight=0.5, description="d1"),
        RubricDimension(key="b", name="维度B", weight=0.3, description="d2"),
    ]
    with pytest.raises(ValueError, match="权重之和必须等于 1.0"):
        DefenseRubric(dimensions=bad_dims_sum)

    with pytest.raises(ValueError, match="权重必须在"):
        RubricDimension(key="neg", name="负权重", weight=-0.1, description="bad")

    rubric = DefenseRubric()
    with pytest.raises(ValueError, match="必须在 \\[0, 100\\] 范围内"):
        rubric.compute_weighted_score(
            {
                "business_value": 105.0,
                "architecture_depth": 90.0,
                "engineering_quality": 90.0,
                "demo_fluency": 90.0,
                "qa_performance": 90.0,
            }
        )

    with pytest.raises(ValueError, match="缺少以下必填评分维度"):
        rubric.compute_weighted_score({"business_value": 90.0})


def test_markdown_scorecard_export() -> None:
    """验证 Markdown 评分卡包含总分、等级、五维度表格、优势亮点与改进计划。"""
    res = evaluate_defense(
        scores=[
            {
                "judge_name": "周明远",
                "judge_role": "外部 CTO",
                "scores": {
                    "business_value": 92.0,
                    "architecture_depth": 94.0,
                    "engineering_quality": 88.0,
                    "demo_fluency": 78.0,
                    "qa_performance": 86.0,
                },
                "comment": "架构深度突出，演示节奏可再紧凑。",
            }
        ],
        project_name="智枢企业级智能体平台",
        team_name="星辰数科 Capstone 小组",
    )
    md = export_markdown_scorecard(res)
    assert "# 毕业答辩评审评分卡 — 智枢企业级智能体平台" in md
    assert f"**{res.grade} 级**" in md
    assert "技术架构与RAG/Agent深度" in md
    assert "周明远" in md
    assert "核心优势亮点" in md
    assert "后续改进计划" in md
    assert res.to_markdown() == md
