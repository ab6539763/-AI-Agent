"""Day 68 单元测试：AI 系统设计与项目深挖评估器。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from zhishu_agent import (
    ArchitectureProposal,
    estimate_cost,
    evaluate_system_design,
    get_scenario,
    list_scenarios,
)


def test_scenario_loading() -> None:
    """校验内置场景加载与异常处理。"""
    scenarios = list_scenarios()
    assert len(scenarios) >= 3
    ids = {s.scenario_id for s in scenarios}
    assert {"enterprise_kb_1m", "high_concurrency_cs", "multi_agent_fin_research"} <= ids

    kb = get_scenario("enterprise_kb_1m")
    assert kb.target_qps == 200
    assert kb.p99_latency_ms == 1200

    with pytest.raises(ValueError):
        get_scenario("non_existent_scenario")


def test_strong_vs_weak_proposal_scoring() -> None:
    """校验高可用架构方案得分显著高于简陋直连方案。"""
    weak = ArchitectureProposal(
        proposal_name="简陋直连方案",
        scenario_id="enterprise_kb_1m",
        components=["FastAPI", "单机向量库", "LLM API"],
        target_qps=40,
        expected_p99_ms=3000,
    )
    strong = ArchitectureProposal(
        proposal_name="智枢全栈高可用方案",
        scenario_id="enterprise_kb_1m",
        components=[
            "API Gateway 令牌桶限流",
            "Redis 语义缓存",
            "Milvus HNSW + BM25 混合检索 + Rerank",
            "大小模型 Router",
            "Langfuse + Prometheus 可观测",
        ],
        target_qps=260,
        expected_p99_ms=900,
        caching="Redis Semantic Cache",
        fallback="Circuit Breaker 熔断降级至轻量模型",
        guardrails="PII 脱敏 + Prompt 注入拦截",
        cost_control="大小模型路由 + Token 预算配额",
    )

    weak_review = evaluate_system_design(weak)
    strong_review = evaluate_system_design(strong)

    assert strong_review.overall_score >= 95
    assert strong_review.grade == "S"
    assert weak_review.overall_score < 40
    assert strong_review.overall_score - weak_review.overall_score >= 60


def test_missing_bottleneck_detection() -> None:
    """校验缺失关键架构瓶颈时能精确识别并给出改进建议。"""
    partial = ArchitectureProposal(
        proposal_name="缺少熔断与可观测的方案",
        scenario_id="high_concurrency_cs",
        components=["API Gateway 限流", "Milvus HNSW 向量索引", "Redis 语义缓存", "大小模型路由"],
        target_qps=1200,
        expected_p99_ms=700,
        caching="Redis Semantic Cache",
        guardrails="敏感词与越权拦截",
        cost_control="大小模型分级路由",
    )

    review = evaluate_system_design(partial)
    assert "circuit_breaker" in review.missing_bottlenecks
    assert "observability" in review.missing_bottlenecks
    assert "vector_index" not in review.missing_bottlenecks
    assert any("熔断" in rec for rec in review.risks_and_recommendations)
    assert any("可观测" in rec for rec in review.risks_and_recommendations)


def test_cost_estimation_with_cache_and_routing() -> None:
    """校验语义缓存与大小模型路由能显著降低月度推理成本并满足预算。"""
    scenario = get_scenario("high_concurrency_cs")
    no_opt = ArchitectureProposal(
        proposal_name="无成本优化方案",
        scenario_id="high_concurrency_cs",
        components=["FastAPI", "LLM API"],
        target_qps=1000,
        expected_p99_ms=800,
    )
    with_opt = ArchitectureProposal(
        proposal_name="缓存+路由优化方案",
        scenario_id="high_concurrency_cs",
        components=["Redis 语义缓存", "大小模型 Router"],
        target_qps=1000,
        expected_p99_ms=800,
        caching="Redis Semantic Cache",
        cost_control="大小模型路由 (7B + 旗舰)",
    )

    cost_no_opt = estimate_cost(scenario, no_opt)
    cost_with_opt = estimate_cost(scenario, with_opt)

    assert cost_no_opt.cache_hit_rate == 0.0
    assert cost_no_opt.small_model_ratio == 0.0
    assert cost_no_opt.within_budget is False

    assert cost_with_opt.cache_hit_rate >= 0.3
    assert cost_with_opt.small_model_ratio >= 0.6
    assert cost_with_opt.estimated_monthly_cost_cny < cost_no_opt.estimated_monthly_cost_cny
    assert cost_with_opt.within_budget is True


def test_mermaid_blueprint_generation() -> None:
    """校验生成的 Mermaid 架构蓝图语法完整且反映瓶颈覆盖状态。"""
    proposal = ArchitectureProposal(
        proposal_name="多 Agent 金融研报架构",
        scenario_id="multi_agent_fin_research",
        components=["API Gateway 限流", "Milvus HNSW", "Langfuse Trace"],
        target_qps=60,
        expected_p99_ms=6500,
        caching="Redis 语义缓存",
        fallback="超时熔断降级",
        guardrails="金融合规校验",
        cost_control="大小模型路由",
    )

    review = evaluate_system_design(proposal)
    bp = review.mermaid_blueprint
    assert bp.startswith("flowchart LR")
    assert "API Gateway" in bp
    assert "Semantic Cache" in bp
    assert "Circuit Breaker" in bp
    assert "Observability" in bp
