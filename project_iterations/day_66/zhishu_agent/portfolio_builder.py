"""Day 66 核心模块：STAR 法则简历生成器与 GitHub README 作品集质量检查器 (v1.0.0-day66)。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# 领域词典：量化指标、技术关键词、强动作动词、目标岗位画像
# ---------------------------------------------------------------------------

METRIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+(?:\.\d+)?\s*%"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:ms|s|秒|分钟|小时|h)\b", re.IGNORECASE),
    re.compile(r"\d+(?:\.\d+)?\s*(?:倍|x|X)\b"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:万|千|亿|k|K|M|GB|MB|QPS|TPS|token|tokens)\b", re.IGNORECASE),
    re.compile(r"(?:P95|P99|Top-?\d+|F1|Recall|Precision|MRR|NDCG)\s*[:：=]?\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"(?:提升|降低|减少|缩短|节省|达到|高达|突破|覆盖|支持)\s*\d+(?:\.\d+)?"),
)

TECH_KEYWORDS: tuple[str, ...] = (
    "RAG",
    "BM25",
    "RRF",
    "FAISS",
    "Milvus",
    "Qdrant",
    "Chroma",
    "Embedding",
    "Rerank",
    "BGE",
    "LangGraph",
    "LangChain",
    "LlamaIndex",
    "FastAPI",
    "Uvicorn",
    "SSE",
    "WebSocket",
    "HITL",
    "MCP",
    "Function Calling",
    "Tool Use",
    "ReAct",
    "Multi-Agent",
    "Agent",
    "Prompt",
    "LoRA",
    "QLoRA",
    "vLLM",
    "PyTorch",
    "Pydantic",
    "SQLite",
    "PostgreSQL",
    "Redis",
    "Docker",
    "Kubernetes",
    "Prometheus",
    "OpenTelemetry",
    "pytest",
    "CI/CD",
    "PII",
    "RBAC",
    "Python",
    "LLM",
)

ACTION_VERBS: tuple[str, ...] = (
    "主导",
    "设计",
    "构建",
    "搭建",
    "重构",
    "优化",
    "落地",
    "实现",
    "研发",
    "封装",
    "集成",
    "压测",
    "治理",
    "提升",
    "降低",
    "Architected",
    "Designed",
    "Built",
    "Implemented",
    "Optimized",
    "Refactored",
    "Deployed",
    "Led",
    "Reduced",
    "Improved",
)

ROLE_PROFILES: dict[str, dict[str, object]] = {
    "AI Application Engineer": {
        "zh_title": "AI 应用工程师 (AI Application Engineer)",
        "summary": (
            "具备企业级大模型应用全栈落地经验，熟练掌握 FastAPI 异步网关、SSE 流式交互、"
            "PII 合规脱敏与检索增强生成（RAG）工程化集成，能够独立完成从需求拆解到生产级交付。"
        ),
        "core_skills": [
            "Python / FastAPI / Uvicorn / SSE 流式通信",
            "LLM 应用工程：Prompt 工程、Function Calling、结构化输出 (Pydantic)",
            "混合检索与上下文治理：BM25 + 向量检索 + RRF 融合",
            "安全与可观测性：PII 脱敏、注入拦截、OpenTelemetry 追踪、pytest 自动化测试",
        ],
        "priority_keywords": ["FastAPI", "SSE", "PII", "RAG", "Pydantic", "SQLite", "Docker", "pytest"],
    },
    "Agent Engineer": {
        "zh_title": "大模型智能体工程师 (Agent Engineer)",
        "summary": (
            "专注于多智能体（Multi-Agent）协作架构、状态机编排与 Human-in-the-Loop（HITL）"
            "审批闭环设计，具备工具沙箱安全隔离、长短时记忆治理与高可靠任务执行链路实战经验。"
        ),
        "core_skills": [
            "Agent 编排框架：ReAct、Plan-and-Execute、Multi-Agent 状态机与路由",
            "协议与工具生态：MCP (Model Context Protocol)、Function Calling、沙箱隔离",
            "人机协同与内控：HITL 高风险动作挂起/恢复、幂等审批、审计日志",
            "评测与稳定性：轨迹回放、幻觉/越权拦截、FastAPI + SSE 实时可观测",
        ],
        "priority_keywords": ["Agent", "Multi-Agent", "HITL", "MCP", "LangGraph", "ReAct", "Function Calling", "SSE"],
    },
    "RAG Engineer": {
        "zh_title": "检索增强生成工程师 (RAG Engineer)",
        "summary": (
            "深耕企业级知识库与财报/文档混合检索系统，擅长多路召回（BM25 + Dense Vector + RRF）、"
            "精排重排序（Rerank）、文档切片策略优化及 RAGAS/离线基准评测体系建设。"
        ),
        "core_skills": [
            "混合检索架构：BM25 稀疏检索、Dense Embedding 向量检索、RRF 倒数秩融合",
            "文档解析与切片：PDF/表格结构化提取、父子分块、元数据过滤与引用溯源",
            "精排与评测：Cross-Encoder Rerank、Recall@K / MRR / Faithfulness 量化评测",
            "工程与性能：FAISS / Milvus、Redis 语义缓存、P95 检索延迟优化",
        ],
        "priority_keywords": ["RAG", "BM25", "RRF", "Embedding", "Rerank", "FAISS", "Milvus", "Recall"],
    },
}

ROLE_ALIASES: dict[str, str] = {
    "ai application engineer": "AI Application Engineer",
    "ai应用工程师": "AI Application Engineer",
    "ai 应用工程师": "AI Application Engineer",
    "agent engineer": "Agent Engineer",
    "agent工程师": "Agent Engineer",
    "智能体工程师": "Agent Engineer",
    "rag engineer": "RAG Engineer",
    "rag工程师": "RAG Engineer",
}


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------


@dataclass
class STARBullet:
    """STAR 法则项目经历条目。"""

    situation: str
    task: str
    action: str
    result: str
    tech_stack: list[str] = field(default_factory=list)
    role_tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.situation = self.situation.strip()
        self.task = self.task.strip()
        self.action = self.action.strip()
        self.result = self.result.strip()

    def extracted_metrics(self) -> list[str]:
        """从 Action 与 Result 中提取量化指标片段。"""
        combined = f"{self.action} {self.result}"
        return extract_metrics(combined)

    def has_quantified_metrics(self) -> bool:
        """判断是否包含至少一项量化成果指标。"""
        return len(self.extracted_metrics()) > 0


@dataclass
class BulletAuditItem:
    """单条简历描述的质检结果。"""

    index: int
    text: str
    passed: bool
    has_metrics: bool
    detected_metrics: list[str]
    has_tech_keywords: bool
    detected_tech_keywords: list[str]
    has_action_verb: bool
    issues: list[str]
    suggestions: list[str]
    score: int


@dataclass
class ResumeAuditReport:
    """简历条目批量质检报告。"""

    total_bullets: int
    passed_bullets: int
    flagged_bullets: int
    average_score: float
    items: list[BulletAuditItem]


@dataclass
class ReadmeSectionCheck:
    """GitHub README 单项章节检查结果。"""

    section: str
    label: str
    present: bool
    weight: int
    evidence: str
    recommendation: str


@dataclass
class ReadmeAuditReport:
    """GitHub README 作品集完整性评估报告。"""

    score: int
    grade: str
    passed: bool
    checks: list[ReadmeSectionCheck]
    missing_sections: list[str]
    summary: str


# ---------------------------------------------------------------------------
# 核心工具函数
# ---------------------------------------------------------------------------


def extract_metrics(text: str) -> list[str]:
    """提取文本中的量化指标表达。"""
    found: list[str] = []
    for pattern in METRIC_PATTERNS:
        for match in pattern.finditer(text):
            token = match.group(0).strip()
            if token and token not in found:
                found.append(token)
    return found


def extract_tech_keywords(text: str) -> list[str]:
    """提取文本中命中的 AI / 工程技术关键词（不区分大小写匹配）。"""
    lowered = text.lower()
    matched: list[str] = []
    for kw in TECH_KEYWORDS:
        if kw.lower() in lowered and kw not in matched:
            matched.append(kw)
    return matched


def has_strong_action_verb(text: str) -> bool:
    """判断是否包含强工程动作动词。"""
    lowered = text.lower()
    return any(verb.lower() in lowered for verb in ACTION_VERBS)


def format_star_bullet(
    bullet: STARBullet,
    include_tech_tags: bool = True,
    language: str = "zh",
) -> str:
    """将 STARBullet 结构化对象格式化为可直接写入简历的 STAR 高亮条目。"""
    if not all([bullet.situation, bullet.task, bullet.action, bullet.result]):
        raise ValueError("STARBullet 的 situation / task / action / result 均不能为空。")

    tech_suffix = ""
    if include_tech_tags and bullet.tech_stack:
        tech_joined = " / ".join(bullet.tech_stack)
        tech_suffix = f"（技术栈：{tech_joined}）" if language == "zh" else f" [Tech: {tech_joined}]"

    if language == "en":
        return (
            f"Given {bullet.situation}, tasked with {bullet.task}; "
            f"{bullet.action}, achieving {bullet.result}.{tech_suffix}"
        )

    return (
        f"针对{bullet.situation}，承担{bullet.task}；"
        f"{bullet.action}，最终{bullet.result}。{tech_suffix}"
    )


def audit_resume_bullets(bullets: Sequence[str | STARBullet]) -> ResumeAuditReport:
    """批量检查简历项目描述，识别缺少量化指标、缺少技术词或表述空洞的条目。"""
    items: list[BulletAuditItem] = []

    for idx, entry in enumerate(bullets):
        if isinstance(entry, STARBullet):
            text = format_star_bullet(entry, include_tech_tags=True, language="zh")
            tech_hint = " ".join(entry.tech_stack)
            combined_for_tech = f"{text} {tech_hint}"
        else:
            text = str(entry).strip()
            combined_for_tech = text

        metrics = extract_metrics(text)
        tech_kws = extract_tech_keywords(combined_for_tech)
        action_ok = has_strong_action_verb(text)

        has_metrics = len(metrics) > 0
        has_tech = len(tech_kws) > 0

        issues: list[str] = []
        suggestions: list[str] = []
        score = 0

        if has_metrics:
            score += 45
        else:
            issues.append("缺少量化指标（Result 无具体百分比、延迟、召回率或成本数据）")
            suggestions.append("补充可验证结果，例如“Top-5 召回率从 71% 提升至 92%，P95 延迟降至 180ms”。")

        if has_tech:
            score += 35
        else:
            issues.append("缺少核心技术关键词（未体现具体架构、框架或算法选型）")
            suggestions.append("明确技术栈，例如 FastAPI、SSE、BM25+RRF、LangGraph、HITL 或 pytest。")

        if action_ok:
            score += 20
        else:
            issues.append("动词偏弱或偏被动（如“参与”、“负责”、“了解”）")
            suggestions.append("改用“主导设计”、“重构”、“搭建”、“压测优化”等强工程动作词。")

        passed = has_metrics and has_tech and score >= 70
        items.append(
            BulletAuditItem(
                index=idx,
                text=text,
                passed=passed,
                has_metrics=has_metrics,
                detected_metrics=metrics,
                has_tech_keywords=has_tech,
                detected_tech_keywords=tech_kws,
                has_action_verb=action_ok,
                issues=issues,
                suggestions=suggestions,
                score=score,
            )
        )

    total = len(items)
    passed_count = sum(1 for item in items if item.passed)
    flagged_count = total - passed_count
    avg_score = round(sum(item.score for item in items) / total, 1) if total else 0.0

    return ResumeAuditReport(
        total_bullets=total,
        passed_bullets=passed_count,
        flagged_bullets=flagged_count,
        average_score=avg_score,
        items=items,
    )


def audit_github_readme(readme_text: str) -> ReadmeAuditReport:
    """检查 GitHub 仓库 README.md 的作品集专业度与完整性（满分 100）。"""
    text = readme_text or ""
    lowered = text.lower()

    checks_spec = [
        (
            "architecture_diagram",
            "系统架构图 (Architecture Diagram)",
            20,
            ("```mermaid", "架构图", "architecture", "flowchart", "sequencediagram", "system design"),
            "建议嵌入 Mermaid 架构图（flowchart/sequenceDiagram）直观展示 RAG/Agent/HITL 数据流。",
        ),
        (
            "quickstart",
            "快速开始与可复现命令 (Quickstart)",
            20,
            ("quickstart", "快速开始", "installation", "安装", "pip install", "uvicorn", "pytest", "docker compose"),
            "补充 Quickstart 章节，提供可直接复制运行的安装、启动与 pytest 校验命令。",
        ),
        (
            "api_docs",
            "API 接口文档与示例 (API Docs)",
            20,
            ("api", "接口文档", "endpoint", "/api/", "swagger", "openapi", "curl "),
            "列出核心接口路径（如 POST /api/v1/capstone/chat/stream）及请求/响应 JSON 示例。",
        ),
        (
            "eval_benchmarks",
            "量化评测基线 (Eval Benchmarks)",
            20,
            ("benchmark", "evaluation", "评测", "基线", "recall", "accuracy", "准确率", "p95", "latency", "qps"),
            "增加评测对比表（如 BM25 vs 混合 RRF 召回率、延迟 P95 与端到端通过率）。",
        ),
        (
            "demo_gif",
            "演示动图或界面截图 (Demo GIF / Screenshots)",
            10,
            (".gif", ".mp4", "demo", "演示", "截图", "screenshot", "![", "<video"),
            "在顶部放置 15-30 秒产品演示 GIF 或前端分析台截图，提升 HR 与技术面试官第一印象。",
        ),
        (
            "license",
            "开源协议 (License)",
            10,
            ("license", "mit ", "apache-2.0", "apache 2.0", "开源协议", "许可证"),
            "在文末声明开源协议（如 MIT License）并附带 LICENSE 文件链接。",
        ),
    ]

    checks: list[ReadmeSectionCheck] = []
    total_score = 0
    missing: list[str] = []

    for section_key, label, weight, keywords, rec in checks_spec:
        matched_kw = next((kw for kw in keywords if kw in lowered), "")
        present = bool(matched_kw)
        if present:
            total_score += weight
            evidence = f"命中标识: `{matched_kw}`"
        else:
            missing.append(section_key)
            evidence = "未检测到相关章节或标识"

        checks.append(
            ReadmeSectionCheck(
                section=section_key,
                label=label,
                present=present,
                weight=weight,
                evidence=evidence,
                recommendation="" if present else rec,
            )
        )

    if total_score >= 85:
        grade = "A"
    elif total_score >= 70:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    else:
        grade = "D"

    passed = total_score >= 70
    summary = (
        f"README 完整度评分 {total_score}/100（等级 {grade}），"
        f"{'达到投递展示标准' if passed else '暂未达到优质作品集标准'}；"
        + (f"待补全项：{', '.join(missing)}。" if missing else "6 大核心维度齐全！")
    )

    return ReadmeAuditReport(
        score=total_score,
        grade=grade,
        passed=passed,
        checks=checks,
        missing_sections=missing,
        summary=summary,
    )


def _normalize_role(target_role: str) -> str:
    key = target_role.strip().lower()
    if key in ROLE_ALIASES:
        return ROLE_ALIASES[key]
    if target_role in ROLE_PROFILES:
        return target_role
    supported = ", ".join(ROLE_PROFILES.keys())
    raise ValueError(f"不支持的目标岗位 '{target_role}'，可选岗位：{supported}")


def _bullet_role_relevance(bullet: STARBullet, canonical_role: str, priority_keywords: Iterable[str]) -> int:
    score = 0
    lowered_tags = {t.lower() for t in bullet.role_tags}
    if canonical_role.lower() in lowered_tags:
        score += 10
    combined = f"{bullet.situation} {bullet.task} {bullet.action} {bullet.result} {' '.join(bullet.tech_stack)}".lower()
    for kw in priority_keywords:
        if kw.lower() in combined:
            score += 2
    if bullet.has_quantified_metrics():
        score += 1
    return score


def generate_resume_markdown(
    candidate_name: str,
    target_role: str,
    bullets: Sequence[STARBullet],
    contact: str = "email@example.com | GitHub: github.com/example",
    summary: str = "",
    github_url: str = "",
    skills_override: Sequence[str] | None = None,
) -> str:
    """根据目标岗位生成定制化的 STAR 法则 Markdown 简历。"""
    if not candidate_name.strip():
        raise ValueError("candidate_name 不能为空")
    if not bullets:
        raise ValueError("bullets 至少需要包含 1 条 STARBullet")

    canonical_role = _normalize_role(target_role)
    profile = ROLE_PROFILES[canonical_role]
    zh_title = str(profile["zh_title"])
    role_summary = summary.strip() or str(profile["summary"])
    skills = list(skills_override) if skills_override else list(profile["core_skills"])  # type: ignore[arg-type]
    priority_kws = list(profile["priority_keywords"])  # type: ignore[arg-type]

    # 按岗位相关性与量化指标完整度排序
    ranked_bullets = sorted(
        bullets,
        key=lambda b: _bullet_role_relevance(b, canonical_role, priority_kws),
        reverse=True,
    )

    lines: list[str] = [
        f"# {candidate_name.strip()} — {zh_title}",
        "",
        f"> 联系方式：{contact}" + (f" | 作品集：{github_url}" if github_url else ""),
        "",
        "## 个人优势与岗位匹配度",
        role_summary,
        "",
        "## 核心技术栈",
    ]
    for skill in skills:
        lines.append(f"- {skill}")

    lines.extend([
        "",
        "## 核心项目经历（星辰数科 · 智枢企业级智能体平台）",
    ])
    for bullet in ranked_bullets:
        formatted = format_star_bullet(bullet, include_tech_tags=True, language="zh")
        lines.append(f"- {formatted}")

    return "\n".join(lines) + "\n"
