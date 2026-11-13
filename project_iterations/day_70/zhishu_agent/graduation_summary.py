"""Day 70 结业模块：70天课程全景回顾、前沿趋势追踪、结业证书与 30/60/90 天职业发展路线图。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class StageMilestone:
    """70 天课程与智枢平台演进的阶段里程碑。"""

    stage_number: int
    stage_code: str
    title: str
    day_start: int
    day_end: int
    version_tag: str
    core_topics: tuple[str, ...]
    platform_deliverable: str
    key_metrics: str

    @property
    def day_count(self) -> int:
        return self.day_end - self.day_start + 1

    @property
    def day_range_label(self) -> str:
        return f"Day {self.day_start:02d}-{self.day_end:02d}"


ZHISHU_STAGE_MILESTONES: tuple[StageMilestone, ...] = (
    StageMilestone(
        stage_number=1,
        stage_code="stage_01_python_foundation",
        title="第一阶段：Python 工程底座与异步并发架构",
        day_start=1,
        day_end=14,
        version_tag="v0.1.0",
        core_topics=("类型注解与 Pydantic v2", "asyncio 异步并发", "装饰器与上下文管理", "pytest 自动化测试", "CLI 与日志规范"),
        platform_deliverable="智枢平台基础工程骨架、配置中心与异步任务调度器",
        key_metrics="核心工具函数单元测试覆盖率 >= 90%，零外部依赖可独立运行",
    ),
    StageMilestone(
        stage_number=2,
        stage_code="stage_02_llm_and_web",
        title="第二阶段：大模型 API 工程与 FastAPI 全栈服务",
        day_start=15,
        day_end=24,
        version_tag="v0.2.0",
        core_topics=("Prompt 工程与结构化输出", "Function Calling", "FastAPI + SSE 流式网关", "SQLite/ORM 持久化", "Token 计量与限流"),
        platform_deliverable="智枢流式对话网关与结构化工具调用服务",
        key_metrics="SSE 首字延迟 < 200ms，Schema 校验解析成功率 100%",
    ),
    StageMilestone(
        stage_number=3,
        stage_code="stage_03_langchain_and_rag",
        title="第三阶段：LangChain 编排与企业级混合 RAG 引擎",
        day_start=25,
        day_end=38,
        version_tag="v0.3.0",
        core_topics=("文档切分与向量索引", "BM25 + Dense 混合检索", "RRF 倒数秩融合", "Cross-Encoder Rerank", "RAGAS 量化评测"),
        platform_deliverable="智枢企业财报与知识库混合检索问答引擎（带引用溯源）",
        key_metrics="Top-5 召回率由 71% 提升至 92%，P95 检索延迟 <= 165ms",
    ),
    StageMilestone(
        stage_number=4,
        stage_code="stage_04_agent_development",
        title="第四阶段：多智能体协作、MCP 协议与 HITL 生产安全",
        day_start=39,
        day_end=50,
        version_tag="v0.4.0",
        core_topics=("ReAct 与 Plan-and-Execute", "LangGraph 状态机与长短期记忆", "Multi-Agent 协同路由", "HITL 人机协同审批", "PII 脱敏与审计日志"),
        platform_deliverable="智枢多智能体协同中枢与高风险操作 HITL 审批闭环",
        key_metrics="高风险动作 100% 强制人工复核，重复审批幂等拦截率 100%",
    ),
    StageMilestone(
        stage_number=5,
        stage_code="stage_05_finetuning_and_deployment",
        title="第五阶段：模型微调、量化评测与云原生部署",
        day_start=51,
        day_end=57,
        version_tag="v0.5.0",
        core_topics=("LoRA / QLoRA 领域微调", "合成数据与偏好对齐", "vLLM 高吞吐推理", "Docker / K8s 容器化部署", "Prometheus + Grafana 可观测性"),
        platform_deliverable="智枢推理加速与生产级可观测部署方案",
        key_metrics="推理吞吐提升 3.2x，全链路 Trace 与 SLA 告警覆盖核心接口",
    ),
    StageMilestone(
        stage_number=6,
        stage_code="stage_06_capstone_and_career",
        title="第六阶段：全栈综合实战交付与 AI 工程师求职冲刺",
        day_start=58,
        day_end=70,
        version_tag="v1.0.0",
        core_topics=("Capstone 端到端集成", "压测与故障演练", "STAR 简历与 GitHub 作品集", "系统设计 & 算法手撕面试", "前沿趋势与 90 天成长规划"),
        platform_deliverable="智枢企业级智能体平台 v1.0.0 正式版与完整求职工程作品集",
        key_metrics="70 天累计 70 个迭代版本，全链路自动化验证 100% 通过",
    ),
)


def validate_curriculum_span(milestones: Iterable[StageMilestone] = ZHISHU_STAGE_MILESTONES) -> dict[str, object]:
    """校验阶段里程碑是否完整覆盖 Day 01 到 Day 70（无断档、无重叠）。"""
    ordered = sorted(milestones, key=lambda m: m.stage_number)
    if len(ordered) != 6:
        raise ValueError(f"期望 6 个阶段里程碑，实际为 {len(ordered)}")

    expected_start = 1
    total_days = 0
    for idx, stage in enumerate(ordered, start=1):
        if stage.stage_number != idx:
            raise ValueError(f"阶段编号不连续：期望 {idx}，实际 {stage.stage_number}")
        if stage.day_start != expected_start:
            raise ValueError(
                f"阶段 {stage.stage_number} 起始天数不连续：期望 Day {expected_start}，实际 Day {stage.day_start}"
            )
        if stage.day_end < stage.day_start:
            raise ValueError(f"阶段 {stage.stage_number} 结束天数早于开始天数")
        total_days += stage.day_count
        expected_start = stage.day_end + 1

    if expected_start - 1 != 70 or total_days != 70:
        raise ValueError(f"课程总跨度必须为 70 天，当前结束于 Day {expected_start - 1}，总计 {total_days} 天")

    return {
        "total_stages": len(ordered),
        "total_days": total_days,
        "start_day": ordered[0].day_start,
        "end_day": ordered[-1].day_end,
        "versions": [s.version_tag for s in ordered],
        "valid": True,
    }


def render_evolution_summary(milestones: Iterable[StageMilestone] = ZHISHU_STAGE_MILESTONES) -> str:
    """生成智枢平台 70 天演进全景 Markdown 摘要。"""
    ordered = sorted(milestones, key=lambda m: m.stage_number)
    span = validate_curriculum_span(ordered)
    lines = [
        "# 星辰数科 · 智枢企业级智能体平台 (ZhiShu-Agent) 70天演进全景",
        "",
        f"- 覆盖周期：Day {span['start_day']:02d} ~ Day {span['end_day']:02d}（共 {span['total_days']} 天 / {span['total_stages']} 大阶段）",
        f"- 版本主线：{' -> '.join(span['versions'])}",
        "",
        "| 阶段 | 天数跨度 | 天数 | 版本标签 | 核心交付物 | 关键量化指标 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in ordered:
        lines.append(
            f"| {s.title} | {s.day_range_label} | {s.day_count}天 | `{s.version_tag}` | "
            f"{s.platform_deliverable} | {s.key_metrics} |"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class FrontierTrend:
    """2025-2026 AI Agent 前沿技术趋势条目。"""

    trend_id: str
    name: str
    category: str
    maturity: str
    year_window: str
    summary: str
    key_technologies: tuple[str, ...]
    impact_on_zhishu: str
    learning_actions: tuple[str, ...]


DEFAULT_FRONTIER_TRENDS: tuple[FrontierTrend, ...] = (
    FrontierTrend(
        trend_id="reasoning_models",
        name="推理增强模型 (Reasoning Models / o1-R1)",
        category="reasoning",
        maturity="production",
        year_window="2025-2026",
        summary="Test-time Compute 缩放与长思维链（CoT）强化学习，使复杂规划、代码修复与多步财务推理准确率大幅跃升。",
        key_technologies=("o1 / o3", "DeepSeek-R1", "Test-time Compute", "Process Reward Model"),
        impact_on_zhishu="在智枢 Planner 与复杂合规审计链路中引入慢思考路由，简单意图走快模型降本，复杂决策走推理模型提准。",
        learning_actions=("掌握快慢思考分层路由策略", "设计推理预算（Token Budget）与超时熔断机制"),
    ),
    FrontierTrend(
        trend_id="mcp_agent_protocols",
        name="MCP 与智能体互操作协议 (MCP & Agent Protocols)",
        category="protocol",
        maturity="production",
        year_window="2025-2026",
        summary="Model Context Protocol (MCP) 与 A2A (Agent-to-Agent) 协议推动工具连接与跨框架智能体协作标准化。",
        key_technologies=("MCP (Model Context Protocol)", "A2A Protocol", "JSON-RPC 2.0", "Capability Discovery"),
        impact_on_zhishu="将智枢内部工具封装为标准 MCP Server，实现跨 IDE、桌面端与企业内部系统的即插即用。",
        learning_actions=("用 Python SDK 实现带鉴权的 MCP Server", "对比 Function Calling 与 MCP/A2A 的适用边界"),
    ),
    FrontierTrend(
        trend_id="multimodal_agents",
        name="多模态与 GUI 操纵智能体 (Multimodal & Computer-Use Agents)",
        category="multimodal",
        maturity="emerging",
        year_window="2025-2026",
        summary="原生视觉语言模型（VLM）结合屏幕理解与浏览器/桌面 DOM 操作，使 Agent 能直接处理复杂 PDF 图表与跨系统 RPA 任务。",
        key_technologies=("Native VLM", "Computer Use", "Browser-Use", "Document Layout Parsing"),
        impact_on_zhishu="升级智枢研报解析器，支持扫描件、财报折线图与无 API 老旧 ERP 系统的安全自动化操作。",
        learning_actions=("构建图表+文本混合多模态 RAG 原型", "为 GUI 动作加入高危操作二次确认（HITL）"),
    ),
    FrontierTrend(
        trend_id="voice_realtime_agents",
        name="实时语音与全双工交互智能体 (Voice & Realtime Agents)",
        category="voice",
        maturity="emerging",
        year_window="2025-2026",
        summary="端到端语音大模型与 WebRTC 低延迟流式传输结合，支持自然打断（Barge-in）、情绪感知与毫秒级语音客服。",
        key_technologies=("WebRTC", "Realtime API", "VAD 语音活动检测", "End-to-End Speech LLM"),
        impact_on_zhishu="扩展智枢客服与车载/电话外呼场景，将端到端语音响应延迟压降至 300-500ms 区间。",
        learning_actions=("理解 ASR->LLM->TTS 级联与端到端语音架构差异", "实现支持打断恢复的流式会话状态机"),
    ),
    FrontierTrend(
        trend_id="edge_on_device_ai",
        name="端侧与边缘智能体 (Edge & On-device AI)",
        category="edge",
        maturity="experimental",
        year_window="2025-2026",
        summary="3B-8B 高效小模型配合 4-bit 量化（GGUF/MLX/ONNX）在 PC、手机与私有边缘网关本地运行，满足离线与强隐私要求。",
        key_technologies=("Qwen2.5/3 Small", "GGUF / llama.cpp", "MLX / ONNX Runtime", "Cloud-Edge Hybrid Routing"),
        impact_on_zhishu="为涉密金融/政务客户提供“端侧脱敏+云端深度推理”混合部署形态，降低 60% 云端 Token 成本。",
        learning_actions=("在本地量化部署 7B 以下模型并测试吞吐", "设计端云协同路由与隐私脱敏网关"),
    ),
)


class TrendTracker:
    """前沿 AI Agent 趋势追踪与检索器。"""

    def __init__(self, trends: Optional[Iterable[FrontierTrend]] = None) -> None:
        self._trends: List[FrontierTrend] = list(trends or DEFAULT_FRONTIER_TRENDS)

    def list_trends(self) -> List[FrontierTrend]:
        return list(self._trends)

    def filter_by_category(self, category: str) -> List[FrontierTrend]:
        target = category.strip().lower()
        return [t for t in self._trends if t.category.lower() == target]

    def filter_by_maturity(self, maturity: str) -> List[FrontierTrend]:
        target = maturity.strip().lower()
        return [t for t in self._trends if t.maturity.lower() == target]

    def search(self, keyword: str) -> List[FrontierTrend]:
        kw = keyword.strip().lower()
        if not kw:
            return self.list_trends()
        results: List[FrontierTrend] = []
        for t in self._trends:
            haystack = " ".join([t.trend_id, t.name, t.category, t.summary, *t.key_technologies]).lower()
            if kw in haystack:
                results.append(t)
        return results

    def summarize_markdown(self) -> str:
        lines = [
            "## 2025-2026 AI Agent 前沿技术趋势追踪",
            "",
            "| 趋势方向 | 类别 | 成熟度 | 核心技术 | 对智枢平台的影响 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for t in self._trends:
            techs = ", ".join(t.key_technologies[:3])
            lines.append(f"| {t.name} | `{t.category}` | `{t.maturity}` | {techs} | {t.impact_on_zhishu} |")
        return "\n".join(lines)


def generate_graduation_certificate(
    learner_name: str,
    completion_date: str = "2026-11-13",
    track: str = "Agent Engineer",
    completed_days: int = 70,
    highlights: Optional[List[str]] = None,
) -> str:
    """生成《智枢企业级智能体平台》70天结业电子证书（Markdown 格式）。"""
    clean_name = learner_name.strip()
    if not clean_name:
        raise ValueError("learner_name 不能为空")
    if completed_days < 1 or completed_days > 70:
        raise ValueError("completed_days 必须在 1 到 70 之间")

    default_highlights = [
        "完成 Day 01 ~ Day 70 全部 6 大阶段工程实战，交付智枢企业级智能体平台 v1.0.0",
        "掌握 Hybrid RAG（BM25+Dense+RRF+Rerank）、Multi-Agent、MCP 协议与 HITL 审批闭环",
        "通过全链路 pytest 自动化测试与 Notebook 端到端真实内核验证",
    ]
    items = highlights or default_highlights
    bullet_lines = "\n".join(f"- {h}" for h in items)

    return "\n".join(
        [
            "========================================================================",
            "                  星辰数科 · 智枢企业级智能体实战营 结业证书",
            "                  ZhiShu-Agent 70-Day Engineering Certificate",
            "========================================================================",
            f"授予学员：{clean_name}",
            f"认证方向：{track}",
            f"完成进度：{completed_days}/70 天（版本里程碑 v0.1.0 -> v1.0.0）",
            f"颁发日期：{completion_date}",
            "签发团队：星辰数科教研与工程委员会（林晓 / 张工 / 陈默 / 李婷 / 赵磊）",
            "",
            "核心工程能力认证：",
            bullet_lines,
            "========================================================================",
        ]
    )


_ROLE_ROADMAP_FOCUS: dict[str, dict[str, tuple[str, ...]]] = {
    "Agent Engineer": {
        "30": (
            "精读 MCP 与 A2A 协议规范，将智枢平台工具集封装为独立可发布的 MCP Server",
            "使用推理模型（o1/DeepSeek-R1）改造复杂任务 Planner，建立快慢思考分层路由",
            "完善 GitHub 开源仓库 README、架构图与在线 Demo，完成 10 次目标岗位投递与复盘",
        ),
        "60": (
            "引入多模态/Computer-Use 能力，打通复杂 PDF 图表与跨系统自动化工作流",
            "构建 Agent 评测基准集（任务成功率、工具误调用率、HITL 触发准确率）并接入 CI",
            "输出 2 篇深度技术博客（如《企业级 HITL 状态机设计》《MCP 生产落地实践》）",
        ),
        "90": (
            "在真实业务场景中主导 1 个跨部门智能体项目从 0 到 1 上线与灰度观测",
            "沉淀端云协同与推理成本优化方案，形成可量化的降本增效年度案例",
            "参与主流开源 Agent 框架社区 PR 贡献，建立行业技术影响力",
        ),
    },
    "RAG Engineer": {
        "30": (
            "针对多模态财报/表格场景优化文档版面解析与父子索引（Parent-Child Chunking）",
            "在智枢平台基础上补充 RAGAS / TruLens 自动化回归评测流水线",
            "整理 Recall@K、MRR、Faithfulness 调优实验报告并更新至简历 STAR 亮点",
        ),
        "60": (
            "探索 GraphRAG / 知识图谱与混合检索结合，解决多跳推理与跨文档实体关联问题",
            "压测向量数据库（Milvus/Qdrant/FAISS）千万级分片性能与冷热数据分层策略",
            "实现租户级权限过滤（ACL-aware Retrieval）与 PII 检索前脱敏审计",
        ),
        "90": (
            "构建领域知识库自动更新与数据飞轮（Badcase 收集 -> 难例挖掘 -> Reranker 微调）",
            "主导企业级知识中台 SLA 达标（P95 < 200ms，幻觉率 < 2%）",
            "输出企业级 RAG 架构演进白皮书并在团队内完成技术分享",
        ),
    },
    "AI Application Engineer": {
        "30": (
            "打磨 FastAPI + SSE 全栈流式交互体验，补充断线重连与前端状态恢复机制",
            "完善 Docker Compose / K8s 部署清单与 Prometheus 业务指标看板",
            "围绕全栈交付项目准备 15 分钟系统设计演讲与现场演示脚本",
        ),
        "60": (
            "集成 Realtime 语音或边缘端侧小模型推理能力，拓展多端交互入口",
            "建立 LLM 网关多供应商容灾切换（Fallback）、语义缓存（Semantic Cache）与成本账单",
            "完成 3 轮模拟系统设计面试与高频并发/工程故障排查演练",
        ),
        "90": (
            "主导高并发 AI 应用产品化落地，建立完整的 A/B 测试与用户反馈闭环",
            "打通从需求拆解、Prompt/Agent 编排到灰度发布的全栈工程化标准",
            "向资深 AI 全栈架构师进阶，承担核心技术选型与团队 Code Review 职责",
        ),
    },
}


def generate_career_roadmap(
    target_role: str = "Agent Engineer",
    current_level: str = "Graduate",
    learner_name: str = "陈默",
) -> str:
    """生成结业后 30 / 60 / 90 天职业发展路线图（Markdown 格式）。"""
    role_key = target_role.strip()
    if role_key not in _ROLE_ROADMAP_FOCUS:
        supported = ", ".join(_ROLE_ROADMAP_FOCUS.keys())
        raise ValueError(f"不支持的目标岗位 '{target_role}'，可选岗位：{supported}")

    focus = _ROLE_ROADMAP_FOCUS[role_key]
    lines = [
        f"# 结业后 30 / 60 / 90 天职业发展路线图（{learner_name} · {role_key}）",
        "",
        f"- **当前阶段**：{current_level}（已完成智枢平台 70 天全栈训练 `v1.0.0`）",
        f"- **目标岗位**：{role_key}",
        "",
        "## Day 1 - Day 30：巩固交付与求职突破期（夯实底座 & 拿到面试）",
        *[f"- [ ] {item}" for item in focus["30"]],
        "",
        "## Day 31 - Day 60：前沿拓展与深度攻坚期（架构升级 & 技术背书）",
        *[f"- [ ] {item}" for item in focus["60"]],
        "",
        "## Day 61 - Day 90：生产实战与影响力跃迁期（业务闭环 & 架构进阶）",
        *[f"- [ ] {item}" for item in focus["90"]],
    ]
    return "\n".join(lines)
