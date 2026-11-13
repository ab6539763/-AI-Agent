"""Day 69 单元测试：覆盖轮次流转、技术面与HR面权重差异、录用阈值、空回答处理与7天清单。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.mock_interview import (
    DEFAULT_ROUNDS,
    RECOMMENDATION_HIRE,
    RECOMMENDATION_NO_HIRE,
    RECOMMENDATION_OFFER,
    RECOMMENDATION_STRONG_HIRE,
    DimensionScores,
    MockInterviewEngine,
    TurnEvaluation,
    generate_interview_feedback,
)


def _make_turn(
    round_id: int,
    round_name: str,
    category: str,
    weighted_score: float,
    clarity: float = 80.0,
    tech: float = 80.0,
    star: float = 80.0,
    honesty: float = 80.0,
    is_empty: bool = False,
) -> TurnEvaluation:
    return TurnEvaluation(
        round_id=round_id,
        round_name=round_name,
        category=category,
        interviewer="Tech Lead 张工" if category == "technical" else "HRBP / PM 林晓",
        prompt="测试问题",
        response="" if is_empty else "测试回答",
        scores=DimensionScores(
            clarity=clarity,
            technical_depth=tech,
            star_structure=star,
            honesty_ownership=honesty,
        ),
        weighted_score=weighted_score,
        is_empty=is_empty,
    )


def test_round_progression_and_completion() -> None:
    """测试四轮结构化面试严格按顺序推进并在结束后阻止继续提交。"""
    engine = MockInterviewEngine(candidate_name="陈默", target_role="AI Agent Engineer")
    first = engine.start_interview()
    assert first.name == "自我介绍"
    assert engine.progress == (0, 4)
    assert not engine.is_finished

    expected_names = ["自我介绍", "项目深挖", "场景手撕/架构", "行为面试 HR 面"]
    for idx, expected_name in enumerate(expected_names):
        current = engine.current_round()
        assert current is not None
        assert current.name == expected_name
        engine.submit_response(
            "首先，我主导设计了 RAG 与 HITL 状态机，通过 BM25+RRF 将召回率从 70% 提升至 92%，"
            "最终通过 pytest 100% 回归验证，我也复盘了并发边界。"
        )
        assert engine.progress == (idx + 1, 4)

    assert engine.is_finished
    assert engine.current_round() is None
    with pytest.raises(RuntimeError):
        engine.submit_response("多余的回答")


def test_technical_vs_hr_scoring_weights() -> None:
    """测试技术面侧重技术深度、HR面侧重诚实担当与STAR结构的评分差异。"""
    engine = MockInterviewEngine()
    engine.start_interview()

    # 跳过第1轮，测第2轮（技术面：项目深挖）
    engine.submit_response("我主导了智能体平台开发，首先明确目标，最终提升 20%。")
    tech_heavy_answer = (
        "针对 RAG 漏召回，我设计了 BM25 + FAISS + RRF 融合排序与 Cross-Encoder Rerank，"
        "结合 FastAPI SSE 与 SQLite 状态机实现 HITL 幂等审批与 PII 脱敏，"
        "Top-5 召回率提升至 92%，P95 延迟 160ms，QPS 达 120。"
    )
    tech_eval = engine.submit_response(tech_heavy_answer)
    assert tech_eval.category == "technical"
    assert tech_eval.scores.technical_depth >= 80.0

    # 第3轮
    engine.submit_response("采用熔断降级与幂等状态机，时间复杂度 O(1)，保障并发安全。")

    # 第4轮（HR 面）：同样包含诚实反思与 STAR，但几乎不含硬核技术词
    hr_reflective_answer = (
        "当时线上发布前出现分歧，我的职责是守住质量底线。我主动承担了沟通不够前置的责任，"
        "通过复盘和坦诚对齐业务目标，最终推动团队在 2 天内补齐回归用例，避免了线上故障。"
    )
    hr_eval = engine.submit_response(hr_reflective_answer)
    assert hr_eval.category == "hr"
    assert hr_eval.scores.honesty_ownership >= 75.0
    assert hr_eval.weighted_score > 65.0

    report = engine.generate_feedback()
    assert report.technical_score != report.hr_score


def test_hire_decision_thresholds() -> None:
    """测试 Strong-Hire / Offer / Hire / No-Hire 四档录用决策阈值。"""
    strong_turns = [
        _make_turn(1, "自我介绍", "technical", 88.0),
        _make_turn(2, "项目深挖", "technical", 90.0),
        _make_turn(3, "场景手撕/架构", "technical", 86.0),
        _make_turn(4, "行为面试 HR 面", "hr", 85.0),
    ]
    assert generate_interview_feedback(strong_turns).recommendation == RECOMMENDATION_STRONG_HIRE

    offer_turns = [
        _make_turn(1, "自我介绍", "technical", 78.0),
        _make_turn(2, "项目深挖", "technical", 76.0),
        _make_turn(3, "场景手撕/架构", "technical", 75.0),
        _make_turn(4, "行为面试 HR 面", "hr", 74.0),
    ]
    assert generate_interview_feedback(offer_turns).recommendation == RECOMMENDATION_OFFER

    hire_turns = [
        _make_turn(1, "自我介绍", "technical", 64.0),
        _make_turn(2, "项目深挖", "technical", 62.0),
        _make_turn(3, "场景手撕/架构", "technical", 60.0),
        _make_turn(4, "行为面试 HR 面", "hr", 60.0),
    ]
    assert generate_interview_feedback(hire_turns).recommendation == RECOMMENDATION_HIRE

    no_hire_turns = [
        _make_turn(1, "自我介绍", "technical", 45.0),
        _make_turn(2, "项目深挖", "technical", 50.0),
        _make_turn(3, "场景手撕/架构", "technical", 48.0),
        _make_turn(4, "行为面试 HR 面", "hr", 52.0),
    ]
    assert generate_interview_feedback(no_hire_turns).recommendation == RECOMMENDATION_NO_HIRE


def test_empty_response_handling() -> None:
    """测试空字符串或纯空白回答应被安全拦截并记为 0 分，且多项空答直接判定 No-Hire。"""
    engine = MockInterviewEngine()
    engine.start_interview()

    t1 = engine.submit_response("   \n\t  ")
    assert t1.is_empty is True
    assert t1.weighted_score == 0.0
    assert t1.scores == DimensionScores(0.0, 0.0, 0.0, 0.0)
    assert len(t1.improvements) >= 1

    t2 = engine.submit_response("")
    assert t2.is_empty is True

    engine.submit_response("使用状态机与熔断降级保障并发幂等，P95 低于 200ms。")
    engine.submit_response("我主动复盘了线上失误并推动团队改进流程。")

    report = engine.generate_feedback()
    assert report.recommendation == RECOMMENDATION_NO_HIRE


def test_seven_day_checklist_generation_and_markdown() -> None:
    """测试 7 天改进清单完整性、针对性（聚焦最弱维度）及 Markdown 报告渲染。"""
    turns = [
        _make_turn(1, "自我介绍", "technical", 72.0, clarity=85.0, tech=45.0, star=78.0, honesty=80.0),
        _make_turn(2, "项目深挖", "technical", 68.0, clarity=80.0, tech=40.0, star=75.0, honesty=78.0),
        _make_turn(3, "场景手撕/架构", "technical", 70.0, clarity=82.0, tech=42.0, star=76.0, honesty=79.0),
        _make_turn(4, "行为面试 HR 面", "hr", 78.0, clarity=84.0, tech=50.0, star=80.0, honesty=85.0),
    ]
    report = generate_interview_feedback(turns, candidate_name="陈默", target_role="RAG Engineer")
    assert len(report.seven_day_checklist) == 7
    assert [item.day for item in report.seven_day_checklist] == [1, 2, 3, 4, 5, 6, 7]
    # Day 1 应精准命中最低分维度（技术深度与量化指标）
    assert "技术深度与量化指标" in report.seven_day_checklist[0].focus_area

    md = report.format_markdown()
    assert "陈默" in md
    assert "RAG Engineer" in md
    assert report.recommendation in md
    assert "Day 7" in md
