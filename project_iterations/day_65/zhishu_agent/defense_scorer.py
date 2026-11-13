"""Day 65: 企业级 Capstone 毕业答辩评分引擎与评委问答模拟器。

支持：
1. 五维度加权答辩评分标准 (`DefenseRubric`) 与权重合法性校验；
2. 企业评委高频硬核题库 (`JudgeQuestionBank`)：幻觉治理、高并发成本、权限隔离、HITL超时、微调 vs RAG 选型；
3. 多评委聚合评估 (`evaluate_defense`)，输出加权总分、等级 (`S`/`A`/`B`/`C`)、优势项、改进计划及 Markdown 评分卡导出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class RubricDimension:
    """答辩评分维度定义。"""

    key: str
    name: str
    weight: float
    description: str
    criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("评分维度 key 和 name 不能为空")
        if self.weight <= 0 or self.weight > 1.0:
            raise ValueError(f"维度 {self.name} 权重必须在 (0, 1] 区间内，当前为 {self.weight}")


DEFAULT_DIMENSIONS: tuple[RubricDimension, ...] = (
    RubricDimension(
        key="business_value",
        name="业务价值",
        weight=0.20,
        description="是否切中企业真实痛点、ROI 可量化且具备清晰的落地场景与交付闭环。",
        criteria=(
            "90-100: 痛点精准，ROI/人效提升指标可量化，具备可直接上线的业务闭环",
            "80-89: 场景明确，业务价值清晰，但量化指标或推广路径略显不足",
            "70-79: 有一定业务背景，但与真实企业流程仍有脱节",
            "<70: 停留在玩具 Demo 层面，缺乏明确业务收益",
        ),
    ),
    RubricDimension(
        key="architecture_depth",
        name="技术架构与RAG/Agent深度",
        weight=0.30,
        description="混合检索(BM25+向量+RRF)、多 Agent 编排、状态机与安全护栏的技术深度。",
        criteria=(
            "90-100: 架构分层清晰，混合 RAG、HITL 状态机与安全隔离设计严谨且有量化压测支撑",
            "80-89: 核心 RAG/Agent 链路完整，技术选型合理，局部边界条件有待打磨",
            "70-79: 能跑通基础检索与工具调用，但缺乏容错与深度优化",
            "<70: 单一 Prompt 拼接，缺乏工程化架构设计",
        ),
    ),
    RubricDimension(
        key="engineering_quality",
        name="工程质量与可观测性",
        weight=0.20,
        description="代码模块化、单元测试覆盖率、结构化日志、Trace 追踪与异常恢复能力。",
        criteria=(
            "90-100: 模块解耦、测试覆盖充分、具备全链路 Trace 与完善的降级告警机制",
            "80-89: 代码规范、核心路径有单测，可观测性基本完备",
            "70-79: 代码可运行但耦合度较高，测试或日志记录不够系统",
            "<70: 缺乏测试与异常处理，难以维护",
        ),
    ),
    RubricDimension(
        key="demo_fluency",
        name="演示流畅度",
        weight=0.15,
        description="15 分钟现场/录屏演示的节奏控制、端到端交互稳定性与关键亮点呈现。",
        criteria=(
            "90-100: 15 分钟节奏精准，端到端演示零卡顿，SSE 流式与 HITL 闭环直观震撼",
            "80-89: 演示完整流畅，时间把控良好，偶有细微衔接停顿",
            "70-79: 主要功能展示完成，但节奏偏赶或依赖临时解释",
            "<70: 演示频繁报错或超时，核心流程未能完整呈现",
        ),
    ),
    RubricDimension(
        key="qa_performance",
        name="评委问答表现",
        weight=0.15,
        description="面对企业评委深度追问时的反应速度、原理理解深度与权衡(Trade-off)思维。",
        criteria=(
            "90-100: 直击本质，能结合架构权衡与真实线上数据给出令人信服的方案",
            "80-89: 回答准确有条理，能覆盖主要技术点",
            "70-79: 能回答基础原理，但对极端场景与成本边界思考不足",
            "<70: 答非所问或对自身系统关键实现不熟悉",
        ),
    ),
)


class DefenseRubric:
    """企业级毕业答辩五维度加权评分标准。"""

    def __init__(self, dimensions: Sequence[RubricDimension] | None = None) -> None:
        self.dimensions: tuple[RubricDimension, ...] = (
            tuple(dimensions) if dimensions is not None else DEFAULT_DIMENSIONS
        )
        if not self.dimensions:
            raise ValueError("评分标准至少需要包含 1 个维度")

        keys = [d.key for d in self.dimensions]
        if len(set(keys)) != len(keys):
            raise ValueError("评分维度 key 存在重复")

        total_weight = sum(d.weight for d in self.dimensions)
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                f"所有评分维度权重之和必须等于 1.0，当前总和为 {total_weight:.6f}"
            )

        self._by_key: dict[str, RubricDimension] = {d.key: d for d in self.dimensions}
        self._by_name: dict[str, RubricDimension] = {d.name: d for d in self.dimensions}

    def get_dimension(self, identifier: str) -> RubricDimension:
        """支持通过维度 key 或中文名称获取维度定义。"""
        if identifier in self._by_key:
            return self._by_key[identifier]
        if identifier in self._by_name:
            return self._by_name[identifier]
        raise KeyError(f"未知的评分维度: {identifier}")

    def normalize_scores(self, raw_scores: Mapping[str, float]) -> dict[str, float]:
        """校验并将输入分数字典规范化为以 dimension.key 为键的字典。"""
        normalized: dict[str, float] = {}
        for identifier, score in raw_scores.items():
            dim = self.get_dimension(identifier)
            val = float(score)
            if val < 0.0 or val > 100.0:
                raise ValueError(f"维度 [{dim.name}] 分数必须在 [0, 100] 范围内，当前为 {val}")
            normalized[dim.key] = val

        missing = [d.name for d in self.dimensions if d.key not in normalized]
        if missing:
            raise ValueError(f"缺少以下必填评分维度: {', '.join(missing)}")
        return normalized

    def compute_weighted_score(self, raw_scores: Mapping[str, float]) -> float:
        """计算单份评分表的加权总分（0-100）。"""
        normalized = self.normalize_scores(raw_scores)
        total = sum(normalized[d.key] * d.weight for d in self.dimensions)
        return round(total, 2)


@dataclass(frozen=True)
class JudgeQuestion:
    """企业评委高频硬核提问条目。"""

    question_id: str
    category: str
    judge_role: str
    question: str
    keywords: tuple[str, ...]
    key_points: tuple[str, ...]
    model_answer: str
    difficulty: str = "hard"


DEFAULT_JUDGE_QUESTIONS: tuple[JudgeQuestion, ...] = (
    JudgeQuestion(
        question_id="JQ-01",
        category="幻觉治理",
        judge_role="AI 算法与质量评审专家",
        question=(
            "企业财报与合规场景对准确率要求极高，你们如何治理大模型幻觉？"
            "如果 RAG 检索回来的上下文缺失或存在冲突，Agent 怎么避免一本正经地胡说八道？"
        ),
        keywords=("幻觉", "faithfulness", "rag", "引用", "拒答", "冲突", "校验", "grounding"),
        key_points=(
            "混合检索(BM25+向量+RRF)+Cross-Encoder重排提升召回精准度",
            "强制 Citation 证据锚定与段落级溯源校验",
            "低置信度/检索空集时触发严格拒答(Abstention)与人工兜底",
            "引入 Faithfulness/Context Recall 自动化离线与在线评测门禁",
        ),
        model_answer=(
            "我们采用四层幻觉防线：1）检索层使用 BM25 + 向量双路召回与 RRF 融合重排，确保证据完整；"
            "2）生成层强制要求每条结论附带文档 ID 与原句 Citation，禁止无证据外推；"
            "3）校验层设置相似度与忠实度阈值，当上下文缺失或财报口径冲突时触发拒答策略并提示补充材料；"
            "4）评测层接入 Ragas/Faithfulness 自动化门禁，低于 0.85 阻断上线。"
        ),
        difficulty="expert",
    ),
    JudgeQuestion(
        question_id="JQ-02",
        category="高并发成本",
        judge_role="CTO / FinOps 架构负责人",
        question=(
            "如果在集团内推广，早高峰 500 并发同时调用多 Agent + 长文档 RAG，"
            "Token 成本和 P99 延迟怎么控制？会不会把预算打爆？"
        ),
        keywords=("并发", "成本", "token", "缓存", "路由", "延迟", "p99", "限流", "预算"),
        key_points=(
            "语义缓存(Semantic Cache)拦截高频重复财报/制度问答",
            "大小模型分级路由(Router)：简单意图走轻量模型，复杂推理走旗舰模型",
            "上下文压缩与 Top-K 动态裁剪控制输入 Token 预算",
            "Token 桶限流、异步队列削峰与单租户配额熔断",
        ),
        model_answer=(
            "我们在网关与编排层做了四项成本与延迟优化：1）语义缓存层对高频制度与财报摘要问题直接命中返回，"
            "实测可削减约 35%-45% 的 LLM 调用；2）引入意图复杂度路由器，简单查询分发给轻量低成本模型，"
            "复杂多步分析才调用旗舰模型；3）对检索 Chunk 进行去重与摘要压缩，严格控制 Prompt 上限；"
            "4）在网关侧实施租户级 Token 配额、并发信号量控制与降级熔断，保障 P99 延迟可控且预算不超支。"
        ),
        difficulty="expert",
    ),
    JudgeQuestion(
        question_id="JQ-03",
        category="权限隔离",
        judge_role="信息安全与合规总监",
        question=(
            "不同部门（如财务部、法务部、普通员工）共用一套向量库，如何防止越权检索？"
            "如果有人通过 Prompt 注入诱导 Agent 套取高管薪酬或未公开财报怎么办？"
        ),
        keywords=("权限", "隔离", "acl", "rbac", "abac", "越权", "注入", "pii", "脱敏", "多租户"),
        key_points=(
            "文档级 ACL 元数据过滤下推至向量/BM25 检索层(Pre-filtering)",
            "RBAC/ABAC 鉴权与租户命名空间物理/逻辑隔离",
            "输入侧 Prompt 注入检测与输出侧 PII/敏感词二次脱敏",
            "全链路审计日志记录操作人、检索文档 ID 与脱敏状态",
        ),
        model_answer=(
            "权限隔离遵循'检索前过滤(Pre-filtering) + 纵深防御'原则：1）所有文档切片入库时绑定 tenant_id、dept_acl "
            "与密级标签，检索请求必须携带经过 JWT 校验的用户角色，在向量/BM25 查询条件中强制下推 ACL 过滤，绝不在召回后过滤；"
            "2）输入端部署 Prompt 注入规则与分类器拦截越权指令；3）输出端与落库前执行 PII 脱敏（身份证/银行卡/手机号）；"
            "4）所有高敏访问写入不可篡改审计日志。"
        ),
        difficulty="expert",
    ),
    JudgeQuestion(
        question_id="JQ-04",
        category="HITL超时",
        judge_role="业务运维与风控 VP",
        question=(
            "你们设计了高风险动作的 HITL 人工审批挂起机制，但如果审批人出差一直不点通过怎么办？"
            "系统重启后挂起的状态会丢吗？审批人重复点击批准会不会导致资金或公告重复执行？"
        ),
        keywords=("hitl", "超时", "审批", "挂起", "恢复", "幂等", "持久化", "409", "升级"),
        key_points=(
            "审批单与会话状态持久化至 SQLite/PostgreSQL，支持进程重启恢复",
            "TTL 超时自动过期策略与多级升级/转派(Escalation)通知",
            "状态机 CAS 校验(仅 pending 允许流转)，重复审批返回 409 Conflict 保证幂等",
            "工具执行层引入幂等键(Idempotency Key)防止副作用重复触发",
        ),
        model_answer=(
            "针对 HITL 生产可靠性，我们有三重保障：1）所有审批单据(approvals)与上下文快照持久化在数据库而非内存，"
            "服务重启后仍可通过 session_id/approval_id 恢复现场；2）每张审批单配置 TTL 超时时间，超时未批自动转为 expired "
            "并触发企微/邮件升级提醒或安全自动拒绝；3）审批接口采用严格状态机校验，仅 pending 状态可被批准/拒绝，"
            "重复提交直接返回 409 Conflict，配合下游工具幂等键彻底杜绝重复执行。"
        ),
        difficulty="hard",
    ),
    JudgeQuestion(
        question_id="JQ-05",
        category="微调vs RAG选型",
        judge_role="首席 AI 架构师",
        question=(
            "为什么你们选择用混合 RAG + 工作流编排，而不是直接用企业内部文档微调（SFT/LoRA）一个专属大模型？"
            "什么情况下你们才会考虑微调？"
        ),
        keywords=("微调", "rag", "sft", "lora", "选型", "知识更新", "幻觉", "成本", "风格"),
        key_points=(
            "RAG 适合高频更新、强溯源、严格权限隔离的企业知识库",
            "微调无法解决动态知识更新与细粒度文档级权限控制，且易遗忘/幻觉",
            "微调适用场景：固定输出格式(JSON/SQL)、领域话术风格、特定工具调用规范",
            "最佳工程实践是 RAG 管知识与事实，微调/Prompt 管格式与行为规范",
        ),
        model_answer=(
            "核心遵循'RAG 管动态知识，微调管行为模式'的选型原则：1）财报与合规制度更新频繁，且必须支持文档级 ACL 权限隔离与原句溯源，"
            "微调模型无法在不重训的情况下实时更新或按用户权限遗忘特定文档；2）混合 RAG 配合引用校验能把事实准确率控制在可审计范围内；"
            "3）我们仅在需要固化复杂 JSON/Tool-Call 输出格式、领域术语理解或降低超长 System Prompt 推理成本时，才会采用小规模 LoRA 微调辅助 RAG。"
        ),
        difficulty="hard",
    ),
)


class JudgeQuestionBank:
    """企业评委答辩题库与回答匹配模拟器。"""

    def __init__(self, questions: Sequence[JudgeQuestion] | None = None) -> None:
        self._questions: tuple[JudgeQuestion, ...] = (
            tuple(questions) if questions is not None else DEFAULT_JUDGE_QUESTIONS
        )
        self._by_id: dict[str, JudgeQuestion] = {q.question_id: q for q in self._questions}

    def list_questions(self) -> list[JudgeQuestion]:
        return list(self._questions)

    def get_by_id(self, question_id: str) -> JudgeQuestion:
        if question_id not in self._by_id:
            raise KeyError(f"未找到评委问题 ID: {question_id}")
        return self._by_id[question_id]

    def get_by_category(self, category: str) -> list[JudgeQuestion]:
        cat_lower = category.strip().lower()
        return [q for q in self._questions if cat_lower in q.category.lower()]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower())
        return set(tokens)

    def match_question(self, query: str, top_k: int = 3) -> list[tuple[JudgeQuestion, float]]:
        """根据评委口头提问或关键词，匹配最相关的标准考题与相关度得分。"""
        query_clean = query.strip().lower()
        if not query_clean:
            return []

        query_tokens = self._tokenize(query_clean)
        scored: list[tuple[JudgeQuestion, float]] = []

        for q in self._questions:
            score = 0.0
            if q.category.lower() in query_clean:
                score += 3.0
            for kw in q.keywords:
                if kw.lower() in query_clean:
                    score += 1.5
            q_tokens = self._tokenize(f"{q.category} {q.question} {' '.join(q.keywords)}")
            overlap = len(query_tokens & q_tokens)
            score += overlap * 0.5

            if score > 0:
                scored.append((q, round(score, 2)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def score_answer(self, question_id: str, candidate_answer: str) -> dict[str, Any]:
        """评估候选人回答对关键采分点的覆盖度，返回结构化诊断结果。"""
        q = self.get_by_id(question_id)
        ans_lower = candidate_answer.strip().lower()
        matched: list[str] = []
        missed: list[str] = []

        for point in q.key_points:
            # 提取采分点中的英文关键词和中文核心词组进行匹配
            point_tokens = [
                tok
                for tok in re.findall(r"[a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,4}", point.lower())
                if len(tok) >= 2
            ]
            # 只要命中该采分点中的任意核心术语（或至少2个词）即视为覆盖
            hits = sum(1 for tok in set(point_tokens) if tok in ans_lower)
            if hits >= 2 or (len(point_tokens) <= 2 and hits >= 1):
                matched.append(point)
            else:
                missed.append(point)

        total = len(q.key_points)
        coverage = round(len(matched) / total, 2) if total else 0.0
        # 基础分 55 + 覆盖率 * 45，空回答直接 0 分
        suggested_score = 0.0 if not ans_lower else round(55.0 + coverage * 45.0, 2)
        return {
            "question_id": q.question_id,
            "category": q.category,
            "matched_points": matched,
            "missed_points": missed,
            "coverage_ratio": coverage,
            "suggested_score": suggested_score,
        }


@dataclass(frozen=True)
class JudgeScorecard:
    """单个企业评委的打分明细。"""

    judge_name: str
    judge_role: str
    dimension_scores: dict[str, float]
    weighted_score: float
    comment: str = ""


def assign_grade(score: float) -> str:
    """根据答辩加权总分划分评级：S (>=90) / A (>=80) / B (>=70) / C (<70)。"""
    if score >= 90.0:
        return "S"
    if score >= 80.0:
        return "A"
    if score >= 70.0:
        return "B"
    return "C"


@dataclass
class DefenseEvaluationResult:
    """毕业答辩综合评分结果。"""

    project_name: str
    team_name: str
    total_score: float
    grade: str
    dimension_averages: dict[str, float]
    dimension_contributions: dict[str, float]
    judge_scorecards: list[JudgeScorecard] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    improvement_plan: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """导出结构化 Markdown 答辩评分卡。"""
        return export_markdown_scorecard(self)


_IMPROVEMENT_TIPS: dict[str, str] = {
    "business_value": "补充企业试点 ROI 测算表（如人工审阅耗时对比、单月节省人天与误报率下降数据）。",
    "architecture_depth": "深化混合 RAG 检索消融实验对比与高并发场景下的降级/缓存架构演进图。",
    "engineering_quality": "补齐端到端集成测试、全链路 TraceID 日志关联以及故障注入演练报告。",
    "demo_fluency": "精简背景铺垫至 2 分钟内，将核心 SSE 流式与 HITL 审批闭环提前至前 8 分钟演示。",
    "qa_performance": "针对幻觉拒答边界、Token 成本路由与 HITL 超时幂等性准备 30 秒结构化应答模板。",
}


def evaluate_defense(
    scores: Mapping[str, float] | Sequence[Mapping[str, Any]],
    rubric: DefenseRubric | None = None,
    project_name: str = "智枢企业级智能体平台 (ZhiShu-Agent)",
    team_name: str = "星辰数科 Capstone 交付小组",
) -> DefenseEvaluationResult:
    """执行毕业答辩综合评分。

    Args:
        scores: 可以是单组维度分数字典（如 ``{"business_value": 90, ...}``），
            也可以是多位评委的打分列表（每项含 ``judge_name``、``judge_role``、``scores``、可选 ``comment``）。
        rubric: 自定义或默认的 ``DefenseRubric``。
        project_name: 参评项目名称。
        team_name: 参评团队名称。
    """
    active_rubric = rubric or DefenseRubric()

    if isinstance(scores, Mapping):
        judge_inputs: list[Mapping[str, Any]] = [
            {
                "judge_name": "综合评审委员会",
                "judge_role": "默认联合评委",
                "scores": scores,
                "comment": "基于五维度加权标准自动汇总。",
            }
        ]
    else:
        judge_inputs = list(scores)
        if not judge_inputs:
            raise ValueError("评委打分列表不能为空")

    judge_scorecards: list[JudgeScorecard] = []
    dim_sums: dict[str, float] = {d.key: 0.0 for d in active_rubric.dimensions}

    for idx, entry in enumerate(judge_inputs, start=1):
        raw_dim_scores = entry.get("scores") if "scores" in entry else entry
        if not isinstance(raw_dim_scores, Mapping):
            raise ValueError(f"第 {idx} 位评委的打分格式无效")
        normalized = active_rubric.normalize_scores(raw_dim_scores)
        weighted = active_rubric.compute_weighted_score(normalized)
        for k, v in normalized.items():
            dim_sums[k] += v

        judge_scorecards.append(
            JudgeScorecard(
                judge_name=str(entry.get("judge_name", f"评委#{idx}")),
                judge_role=str(entry.get("judge_role", "企业技术评委")),
                dimension_scores=normalized,
                weighted_score=weighted,
                comment=str(entry.get("comment", "")),
            )
        )

    judge_count = len(judge_scorecards)
    dimension_averages: dict[str, float] = {
        d.key: round(dim_sums[d.key] / judge_count, 2) for d in active_rubric.dimensions
    }
    dimension_contributions: dict[str, float] = {
        d.key: round(dimension_averages[d.key] * d.weight, 2) for d in active_rubric.dimensions
    }
    total_score = round(
        sum(dimension_averages[d.key] * d.weight for d in active_rubric.dimensions), 2
    )
    grade = assign_grade(total_score)

    # 识别优势维度（>= 85 分；若无则取最高分维度）
    sorted_dims = sorted(
        active_rubric.dimensions,
        key=lambda d: dimension_averages[d.key],
        reverse=True,
    )
    strengths = [
        f"{d.name}（均分 {dimension_averages[d.key]:.1f}，权重 {int(d.weight * 100)}%）"
        for d in sorted_dims
        if dimension_averages[d.key] >= 85.0
    ]
    if not strengths:
        top_dim = sorted_dims[0]
        strengths.append(
            f"{top_dim.name}相对突出（均分 {dimension_averages[top_dim.key]:.1f}）"
        )

    # 生成改进计划（所有 < 85 分的维度，或至少给出最低分维度的优化建议）
    low_dims = [d for d in reversed(sorted_dims) if dimension_averages[d.key] < 85.0]
    if not low_dims:
        low_dims = [sorted_dims[-1]]

    improvement_plan = [
        f"[{d.name} | 均分 {dimension_averages[d.key]:.1f}] "
        + _IMPROVEMENT_TIPS.get(d.key, f"针对「{d.name}」补充量化验证数据与边界案例演练。")
        for d in low_dims
    ]

    return DefenseEvaluationResult(
        project_name=project_name,
        team_name=team_name,
        total_score=total_score,
        grade=grade,
        dimension_averages=dimension_averages,
        dimension_contributions=dimension_contributions,
        judge_scorecards=judge_scorecards,
        strengths=strengths,
        improvement_plan=improvement_plan,
    )


def export_markdown_scorecard(
    result: DefenseEvaluationResult,
    rubric: DefenseRubric | None = None,
) -> str:
    """将答辩评估结果渲染为企业级 Markdown 评分卡报告。"""
    active_rubric = rubric or DefenseRubric()
    lines: list[str] = [
        f"# 毕业答辩评审评分卡 — {result.project_name}",
        "",
        f"- **汇报团队**：{result.team_name}",
        f"- **综合加权总分**：**{result.total_score:.2f} / 100.00**",
        f"- **答辩评级**：**{result.grade} 级**",
        "",
        "## 一、五维度加权得分明细",
        "",
        "| 评分维度 | 权重 | 评委均分 | 加权贡献分 |",
        "| --- | :---: | :---: | :---: |",
    ]

    for dim in active_rubric.dimensions:
        avg = result.dimension_averages.get(dim.key, 0.0)
        contrib = result.dimension_contributions.get(dim.key, 0.0)
        lines.append(
            f"| {dim.name} (`{dim.key}`) | {int(dim.weight * 100)}% | {avg:.2f} | {contrib:.2f} |"
        )

    lines.extend(["", "## 二、评委独立打分与评语", ""])
    for card in result.judge_scorecards:
        lines.append(
            f"- **{card.judge_name}**（{card.judge_role}）：加权得分 **{card.weighted_score:.2f}**"
            + (f" — {card.comment}" if card.comment else "")
        )

    lines.extend(["", "## 三、核心优势亮点", ""])
    for item in result.strengths:
        lines.append(f"- {item}")

    lines.extend(["", "## 四、后续改进计划（Action Items）", ""])
    for item in result.improvement_plan:
        lines.append(f"- {item}")

    lines.append("")
    return "\n".join(lines)
