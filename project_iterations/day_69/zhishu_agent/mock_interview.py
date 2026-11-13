"""Day 69 核心模块：一对一全真模拟面试引擎（技术面 + HR 面全闭环）。

支持四轮结构化面试流转：
  1. 自我介绍（技术面热身）
  2. 项目深挖（RAG / HITL / Multi-Agent 核心架构与量化指标）
  3. 场景手撕/架构（高并发、幂等容错、降级熔断与系统设计）
  4. 行为面试 HR 面（冲突解决、失败复盘、主人翁意识与团队协作）

基于四维评分模型（clarity、technical_depth、star_structure、honesty_ownership）
对候选人回答进行客观量化评估，并由 `generate_interview_feedback()` 生成
Strong-Hire / Offer / Hire / No-Hire 录用建议与针对性 7 天改进清单。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

ROUND_SELF_INTRO = "自我介绍"
ROUND_PROJECT_DEEP_DIVE = "项目深挖"
ROUND_SCENARIO_CODING_ARCH = "场景手撕/架构"
ROUND_HR_BEHAVIORAL = "行为面试 HR 面"

RECOMMENDATION_STRONG_HIRE = "Strong-Hire"
RECOMMENDATION_OFFER = "Offer"
RECOMMENDATION_HIRE = "Hire"
RECOMMENDATION_NO_HIRE = "No-Hire"

_TECHNICAL_KEYWORDS = (
    "rag",
    "bm25",
    "rrf",
    "rerank",
    "faiss",
    "embedding",
    "hitl",
    "mcp",
    "agent",
    "multi-agent",
    "fastapi",
    "sse",
    "sqlite",
    "redis",
    "pytest",
    "pydantic",
    "recall",
    "latency",
    "p95",
    "p99",
    "qps",
    "token",
    "llm",
    "prompt",
    "状态机",
    "幂等",
    "熔断",
    "降级",
    "异步",
    "并发",
    "缓存",
    "溯源",
    "脱敏",
    "pii",
    "沙箱",
    "限流",
    "微调",
    "评测",
    "向量",
    "重排",
    "召回",
    "架构",
    "时间复杂度",
    "空间复杂度",
    "o(n)",
    "o(log n)",
)

_METRIC_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|ms|s|秒|毫秒|倍|x|qps|tps|mb|gb|k|条|次|项))"
    r"|(?:recall@\d+|p95|p99|top-\d+)",
    re.IGNORECASE,
)

_CLARITY_CONNECTORS = (
    "首先",
    "其次",
    "最后",
    "第一",
    "第二",
    "第三",
    "总结",
    "因此",
    "所以",
    "一方面",
    "另一方面",
    "核心在于",
    "分为",
)

_STAR_S_MARKERS = ("背景", "痛点", "当时", "遇到", "面临", "场景", "线上", "需求", "问题在于", "situation")
_STAR_T_MARKERS = ("目标", "职责", "负责", "需要", "任务", "指标", "要求", "task")
_STAR_A_MARKERS = ("通过", "采用", "设计", "实现", "重构", "引入", "搭建", "优化", "排查", "action")
_STAR_R_MARKERS = ("结果", "最终", "提升", "降低", "减少", "通过率", "收益", "复盘", "沉淀", "result")

_OWNERSHIP_POSITIVE = (
    "我主导",
    "我负责",
    "我设计",
    "我排查",
    "我提出",
    "我推动",
    "我的问题",
    "我反思",
    "复盘",
    "改进",
    "主动",
    "坦白",
    "坦诚",
    "承认",
    "承担",
    "责任",
    "边界",
    "不足",
    "教训",
    "权衡",
    "取舍",
)

_BLAME_OR_BOAST_NEGATIVE = (
    "都是别人",
    "不关我的事",
    "产品的问题",
    "测试没测出来",
    "老板非要",
    "完美无缺",
    "没有任何缺点",
    "从来不犯错",
    "随便写写",
    "记不清了反正效果很好",
)


@dataclass(frozen=True)
class InterviewRoundSpec:
    """单轮面试配置规范。"""

    round_id: int
    name: str
    category: str  # "technical" | "hr"
    interviewer: str
    prompt: str
    weights: dict[str, float]


DEFAULT_ROUNDS: tuple[InterviewRoundSpec, ...] = (
    InterviewRoundSpec(
        round_id=1,
        name=ROUND_SELF_INTRO,
        category="technical",
        interviewer="Tech Lead 张工",
        prompt=(
            "请用 2 分钟做个自我介绍，重点说明你在『智枢企业级智能体平台』中的核心角色、"
            "技术栈以及最能代表你工程能力的一项成果。"
        ),
        weights={
            "clarity": 0.35,
            "technical_depth": 0.30,
            "star_structure": 0.20,
            "honesty_ownership": 0.15,
        },
    ),
    InterviewRoundSpec(
        round_id=2,
        name=ROUND_PROJECT_DEEP_DIVE,
        category="technical",
        interviewer="Tech Lead 张工",
        prompt=(
            "在智枢平台的企业财报 RAG 与 HITL 审批模块中，你是如何解决专有名词漏召回"
            "和高风险工具调用越权问题的？请给出具体架构选型与可验证的量化指标。"
        ),
        weights={
            "clarity": 0.20,
            "technical_depth": 0.45,
            "star_structure": 0.20,
            "honesty_ownership": 0.15,
        },
    ),
    InterviewRoundSpec(
        round_id=3,
        name=ROUND_SCENARIO_CODING_ARCH,
        category="technical",
        interviewer="Tech Lead 张工",
        prompt=(
            "【场景手撕/架构】假设智枢平台的高风险审批接口遭遇并发重复提交与下游 LLM 超时，"
            "请阐述你的幂等状态机设计、熔断降级策略，以及关键数据结构/复杂度考量。"
        ),
        weights={
            "clarity": 0.25,
            "technical_depth": 0.45,
            "star_structure": 0.15,
            "honesty_ownership": 0.15,
        },
    ),
    InterviewRoundSpec(
        round_id=4,
        name=ROUND_HR_BEHAVIORAL,
        category="hr",
        interviewer="HRBP / PM 林晓",
        prompt=(
            "【行为面试 HR 面】请分享一次你在项目推进中与团队成员产生技术分歧，"
            "或线上出现故障/失误的经历。你当时如何处理、承担了什么责任，事后做了哪些改进？"
        ),
        weights={
            "clarity": 0.20,
            "technical_depth": 0.10,
            "star_structure": 0.35,
            "honesty_ownership": 0.35,
        },
    ),
)


@dataclass(frozen=True)
class DimensionScores:
    """四维面试评分结果（0-100 分制）。"""

    clarity: float
    technical_depth: float
    star_structure: float
    honesty_ownership: float


@dataclass
class TurnEvaluation:
    """单轮面试作答评估详情。"""

    round_id: int
    round_name: str
    category: str
    interviewer: str
    prompt: str
    response: str
    scores: DimensionScores
    weighted_score: float
    is_empty: bool
    matched_keywords: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChecklistItem:
    """7 天针对性改进计划条目。"""

    day: int
    focus_area: str
    action_item: str
    deliverable: str


@dataclass
class InterviewFeedbackReport:
    """全闭环模拟面试综合评估报告。"""

    candidate_name: str
    target_role: str
    technical_score: float
    hr_score: float
    overall_score: float
    recommendation: str
    dimension_averages: dict[str, float]
    turn_evaluations: list[TurnEvaluation]
    strengths: list[str]
    weaknesses: list[str]
    seven_day_checklist: list[ChecklistItem]

    def format_markdown(self) -> str:
        """生成可读性良好的 Markdown 格式面试复盘报告。"""
        lines = [
            f"# 模拟面试评估报告 — {self.candidate_name}（{self.target_role}）",
            "",
            f"- **录用建议**：`{self.recommendation}`",
            f"- **综合总分**：{self.overall_score:.1f} / 100",
            f"- **技术面得分**：{self.technical_score:.1f} / 100",
            f"- **HR 面得分**：{self.hr_score:.1f} / 100",
            "",
            "## 四维能力均值",
            f"- 表达清晰度 (Clarity)：{self.dimension_averages['clarity']:.1f}",
            f"- 技术深度 (Technical Depth)：{self.dimension_averages['technical_depth']:.1f}",
            f"- STAR 结构 (STAR Structure)：{self.dimension_averages['star_structure']:.1f}",
            f"- 诚实度与担当 (Honesty & Ownership)：{self.dimension_averages['honesty_ownership']:.1f}",
            "",
            "## 各轮次明细",
        ]
        for turn in self.turn_evaluations:
            lines.append(
                f"- **Round {turn.round_id} [{turn.round_name}]** ({turn.interviewer})："
                f"{turn.weighted_score:.1f} 分"
            )
        lines.append("")
        lines.append("## 核心优势")
        for s in self.strengths:
            lines.append(f"- {s}")
        lines.append("")
        lines.append("## 待改进项")
        for w in self.weaknesses:
            lines.append(f"- {w}")
        lines.append("")
        lines.append("## 7 天冲刺改进清单")
        for item in self.seven_day_checklist:
            lines.append(
                f"- **Day {item.day} [{item.focus_area}]**：{item.action_item}"
                f"（交付物：{item.deliverable}）"
            )
        return "\n".join(lines)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)


def _count_matches(text_lower: str, markers: Sequence[str]) -> int:
    return sum(1 for m in markers if m in text_lower)


def evaluate_response(round_spec: InterviewRoundSpec, response: str) -> TurnEvaluation:
    """对候选人在指定轮次的回答进行四维量化评估。"""
    cleaned = (response or "").strip()
    if not cleaned:
        zero_scores = DimensionScores(0.0, 0.0, 0.0, 0.0)
        return TurnEvaluation(
            round_id=round_spec.round_id,
            round_name=round_spec.name,
            category=round_spec.category,
            interviewer=round_spec.interviewer,
            prompt=round_spec.prompt,
            response="",
            scores=zero_scores,
            weighted_score=0.0,
            is_empty=True,
            matched_keywords=[],
            strengths=[],
            improvements=["未检测到有效回答内容，请至少给出结构化的核心要点。"],
        )

    text_lower = cleaned.lower()
    char_len = len(cleaned)

    # 1. Clarity (表达清晰度)
    connector_hits = _count_matches(text_lower, _CLARITY_CONNECTORS)
    sentence_count = len([s for s in re.split(r"[。！？!?;\n]+", cleaned) if s.strip()])
    clarity = 35.0
    if char_len >= 120:
        clarity += 25.0
    elif char_len >= 60:
        clarity += 15.0
    elif char_len < 20:
        clarity -= 20.0
    clarity += min(25.0, connector_hits * 8.5)
    if sentence_count >= 3:
        clarity += 15.0
    elif sentence_count == 2:
        clarity += 8.0
    clarity_score = _clamp(clarity)

    # 2. Technical Depth (技术深度与量化指标)
    matched_kw = [kw for kw in _TECHNICAL_KEYWORDS if kw in text_lower]
    metric_hits = len(_METRIC_PATTERN.findall(cleaned))
    tech_base = 25.0 if round_spec.category == "technical" else 40.0
    tech_base += min(45.0, len(matched_kw) * 9.0)
    tech_base += min(30.0, metric_hits * 12.0)
    if char_len < 25:
        tech_base = min(tech_base, 25.0)
    tech_score = _clamp(tech_base)

    # 3. STAR Structure (Situation / Task / Action / Result)
    s_hit = 1 if _count_matches(text_lower, _STAR_S_MARKERS) > 0 else 0
    t_hit = 1 if _count_matches(text_lower, _STAR_T_MARKERS) > 0 else 0
    a_hit = 1 if _count_matches(text_lower, _STAR_A_MARKERS) > 0 else 0
    r_hit = 1 if _count_matches(text_lower, _STAR_R_MARKERS) > 0 else 0
    star_parts = s_hit + t_hit + a_hit + r_hit
    star_base = 20.0 + star_parts * 19.0
    if metric_hits > 0 and r_hit:
        star_base += 4.0
    if char_len < 25:
        star_base = min(star_base, 25.0)
    star_score = _clamp(star_base)

    # 4. Honesty & Ownership (诚实度与主人翁意识)
    pos_own = _count_matches(text_lower, _OWNERSHIP_POSITIVE)
    neg_own = _count_matches(text_lower, _BLAME_OR_BOAST_NEGATIVE)
    honesty_base = 45.0 + min(45.0, pos_own * 11.0) - neg_own * 25.0
    if char_len < 20:
        honesty_base = min(honesty_base, 30.0)
    honesty_score = _clamp(honesty_base)

    scores = DimensionScores(
        clarity=clarity_score,
        technical_depth=tech_score,
        star_structure=star_score,
        honesty_ownership=honesty_score,
    )

    w = round_spec.weights
    weighted = round(
        scores.clarity * w["clarity"]
        + scores.technical_depth * w["technical_depth"]
        + scores.star_structure * w["star_structure"]
        + scores.honesty_ownership * w["honesty_ownership"],
        2,
    )

    strengths: list[str] = []
    improvements: list[str] = []

    if scores.clarity >= 75:
        strengths.append("逻辑层次清晰，善用结构化连接词。")
    else:
        improvements.append("建议采用“首先/其次/最后”分点作答，控制单句长度。")

    if round_spec.category == "technical":
        if scores.technical_depth >= 75:
            strengths.append(f"技术栈与量化指标扎实（命中 {len(matched_kw)} 个核心技术词）。")
        else:
            improvements.append("需补充底层技术选型原因（如 RRF/HITL/幂等）与量化指标（%、ms、Recall）。")

    if scores.star_structure >= 75:
        strengths.append("STAR 叙事闭环完整，因果与结果明确。")
    else:
        improvements.append("建议严格按 Situation-Task-Action-Result 四步展开，避免只讲过程不讲结果。")

    if scores.honesty_ownership >= 75:
        strengths.append("具备良好的主人翁意识与客观复盘态度。")
    else:
        improvements.append("需突出“我主导/我负责”的个人贡献，并坦诚说明技术权衡或改进空间。")

    return TurnEvaluation(
        round_id=round_spec.round_id,
        round_name=round_spec.name,
        category=round_spec.category,
        interviewer=round_spec.interviewer,
        prompt=round_spec.prompt,
        response=cleaned,
        scores=scores,
        weighted_score=weighted,
        is_empty=False,
        matched_keywords=matched_kw,
        strengths=strengths,
        improvements=improvements,
    )


def _decide_recommendation(
    overall_score: float,
    technical_score: float,
    hr_score: float,
    empty_count: int,
) -> str:
    """根据综合分、技术面、HR 面及空答情况给出录用分级。"""
    if empty_count >= 2:
        return RECOMMENDATION_NO_HIRE
    if (
        empty_count == 0
        and overall_score >= 85.0
        and technical_score >= 82.0
        and hr_score >= 80.0
    ):
        return RECOMMENDATION_STRONG_HIRE
    if (
        empty_count == 0
        and overall_score >= 75.0
        and technical_score >= 72.0
        and hr_score >= 70.0
    ):
        return RECOMMENDATION_OFFER
    if overall_score >= 60.0 and technical_score >= 58.0 and hr_score >= 55.0:
        return RECOMMENDATION_HIRE
    return RECOMMENDATION_NO_HIRE


def _build_seven_day_checklist(
    dim_avgs: dict[str, float],
    technical_score: float,
    hr_score: float,
    recommendation: str,
) -> list[ChecklistItem]:
    """根据薄弱维度动态生成具体可执行的 7 天改进清单。"""
    sorted_dims = sorted(dim_avgs.items(), key=lambda kv: kv[1])
    weakest_dim = sorted_dims[0][0]
    second_weakest_dim = sorted_dims[1][0]

    dim_labels = {
        "clarity": "表达结构与逻辑",
        "technical_depth": "技术深度与量化指标",
        "star_structure": "STAR 叙事闭环",
        "honesty_ownership": "诚实复盘与主人翁意识",
    }

    checklist = [
        ChecklistItem(
            day=1,
            focus_area=f"核心短板突破：{dim_labels[weakest_dim]}",
            action_item=(
                f"针对本场最弱维度（{dim_labels[weakest_dim]}，均分 {dim_avgs[weakest_dim]:.1f}），"
                "重写 2 分钟自我介绍与核心项目逐字稿，逐句对齐量化收益。"
            ),
            deliverable="修订版自我介绍逐字稿 + 3 条 STAR 项目卡片",
        ),
        ChecklistItem(
            day=2,
            focus_area="RAG 与检索架构深挖",
            action_item="复盘 BM25 + Dense + RRF 融合排序与 Cross-Encoder Rerank 权衡，准备 P95 延迟与 Recall@5 对比数据。",
            deliverable="1 页 RAG 架构白板演练图与 Q&A 备忘录",
        ),
        ChecklistItem(
            day=3,
            focus_area="Agent 工具安全与 HITL 状态机",
            action_item="梳理 FastAPI SSE 流式挂起恢复、SQLite 幂等状态流转及 PII 脱敏拦截的边界异常案例。",
            deliverable="HITL 幂等状态机时序图与 5 个高频追问标准答案",
        ),
        ChecklistItem(
            day=4,
            focus_area="场景手撕与高并发容错",
            action_item="限时 30 分钟手写“幂等审批令牌桶 + 超时熔断降级”核心代码，并分析时间/空间复杂度。",
            deliverable="可通过 pytest 压测的容错代码片段",
        ),
        ChecklistItem(
            day=5,
            focus_area=f"次弱项强化：{dim_labels[second_weakest_dim]}",
            action_item=(
                f"围绕 {dim_labels[second_weakest_dim]}（均分 {dim_avgs[second_weakest_dim]:.1f}），"
                "录屏模拟回答“线上故障复盘”与“跨团队技术分歧”各 1 次。"
            ),
            deliverable="2 段行为面试复盘录音与自检打分表",
        ),
        ChecklistItem(
            day=6,
            focus_area="压力追问与边界诚实度训练",
            action_item=(
                f"当前 HR 面 {hr_score:.1f} 分 / 技术面 {technical_score:.1f} 分，针对未知问题练习"
                "“明确边界 + 推导思路 + 验证路径”的诚实作答模板，杜绝空话与甩锅。"
            ),
            deliverable="10 道高压追问（反问面试官清单含在内）应对卡片",
        ),
        ChecklistItem(
            day=7,
            focus_area="全真定时模考与状态校准",
            action_item=(
                f"基于当前评级 `{recommendation}`，使用 MockInterviewEngine 完成一轮 4 环节全真模拟，"
                "目标将四维均分稳定提升至 80+。"
            ),
            deliverable="新一轮模拟面试报告（目标 Strong-Hire / Offer）",
        ),
    ]
    return checklist


def generate_interview_feedback(
    evaluations: Sequence[TurnEvaluation],
    candidate_name: str = "候选人",
    target_role: str = "AI Agent Engineer",
) -> InterviewFeedbackReport:
    """汇总技术面与 HR 面各轮评估，生成录用建议与 7 天改进清单。"""
    if not evaluations:
        raise ValueError("evaluations 不能为空，至少需要完成一轮面试评估。")

    tech_turns = [t for t in evaluations if t.category == "technical"]
    hr_turns = [t for t in evaluations if t.category == "hr"]

    technical_score = (
        round(sum(t.weighted_score for t in tech_turns) / len(tech_turns), 2)
        if tech_turns
        else 0.0
    )
    hr_score = (
        round(sum(t.weighted_score for t in hr_turns) / len(hr_turns), 2)
        if hr_turns
        else 0.0
    )

    if tech_turns and hr_turns:
        overall_score = round(technical_score * 0.7 + hr_score * 0.3, 2)
    elif tech_turns:
        overall_score = technical_score
    else:
        overall_score = hr_score

    n = len(evaluations)
    dim_avgs = {
        "clarity": round(sum(t.scores.clarity for t in evaluations) / n, 2),
        "technical_depth": round(sum(t.scores.technical_depth for t in evaluations) / n, 2),
        "star_structure": round(sum(t.scores.star_structure for t in evaluations) / n, 2),
        "honesty_ownership": round(sum(t.scores.honesty_ownership for t in evaluations) / n, 2),
    }

    empty_count = sum(1 for t in evaluations if t.is_empty)
    recommendation = _decide_recommendation(
        overall_score=overall_score,
        technical_score=technical_score,
        hr_score=hr_score,
        empty_count=empty_count,
    )

    strengths: list[str] = []
    weaknesses: list[str] = []
    for t in evaluations:
        for s in t.strengths:
            if s not in strengths:
                strengths.append(s)
        for w in t.improvements:
            if w not in weaknesses:
                weaknesses.append(w)

    if not strengths:
        strengths.append("暂未发现明显亮点，建议先夯实基础 STAR 表达与核心技术指标。")
    if not weaknesses:
        weaknesses.append("整体表现均衡，可进一步打磨高并发极端场景的架构权衡深度。")

    checklist = _build_seven_day_checklist(
        dim_avgs=dim_avgs,
        technical_score=technical_score,
        hr_score=hr_score,
        recommendation=recommendation,
    )

    return InterviewFeedbackReport(
        candidate_name=candidate_name,
        target_role=target_role,
        technical_score=technical_score,
        hr_score=hr_score,
        overall_score=overall_score,
        recommendation=recommendation,
        dimension_averages=dim_avgs,
        turn_evaluations=list(evaluations),
        strengths=strengths,
        weaknesses=weaknesses,
        seven_day_checklist=checklist,
    )


class MockInterviewEngine:
    """一对一全真模拟面试引擎（支持技术面 + HR 面多轮状态流转）。"""

    def __init__(
        self,
        candidate_name: str = "陈默",
        target_role: str = "AI Agent Engineer",
        rounds: Sequence[InterviewRoundSpec] = DEFAULT_ROUNDS,
    ) -> None:
        if not rounds:
            raise ValueError("rounds 不能为空")
        self.candidate_name = candidate_name
        self.target_role = target_role
        self._rounds: tuple[InterviewRoundSpec, ...] = tuple(rounds)
        self._current_index: int = 0
        self._started: bool = False
        self._evaluations: list[TurnEvaluation] = []

    @property
    def is_finished(self) -> bool:
        return self._current_index >= len(self._rounds)

    @property
    def progress(self) -> tuple[int, int]:
        return (len(self._evaluations), len(self._rounds))

    @property
    def evaluations(self) -> list[TurnEvaluation]:
        return list(self._evaluations)

    def start_interview(self) -> InterviewRoundSpec:
        """初始化/重置面试会话并返回首轮问题。"""
        self._current_index = 0
        self._started = True
        self._evaluations = []
        return self._rounds[0]

    def current_round(self) -> InterviewRoundSpec | None:
        """获取当前待作答的面试轮次；若已结束则返回 None。"""
        if not self._started:
            self._started = True
        if self.is_finished:
            return None
        return self._rounds[self._current_index]

    def submit_response(self, response: str) -> TurnEvaluation:
        """提交当前轮次回答，完成四维评分并推进至下一轮。"""
        if not self._started:
            self._started = True
        if self.is_finished:
            raise RuntimeError("模拟面试已全部结束，请调用 generate_feedback() 获取评估报告。")

        round_spec = self._rounds[self._current_index]
        evaluation = evaluate_response(round_spec, response)
        self._evaluations.append(evaluation)
        self._current_index += 1
        return evaluation

    def generate_feedback(self) -> InterviewFeedbackReport:
        """生成完整的技术面 + HR 面综合反馈报告与 7 天改进清单。"""
        return generate_interview_feedback(
            evaluations=self._evaluations,
            candidate_name=self.candidate_name,
            target_role=self.target_role,
        )
