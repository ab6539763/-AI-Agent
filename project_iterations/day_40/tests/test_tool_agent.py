"""Day 40 单元测试：验证 @tool、StructuredTool、ToolCallingAgent、AgentExecutor 与沙箱工具集."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    AgentExecutor,
    StructuredTool,
    ToolCallingAgent,
    create_sandbox_file_tools,
    safe_math_eval,
    tavily_search,
    tool,
)


def test_tool_decorator_schema_extraction() -> None:
    """验证 @tool 自动提取函数名、Docstring、类型注解与默认值生成 JSON Schema."""

    @tool
    def query_order(order_id: str, include_items: bool = False, limit: int = 5) -> str:
        """查询企业订单详情.

        Args:
            order_id: 订单编号。
            include_items: 是否返回明细。
            limit: 返回条数上限。
        """
        return f"{order_id}:{include_items}:{limit}"

    assert isinstance(query_order, StructuredTool)
    assert query_order.name == "query_order"
    assert "查询企业订单详情" in query_order.description
    assert query_order.args_schema["required"] == ["order_id"]
    props = query_order.args_schema["properties"]
    assert props["order_id"]["type"] == "string"
    assert props["order_id"]["description"] == "订单编号。"
    assert props["include_items"] == {
        "type": "boolean",
        "description": "是否返回明细。",
        "default": False,
    }
    assert props["limit"]["type"] == "integer"
    assert props["limit"]["default"] == 5

    openai_schema = query_order.to_openai_tool()
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "query_order"
    assert query_order("ORD-001") == "ORD-001:False:5"


def test_tool_decorator_custom_name_and_missing_docstring() -> None:
    """验证带参 @tool 装饰器与缺失 Docstring 时的显式校验."""

    @tool("fast_ping", return_direct=True)
    def ping_service(host: str) -> str:
        """检测服务连通性."""
        return f"pong:{host}"

    assert ping_service.name == "fast_ping"
    assert ping_service.return_direct is True
    assert ping_service.invoke("127.0.0.1") == "pong:127.0.0.1"

    with pytest.raises(ValueError, match="Docstring"):

        @tool
        def no_doc_tool(x: int) -> int:
            return x + 1


def test_safe_math_eval_and_injection_blocking() -> None:
    """验证 AST 数学求值器支持合法运算并拦截危险代码注入."""
    assert safe_math_eval.invoke({"expression": "(12 + 8) * 3 / 2"}) == 30.0
    assert safe_math_eval.invoke({"expression": "sqrt(16) + pow(2, 3)"}) == 12.0

    for dangerous_expr in [
        "__import__('os').system('ls')",
        "eval('1 + 1')",
        "open('/etc/passwd').read()",
        "10 ** 5000",
    ]:
        with pytest.raises(ValueError, match="安全拦截"):
            safe_math_eval.invoke({"expression": dangerous_expr})


def test_tavily_search_mock() -> None:
    """验证 Mock Tavily 联网搜索返回结构化结果并遵守 max_results."""
    hits = tavily_search.invoke({"query": "LangChain @tool", "max_results": 2})
    assert isinstance(hits, list)
    assert 1 <= len(hits) <= 2
    assert {"title", "url", "content"}.issubset(hits[0].keys())

    fallback = tavily_search.invoke({"query": "不存在的冷门词xyz123", "max_results": 1})
    assert len(fallback) == 1
    assert "xyz123" in fallback[0]["title"]


def test_sandbox_file_tools_and_path_traversal(tmp_path: Path) -> None:
    """使用 tmp_path 验证沙箱文件正常读写与路径穿越攻击拦截."""
    read_file, write_file = create_sandbox_file_tools(tmp_path)

    msg = write_file.invoke({"file_path": "reports/summary.md", "content": "智枢 Day 40 测试"})
    assert "安全写入" in msg
    assert read_file.invoke({"file_path": "reports/summary.md"}) == "智枢 Day 40 测试"

    for attack_path in ["../outside.txt", "../../etc/passwd", "/etc/passwd"]:
        with pytest.raises(PermissionError, match="安全拦截"):
            read_file.invoke({"file_path": attack_path})
        with pytest.raises(PermissionError, match="安全拦截"):
            write_file.invoke({"file_path": attack_path, "content": "hack"})


def test_agent_executor_multistep_and_intermediate_steps(tmp_path: Path) -> None:
    """验证 ToolCallingAgent 与 AgentExecutor 多步调度及 intermediate_steps 轨迹."""
    read_file, write_file = create_sandbox_file_tools(tmp_path)
    tools = [tavily_search, safe_math_eval, read_file, write_file]

    agent = ToolCallingAgent(tools=tools)
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=5)

    result = executor.invoke({"input": "请计算 (15 + 25) * 2 并写入 math_out.txt"})
    assert "output" in result
    assert "intermediate_steps" in result
    steps = result["intermediate_steps"]
    assert len(steps) == 2
    assert steps[0][0].tool == "safe_math_eval"
    assert steps[0][1] == 80
    assert steps[1][0].tool == "write_file"
    assert (tmp_path / "math_out.txt").read_text(encoding="utf-8") == "80"


def test_agent_executor_custom_llm_error_handling_and_max_iterations(tmp_path: Path) -> None:
    """验证自定义 LLM 回调、沙箱越权错误捕获与 max_iterations 上限保护."""
    read_file, write_file = create_sandbox_file_tools(tmp_path)
    tools = [read_file, write_file]

    def malicious_once_llm(messages: list[dict], schemas: list[dict]) -> dict:
        assert len(schemas) == 2
        has_tool_obs = any(m.get("role") == "tool" for m in messages)
        if not has_tool_obs:
            return {"tool_calls": [{"name": "read_file", "arguments": {"file_path": "../../etc/passwd"}}]}
        last_obs = [m["content"] for m in messages if m.get("role") == "tool"][-1]
        return {"content": f"安全审计拦截结果：{last_obs}"}

    agent = ToolCallingAgent(tools=tools, llm=malicious_once_llm)
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=4)
    res = executor.invoke({"input": "读取系统密码文件"})
    assert "PermissionError" in res["output"]
    assert "安全拦截" in res["intermediate_steps"][0][1]

    # 测试死循环触发 max_iterations
    def infinite_loop_llm(messages: list[dict], schemas: list[dict]) -> dict:
        return {"tool_calls": [{"name": "unknown_tool", "arguments": {}}]}

    loop_executor = AgentExecutor(
        agent=ToolCallingAgent(tools=tools, llm=infinite_loop_llm),
        tools=tools,
        max_iterations=2,
    )
    loop_res = loop_executor.invoke({"input": "loop"})
    assert "最大迭代次数" in loop_res["output"]
    assert len(loop_res["intermediate_steps"]) == 2
