"""Day 58 单元测试：毕业项目 8 大赛道与开题技术方案评审器."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY58_DIR = Path(__file__).resolve().parents[1]
if str(DAY58_DIR) not in sys.path:
    sys.path.insert(0, str(DAY58_DIR))

from zhishu_agent import (  # noqa: E402
    CAPSTONE_TOPICS,
    TechnicalProposal,
    create_sample_proposal,
    get_capstone_topic,
    list_capstone_topics,
    review_proposal,
)


EXPECTED_TOPICS = [
    "法律咨询助手",
    "简历优化Agent",
    "电商智能客服",
    "论文阅读助手",
    "旅行规划Agent",
    "企业财报分析系统",
    "教育答疑系统",
    "医疗健康科普助手",
]


def test_eight_capstone_topics_present() -> None:
    assert len(CAPSTONE_TOPICS) == 8
    topics = list_capstone_topics()
    assert len(topics) == 8
    for name in EXPECTED_TOPICS:
        assert name in CAPSTONE_TOPICS
        topic = get_capstone_topic(name)
        assert topic is not None
        assert get_capstone_topic(topic.topic_id) == topic
        assert len(topic.core_scenarios) >= 2
        assert len(topic.recommended_tools) >= 2
        assert len(topic.key_guardrails) >= 2
        assert len(topic.evaluation_metrics) >= 2


@pytest.mark.parametrize("topic_name", EXPECTED_TOPICS)
def test_complete_proposal_approved_for_all_topics(topic_name: str) -> None:
    proposal = create_sample_proposal(topic_name)
    result = review_proposal(proposal)
    assert result.topic_recognized is True
    assert result.status == "APPROVED"
    assert result.overall_score == 100
    assert result.blocking_issues == []
    assert set(result.dimension_reviews.keys()) == {"RAG", "Agent", "Guardrails", "Deployment"}
    assert all(rev.passed for rev in result.dimension_reviews.values())


def test_incomplete_proposal_needs_revision() -> None:
    proposal = TechnicalProposal(
        project_title="电商客服一期",
        author="陈默",
        topic_name="电商智能客服",
        problem_statement="降低人工客服重复咨询压力",
        target_users=["电商买家"],
        knowledge_sources=["商品知识库"],
        chunking_strategy="Markdown 标题切分",
        embedding_model="bge-m3",
        agent_framework="LangGraph",
        tools=["order_status_query"],
        memory_strategy="Redis",
        # 故意缺少 Guardrails 和 Deployment
    )
    result = review_proposal(proposal)
    assert result.status == "NEEDS_REVISION"
    assert result.overall_score == 50
    assert result.dimension_reviews["RAG"].passed is True
    assert result.dimension_reviews["Agent"].passed is True
    assert result.dimension_reviews["Guardrails"].passed is False
    assert result.dimension_reviews["Deployment"].passed is False
    assert any("[Guardrails]" in item for item in result.blocking_issues)
    assert any("[Deployment]" in item for item in result.blocking_issues)


def test_empty_proposal_rejected() -> None:
    proposal = TechnicalProposal(topic_name="未知自定义赛道")
    result = review_proposal(proposal)
    assert result.topic_recognized is False
    assert result.status == "REJECTED"
    assert result.overall_score == 0
    assert len(result.blocking_issues) >= 4
    assert any("不在 8 大标准赛道中" in rec for rec in result.recommendations)


def test_single_guardrail_partial_credit_still_passes_with_suggestion() -> None:
    proposal = create_sample_proposal("医疗健康科普助手")
    proposal.guardrails = ["严禁下达临床诊断或开具处方"]
    result = review_proposal(proposal)
    assert result.dimension_reviews["Guardrails"].passed is True
    assert result.dimension_reviews["Guardrails"].score == 20
    assert result.overall_score == 95
    assert result.status == "APPROVED"
    assert any("至少配置 2 项安全护栏" in s for s in result.dimension_reviews["Guardrails"].suggestions)
