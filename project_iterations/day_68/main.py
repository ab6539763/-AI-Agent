"""Day 68 入口：评估企业级 AI 系统设计方案并输出评分报告与 Mermaid 架构蓝图。"""

from __future__ import annotations

from zhishu_agent import (
    ArchitectureProposal,
    evaluate_system_design,
    get_scenario,
    list_scenarios,
)


def _print_review(title: str, proposal: ArchitectureProposal) -> None:
    review = evaluate_system_design(proposal)
    print("=" * 72)
    print(f"【{title}】{review.proposal_name}")
    print(f"场景：{review.scenario_title} ({review.scenario_id})")
    print(
        f"综合评分：{review.overall_score}/100 (等级 {review.grade}) | "
        f"QPS达标={review.sla_qps_met} | P99达标={review.sla_latency_met}"
    )
    if review.cost_estimate:
        c = review.cost_estimate
        print(
            f"成本估算：缓存命中率={c.cache_hit_rate:.0%} | 轻量模型占比={c.small_model_ratio:.0%} | "
            f"月度预估=¥{c.estimated_monthly_cost_cny:,.2f} (预算=¥{c.budget_cny:,.2f}, 达标={c.within_budget})"
        )
    print("\n[优势与已覆盖瓶颈]")
    for item in review.strengths:
        print(f"  + {item}")
    print("\n[风险与改进建议]")
    if not review.risks_and_recommendations:
        print("  (无明显瓶颈缺失，可直接进入压测上线阶段)")
    else:
        for item in review.risks_and_recommendations:
            print(f"  - {item}")
    print("\n[自动生成的 Mermaid 架构蓝图]")
    print("```mermaid")
    print(review.mermaid_blueprint)
    print("```")


def main() -> None:
    print("智枢企业级智能体平台 Day 68 — AI 系统设计评估器")
    print(f"已加载面试场景数：{len(list_scenarios())}")
    for sc in list_scenarios():
        print(f"  - {sc.scenario_id}: {sc.title} (QPS={sc.target_qps}, P99<={sc.p99_latency_ms}ms)")

    kb_scenario = get_scenario("enterprise_kb_1m")

    weak_proposal = ArchitectureProposal(
        proposal_name="初级直连方案（无缓存/无熔断/无路由）",
        scenario_id=kb_scenario.scenario_id,
        components=["FastAPI Server", "单机 FAISS", "GPT-4o API"],
        target_qps=50,
        expected_p99_ms=2600,
        caching="无",
        fallback="无",
        guardrails="",
        cost_control="无",
    )

    strong_proposal = ArchitectureProposal(
        proposal_name="智枢高可用 RAG 生产方案 v2.0",
        scenario_id=kb_scenario.scenario_id,
        components=[
            "API Gateway (Kong 令牌桶限流)",
            "Redis Semantic Cache",
            "Milvus HNSW 分片 + BM25 混合检索 + Cross-Encoder Rerank",
            "大小模型智能 Router (Qwen-7B + 旗舰模型)",
            "Langfuse + OpenTelemetry + Prometheus 可观测大盘",
        ],
        target_qps=250,
        expected_p99_ms=950,
        caching="Redis 向量语义缓存 (cosine >= 0.92)",
        fallback="Circuit Breaker 熔断降级至本地 7B 模型与缓存摘要",
        guardrails="PII 脱敏 + Prompt 注入检测 + Citation 强校验",
        cost_control="大小模型路由 (65% 简单问答走 7B) + 租户每日 Token 配额",
    )

    _print_review("反面案例", weak_proposal)
    _print_review("标杆案例", strong_proposal)


if __name__ == "__main__":
    main()
