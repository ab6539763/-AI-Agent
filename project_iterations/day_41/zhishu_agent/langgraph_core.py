"""Day 41 核心模块：轻量级 LangGraph 兼容状态图引擎与企业智能体编排 (v0.4.0-day41).

提供零外部依赖的 `StateGraph`、`START`、`END`、`CompiledGraph`（支持 `invoke`、`stream`、
`to_mermaid()`、普通边、条件边与有界循环），并内置：
1. ReAct 工具调用循环图 (`build_react_graph`)
2. 高风险操作/费用报销人工审批流图 (`build_approval_graph`)
"""

from __future__ import annotations

import operator
import re
from copy import deepcopy
from typing import Annotated, Any, Callable, Iterator, TypedDict, get_args, get_origin, get_type_hints

START = "__start__"
END = "__end__"


class GraphRecursionError(RuntimeError):
    """当状态图循环执行步数超过 `recursion_limit` 时抛出，防止死循环."""


class GraphValidationError(ValueError):
    """当状态图拓扑结构不合法（如缺少入口、悬空边或重复节点）时抛出."""


def add_messages(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """LangGraph 风格消息列表归约器（Reducer）：追加新消息而不覆盖历史."""
    return [*left, *right]


def _extract_reducers(state_schema: type[Any] | None) -> dict[str, Callable[[Any, Any], Any]]:
    """从 TypedDict 状态模式中提取 `Annotated[T, reducer]` 字段的归约函数."""
    if state_schema is None:
        return {}
    try:
        hints = get_type_hints(state_schema, include_extras=True)
    except Exception:
        return {}

    reducers: dict[str, Callable[[Any, Any], Any]] = {}
    for field_name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            for meta in args[1:]:
                if callable(meta):
                    reducers[field_name] = meta
                    break
    return reducers


def _merge_state(
    current: dict[str, Any],
    update: dict[str, Any] | None,
    reducers: dict[str, Callable[[Any, Any], Any]],
) -> dict[str, Any]:
    """将节点返回的状态增量合并到当前全局状态中."""
    if not update:
        return current
    next_state = deepcopy(current)
    for key, value in update.items():
        if key in reducers and key in next_state:
            next_state[key] = reducers[key](next_state[key], value)
        else:
            next_state[key] = deepcopy(value)
    return next_state


class CompiledGraph:
    """编译后的可执行状态图，支持 `invoke`、`stream` 与 `to_mermaid` 导出."""

    def __init__(
        self,
        nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]],
        edges: dict[str, str],
        conditional_edges: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str] | None]],
        reducers: dict[str, Callable[[Any, Any], Any]],
        interrupt_before: list[str] | None = None,
    ) -> None:
        self._nodes = dict(nodes)
        self._edges = dict(edges)
        self._conditional_edges = dict(conditional_edges)
        self._reducers = dict(reducers)
        self._interrupt_before = set(interrupt_before or [])

    def _next_node(self, current: str, state: dict[str, Any]) -> str:
        """根据普通边或条件边计算下一个目标节点名称."""
        if current in self._edges:
            return self._edges[current]
        if current in self._conditional_edges:
            router_fn, path_map = self._conditional_edges[current]
            route_key = router_fn(deepcopy(state))
            if path_map is not None:
                if route_key not in path_map:
                    raise GraphValidationError(
                        f"条件边路由返回值 '{route_key}' 不在路径映射 {list(path_map.keys())} 中"
                    )
                return path_map[route_key]
            return route_key
        return END

    def stream(
        self,
        initial_state: dict[str, Any],
        *,
        config: dict[str, Any] | None = None,
        stream_mode: str = "updates",
    ) -> Iterator[dict[str, Any]]:
        """按图执行步骤流式产出每个节点的状态更新（`updates`）或全量快照（`values`）."""
        if stream_mode not in {"updates", "values"}:
            raise ValueError(f"不支持的 stream_mode: {stream_mode}，仅支持 'updates' 或 'values'")

        cfg = config or {}
        recursion_limit = int(cfg.get("recursion_limit", 25))
        if recursion_limit < 1:
            raise ValueError("recursion_limit 必须大于等于 1")

        state = deepcopy(initial_state)
        current = self._next_node(START, state)
        steps = 0

        while current != END:
            if current in self._interrupt_before and not cfg.get("resume", False):
                yield {"__interrupt__": {"node": current, "state": deepcopy(state)}}
                return

            if steps >= recursion_limit:
                raise GraphRecursionError(
                    f"状态图执行步数达到上限 recursion_limit={recursion_limit}，疑似存在未收敛循环 (当前节点: {current})"
                )

            if current not in self._nodes:
                raise GraphValidationError(f"未找到节点 '{current}'")

            node_fn = self._nodes[current]
            update = node_fn(deepcopy(state)) or {}
            state = _merge_state(state, update, self._reducers)
            steps += 1

            if stream_mode == "updates":
                yield {current: deepcopy(update)}
            else:
                yield deepcopy(state)

            current = self._next_node(current, state)

    def invoke(
        self,
        initial_state: dict[str, Any],
        *,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """同步执行状态图直至到达 `END`（或触发中断），返回最终合并后的状态字典."""
        final_state = deepcopy(initial_state)
        for snapshot in self.stream(initial_state, config=config, stream_mode="values"):
            if "__interrupt__" in snapshot:
                return snapshot
            final_state = snapshot
        return final_state

    def to_mermaid(self) -> str:
        """将当前状态图拓扑导出为 Mermaid `stateDiagram-v2` 文本."""
        lines: list[str] = ["stateDiagram-v2"]

        def _fmt(node_name: str) -> str:
            return "[*]" if node_name in {START, END} else node_name

        # 先输出 START 边，保持图顶部入口清晰
        if START in self._edges:
            lines.append(f"    {_fmt(START)} --> {_fmt(self._edges[START])}")
        elif START in self._conditional_edges:
            _, path_map = self._conditional_edges[START]
            if path_map:
                for label, target in path_map.items():
                    lines.append(f"    {_fmt(START)} --> {_fmt(target)} : {label}")

        for source, target in self._edges.items():
            if source == START:
                continue
            lines.append(f"    {_fmt(source)} --> {_fmt(target)}")

        for source, (_, path_map) in self._conditional_edges.items():
            if source == START:
                continue
            if path_map:
                for label, target in path_map.items():
                    lines.append(f"    {_fmt(source)} --> {_fmt(target)} : {label}")
            else:
                lines.append(f"    {_fmt(source)} --> {END} : dynamic")

        return "\n".join(lines)


class StateGraph:
    """LangGraph 风格状态图构建器，支持节点、普通边、条件边与循环."""

    def __init__(self, state_schema: type[Any] | None = None) -> None:
        self._state_schema = state_schema
        self._reducers = _extract_reducers(state_schema)
        self._nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[
            str, tuple[Callable[[dict[str, Any]], str], dict[str, str] | None]
        ] = {}

    def add_node(
        self,
        name: str,
        action: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> StateGraph:
        """向状态图注册一个处理节点."""
        if name in {START, END}:
            raise GraphValidationError(f"节点名称不能使用保留字 '{name}'")
        if name in self._nodes:
            raise GraphValidationError(f"节点 '{name}' 已存在，禁止重复注册")
        self._nodes[name] = action
        return self

    def add_edge(self, source: str, target: str) -> StateGraph:
        """添加一条从 `source` 到 `target` 的确定性有向边."""
        if source == END:
            raise GraphValidationError("END 节点不能作为有向边的起点")
        if target == START:
            raise GraphValidationError("START 节点不能作为有向边的终点")
        if source in self._conditional_edges:
            raise GraphValidationError(f"节点 '{source}' 已注册条件边，不能再添加普通边")
        self._edges[source] = target
        return self

    def add_conditional_edges(
        self,
        source: str,
        path: Callable[[dict[str, Any]], str],
        path_map: dict[str, str] | None = None,
    ) -> StateGraph:
        """为节点 `source` 添加条件分支边（支持分支映射或直接返回目标节点名）."""
        if source == END:
            raise GraphValidationError("END 节点不能作为条件边的起点")
        if source in self._edges:
            raise GraphValidationError(f"节点 '{source}' 已注册普通边，不能再添加条件边")
        self._conditional_edges[source] = (path, dict(path_map) if path_map is not None else None)
        return self

    def set_entry_point(self, key: str) -> StateGraph:
        """设置入口节点，等价于 `add_edge(START, key)`."""
        return self.add_edge(START, key)

    def set_finish_point(self, key: str) -> StateGraph:
        """设置结束节点，等价于 `add_edge(key, END)`."""
        return self.add_edge(key, END)

    def _validate(self) -> None:
        """校验图结构的连通性与节点引用完整性."""
        if START not in self._edges and START not in self._conditional_edges:
            raise GraphValidationError("状态图缺少入口边（请使用 add_edge(START, ...) 或 set_entry_point）")

        valid_sources = set(self._nodes.keys()) | {START}
        valid_targets = set(self._nodes.keys()) | {END}

        for src, dst in self._edges.items():
            if src not in valid_sources:
                raise GraphValidationError(f"普通边起点 '{src}' 未注册")
            if dst not in valid_targets:
                raise GraphValidationError(f"普通边终点 '{dst}' 未注册")

        for src, (_, path_map) in self._conditional_edges.items():
            if src not in valid_sources:
                raise GraphValidationError(f"条件边起点 '{src}' 未注册")
            if path_map is not None:
                for label, dst in path_map.items():
                    if dst not in valid_targets:
                        raise GraphValidationError(f"条件边 '{src}' 分支 '{label}' 目标 '{dst}' 未注册")

    def compile(self, *, interrupt_before: list[str] | None = None) -> CompiledGraph:
        """校验拓扑结构并编译为可执行的 `CompiledGraph`."""
        self._validate()
        return CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            reducers=self._reducers,
            interrupt_before=interrupt_before,
        )


# ============================================================================
# 示例图 1：ReAct 工具调用循环图 (Reason -> Tool -> Observation -> Reason)
# ============================================================================


class ReActState(TypedDict, total=False):
    """ReAct 智能体状态定义."""

    query: str
    messages: Annotated[list[dict[str, Any]], operator.add]
    iteration: int
    pending_tool: str | None
    pending_tool_input: str | None
    final_answer: str | None


def _default_react_tools() -> dict[str, Callable[[str], str]]:
    """内置确定性工具集（用于离线演示与单元测试）."""

    def calculator(expr: str) -> str:
        # 仅允许安全四则运算字符，严禁使用 eval
        cleaned = expr.strip()
        if not re.fullmatch(r"[0-9+\-*/().\s]+", cleaned):
            return f"不支持的算式: {cleaned}"
        try:
            tokens = re.findall(r"\d+(?:\.\d+)?|[+\-*/]", cleaned)
            if len(tokens) == 3 and tokens[1] in {"+", "-", "*", "/"}:
                a, op, b = float(tokens[0]), tokens[1], float(tokens[2])
                ops = {
                    "+": a + b,
                    "-": a - b,
                    "*": a * b,
                    "/": a / b if b != 0 else float("inf"),
                }
                res = ops[op]
                return str(int(res)) if res == int(res) else f"{res:.2f}"
            return f"已解析表达式: {cleaned}"
        except Exception as exc:
            return f"计算异常: {exc}"

    def kb_search(keyword: str) -> str:
        kb = {
            "差旅": "星辰数科差旅规范：一线城市住宿上限 600 元/晚，二线城市 450 元/晚。",
            "报销": "星辰数科报销规范：单笔超过 1000 元需部门总监人工审批。",
        }
        for k, v in kb.items():
            if k in keyword:
                return v
        return f"知识库中未找到与 '{keyword}' 相关的制度。"

    return {"calculator": calculator, "kb_search": kb_search}


def build_react_graph(
    tools: dict[str, Callable[[str], str]] | None = None,
    *,
    max_iterations: int = 5,
) -> CompiledGraph:
    """构建标准的 ReAct 循环状态图：Reason <-> Tools."""
    tool_registry = tools if tools is not None else _default_react_tools()

    def reason_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")
        messages = state.get("messages", [])
        iteration = state.get("iteration", 0)

        observations = [m for m in messages if m.get("role") == "tool"]
        if observations:
            last_obs = observations[-1]["content"]
            return {
                "pending_tool": None,
                "pending_tool_input": None,
                "final_answer": f"已完成检索/计算，结果：{last_obs}",
                "messages": [{"role": "assistant", "content": f"最终回答：{last_obs}"}],
            }

        if iteration >= max_iterations:
            return {
                "pending_tool": None,
                "final_answer": "达到最大推理轮次限制，停止工具调用。",
            }

        # 简单确定性路由规则：匹配数学表达式或知识库关键词
        math_match = re.search(r"(\d+\s*[+\-*/]\s*\d+)", query)
        if math_match and "calculator" in tool_registry:
            expr = math_match.group(1)
            return {
                "pending_tool": "calculator",
                "pending_tool_input": expr,
                "messages": [{"role": "assistant", "content": f"Thought: 需要计算 {expr}，调用 calculator"}],
            }

        if any(kw in query for kw in ("差旅", "报销", "住宿", "制度")) and "kb_search" in tool_registry:
            return {
                "pending_tool": "kb_search",
                "pending_tool_input": query,
                "messages": [{"role": "assistant", "content": "Thought: 需要查询企业制度，调用 kb_search"}],
            }

        return {
            "pending_tool": None,
            "final_answer": f"直接回答：{query}",
            "messages": [{"role": "assistant", "content": f"直接回答：{query}"}],
        }

    def tools_node(state: dict[str, Any]) -> dict[str, Any]:
        tool_name = state.get("pending_tool") or ""
        tool_input = state.get("pending_tool_input") or ""
        iteration = state.get("iteration", 0)
        if tool_name not in tool_registry:
            obs = f"错误：未知工具 '{tool_name}'"
        else:
            obs = tool_registry[tool_name](tool_input)
        return {
            "iteration": iteration + 1,
            "pending_tool": None,
            "pending_tool_input": None,
            "messages": [{"role": "tool", "name": tool_name, "content": obs}],
        }

    def route_after_reason(state: dict[str, Any]) -> str:
        if state.get("pending_tool") and state.get("iteration", 0) < max_iterations:
            return "tools"
        return "done"

    graph = StateGraph(ReActState)
    graph.add_node("reason", reason_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", route_after_reason, {"tools": "tools", "done": END})
    graph.add_edge("tools", "reason")
    return graph.compile()


# ============================================================================
# 示例图 2：费用/高风险操作人工审批流图 (Human-in-the-Loop Approval Graph)
# ============================================================================


class ApprovalState(TypedDict, total=False):
    """费用报销与高风险操作审批状态定义."""

    request_id: str
    applicant: str
    action_type: str
    amount: float
    reason: str
    human_decision: bool | None
    risk_level: str
    approval_status: str
    reviewer_comment: str
    execution_result: str
    audit_log: Annotated[list[str], operator.add]


HIGH_RISK_ACTIONS = {"delete_prod_db", "prod_deploy", "bulk_transfer"}


def build_approval_graph(
    *,
    auto_approve_limit: float = 1000.0,
    approver_fn: Callable[[dict[str, Any]], bool] | None = None,
) -> CompiledGraph:
    """构建企业费用报销与高风险操作人工审批流图."""

    def risk_assess(state: dict[str, Any]) -> dict[str, Any]:
        amount = float(state.get("amount", 0.0))
        action_type = state.get("action_type", "expense")
        is_high = action_type in HIGH_RISK_ACTIONS or amount > auto_approve_limit
        risk = "high" if is_high else "low"
        return {
            "risk_level": risk,
            "approval_status": "pending",
            "audit_log": [f"[risk_assess] action={action_type}, amount={amount}, risk={risk}"],
        }

    def auto_approve(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "approval_status": "approved",
            "reviewer_comment": f"系统自动审批通过（金额 <= {auto_approve_limit} 且非高危操作）",
            "audit_log": ["[auto_approve] 自动审批通过"],
        }

    def human_review(state: dict[str, Any]) -> dict[str, Any]:
        if approver_fn is not None:
            approved = bool(approver_fn(state))
        elif state.get("human_decision") is not None:
            approved = bool(state["human_decision"])
        else:
            # 默认安全策略：无人工明确授权时拒绝高风险操作
            approved = False

        status = "approved" if approved else "rejected"
        comment = "人工审批通过" if approved else "人工审批驳回（未获授权）"
        return {
            "approval_status": status,
            "reviewer_comment": comment,
            "audit_log": [f"[human_review] status={status}"],
        }

    def execute_action(state: dict[str, Any]) -> dict[str, Any]:
        req_id = state.get("request_id", "UNKNOWN")
        action_type = state.get("action_type", "expense")
        return {
            "execution_result": f"已执行请求 {req_id} ({action_type})",
            "audit_log": [f"[execute_action] {req_id} 执行完成"],
        }

    def reject_action(state: dict[str, Any]) -> dict[str, Any]:
        req_id = state.get("request_id", "UNKNOWN")
        return {
            "execution_result": f"请求 {req_id} 已被驳回，终止执行",
            "audit_log": [f"[reject_action] {req_id} 已拦截"],
        }

    def route_by_risk(state: dict[str, Any]) -> str:
        return "high_risk" if state.get("risk_level") == "high" else "low_risk"

    def route_by_approval(state: dict[str, Any]) -> str:
        return "approved" if state.get("approval_status") == "approved" else "rejected"

    graph = StateGraph(ApprovalState)
    graph.add_node("risk_assess", risk_assess)
    graph.add_node("auto_approve", auto_approve)
    graph.add_node("human_review", human_review)
    graph.add_node("execute_action", execute_action)
    graph.add_node("reject_action", reject_action)

    graph.add_edge(START, "risk_assess")
    graph.add_conditional_edges(
        "risk_assess",
        route_by_risk,
        {"low_risk": "auto_approve", "high_risk": "human_review"},
    )
    graph.add_edge("auto_approve", "execute_action")
    graph.add_conditional_edges(
        "human_review",
        route_by_approval,
        {"approved": "execute_action", "rejected": "reject_action"},
    )
    graph.add_edge("execute_action", END)
    graph.add_edge("reject_action", END)
    return graph.compile()
