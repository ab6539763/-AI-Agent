"""纯 Python ReAct 智能体引擎 (v0.4.0-day39 · 无框架依赖).

实现经典的 Thought -> Action -> Action Input -> Observation -> Final Answer
推理-行动循环，内置安全 AST 计算器、离线企业知识检索工具、正则输出解析器、
max_steps 防死循环守卫以及确定性 Mock LLM 规划器。
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# 1. 核心数据结构
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """智能体可调用的工具定义."""

    name: str
    description: str
    func: Callable[[str], str]


@dataclass
class ReActStep:
    """单步 ReAct 推理与工具执行轨迹."""

    step_number: int
    thought: str
    action: str | None = None
    action_input: str | None = None
    observation: str | None = None
    final_answer: str | None = None
    raw_output: str = ""


@dataclass
class ReActTrace:
    """完整 ReAct 执行轨迹与最终结果."""

    query: str
    steps: list[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    stopped_reason: str = "final_answer"

    def format_trace(self) -> str:
        """格式化输出人类可读的 ReAct 推理轨迹."""
        lines: list[str] = [f"Query: {self.query}", "-" * 60]
        for step in self.steps:
            lines.append(f"[Step {step.step_number}]")
            lines.append(f"  Thought: {step.thought}")
            if step.action is not None:
                lines.append(f"  Action: {step.action}")
                lines.append(f"  Action Input: {step.action_input or ''}")
            if step.observation is not None:
                lines.append(f"  Observation: {step.observation}")
            if step.final_answer is not None:
                lines.append(f"  Final Answer: {step.final_answer}")
        lines.append("-" * 60)
        lines.append(f"Stopped Reason: {self.stopped_reason}")
        lines.append(f"Final Answer: {self.final_answer}")
        return "\n".join(lines)


@dataclass
class ParsedAction:
    """从 LLM 输出中解析出的工具调用指令."""

    thought: str
    action: str
    action_input: str


@dataclass
class ParsedFinalAnswer:
    """从 LLM 输出中解析出的最终回答."""

    thought: str
    final_answer: str


# ---------------------------------------------------------------------------
# 2. 内置安全工具：AST 计算器 & 离线知识检索
# ---------------------------------------------------------------------------

_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_ast_node(node: ast.AST) -> float:
    """递归求值受限的算术 AST 节点，严禁任意代码执行."""
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ValueError(f"不支持的二元运算符: {op_type.__name__}")
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("除数不能为零")
        if op_type is ast.Pow and abs(right) > 1000:
            raise ValueError("指数过大，已触发安全限制")
        return _BIN_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        return _UNARY_OPS[op_type](_eval_ast_node(node.operand))
    raise ValueError(f"禁止的语法结构: {type(node).__name__}")


def calculator_tool(expression: str) -> str:
    """基于 Python AST 的安全数学表达式计算器（禁用 eval/exec）."""
    expr = expression.strip()
    if not expr:
        return "计算错误: 表达式不能为空"
    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_ast_node(tree)
    except ZeroDivisionError as exc:
        return f"计算错误: {exc}"
    except (SyntaxError, ValueError) as exc:
        return f"计算错误: {exc}"

    if result.is_integer():
        return str(int(result))
    return f"{result:.6g}"


DEFAULT_KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "title": "星辰数科差旅住宿报销标准",
        "keywords": "差旅 住宿 报销 标准 高级工程师 酒店 预算",
        "content": (
            "星辰数科员工一线城市出差住宿报销上限：普通工程师 350 元/晚，"
            "高级工程师 450 元/晚，技术专家及总监 650 元/晚；餐补统一为 100 元/天。"
        ),
    },
    {
        "title": "星辰数科带薪年假与病假制度",
        "keywords": "年假 病假 假期 请假 制度 考勤",
        "content": (
            "入职满 1 年不满 10 年享有 5 天带薪年假；满 10 年享有 10 天。"
            "每年享有 5 天全薪病假，需在 OA 系统附三甲医院就诊证明。"
        ),
    },
    {
        "title": "智枢平台算力与 GPU 配额规范",
        "keywords": "智枢 GPU 算力 配额 模型 部署 推理",
        "content": (
            "智枢生产集群默认单租户并发限制为 20 QPS，测试环境单次申请最多分配 "
            "2 张 A10G GPU，单张显存 24GB，最长连续占用 72 小时。"
        ),
    },
    {
        "title": "办公设备领用与采购审批流程",
        "keywords": "设备 电脑 MacBook 采购 审批 IT 资产",
        "content": (
            "研发岗位入职标配 MacBook Pro 14 寸（16G/512G），升级至 32G 内存需"
            "部门总监与 IT 负责人双审批，审批周期约 3 个工作日。"
        ),
    },
]


def knowledge_search_tool(
    query: str,
    knowledge_base: list[dict[str, str]] | None = None,
) -> str:
    """离线企业知识库检索工具（基于关键词与双字切片匹配）."""
    kb = knowledge_base if knowledge_base is not None else DEFAULT_KNOWLEDGE_BASE
    cleaned = query.strip().lower()
    if not cleaned:
        return "检索失败: 查询关键词不能为空"

    # 提取英文/数字词元与中文双字切片以提升离线召回率
    tokens = set(re.findall(r"[a-z0-9_]+", cleaned))
    cn_chars = "".join(re.findall(r"[\u4e00-\u9fff]", cleaned))
    for i in range(len(cn_chars) - 1):
        tokens.add(cn_chars[i : i + 2])
    if len(cn_chars) == 1:
        tokens.add(cn_chars)

    scored: list[tuple[int, dict[str, str]]] = []
    for doc in kb:
        haystack = f"{doc['title']} {doc['keywords']} {doc['content']}".lower()
        score = sum(1 for tok in tokens if tok in haystack)
        if score > 0:
            scored.append((score, doc))

    if not scored:
        return f"未在企业知识库中找到与 '{query}' 相关的制度记录。"

    scored.sort(key=lambda item: item[0], reverse=True)
    top_docs = [doc for _, doc in scored[:2]]
    return "\n".join(f"[{d['title']}] {d['content']}" for d in top_docs)


# ---------------------------------------------------------------------------
# 3. ReAct 正则输出解析器
# ---------------------------------------------------------------------------

_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\n(?:Action|Final Answer):|\Z)", re.DOTALL)
_FINAL_ANSWER_RE = re.compile(r"Final Answer:\s*(.+)\Z", re.DOTALL)
_ACTION_RE = re.compile(r"Action:\s*([A-Za-z0-9_.-]+)")
_ACTION_INPUT_RE = re.compile(r"Action Input:\s*(.*?)(?=\nObservation:|\Z)", re.DOTALL)


def parse_react_output(text: str) -> ParsedAction | ParsedFinalAnswer:
    """解析 LLM 输出中的 Thought / Action / Action Input / Final Answer."""
    thought_match = _THOUGHT_RE.search(text)
    thought = thought_match.group(1).strip() if thought_match else ""

    final_match = _FINAL_ANSWER_RE.search(text)
    if final_match:
        return ParsedFinalAnswer(
            thought=thought,
            final_answer=final_match.group(1).strip(),
        )

    action_match = _ACTION_RE.search(text)
    if action_match:
        action_name = action_match.group(1).strip()
        input_match = _ACTION_INPUT_RE.search(text)
        action_input = input_match.group(1).strip() if input_match else ""
        return ParsedAction(
            thought=thought,
            action=action_name,
            action_input=action_input,
        )

    raise ValueError(f"无法从模型输出中解析 Action 或 Final Answer:\n{text}")


# ---------------------------------------------------------------------------
# 4. 确定性 Mock LLM 规划器（用于无 API Key 教学与测试）
# ---------------------------------------------------------------------------


def default_mock_planner(query: str, steps: list[ReActStep]) -> str:
    """确定性模拟 LLM 规划器，支持单步与多跳 ReAct 推理演示."""
    q = query.strip()

    # 场景 A：多跳组合问题（先查制度标准，再做预算计算）
    if ("住宿" in q or "差旅" in q) and ("计算" in q or "总" in q or "天" in q or "晚" in q):
        if len(steps) == 0:
            return (
                "Thought: 需要先查询星辰数科的差旅住宿报销标准，再根据天数计算总预算。\n"
                "Action: knowledge_search\n"
                "Action Input: 高级工程师 差旅 住宿 报销 标准"
            )
        if len(steps) == 1:
            obs = steps[0].observation or ""
            rate_match = re.search(r"高级工程师\s*(\d+)\s*元", obs)
            rate = rate_match.group(1) if rate_match else "450"
            days_match = re.search(r"(\d+)\s*[天晚]", q)
            days = days_match.group(1) if days_match else "4"
            return (
                f"Thought: 已查到高级工程师住宿标准为 {rate} 元/晚，"
                f"接下来使用计算器计算 {days} 晚的总预算。\n"
                "Action: calculator\n"
                f"Action Input: {rate} * {days}"
            )
        total = steps[-1].observation or "未知"
        return (
            "Thought: 已经拿到精确的计算结果，可以汇总输出最终答案。\n"
            f"Final Answer: 根据星辰数科差旅制度，高级工程师住宿报销上限为 450 元/晚，"
            f"总住宿预算上限为 {total} 元。"
        )

    # 场景 B：纯数学计算问题
    math_match = re.search(r"([0-9+\-*/().\s]{3,})", q)
    if any(op in q for op in ("+", "-", "*", "/")) and math_match:
        if len(steps) == 0:
            expr = math_match.group(1).strip()
            return (
                "Thought: 这是一个数学计算问题，应该调用安全计算器工具避免心算幻觉。\n"
                "Action: calculator\n"
                f"Action Input: {expr}"
            )
        result = steps[-1].observation or ""
        return (
            "Thought: 计算器已返回准确结果，可以直接给出最终回答。\n"
            f"Final Answer: 表达式计算结果为 {result}。"
        )

    # 场景 C：企业知识检索问题
    kb_keywords = ("差旅", "报销", "年假", "病假", "gpu", "算力", "macbook", "设备", "审批")
    if any(kw in q.lower() for kw in kb_keywords):
        if len(steps) == 0:
            return (
                "Thought: 问题涉及星辰数科企业制度或平台规范，先调用知识库检索工具。\n"
                "Action: knowledge_search\n"
                f"Action Input: {q}"
            )
        obs = steps[-1].observation or ""
        return (
            "Thought: 已从企业知识库检索到相关条款，整理后回复用户。\n"
            f"Final Answer: {obs}"
        )

    # 场景 D：常规直接问答（无需工具）
    return (
        "Thought: 这是一个通用概念问题，无需调用外部工具即可直接回答。\n"
        f"Final Answer: 已收到您的问题「{q}」。我是智枢纯 Python ReAct 智能体，"
        "擅长通过 Thought-Action-Observation 循环调用计算器与企业知识库解决问题。"
    )


# ---------------------------------------------------------------------------
# 5. ReActAgent 主循环引擎
# ---------------------------------------------------------------------------


class ReActAgent:
    """纯 Python 实现的 ReAct（Reasoning + Acting）智能体引擎."""

    def __init__(
        self,
        tools: list[ToolSpec] | None = None,
        planner: Callable[[str, list[ReActStep]], str] | None = None,
        max_steps: int = 5,
    ) -> None:
        """初始化 ReAct 智能体，注册工具、规划器与最大步数守卫."""
        if max_steps < 1:
            raise ValueError("max_steps 必须大于等于 1")

        default_tools = [
            ToolSpec(
                name="calculator",
                description="安全数学表达式计算器，输入如 '(120 + 80) * 3'",
                func=calculator_tool,
            ),
            ToolSpec(
                name="knowledge_search",
                description="星辰数科离线企业知识库检索工具，输入检索关键词",
                func=knowledge_search_tool,
            ),
        ]
        tool_list = tools if tools is not None else default_tools
        self.tools: dict[str, ToolSpec] = {t.name: t for t in tool_list}
        self.planner = planner if planner is not None else default_mock_planner
        self.max_steps = max_steps

    def register_tool(self, tool: ToolSpec) -> None:
        """动态注册或覆盖一个工具."""
        self.tools[tool.name] = tool

    def build_system_prompt(self) -> str:
        """生成标准 ReAct 提示词模板（展示给 LLM 的工具契约）."""
        tool_lines = "\n".join(
            f"- {t.name}: {t.description}" for t in self.tools.values()
        )
        return (
            "你是一个遵循 ReAct 范式的企业智能体，可使用以下工具：\n"
            f"{tool_lines}\n\n"
            "请严格按照以下格式输出：\n"
            "Thought: 你的思考过程\n"
            "Action: 工具名称\n"
            "Action Input: 工具输入参数\n"
            "或者当你已有足够信息时输出：\n"
            "Thought: 你的总结思考\n"
            "Final Answer: 最终给用户的完整回答"
        )

    def run(self, query: str) -> ReActTrace:
        """执行 Thought -> Action -> Observation 循环直至 Final Answer 或 max_steps."""
        steps: list[ReActStep] = []

        for step_idx in range(1, self.max_steps + 1):
            raw_output = self.planner(query, steps)
            try:
                parsed = parse_react_output(raw_output)
            except ValueError as exc:
                steps.append(
                    ReActStep(
                        step_number=step_idx,
                        thought="输出格式解析失败",
                        observation=str(exc),
                        raw_output=raw_output,
                    )
                )
                return ReActTrace(
                    query=query,
                    steps=steps,
                    final_answer=f"执行中止：模型输出不符合 ReAct 协议 ({exc})",
                    stopped_reason="parse_error",
                )

            if isinstance(parsed, ParsedFinalAnswer):
                steps.append(
                    ReActStep(
                        step_number=step_idx,
                        thought=parsed.thought,
                        final_answer=parsed.final_answer,
                        raw_output=raw_output,
                    )
                )
                return ReActTrace(
                    query=query,
                    steps=steps,
                    final_answer=parsed.final_answer,
                    stopped_reason="final_answer",
                )

            # 执行工具调用
            tool = self.tools.get(parsed.action)
            if tool is None:
                available = ", ".join(sorted(self.tools))
                observation = f"工具错误: 未知工具 '{parsed.action}'，可用工具: {available}"
            else:
                try:
                    observation = tool.func(parsed.action_input)
                except Exception as exc:  # noqa: BLE001
                    observation = f"工具执行异常 ({parsed.action}): {exc}"

            steps.append(
                ReActStep(
                    step_number=step_idx,
                    thought=parsed.thought,
                    action=parsed.action,
                    action_input=parsed.action_input,
                    observation=observation,
                    raw_output=raw_output,
                )
            )

        return ReActTrace(
            query=query,
            steps=steps,
            final_answer=f"已达到最大推理步数限制 (max_steps={self.max_steps})，任务安全中止。",
            stopped_reason="max_steps",
        )
