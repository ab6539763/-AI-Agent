"""AI 系统设计与项目深挖评估模拟器（Day 68）。

围绕企业级 AI 架构高频面试题（100万文档知识库、高并发智能客服、多 Agent 金融研报助手），
对候选人提交的 ArchitectureProposal 进行瓶颈覆盖度、SLA 达标率、成本估算与
Mermaid 架构蓝图生成。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SystemDesignScenario:
    """AI 系统设计面试场景定义。"""

    scenario_id: str
    title: str
    description: str
    target_qps: int
    p99_latency_ms: int
    data_scale: str
    daily_requests: int
    monthly_budget_cny: float
    required_bottlenecks: list[str]
    key_follow_up_questions: list[str]


@dataclass
class ArchitectureProposal:
    """候选人提交的系统架构设计方案。"""

    proposal_name: str
    scenario_id: str
    components: list[str]
    target_qps: int
    expected_p99_ms: int
    caching: str = ""
    fallback: str = ""
    guardrails: str = ""
    cost_control: str = ""
    observability: str = ""
    rate_limiting: str = ""


@dataclass(frozen=True)
class BottleneckCheck:
    """单个架构瓶颈维度的检查结果。"""

    key: str
    label: str
    covered: bool
    weight: int
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class CostEstimate:
    """基于缓存命中率与大小模型路由的月度成本估算。"""

    daily_requests: int
    cache_hit_rate: float
    effective_llm_requests: int
    small_model_ratio: float
    estimated_daily_cost_cny: float
    estimated_monthly_cost_cny: float
    within_budget: bool
    budget_cny: float


@dataclass
class SystemDesignReview:
    """系统设计评估报告与 Mermaid 架构蓝图。"""

    scenario_id: str
    scenario_title: str
    proposal_name: str
    overall_score: int
    grade: str
    sla_qps_met: bool
    sla_latency_met: bool
    bottleneck_checks: list[BottleneckCheck] = field(default_factory=list)
    missing_bottlenecks: list[str] = field(default_factory=list)
    cost_estimate: CostEstimate | None = None
    strengths: list[str] = field(default_factory=list)
    risks_and_recommendations: list[str] = field(default_factory=list)
    mermaid_blueprint: str = ""


BOTTLENECK_SPECS: dict[str, dict[str, object]] = {
    "vector_index": {
        "label": "向量索引与混合检索优化",
        "weight": 15,
        "keywords": [
            "hnsw",
            "ivf",
            "milvus",
            "qdrant",
            "pgvector",
            "faiss",
            "bm25",
            "hybrid",
            "rerank",
            "向量索引",
            "混合检索",
            "分片",
            "shard",
        ],
        "recommendation": "补充百万级向量分片索引（如 Milvus/Qdrant HNSW + 标量过滤）与 BM25 混合检索 + Cross-Encoder 重排，避免全表扫描导致 P99 飙升。",
    },
    "semantic_cache": {
        "label": "语义缓存与高频命中",
        "weight": 15,
        "keywords": [
            "semantic cache",
            "语义缓存",
            "redis",
            "cache",
            "缓存",
            "embedding cache",
            "kv cache",
        ],
        "recommendation": "引入 Redis 向量语义缓存（余弦相似度 >= 0.92 命中），拦截 25%~40% 高频重复提问，显著降低首字延迟与 Token 账单。",
    },
    "rate_limiting": {
        "label": "网关限流与并发控制",
        "weight": 15,
        "keywords": [
            "rate limit",
            "限流",
            "令牌桶",
            "token bucket",
            "漏桶",
            "semaphore",
            "并发控制",
            "gateway",
            "网关",
            "背压",
            "队列",
        ],
        "recommendation": "在 API 网关层按租户/API Key 配置令牌桶限流（RPM/TPM 双维度）与异步任务队列背压，防止突发流量打垮上游推理池。",
    },
    "circuit_breaker": {
        "label": "熔断降级与高可用兜底",
        "weight": 15,
        "keywords": [
            "circuit breaker",
            "熔断",
            "降级",
            "fallback",
            "兜底",
            "重试",
            "retry",
            "多活",
            "主备",
            "timeout",
            "超时",
        ],
        "recommendation": "配置大模型供应商熔断器（失败率 > 20% 自动切换备选模型或本地轻量模型）与超时兜底话术，保障核心链路可用性 >= 99.9%。",
    },
    "observability": {
        "label": "全链路可观测性与 Trace",
        "weight": 15,
        "keywords": [
            "observability",
            "可观测",
            "langfuse",
            "prometheus",
            "grafana",
            "opentelemetry",
            "otel",
            "trace",
            "链路追踪",
            "监控",
            "告警",
            "日志",
        ],
        "recommendation": "接入 OpenTelemetry / Langfuse 全链路 Trace 与 Prometheus 指标大盘，实时监控 TTFT、P99、检索召回率与异常错误码。",
    },
    "cost_routing": {
        "label": "大小模型成本路由与预算控制",
        "weight": 15,
        "keywords": [
            "router",
            "路由",
            "大小模型",
            "cost",
            "成本",
            "预算",
            "配额",
            "quota",
            "7b",
            "mini",
            "flash",
            "蒸馏",
            "分级",
        ],
        "recommendation": "构建意图复杂度路由器（简单问答走轻量/7B 模型，复杂推理才路由至旗舰模型），并按租户设置每日 Token 预算配额。",
    },
}


SCENARIOS: dict[str, SystemDesignScenario] = {
    "enterprise_kb_1m": SystemDesignScenario(
        scenario_id="enterprise_kb_1m",
        title="100万文档企业知识库 RAG 平台",
        description=(
            "服务全集团 3 万名员工的企业级知识库问答系统，包含制度文档、技术 Wiki、PDF 合同与工单沉淀，"
            "要求支持权限隔离（RBAC）、高召回检索与低幻觉引用溯源。"
        ),
        target_qps=200,
        p99_latency_ms=1200,
        data_scale="100万文档（约 2,000 万 Chunks，向量维度 1024）",
        daily_requests=500_000,
        monthly_budget_cny=35_000.0,
        required_bottlenecks=[
            "vector_index",
            "semantic_cache",
            "rate_limiting",
            "circuit_breaker",
            "observability",
            "cost_routing",
        ],
        key_follow_up_questions=[
            "2000 万向量下如何做多租户/部门权限过滤，才能不破坏 HNSW 图连通性导致召回暴跌？",
            "文档每日增量更新 1 万篇，如何保证索引近实时生效且不阻塞在线检索？",
            "Cross-Encoder Rerank 耗时 180ms，如何在 P99 < 1.2s 内平衡精度与延迟？",
        ],
    ),
    "high_concurrency_cs": SystemDesignScenario(
        scenario_id="high_concurrency_cs",
        title="高并发电商/金融智能客服系统",
        description=(
            "面向大促高峰期的在线智能客服 Agent，需支持订单查询、退换货工具调用与情绪安抚，"
            "峰值 QPS 达 1000，要求极端场景下不雪崩、不越权。"
        ),
        target_qps=1000,
        p99_latency_ms=800,
        data_scale="50万 FAQ + 实时订单/物流 API",
        daily_requests=2_000_000,
        monthly_budget_cny=85_000.0,
        required_bottlenecks=[
            "vector_index",
            "semantic_cache",
            "rate_limiting",
            "circuit_breaker",
            "observability",
            "cost_routing",
        ],
        key_follow_up_questions=[
            "大促 QPS 瞬间翻 3 倍到 3000 时，网关限流与降级策略如何逐级触发？",
            "高频重复问题（如“什么时候发货”）如何通过语义缓存与规则引擎零大模型成本拦截？",
            "如何防止恶意用户在客服对话中通过 Prompt 注入诱导 Agent 调用退款工具？",
        ],
    ),
    "multi_agent_fin_research": SystemDesignScenario(
        scenario_id="multi_agent_fin_research",
        title="多 Agent 金融研报分析助手",
        description=(
            "由 Planner、财报检索 Agent、量化计算 Agent 与合规审校 Agent 协作生成深度研报，"
            "单次任务涉及多轮 Tool Call 与长上下文推理，对数据准确性与合规审计要求极高。"
        ),
        target_qps=50,
        p99_latency_ms=8000,
        data_scale="30万份上市公司年报/研报 + 实时行情数据库",
        daily_requests=80_000,
        monthly_budget_cny=45_000.0,
        required_bottlenecks=[
            "vector_index",
            "semantic_cache",
            "rate_limiting",
            "circuit_breaker",
            "observability",
            "cost_routing",
        ],
        key_follow_up_questions=[
            "多 Agent 协作链路长达 6~10 步，某一步 Tool Call 失败或死循环如何做状态回滚与熔断？",
            "金融数据容错率为 0，如何设计计算沙箱与 Citation 强校验避免“数字幻觉”？",
            "单次研报生成消耗 30k+ Tokens，如何通过中间结果缓存与大小模型分工控制月度成本？",
        ],
    ),
}


def list_scenarios() -> list[SystemDesignScenario]:
    """返回所有内置系统设计面试场景。"""
    return list(SCENARIOS.values())


def get_scenario(scenario_id: str) -> SystemDesignScenario:
    """根据 scenario_id 获取场景，不存在时抛出 ValueError。"""
    if scenario_id not in SCENARIOS:
        valid = ", ".join(SCENARIOS.keys())
        raise ValueError(f"未知的场景 ID: '{scenario_id}'，可选值: {valid}")
    return SCENARIOS[scenario_id]


def _collect_proposal_corpus(proposal: ArchitectureProposal) -> str:
    """汇总架构方案的所有技术描述字段用于关键词匹配与证据提取。"""
    parts = [
        " ".join(proposal.components),
        proposal.caching,
        proposal.fallback,
        proposal.guardrails,
        proposal.cost_control,
        proposal.observability,
        proposal.rate_limiting,
    ]
    return " | ".join(p.strip() for p in parts if p and p.strip())


def estimate_cost(
    scenario: SystemDesignScenario,
    proposal: ArchitectureProposal,
) -> CostEstimate:
    """估算月度推理成本（基于语义缓存命中率与大小模型路由比例）。"""
    corpus = _collect_proposal_corpus(proposal).lower()

    # 1. 估算语义缓存命中率
    if any(k in corpus for k in ["semantic cache", "语义缓存", "向量缓存"]):
        cache_hit_rate = 0.35
    elif any(k in corpus for k in ["redis", "cache", "缓存"]):
        cache_hit_rate = 0.15
    else:
        cache_hit_rate = 0.0

    # 2. 估算轻量模型分流比例
    if any(k in corpus for k in ["大小模型", "router", "路由", "7b", "mini", "flash", "分级"]):
        small_model_ratio = 0.65
    else:
        small_model_ratio = 0.0

    effective_llm_requests = int(round(scenario.daily_requests * (1.0 - cache_hit_rate)))

    # 单次请求均价（元）：旗舰模型约 0.0045 元/次，轻量模型约 0.0005 元/次
    # 多 Agent 场景单次请求平均触发 3.5 次 LLM 调用
    agent_multiplier = 3.5 if scenario.scenario_id == "multi_agent_fin_research" else 1.0
    blended_unit_cost = (
        small_model_ratio * 0.0005 + (1.0 - small_model_ratio) * 0.0045
    ) * agent_multiplier

    daily_cost = round(effective_llm_requests * blended_unit_cost, 2)
    monthly_cost = round(daily_cost * 30.0, 2)

    return CostEstimate(
        daily_requests=scenario.daily_requests,
        cache_hit_rate=cache_hit_rate,
        effective_llm_requests=effective_llm_requests,
        small_model_ratio=small_model_ratio,
        estimated_daily_cost_cny=daily_cost,
        estimated_monthly_cost_cny=monthly_cost,
        within_budget=monthly_cost <= scenario.monthly_budget_cny,
        budget_cny=scenario.monthly_budget_cny,
    )


def generate_mermaid_blueprint(
    scenario: SystemDesignScenario,
    proposal: ArchitectureProposal,
    checks: list[BottleneckCheck],
) -> str:
    """根据评估结果生成 Mermaid flowchart 架构蓝图。"""
    check_map = {c.key: c.covered for c in checks}

    gw_label = "API Gateway (限流/鉴权)" if check_map.get("rate_limiting") else "API Gateway (⚠️缺失限流)"
    cache_label = (
        "Redis Semantic Cache (命中直出)"
        if check_map.get("semantic_cache")
        else "无语义缓存 (⚠️直击模型)"
    )
    router_label = (
        "Model Router (大小模型分级)"
        if check_map.get("cost_routing")
        else "单一旗舰模型 (⚠️无成本路由)"
    )
    vec_label = (
        "Hybrid Vector DB (HNSW + BM25 + Rerank)"
        if check_map.get("vector_index")
        else "基础向量检索 (⚠️缺分片/混合检索)"
    )
    cb_label = (
        "Circuit Breaker & Fallback (熔断降级)"
        if check_map.get("circuit_breaker")
        else "无熔断兜底 (⚠️单点雪崩风险)"
    )
    obs_label = (
        "Observability (OTel / Langfuse / Prometheus)"
        if check_map.get("observability")
        else "基础日志 (⚠️缺全链路 Trace)"
    )
    guard_label = (
        f"Guardrails ({proposal.guardrails[:22]}...)"
        if len(proposal.guardrails) > 22
        else (f"Guardrails ({proposal.guardrails})" if proposal.guardrails else "Guardrails (⚠️未配置)")
    )

    lines = [
        "flowchart LR",
        f'    U["用户请求 ({scenario.target_qps} QPS / P99<={scenario.p99_latency_ms}ms)"] --> GW["{gw_label}"]',
        f'    GW --> GUARD["{guard_label}"]',
        f'    GUARD --> CACHE["{cache_label}"]',
        '    CACHE -- "Cache Hit" --> RESP["流式响应 (SSE)"]',
        f'    CACHE -- "Cache Miss" --> RET["{vec_label}"]',
        f'    RET --> RTR["{router_label}"]',
        f'    RTR --> CB["{cb_label}"]',
        '    CB --> RESP',
        f'    GW -. "Metrics & Trace" .-> OBS["{obs_label}"]',
        '    RTR -. "Token & Latency" .-> OBS',
    ]
    return "\n".join(lines)


def evaluate_system_design(
    proposal: ArchitectureProposal,
    scenario: SystemDesignScenario | None = None,
) -> SystemDesignReview:
    """对系统设计方案进行全方位瓶颈检查、SLA 校验、成本估算与打分。"""
    resolved_scenario = scenario or get_scenario(proposal.scenario_id)
    corpus = _collect_proposal_corpus(proposal).lower()

    bottleneck_checks: list[BottleneckCheck] = []
    missing_bottlenecks: list[str] = []
    total_score = 0

    for key in resolved_scenario.required_bottlenecks:
        spec = BOTTLENECK_SPECS[key]
        keywords: list[str] = spec["keywords"]  # type: ignore[assignment]
        weight: int = spec["weight"]  # type: ignore[assignment]
        label: str = spec["label"]  # type: ignore[assignment]
        recommendation: str = spec["recommendation"]  # type: ignore[assignment]

        matched = [kw for kw in keywords if kw in corpus]
        covered = len(matched) > 0
        if covered:
            total_score += weight
            evidence = f"命中关键设计词: {', '.join(matched[:4])}"
        else:
            missing_bottlenecks.append(key)
            evidence = "方案中未检测到相关组件或策略描述"

        bottleneck_checks.append(
            BottleneckCheck(
                key=key,
                label=label,
                covered=covered,
                weight=weight,
                evidence=evidence,
                recommendation=recommendation,
            )
        )

    # SLA 与安全护栏共占 10 分（QPS 4 分、P99 3 分、Guardrails 3 分）
    sla_qps_met = proposal.target_qps >= resolved_scenario.target_qps
    sla_latency_met = proposal.expected_p99_ms <= resolved_scenario.p99_latency_ms
    has_guardrails = bool(proposal.guardrails and proposal.guardrails.strip() and proposal.guardrails.strip() != "无")

    if sla_qps_met:
        total_score += 4
    if sla_latency_met:
        total_score += 3
    if has_guardrails:
        total_score += 3

    total_score = min(100, max(0, total_score))

    if total_score >= 90:
        grade = "S"
    elif total_score >= 75:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    elif total_score >= 40:
        grade = "C"
    else:
        grade = "D"

    cost_est = estimate_cost(resolved_scenario, proposal)

    strengths: list[str] = []
    for chk in bottleneck_checks:
        if chk.covered:
            strengths.append(f"[已覆盖] {chk.label}（{chk.evidence}）")
    if sla_qps_met and sla_latency_met:
        strengths.append(
            f"[SLA 达标] 吞吐目标 {proposal.target_qps} QPS >= {resolved_scenario.target_qps} QPS，"
            f"P99 {proposal.expected_p99_ms}ms <= {resolved_scenario.p99_latency_ms}ms。"
        )
    if has_guardrails:
        strengths.append(f"[安全护栏] 已配置：{proposal.guardrails}")

    risks: list[str] = []
    for chk in bottleneck_checks:
        if not chk.covered:
            risks.append(f"[缺失 {chk.label}] {chk.recommendation}")
    if not sla_qps_met:
        risks.append(
            f"[QPS 不达标] 方案设计容量 {proposal.target_qps} QPS 低于场景要求 {resolved_scenario.target_qps} QPS，需补充水平扩容与异步解耦。"
        )
    if not sla_latency_met:
        risks.append(
            f"[延迟超标] 预期 P99 {proposal.expected_p99_ms}ms 高于 SLA 上限 {resolved_scenario.p99_latency_ms}ms，需优化首字延迟(TTFT)与检索剪枝。"
        )
    if not has_guardrails:
        risks.append("[安全护栏缺失] 未配置 PII 脱敏、Prompt 注入检测或输出格式校验，存在合规与越权风险。")
    if not cost_est.within_budget:
        risks.append(
            f"[预算超支预警] 预估月度推理成本 ¥{cost_est.estimated_monthly_cost_cny:,.2f} "
            f"超出预算 ¥{cost_est.budget_cny:,.2f}，建议提高语义缓存阈值覆盖并引入大小模型路由。"
        )

    blueprint = generate_mermaid_blueprint(resolved_scenario, proposal, bottleneck_checks)

    return SystemDesignReview(
        scenario_id=resolved_scenario.scenario_id,
        scenario_title=resolved_scenario.title,
        proposal_name=proposal.proposal_name,
        overall_score=total_score,
        grade=grade,
        sla_qps_met=sla_qps_met,
        sla_latency_met=sla_latency_met,
        bottleneck_checks=bottleneck_checks,
        missing_bottlenecks=missing_bottlenecks,
        cost_estimate=cost_est,
        strengths=strengths,
        risks_and_recommendations=risks,
        mermaid_blueprint=blueprint,
    )
