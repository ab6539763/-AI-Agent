"""智枢企业级智能体平台 Day 63：毕业设计端到端评估、Ragas 指标与性能/成本压测优化 (v1.0.0-day63)。"""

from zhishu_agent.capstone_eval import (
    CapstoneEvaluator,
    CaseScore,
    EvalCase,
    EvalReport,
    OptimizationAdvisor,
    OptimizationComparison,
    OptimizationRecommendation,
    PerfBenchmark,
    PricingConfig,
    build_sample_capstone_cases,
    compute_answer_relevancy,
    compute_citation_accuracy,
    compute_context_precision,
    compute_faithfulness,
    compute_percentile,
)

__all__ = [
    "CapstoneEvaluator",
    "CaseScore",
    "EvalCase",
    "EvalReport",
    "OptimizationAdvisor",
    "OptimizationComparison",
    "OptimizationRecommendation",
    "PerfBenchmark",
    "PricingConfig",
    "build_sample_capstone_cases",
    "compute_answer_relevancy",
    "compute_citation_accuracy",
    "compute_context_precision",
    "compute_faithfulness",
    "compute_percentile",
]
