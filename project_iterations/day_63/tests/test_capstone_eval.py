"""Day 63 单元测试：Ragas 评估指标、延迟百分位、Token 成本核算、优化对比与 Markdown 报告生成。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.capstone_eval import (
    CapstoneEvaluator,
    EvalCase,
    OptimizationAdvisor,
    PricingConfig,
    build_sample_capstone_cases,
    compute_answer_relevancy,
    compute_citation_accuracy,
    compute_context_precision,
    compute_faithfulness,
    compute_percentile,
)


def test_ragas_metrics_scoring() -> None:
    """验证四大 Ragas 指标（忠实度、相关性、上下文精确率、引用准确率）及边界行为。"""
    contexts = [
        "星辰数科2025年Q3营业收入为18.6亿元，同比增长24.3%。",
        "公司食堂工作日提供三餐补贴。",
    ]
    relevant = ["星辰数科2025年Q3营业收入为18.6亿元，同比增长24.3%。"]

    faith = compute_faithfulness("2025年Q3营业收入为18.6亿元，同比增长24.3%。", contexts)
    assert faith >= 0.85

    ungrounded = compute_faithfulness("火星基地建造成本为999亿美元。", contexts)
    assert ungrounded < 0.25

    rel = compute_answer_relevancy(
        query="星辰数科2025年Q3营业收入是多少？",
        generated_answer="星辰数科2025年Q3营业收入为18.6亿元。",
        expected_answer="2025年Q3营业收入为18.6亿元。",
    )
    assert rel >= 0.75

    precision = compute_context_precision(contexts, relevant)
    assert precision == 1.0

    # 相关片段排在第二位时，precision@2 应低于首位命中的 1.0
    swapped = [contexts[1], contexts[0]]
    assert compute_context_precision(swapped, relevant) == 0.5

    assert compute_citation_accuracy(["doc1#p1", "doc2#p2"], ["doc1#p1", "doc2#p2"]) == 1.0
    assert compute_citation_accuracy(["doc1#p1"], ["doc1#p1", "doc2#p2"]) == pytest.approx(0.6667, abs=1e-4)
    assert compute_citation_accuracy([], []) == 1.0
    assert compute_citation_accuracy(["doc1#p1"], []) == 0.0


def test_latency_percentiles_and_benchmark() -> None:
    """验证 P50/P95 延迟百分位计算与压测套件汇总。"""
    assert compute_percentile([], 95.0) == 0.0
    assert compute_percentile([500.0], 95.0) == 500.0

    latencies = [100.0, 200.0, 300.0, 400.0, 1000.0]
    assert compute_percentile(latencies, 50.0) == 300.0
    assert compute_percentile(latencies, 95.0) == pytest.approx(880.0, abs=0.1)

    cases = build_sample_capstone_cases()
    report = CapstoneEvaluator().evaluate_suite(cases, profile_name="unit-test")
    assert report.total_cases == len(cases)
    assert report.benchmark.p50_ms <= report.benchmark.p95_ms
    assert report.passed_quality_gate is True


def test_token_cost_calculation_with_cache_and_tiers() -> None:
    """验证 Flagship / Lite 模型层级与 Prompt Caching 对单次及千次成本的精确计算。"""
    pricing = PricingConfig()
    # Flagship 无缓存: 2000 input * 0.02 + 500 output * 0.06 = 0.04 + 0.03 = 0.07 CNY
    cost_uncached = pricing.calculate_cost_cny(
        prompt_tokens=2000, completion_tokens=500, cached_tokens=0, model_tier="flagship"
    )
    assert cost_uncached == pytest.approx(0.07, abs=1e-6)

    # Flagship 1000 cached: (1000*0.02 + 1000*0.004 + 500*0.06) / 1000 = 0.054 CNY
    cost_cached = pricing.calculate_cost_cny(
        prompt_tokens=2000, completion_tokens=500, cached_tokens=1000, model_tier="flagship"
    )
    assert cost_cached == pytest.approx(0.054, abs=1e-6)
    assert cost_cached < cost_uncached

    # Lite 模型成本远低于 Flagship
    cost_lite = pricing.calculate_cost_cny(
        prompt_tokens=2000, completion_tokens=500, cached_tokens=0, model_tier="lite"
    )
    assert cost_lite == pytest.approx(0.007, abs=1e-6)
    assert cost_lite < cost_cached


def test_optimization_advisor_comparison_and_roi() -> None:
    """验证 Prompt Caching + Rerank Top-K + 模型路由联合优化后的降本增效幅度。"""
    cases = build_sample_capstone_cases()
    advisor = OptimizationAdvisor()
    comparison = advisor.compare(
        cases,
        enable_prompt_caching=True,
        rerank_top_k=2,
        enable_model_routing=True,
    )

    assert comparison.latency_p95_reduction_pct > 20.0
    assert comparison.cost_reduction_pct > 40.0
    assert comparison.token_reduction_pct > 10.0
    assert comparison.optimized.benchmark.cache_hit_rate >= 0.5
    assert comparison.optimized.overall_ragas_score >= comparison.baseline.overall_ragas_score
    assert comparison.monthly_savings_cny_at_100k_req > 0.0
    assert len(comparison.recommendations) == 3


def test_markdown_reports_and_empty_suite_guard() -> None:
    """验证 Markdown 评估报告、优化对比报告渲染与空用例集异常保护。"""
    evaluator = CapstoneEvaluator()
    with pytest.raises(ValueError, match="empty"):
        evaluator.evaluate_suite([])

    cases = build_sample_capstone_cases()
    comparison = OptimizationAdvisor(evaluator).compare(cases)

    eval_md = comparison.baseline.to_markdown()
    assert "Faithfulness" in eval_md
    assert "P95 延迟" in eval_md
    assert "PASS ✅" in eval_md

    comp_md = comparison.to_markdown()
    assert "Baseline vs Optimized" in comp_md
    assert "Prompt Caching" in comp_md
    assert "ROI 预估" in comp_md
