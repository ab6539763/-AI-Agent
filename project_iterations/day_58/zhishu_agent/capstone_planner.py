"""智枢企业级智能体平台 Day 58 核心模块：毕业项目开题规划与技术方案评审器 (v1.0.0-day58)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CapstoneTopic(BaseModel):
    """毕业项目 8 大行业赛道定义."""

    topic_id: str
    name: str
    domain: str
    core_scenarios: list[str]
    recommended_rag: str
    recommended_tools: list[str]
    key_guardrails: list[str]
    evaluation_metrics: list[str]


CAPSTONE_TOPICS: dict[str, CapstoneTopic] = {
    "法律咨询助手": CapstoneTopic(
        topic_id="legal_assistant",
        name="法律咨询助手",
        domain="法律合规",
        core_scenarios=["法条精准检索与引用", "合同风险条款审查", "劳动/商事纠纷初步咨询"],
        recommended_rag="法条结构化切分 + BM25/向量混合检索 + Reranker 强制溯源",
        recommended_tools=["statute_search", "contract_clause_diff", "case_law_lookup"],
        key_guardrails=["禁止伪造法条与虚构判例", "必须附带非正式法律意见免责声明", "PII 脱敏"],
        evaluation_metrics=["法条引用准确率", "RAGAS Faithfulness >= 0.90", "拒答合规率"],
    ),
    "简历优化Agent": CapstoneTopic(
        topic_id="resume_agent",
        name="简历优化Agent",
        domain="人力资源与求职",
        core_scenarios=["JD 与简历匹配度诊断", "STAR 法则经历改写", "模拟技术面试追问"],
        recommended_rag="岗位胜任力模型库 + 高分简历范式库向量检索",
        recommended_tools=["pdf_resume_parser", "jd_keyword_extractor", "star_rewriter"],
        key_guardrails=["禁止虚构候选人工作经历", "候选人隐私信息(电话/邮箱/住址)脱敏"],
        evaluation_metrics=["JD 关键词覆盖提升率", "STAR 结构完整度", "事实忠实度"],
    ),
    "电商智能客服": CapstoneTopic(
        topic_id="ecommerce_cs",
        name="电商智能客服",
        domain="新零售与电商",
        core_scenarios=["售前商品参数导购", "物流轨迹查询", "退换货售后工单流转"],
        recommended_rag="商品 SKU 知识库 + 平台售后规则库混合检索",
        recommended_tools=["order_status_query", "refund_eligibility_check", "ticket_escalate"],
        key_guardrails=["严禁越权承诺赔付金额", "高风险情绪工单自动转人工", "订单隐私保护"],
        evaluation_metrics=["一次解决率(FCR)", "工具调用准确率", "P95 响应延迟 < 2s"],
    ),
    "论文阅读助手": CapstoneTopic(
        topic_id="paper_reader",
        name="论文阅读助手",
        domain="科研与学术",
        core_scenarios=["PDF 公式/图表多模态解析", "跨论文方法对比矩阵", "相关工作综述生成"],
        recommended_rag="按章节(Abstract/Method/Exp)分层父子索引 + 引用图谱检索",
        recommended_tools=["arxiv_fetcher", "pdf_layout_parser", "bibtex_formatter"],
        key_guardrails=["严格区分原文结论与模型推测", "强制标注页码/章节出处"],
        evaluation_metrics=["Context Recall@5", "跨文档对比准确率", "引用幻觉率 < 2%"],
    ),
    "旅行规划Agent": CapstoneTopic(
        topic_id="travel_planner",
        name="旅行规划Agent",
        domain="文旅与出行",
        core_scenarios=["多日行程动态编排", "预算与交通约束优化", "实时天气与闭馆避坑"],
        recommended_rag="城市攻略库 + 景点开放时间与交通接驳知识库",
        recommended_tools=["weather_forecast", "poi_route_planner", "budget_calculator"],
        key_guardrails=["实时票务/价格以官方查询工具为准", "行程时间冲突硬校验"],
        evaluation_metrics=["约束满足率(预算/时间)", "工具编排成功率", "用户采纳率"],
    ),
    "企业财报分析系统": CapstoneTopic(
        topic_id="financial_report",
        name="企业财报分析系统",
        domain="金融与投研",
        core_scenarios=["资产负债/现金流指标抽取", "同业横向财务对比", "经营风险预警摘要"],
        recommended_rag="财报表格 Markdown/JSON 结构化解析 + 指标口径词典检索",
        recommended_tools=["financial_ratio_calc", "sec_filing_parser", "chart_data_exporter"],
        key_guardrails=["数值计算必须交由 Python/计算器工具执行", "附带非投资建议声明"],
        evaluation_metrics=["财务指标抽取 F1", "数值计算零误差率", "归因可解释性"],
    ),
    "教育答疑系统": CapstoneTopic(
        topic_id="edu_tutor",
        name="教育答疑系统",
        domain="智慧教育",
        core_scenarios=["苏格拉底式启发引导", "错题知识点诊断", "个性化巩固练习推荐"],
        recommended_rag="教材知识点图谱 + 历年真题与解析库检索",
        recommended_tools=["knowledge_graph_lookup", "step_verifier", "quiz_generator"],
        key_guardrails=["禁止直接给出作业/考试完整答案(启发式引导)", "未成年人内容安全过滤"],
        evaluation_metrics=["启发引导合规率", "解题步骤正确率", "知识点定位准确率"],
    ),
    "医疗健康科普助手": CapstoneTopic(
        topic_id="medical_science",
        name="医疗健康科普助手",
        domain="大健康科普",
        core_scenarios=["常见症状科普解释", "体检报告指标通俗解读", "就医科室分诊建议"],
        recommended_rag="权威医学指南(卫健委/临床路径)高可信知识库 + 严格溯源",
        recommended_tools=["lab_indicator_lookup", "department_triage", "emergency_red_flag_check"],
        key_guardrails=["严禁下达临床诊断或开具处方", "急重症红旗症状立即提示就医", "医疗免责声明"],
        evaluation_metrics=["医学指南忠实度", "危险症状识别召回率 100%", "合规拒答率"],
    ),
}


class TechnicalProposal(BaseModel):
    """毕业项目开题 PRD 与技术架构提案模型."""

    project_title: str = ""
    author: str = ""
    topic_name: str = ""
    problem_statement: str = ""
    target_users: list[str] = Field(default_factory=list)

    # 1. RAG 架构设计
    knowledge_sources: list[str] = Field(default_factory=list)
    chunking_strategy: str = ""
    embedding_model: str = ""

    # 2. Agent 编排设计
    agent_framework: str = ""
    tools: list[str] = Field(default_factory=list)
    memory_strategy: str = ""

    # 3. Guardrails 与评测体系
    guardrails: list[str] = Field(default_factory=list)
    eval_metrics: list[str] = Field(default_factory=list)

    # 4. Deployment 与成本预算
    model_serving: str = ""
    deployment_stack: list[str] = Field(default_factory=list)
    budget_limit_cny: float = 0.0


class DimensionReview(BaseModel):
    """单个技术维度的评审结果."""

    dimension: str
    score: int
    max_score: int = 25
    passed: bool
    missing_items: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ProposalReviewResult(BaseModel):
    """技术方案综合评审报告."""

    project_title: str
    topic_name: str
    topic_recognized: bool
    overall_score: int
    status: Literal["APPROVED", "NEEDS_REVISION", "REJECTED"]
    dimension_reviews: dict[str, DimensionReview]
    blocking_issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    summary: str


def list_capstone_topics() -> list[CapstoneTopic]:
    """返回全部 8 个毕业项目行业赛道."""
    return list(CAPSTONE_TOPICS.values())


def get_capstone_topic(identifier: str) -> CapstoneTopic | None:
    """按中文名称或 topic_id 查找行业赛道."""
    if identifier in CAPSTONE_TOPICS:
        return CAPSTONE_TOPICS[identifier]
    for topic in CAPSTONE_TOPICS.values():
        if topic.topic_id == identifier:
            return topic
    return None


def _clean_items(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


def review_proposal(proposal: TechnicalProposal) -> ProposalReviewResult:
    """对毕业项目技术提案进行 RAG / Agent / Guardrails / Deployment 四维完整性评审."""
    topic = get_capstone_topic(proposal.topic_name.strip())
    topic_recognized = topic is not None

    blocking_issues: list[str] = []
    recommendations: list[str] = []

    if not proposal.project_title.strip():
        blocking_issues.append("缺少项目名称（project_title）")
    if not proposal.problem_statement.strip():
        blocking_issues.append("缺少业务痛点与目标描述（problem_statement）")
    if not _clean_items(proposal.target_users):
        recommendations.append("建议明确目标用户画像（target_users），便于细化交互与权限设计。")

    if not topic_recognized:
        recommendations.append(
            f"选题 '{proposal.topic_name or '未填写'}' 不在 8 大标准赛道中，建议对齐标准赛道或补充行业基线评测集。"
        )

    # 1. RAG 维度评审 (25 分)
    rag_missing: list[str] = []
    rag_suggestions: list[str] = []
    rag_score = 0

    if _clean_items(proposal.knowledge_sources):
        rag_score += 9
    else:
        rag_missing.append("knowledge_sources（知识库数据源）")

    if proposal.chunking_strategy.strip():
        rag_score += 8
    else:
        rag_missing.append("chunking_strategy（切分与检索策略）")

    if proposal.embedding_model.strip():
        rag_score += 8
    else:
        rag_missing.append("embedding_model（Embedding / Reranker 模型选型）")

    if rag_missing and topic is not None:
        rag_suggestions.append(f"参考推荐架构：{topic.recommended_rag}")

    rag_review = DimensionReview(
        dimension="RAG",
        score=rag_score,
        passed=len(rag_missing) == 0,
        missing_items=rag_missing,
        suggestions=rag_suggestions,
    )

    # 2. Agent 维度评审 (25 分)
    agent_missing: list[str] = []
    agent_suggestions: list[str] = []
    agent_score = 0

    if proposal.agent_framework.strip():
        agent_score += 9
    else:
        agent_missing.append("agent_framework（智能体编排框架，如 LangGraph）")

    if _clean_items(proposal.tools):
        agent_score += 8
    else:
        agent_missing.append("tools（外部工具/Function Calling 清单）")

    if proposal.memory_strategy.strip():
        agent_score += 8
    else:
        agent_missing.append("memory_strategy（长短期记忆与状态持久化策略）")

    if agent_missing and topic is not None:
        agent_suggestions.append(f"建议接入核心工具：{', '.join(topic.recommended_tools)}")

    agent_review = DimensionReview(
        dimension="Agent",
        score=agent_score,
        passed=len(agent_missing) == 0,
        missing_items=agent_missing,
        suggestions=agent_suggestions,
    )

    # 3. Guardrails 与评测维度评审 (25 分)
    guard_missing: list[str] = []
    guard_suggestions: list[str] = []
    guard_score = 0

    cleaned_guardrails = _clean_items(proposal.guardrails)
    if len(cleaned_guardrails) >= 2:
        guard_score += 13
    elif len(cleaned_guardrails) == 1:
        guard_score += 8
        guard_suggestions.append("建议至少配置 2 项安全护栏（如输入/输出内容审核 + PII 脱敏或行业免责声明）。")
    else:
        guard_missing.append("guardrails（安全护栏与合规策略）")

    if _clean_items(proposal.eval_metrics):
        guard_score += 12
    else:
        guard_missing.append("eval_metrics（RAGAS / 业务准确率 / 延迟评测指标）")

    if guard_missing and topic is not None:
        guard_suggestions.append(f"行业必备护栏：{'; '.join(topic.key_guardrails)}")

    guard_review = DimensionReview(
        dimension="Guardrails",
        score=guard_score,
        passed=len(guard_missing) == 0,
        missing_items=guard_missing,
        suggestions=guard_suggestions,
    )

    # 4. Deployment 与成本维度评审 (25 分)
    deploy_missing: list[str] = []
    deploy_suggestions: list[str] = []
    deploy_score = 0

    if proposal.model_serving.strip():
        deploy_score += 9
    else:
        deploy_missing.append("model_serving（模型推理方案，如 vLLM / 量化模型 / API 网关）")

    if _clean_items(proposal.deployment_stack):
        deploy_score += 8
    else:
        deploy_missing.append("deployment_stack（容器化与可观测性组件，如 Docker Compose / FastAPI）")

    if proposal.budget_limit_cny > 0:
        deploy_score += 8
    else:
        deploy_missing.append("budget_limit_cny（租户日成本预算与熔断阈值需 > 0）")

    if deploy_missing:
        deploy_suggestions.append("建议复用 Stage 5 的 vLLM + Docker Compose + ComplianceGateway 生产基线。")

    deploy_review = DimensionReview(
        dimension="Deployment",
        score=deploy_score,
        passed=len(deploy_missing) == 0,
        missing_items=deploy_missing,
        suggestions=deploy_suggestions,
    )

    dimension_reviews = {
        "RAG": rag_review,
        "Agent": agent_review,
        "Guardrails": guard_review,
        "Deployment": deploy_review,
    }

    for dim_name, rev in dimension_reviews.items():
        if not rev.passed:
            blocking_issues.append(f"[{dim_name}] 缺少: {', '.join(rev.missing_items)}")

    overall_score = sum(rev.score for rev in dimension_reviews.values())
    all_dims_passed = all(rev.passed for rev in dimension_reviews.values())

    if all_dims_passed and overall_score >= 80 and proposal.project_title.strip() and proposal.problem_statement.strip():
        status: Literal["APPROVED", "NEEDS_REVISION", "REJECTED"] = "APPROVED"
        summary = f"提案《{proposal.project_title}》四维架构完整（总分 {overall_score}/100），准予开题进入 Day 59 开发阶段。"
    elif overall_score >= 50:
        status = "NEEDS_REVISION"
        summary = f"提案《{proposal.project_title or '未命名'}》总分 {overall_score}/100，需补齐阻塞项后复审。"
    else:
        status = "REJECTED"
        summary = f"提案《{proposal.project_title or '未命名'}》总分 {overall_score}/100，核心架构要素严重缺失，暂不通过开题。"

    return ProposalReviewResult(
        project_title=proposal.project_title or "未命名项目",
        topic_name=proposal.topic_name or "未指定赛道",
        topic_recognized=topic_recognized,
        overall_score=overall_score,
        status=status,
        dimension_reviews=dimension_reviews,
        blocking_issues=blocking_issues,
        recommendations=recommendations,
        summary=summary,
    )


def create_sample_proposal(topic_name: str, author: str = "陈默") -> TechnicalProposal:
    """根据标准赛道快速生成一份完整的示例技术提案."""
    topic = get_capstone_topic(topic_name)
    if topic is None:
        raise ValueError(f"未知的毕业项目赛道: {topic_name}")
    return TechnicalProposal(
        project_title=f"智枢·{topic.name}系统",
        author=author,
        topic_name=topic.name,
        problem_statement=f"面向{topic.domain}领域，解决{'、'.join(topic.core_scenarios)}中的高幻觉与低效率痛点。",
        target_users=[f"{topic.domain}从业人员", "企业终端业务用户"],
        knowledge_sources=[f"{topic.domain}权威语料库", "企业内部 FAQ 与业务规则库"],
        chunking_strategy=topic.recommended_rag,
        embedding_model="BAAI/bge-m3 + BAAI/bge-reranker-v2-m3",
        agent_framework="LangGraph Stateful Multi-Agent",
        tools=list(topic.recommended_tools),
        memory_strategy="Redis 短期会话记忆 + PostgreSQL/Checkpointer 状态持久化",
        guardrails=list(topic.key_guardrails) + ["ComplianceGateway 输入输出安全审核"],
        eval_metrics=list(topic.evaluation_metrics),
        model_serving="vLLM + Qwen2.5-7B-Instruct-AWQ",
        deployment_stack=["FastAPI", "Docker Compose", "Qdrant", "Redis", "Prometheus"],
        budget_limit_cny=50.0,
    )
