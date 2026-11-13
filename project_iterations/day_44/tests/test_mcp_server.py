"""Day 44 单元测试：MCPServer/MCPClient JSON-RPC 2.0 协议与 DualMemoryManager (v0.4.0-day44)."""

import json
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    DualMemoryManager,
    MCPClient,
    MCPClientError,
    MCPServer,
    create_memory_enabled_mcp_server,
    make_jsonrpc_request,
)


def test_jsonrpc_protocol_and_error_codes() -> None:
    """验证 JSON-RPC 2.0 解析错误、非法请求、未知方法与参数校验."""
    server = MCPServer()
    server.register_tool(
        name="add",
        description="两数相加",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
        handler=lambda args: {"sum": args["a"] + args["b"]},
    )

    # 1. Parse error (-32700)
    resp_parse = server.handle_message("{not-valid-json")
    assert resp_parse["error"]["code"] == PARSE_ERROR

    # 2. Invalid Request (-32600)
    resp_invalid = server.handle_message({"jsonrpc": "1.0", "id": 1, "method": "initialize"})
    assert resp_invalid["error"]["code"] == INVALID_REQUEST

    # 3. Method not found (-32601)
    resp_unknown = server.handle_message(make_jsonrpc_request("unknown/method", request_id=2))
    assert resp_unknown["error"]["code"] == METHOD_NOT_FOUND
    assert resp_unknown["id"] == 2

    # 4. Invalid params (-32602): 缺少必填参数 b
    resp_params = server.handle_message(
        make_jsonrpc_request("tools/call", {"name": "add", "arguments": {"a": 10}}, request_id=3)
    )
    assert resp_params["error"]["code"] == INVALID_PARAMS


def test_mcp_client_server_lifecycle() -> None:
    """验证 MCPClient 与 MCPServer 的 initialize、tools/list、tools/call、resources/list、resources/read."""
    server = MCPServer(name="unit-test-mcp", version="0.4.0-day44")
    server.register_tool(
        name="multiply",
        description="计算两个整数乘积",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"],
        },
        handler=lambda args: {"product": args["x"] * args["y"]},
    )
    server.register_tool(
        name="boom",
        description="模拟工具内部异常",
        input_schema={"type": "object", "properties": {}},
        handler=lambda _args: (_ for _ in ()).throw(RuntimeError("downstream timeout")),
    )
    server.register_resource(
        uri="doc://guide",
        name="开发规范",
        description="智枢开发手册",
        content_or_reader="遵循 JSON-RPC 2.0 与最小权限原则。",
    )

    client = MCPClient(server=server)
    init_result = client.initialize(client_name="pytest-host")
    assert init_result["serverInfo"]["name"] == "unit-test-mcp"
    assert server.initialized is True

    tools = client.list_tools()
    assert [t["name"] for t in tools] == ["multiply", "boom"]

    call_ok = client.call_tool("multiply", {"x": 6, "y": 7})
    assert call_ok["isError"] is False
    assert json.loads(call_ok["content"][0]["text"]) == {"product": 42}

    call_err = client.call_tool("boom", {})
    assert call_err["isError"] is True
    assert "downstream timeout" in call_err["content"][0]["text"]

    resources = client.list_resources()
    assert len(resources) == 1
    assert resources[0]["uri"] == "doc://guide"

    read_res = client.read_resource("doc://guide")
    assert read_res["contents"][0]["text"] == "遵循 JSON-RPC 2.0 与最小权限原则。"

    with pytest.raises(MCPClientError) as exc_info:
        client.read_resource("doc://missing")
    assert exc_info.value.code == INVALID_PARAMS


def test_dual_memory_short_term_sliding_window(tmp_path: Path) -> None:
    """验证短期记忆滑动窗口淘汰机制与会话隔离."""
    mem = DualMemoryManager(db_path=tmp_path / "mem.db", window_size=3)

    for i in range(5):
        mem.add_turn("sess-a", "user", f"turn-{i}")
    mem.add_turn("sess-b", "user", "other-session")

    turns_a = mem.get_short_term("sess-a")
    assert [t["content"] for t in turns_a] == ["turn-2", "turn-3", "turn-4"]
    assert [t["content"] for t in mem.get_short_term("sess-b")] == ["other-session"]

    mem.clear_short_term("sess-a")
    assert mem.get_short_term("sess-a") == []


def test_dual_memory_long_term_sqlite_persistence_and_search(tmp_path: Path) -> None:
    """验证 SQLite 长期记忆的持久化、命名空间隔离、更新、检索与删除."""
    db_path = tmp_path / "ltm.db"
    mem1 = DualMemoryManager(db_path=db_path, window_size=4)

    mem1.remember("stack", "后端采用 Python 3.11 与 FastAPI", namespace="tenant-1", tags=["python", "api"])
    mem1.remember("db", "生产数据库使用 PostgreSQL 16", namespace="tenant-1", tags=["sql", "db"])
    mem1.remember("stack", "前端采用 React 19", namespace="tenant-2", tags=["frontend"])

    # 覆盖更新同 key
    mem1.remember("stack", "后端采用 Python 3.11、FastAPI 与 LangGraph", namespace="tenant-1", tags=["python", "agent"])

    # 模拟进程重启后重新连接同一 SQLite 文件
    mem2 = DualMemoryManager(db_path=db_path, window_size=4)
    recalled_t1 = mem2.recall_key("stack", namespace="tenant-1")
    recalled_t2 = mem2.recall_key("stack", namespace="tenant-2")
    assert recalled_t1 is not None and "LangGraph" in recalled_t1["value"]
    assert recalled_t2 is not None and "React 19" in recalled_t2["value"]

    hits = mem2.search_long_term("Python FastAPI LangGraph", namespace="tenant-1", top_k=2)
    assert len(hits) == 2
    assert hits[0]["key"] == "stack"
    assert hits[0]["score"] >= hits[1]["score"]

    assert mem2.forget("db", namespace="tenant-1") is True
    assert mem2.recall_key("db", namespace="tenant-1") is None
    assert mem2.count_long_term(namespace="tenant-1") == 1


def test_memory_enabled_mcp_server_end_to_end(tmp_path: Path) -> None:
    """端到端测试：通过 MCPClient 读写 DualMemoryManager 并构建混合上下文."""
    db_path = tmp_path / "e2e_mcp.db"
    server, memory = create_memory_enabled_mcp_server(db_path=db_path, window_size=2)
    client = MCPClient(server=server)
    client.initialize()

    store_resp = client.call_tool(
        "memory_store",
        {
            "key": "sla_policy",
            "value": "核心接口 P99 延迟需低于 200ms",
            "namespace": "ops",
            "tags": ["sla", "performance"],
        },
    )
    assert json.loads(store_resp["content"][0]["text"])["status"] == "stored"

    recall_resp = client.call_tool("memory_recall", {"key": "sla_policy", "namespace": "ops"})
    recalled = json.loads(recall_resp["content"][0]["text"])
    assert "200ms" in recalled["value"]

    stats = json.loads(client.read_resource("memory://stats")["contents"][0]["text"])
    assert stats["long_term_count"] == 1
    assert stats["window_size"] == 2

    memory.add_turn("s1", "user", "第一轮问题")
    memory.add_turn("s1", "assistant", "第一轮回答")
    memory.add_turn("s1", "user", "SLA 延迟要求是多少？")

    ctx = memory.build_context("s1", "SLA 延迟", namespace="ops", top_k=1)
    assert len(ctx["short_term"]) == 2
    assert ctx["long_term"][0]["key"] == "sla_policy"
