"""Day 41 单元测试：验证 StateGraph、条件边、循环守卫、Mermaid 导出、ReAct 与人工审批流."""

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (  # noqa: E402
    END,
    START,
    GraphRecursionError,
    GraphValidationError,
    StateGraph,
    add_messages,
    build_approval_graph,
    build_react_graph,
)


class CounterState(TypedDict, total=False):
    count: int
    trace: Annotated[list[str], operator.add]
    messages: Annotated[list[dict[str, str]], add_messages]


def test_linear_graph_and_reducers() -> None:
    """测试普通边串联与 Annotated 归约器（operator.add / add_messages）."""
    g = StateGraph(CounterState)
    g.add_node("step1", lambda s: {"count": s.get("count", 0) + 1, "trace": ["s1"], "messages": [{"role": "user", "content": "hi"}]})
    g.add_node("step2", lambda s: {"count": s["count"] * 10, "trace": ["s2"], "messages": [{"role": "assistant", "content": "ok"}]})
    g.add_edge(START, "step1")
    g.add_edge("step1", "step2")
    g.add_edge("step2", END)

    app = g.compile()
    result = app.invoke({"count": 2, "trace": [], "messages": []})
    assert result["count"] == 30
    assert result["trace"] == ["s1", "s2"]
    assert len(result["messages"]) == 2


def test_conditional_edges_with_and_without_path_map() -> None:
    """测试条件边路由（带 path_map 与直接返回节点名）."""
    g = StateGraph()
    g.add_node("check", lambda s: {"score": s["score"]})
    g.add_node("pass_node", lambda s: {"status": "passed"})
    g.add_node("fail_node", lambda s: {"status": "failed"})

    g.set_entry_point("check")
    g.add_conditional_edges(
        "check",
        lambda s: "ok" if s["score"] >= 60 else "ng",
        {"ok": "pass_node", "ng": "fail_node"},
    )
    g.set_finish_point("pass_node")
    g.set_finish_point("fail_node")

    app = g.compile()
    assert app.invoke({"score": 85})["status"] == "passed"
    assert app.invoke({"score": 40})["status"] == "failed"

    # 无 path_map 时直接返回目标节点名称
    g2 = StateGraph()
    g2.add_node("router", lambda s: {})
    g2.add_node("fast", lambda s: {"lane": "fast"})
    g2.add_edge(START, "router")
    g2.add_conditional_edges("router", lambda s: "fast" if s.get("vip") else END)
    g2.add_edge("fast", END)
    app2 = g2.compile()
    assert app2.invoke({"vip": True})["lane"] == "fast"
    assert "lane" not in app2.invoke({"vip": False})


def test_cycle_and_recursion_limit_guard() -> None:
    """测试有界循环正常收敛与超限触发 GraphRecursionError 守卫."""
    g = StateGraph(CounterState)
    g.add_node("inc", lambda s: {"count": s.get("count", 0) + 1, "trace": [f"n={s.get('count', 0) + 1}"]})
    g.add_edge(START, "inc")
    g.add_conditional_edges("inc", lambda s: "loop" if s["count"] < 3 else "stop", {"loop": "inc", "stop": END})

    app = g.compile()
    res = app.invoke({"count": 0, "trace": []})
    assert res["count"] == 3
    assert res["trace"] == ["n=1", "n=2", "n=3"]

    # 限制 recursion_limit=2 时应触发死循环保护
    with pytest.raises(GraphRecursionError):
        app.invoke({"count": 0, "trace": []}, config={"recursion_limit": 2})


def test_stream_updates_and_values_and_interrupt() -> None:
    """测试 stream('updates')、stream('values') 以及 interrupt_before 中断机制."""
    g = StateGraph()
    g.add_node("a", lambda s: {"x": 1})
    g.add_node("b", lambda s: {"x": s["x"] + 2})
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)

    app = g.compile()
    updates = list(app.stream({}, stream_mode="updates"))
    assert updates == [{"a": {"x": 1}}, {"b": {"x": 3}}]

    values = list(app.stream({}, stream_mode="values"))
    assert values == [{"x": 1}, {"x": 3}]

    # 测试 interrupt_before
    interrupted_app = g.compile(interrupt_before=["b"])
    paused = interrupted_app.invoke({})
    assert "__interrupt__" in paused
    assert paused["__interrupt__"]["node"] == "b"
    assert paused["__interrupt__"]["state"] == {"x": 1}


def test_to_mermaid_export() -> None:
    """测试 to_mermaid() 导出合法的 stateDiagram-v2 拓扑文本."""
    react_app = build_react_graph()
    mermaid_text = react_app.to_mermaid()
    assert mermaid_text.startswith("stateDiagram-v2")
    assert "[*] --> reason" in mermaid_text
    assert "reason --> tools : tools" in mermaid_text
    assert "reason --> [*] : done" in mermaid_text
    assert "tools --> reason" in mermaid_text


def test_graph_validation_errors() -> None:
    """测试非法图结构校验（缺少入口、重复节点、未知目标）."""
    g = StateGraph()
    g.add_node("a", lambda s: {})
    with pytest.raises(GraphValidationError):
        g.compile()  # 缺少 START 入口

    with pytest.raises(GraphValidationError):
        g.add_node("a", lambda s: {})  # 重复节点

    g.add_edge(START, "missing_node")
    with pytest.raises(GraphValidationError):
        g.compile()


def test_react_graph_tool_cycle_and_direct_answer() -> None:
    """测试 ReAct 图的工具调用循环（calculator / kb_search）与直接回答分支."""
    app = build_react_graph(max_iterations=3)

    calc_res = app.invoke({"query": "请帮我计算 12 * 8", "messages": [], "iteration": 0})
    assert calc_res["iteration"] == 1
    assert "96" in (calc_res["final_answer"] or "")

    kb_res = app.invoke({"query": "一线城市差旅住宿标准是多少？", "messages": [], "iteration": 0})
    assert kb_res["iteration"] == 1
    assert "600" in (kb_res["final_answer"] or "")

    direct_res = app.invoke({"query": "你好，介绍一下你自己", "messages": [], "iteration": 0})
    assert direct_res["iteration"] == 0
    assert "直接回答" in (direct_res["final_answer"] or "")


def test_approval_graph_paths() -> None:
    """测试费用/高风险操作人工审批流的三条路径：自动通过、人工通过、人工驳回."""
    app = build_approval_graph(auto_approve_limit=1000.0)

    # 1. 低额度自动通过
    low = app.invoke({"request_id": "R1", "action_type": "expense", "amount": 500.0, "audit_log": []})
    assert low["risk_level"] == "low"
    assert low["approval_status"] == "approved"
    assert "已执行" in low["execution_result"]

    # 2. 高额度人工审批通过
    high_ok = app.invoke(
        {"request_id": "R2", "action_type": "expense", "amount": 2500.0, "human_decision": True, "audit_log": []}
    )
    assert high_ok["risk_level"] == "high"
    assert high_ok["approval_status"] == "approved"
    assert "已执行" in high_ok["execution_result"]

    # 3. 高风险操作默认/人工驳回
    high_reject = app.invoke(
        {"request_id": "R3", "action_type": "delete_prod_db", "amount": 0.0, "audit_log": []}
    )
    assert high_reject["risk_level"] == "high"
    assert high_reject["approval_status"] == "rejected"
    assert "驳回" in high_reject["execution_result"]
