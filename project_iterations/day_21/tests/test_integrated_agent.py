"""Day 21 单元测试：多轮记忆 + 工具调用 + 生成器流式输出集成智能体 (v0.2.0-day21)"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    IntegratedAgent,
    calculate_math,
    create_default_registry,
    get_weather,
    parse_sse_line,
    safe_calculate_math,
)


def test_safe_calculate_math_and_injection_guard() -> None:
    assert safe_calculate_math("(120 + 80) * 3 / 4") == 150
    assert safe_calculate_math("2 ** 10 - 24") == 1000
    assert safe_calculate_math("-5 + 3.5") == -1.5

    with pytest.raises(ValueError, match="除数不能为 0"):
        safe_calculate_math("10 / 0")
    with pytest.raises(ValueError, match="不允许的常量类型"):
        safe_calculate_math("True + 1")
    with pytest.raises(ValueError, match="不安全的表达式语法节点"):
        safe_calculate_math("__import__('os').system('ls')")


def test_tool_registry_dispatch_and_error_recovery() -> None:
    registry = create_default_registry()
    assert set(registry.list_tools()) == {"get_weather", "calculate_math"}
    assert len(registry.get_schemas()) == 2

    weather_res = json.loads(registry.dispatch("get_weather", '{"city": "北京", "unit": "celsius"}'))
    assert weather_res["city"] == "北京"
    assert weather_res["temperature"] == 18

    math_res = json.loads(registry.dispatch("calculate_math", {"expression": "6 * 7"}))
    assert math_res["result"] == 42

    unknown_res = json.loads(registry.dispatch("nonexistent_tool", "{}"))
    assert "未知工具" in unknown_res["error"]

    bad_json_res = json.loads(registry.dispatch("get_weather", "{invalid-json"))
    assert "JSON 解析失败" in bad_json_res["error"]


def test_parse_sse_line() -> None:
    assert parse_sse_line("") is None
    assert parse_sse_line(": heartbeat") is None
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("data: {bad json}") is None
    line = 'data: {"choices": [{"delta": {"content": "你好"}}]}'
    assert parse_sse_line(line) == "你好"


def test_stream_reply_is_generator_and_yields_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = IntegratedAgent()
    assert agent.is_mock is True

    gen = agent.stream_reply("你好，请介绍一下你自己")
    assert isinstance(gen, Iterator)
    chunks = list(gen)
    assert len(chunks) >= 2
    assert agent.last_run is not None
    assert "".join(chunks) == agent.last_run.answer
    assert agent.last_run.streamed_chunks == len(chunks)
    assert agent.turn_count == 1


def test_parallel_tool_calling_with_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = IntegratedAgent()

    chunks = list(agent.stream_reply("请查一下北京天气，并计算 (120 + 80) * 3 / 4"))
    full_text = "".join(chunks)

    assert agent.last_run is not None
    assert agent.last_run.rounds == 2
    assert len(agent.last_run.executed_tools) == 2
    tool_names = [t["name"] for t in agent.last_run.executed_tools]
    assert tool_names == ["get_weather", "calculate_math"]
    assert "北京" in full_text
    assert "150" in full_text

    roles = [m["role"] for m in agent.get_history()]
    assert roles == ["system", "user", "assistant", "tool", "tool", "assistant"]


def test_multi_turn_memory_and_clear_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = IntegratedAgent()

    r1 = agent.run("你好，我叫陈默")
    assert "陈默" in r1.answer

    r2 = agent.run("查一下上海天气")
    assert "上海" in r2.answer

    r3 = agent.run("我叫什么名字？")
    assert "陈默" in r3.answer

    r4 = agent.run("刚才我查了哪个城市的天气？")
    assert "上海" in r4.answer
    assert agent.turn_count == 4

    agent.clear_history()
    assert agent.turn_count == 0
    assert agent.total_tokens == 0
    assert agent.last_run is None
    assert len(agent.get_history()) == 1
    assert agent.get_history()[0]["role"] == "system"


def test_transactional_rollback_on_http_error() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, json={"error": "Internal Server Error"})

    agent = IntegratedAgent(transport=httpx.MockTransport(failing_handler))
    initial_len = len(agent.get_history())

    with pytest.raises(httpx.HTTPStatusError):
        list(agent.stream_reply("触发服务端异常"))

    assert len(agent.get_history()) == initial_len
    assert agent.turn_count == 0


def test_max_iterations_guard_and_empty_input() -> None:
    def infinite_tool_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_loop",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city": "北京"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"total_tokens": 10},
            },
        )

    agent = IntegratedAgent(
        transport=httpx.MockTransport(infinite_tool_handler),
        max_iterations=2,
    )
    with pytest.raises(RuntimeError, match="超过最大轮数限制"):
        agent.run("北京天气")
    assert len(agent.get_history()) == 1

    with pytest.raises(ValueError, match="不能为空"):
        agent.run("   ")
