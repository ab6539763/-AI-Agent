"""Day 19 单元测试：全面覆盖安全 AST 数学求值、ToolRegistry 分发、MockTransport 两轮/多工具闭环与异常边界"""
import json
import sys
from pathlib import Path

import httpx
import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.tool_calling import (
    TOOL_SCHEMAS,
    ToolCallingAgentLoop,
    ToolRegistry,
    calculate_math,
    create_default_registry,
    get_weather,
    query_employee_info,
    safe_calculate_math,
)


class TestSafeMathEvaluator:
    """测试基于 AST 白名单的安全数学求值器（严禁 eval 任意代码执行）。"""

    def test_valid_arithmetic_expressions(self) -> None:
        assert safe_calculate_math("2 + 3 * 4") == 14
        assert safe_calculate_math("(128 + 32) * 3 / 4") == 120
        assert safe_calculate_math("-5 + 2 ** 3") == 3
        assert safe_calculate_math("10 // 3") == 3
        assert safe_calculate_math("10 % 3") == 1

    @pytest.mark.parametrize(
        "malicious_expr",
        [
            "__import__('os').system('echo pwned')",
            "open('/etc/passwd').read()",
            "eval('1+1')",
            "[x for x in range(10)]",
            "True + 1",
            "'hello' + 'world'",
            "abs(-5)",
        ],
    )
    def test_rejects_unsafe_code_execution(self, malicious_expr: str) -> None:
        with pytest.raises(ValueError):
            safe_calculate_math(malicious_expr)

    def test_division_by_zero_and_large_exponent(self) -> None:
        with pytest.raises(ValueError, match="除数不能为 0"):
            safe_calculate_math("10 / 0")
        with pytest.raises(ValueError, match="幂运算指数过大"):
            safe_calculate_math("2 ** 5000")
        with pytest.raises(ValueError, match="不能为空"):
            safe_calculate_math("   ")


class TestBuiltinToolsAndRegistry:
    """测试企业内置工具函数与 ToolRegistry 注册分发。"""

    def test_builtin_tools(self) -> None:
        w_c = get_weather("北京", "celsius")
        assert w_c["city"] == "北京"
        assert w_c["unit"] == "°C"

        w_f = get_weather("北京", "fahrenheit")
        assert w_f["unit"] == "°F"
        assert w_f["temperature"] > w_c["temperature"]

        m = calculate_math("(10 + 20) * 2")
        assert m["result"] == 60

        emp_by_id = query_employee_info(employee_id="EMP-001")
        assert emp_by_id["found"] is True
        assert emp_by_id["employee"]["name"] == "陈默"

        emp_by_name = query_employee_info(name="林晓")
        assert emp_by_name["found"] is True
        assert emp_by_name["employee"]["employee_id"] == "EMP-002"

        emp_missing = query_employee_info(employee_id="EMP-999")
        assert emp_missing["found"] is False

    def test_registry_schemas_and_dispatch(self) -> None:
        registry = create_default_registry()
        assert set(registry.list_tools()) == {"get_weather", "calculate_math", "query_employee_info"}
        assert len(registry.get_schemas()) == len(TOOL_SCHEMAS)

        out = json.loads(registry.dispatch("calculate_math", '{"expression": "6 * 7"}'))
        assert out["result"] == 42

    def test_registry_handles_unknown_tool_and_bad_json_safely(self) -> None:
        registry = create_default_registry()

        unknown_out = json.loads(registry.dispatch("drop_database", "{}"))
        assert "未知工具" in unknown_out["error"]
        assert "get_weather" in unknown_out["available_tools"]

        bad_json_out = json.loads(registry.dispatch("get_weather", "{bad_json"))
        assert "JSON 解析失败" in bad_json_out["error"]

        bad_kwarg_out = json.loads(registry.dispatch("get_weather", '{"unknown_param": 1}'))
        assert "执行失败" in bad_kwarg_out["error"]


class TestToolCallingAgentLoop:
    """测试 Pure-API ToolCallingAgentLoop 的完整多轮闭环。"""

    def test_single_tool_two_round_cycle(self) -> None:
        agent = ToolCallingAgentLoop(api_key="")
        result = agent.run("请问上海今天天气怎么样？")

        assert result.rounds == 2
        assert len(result.executed_tools) == 1
        assert result.executed_tools[0]["name"] == "get_weather"
        assert "上海" in result.answer

        roles = [m["role"] for m in result.messages]
        assert roles == ["system", "user", "assistant", "tool", "assistant"]
        assert result.messages[3]["tool_call_id"] == result.messages[2]["tool_calls"][0]["id"]

    def test_multi_tool_parallel_dispatch(self) -> None:
        agent = ToolCallingAgentLoop(api_key="")
        result = agent.run("查询杭州天气，并计算 (25 + 15) * 3 的结果。")

        assert result.rounds == 2
        assert len(result.executed_tools) == 2
        called_names = [t["name"] for t in result.executed_tools]
        assert "get_weather" in called_names
        assert "calculate_math" in called_names
        assert "杭州" in result.answer
        assert "120" in result.answer

    def test_direct_answer_without_tool_calls(self) -> None:
        agent = ToolCallingAgentLoop(api_key="")
        result = agent.run("你好，请介绍一下智枢平台。")

        assert result.rounds == 1
        assert result.executed_tools == []
        assert "无需调用外部工具" in result.answer

    def test_unknown_tool_in_loop_recovers_gracefully(self) -> None:
        captured_payloads: list[dict] = []

        def custom_handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(payload)
            msgs = payload["messages"]
            if not any(m.get("role") == "tool" for m in msgs):
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_bad_1",
                                            "type": "function",
                                            "function": {"name": "non_existent_tool", "arguments": "{}"},
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            tool_content = msgs[-1]["content"]
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": f"工具调用异常已捕获：{tool_content}",
                            }
                        }
                    ]
                },
            )

        agent = ToolCallingAgentLoop(transport=httpx.MockTransport(custom_handler))
        result = agent.run("调用不存在的工具")
        assert result.rounds == 2
        assert "未知工具" in result.answer
        assert len(captured_payloads) == 2
        assert "tools" in captured_payloads[0]

    def test_max_iterations_exceeded_and_empty_query(self) -> None:
        def infinite_tool_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_loop",
                                        "type": "function",
                                        "function": {
                                            "name": "calculate_math",
                                            "arguments": '{"expression": "1 + 1"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        agent = ToolCallingAgentLoop(
            transport=httpx.MockTransport(infinite_tool_handler),
            max_iterations=2,
        )
        with pytest.raises(RuntimeError, match="超过最大工具调用轮数限制"):
            agent.run("死循环测试")

        with pytest.raises(ValueError, match="不能为空"):
            agent.run("   ")
