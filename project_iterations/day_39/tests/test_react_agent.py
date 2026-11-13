"""Day 39 单元测试：纯 Python ReAct 智能体引擎验证 (v0.4.0-day39)."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    ParsedAction,
    ParsedFinalAnswer,
    ReActAgent,
    ReActStep,
    ToolSpec,
    calculator_tool,
    knowledge_search_tool,
    parse_react_output,
)


def test_calculator_tool_safe_arithmetic() -> None:
    """AST 计算器应正确计算四则运算与幂运算，并拦截非法注入."""
    assert calculator_tool("(128 + 72) * 3 / 4") == "150"
    assert calculator_tool("-5 + 2 ** 3") == "3"
    assert "除数不能为零" in calculator_tool("10 / 0")
    assert "禁止的语法结构" in calculator_tool("__import__('os').system('ls')")


def test_knowledge_search_tool() -> None:
    """离线企业知识检索工具应命中制度条款并在无匹配时给出提示."""
    hit = knowledge_search_tool("高级工程师 差旅 住宿")
    assert "450 元/晚" in hit

    miss = knowledge_search_tool("火星移民补贴政策")
    assert "未在企业知识库中找到" in miss


def test_parse_react_output_action_and_final_answer() -> None:
    """正则解析器应准确提取 Action/Action Input 与 Final Answer."""
    action_text = (
        "Thought: 先查询差旅制度。\n"
        "Action: knowledge_search\n"
        "Action Input: 差旅 住宿 标准"
    )
    parsed_action = parse_react_output(action_text)
    assert isinstance(parsed_action, ParsedAction)
    assert parsed_action.action == "knowledge_search"
    assert parsed_action.action_input == "差旅 住宿 标准"

    final_text = (
        "Thought: 已经拿到所有信息。\n"
        "Final Answer: 住宿报销上限为 1800 元。"
    )
    parsed_final = parse_react_output(final_text)
    assert isinstance(parsed_final, ParsedFinalAnswer)
    assert parsed_final.final_answer == "住宿报销上限为 1800 元。"

    with pytest.raises(ValueError):
        parse_react_output("只有随意的文本，没有任何协议字段")


def test_react_agent_multi_step_reasoning() -> None:
    """默认 Mock 规划器应能完成 knowledge_search -> calculator -> Final Answer 多跳推理."""
    agent = ReActAgent(max_steps=5)
    trace = agent.run("请查询高级工程师的差旅住宿标准，并计算出差 4 晚的总预算。")

    assert trace.stopped_reason == "final_answer"
    assert len(trace.steps) == 3
    assert trace.steps[0].action == "knowledge_search"
    assert trace.steps[1].action == "calculator"
    assert trace.steps[1].observation == "1800"
    assert "1800" in trace.final_answer


def test_react_agent_max_steps_guard() -> None:
    """当规划器陷入死循环时，max_steps 守卫应安全终止并返回 max_steps 原因."""

    def looping_planner(query: str, steps: list[ReActStep]) -> str:
        return (
            "Thought: 继续计算。\n"
            "Action: calculator\n"
            "Action Input: 1 + 1"
        )

    agent = ReActAgent(planner=looping_planner, max_steps=3)
    trace = agent.run("测试死循环")

    assert trace.stopped_reason == "max_steps"
    assert len(trace.steps) == 3
    assert "max_steps=3" in trace.final_answer


def test_react_agent_unknown_tool_and_custom_tool() -> None:
    """未知工具应返回错误 Observation 而不崩溃；支持动态注册自定义工具."""

    def custom_planner(query: str, steps: list[ReActStep]) -> str:
        if len(steps) == 0:
            return "Thought: 尝试未知工具\nAction: no_such_tool\nAction Input: x"
        if len(steps) == 1:
            return "Thought: 改用 get_date\nAction: get_date\nAction Input: today"
        return f"Thought: 完成\nFinal Answer: 日期是 {steps[-1].observation}"

    agent = ReActAgent(planner=custom_planner, max_steps=4)
    agent.register_tool(
        ToolSpec(
            name="get_date",
            description="返回固定演示日期",
            func=lambda _: "2026-11-13",
        )
    )
    trace = agent.run("今天几号？")

    assert trace.stopped_reason == "final_answer"
    assert "未知工具" in (trace.steps[0].observation or "")
    assert trace.steps[1].observation == "2026-11-13"
    assert "2026-11-13" in trace.final_answer
