# Day 44 课后作业与参考答案

## 作业一：JSON-RPC 2.0 请求/响应构造与错误码校验
**题目**：在 MCP 协议中，所有通信都基于 JSON-RPC 2.0 报文格式。请你使用 `MCPServer` 和 `make_jsonrpc_request` 完成以下验证：
1. 实例化一个 `MCPServer`，向其发送一条非法 JSON 字符串 `"{bad json"`，断言返回错误码为 `PARSE_ERROR`（`-32700`）。
2. 发送一条合法的 `initialize` 请求（`id="init-1"`），验证响应中包含 `jsonrpc == "2.0"`、`id == "init-1"` 与 `result.protocolVersion`。
3. 发送一条未定义方法 `"prompts/get"` 的请求，断言返回错误码为 `METHOD_NOT_FOUND`（`-32601`）。

### 参考答案：
```python
from zhishu_agent import (
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    MCPServer,
    make_jsonrpc_request,
)

server = MCPServer(name="hw1-mcp", version="0.4.0-day44")

# 1. 非法 JSON 触发 -32700 Parse Error
err_parse = server.handle_message("{bad json")
assert err_parse["error"]["code"] == PARSE_ERROR

# 2. 标准 initialize 请求
req_init = make_jsonrpc_request(
    "initialize",
    {"protocolVersion": "2024-11-05", "clientInfo": {"name": "hw-client"}},
    request_id="init-1",
)
resp_init = server.handle_message(req_init)
assert resp_init["jsonrpc"] == "2.0"
assert resp_init["id"] == "init-1"
assert "protocolVersion" in resp_init["result"]

# 3. 未知方法触发 -32601 Method Not Found
req_unknown = make_jsonrpc_request("prompts/get", request_id=99)
resp_unknown = server.handle_message(req_unknown)
assert resp_unknown["error"]["code"] == METHOD_NOT_FOUND
assert resp_unknown["id"] == 99

print("作业一校验通过！协议版本:", resp_init["result"]["protocolVersion"])
```

---

## 作业二：为 `MCPServer` 注册并调用自定义业务工具
**题目**：星辰数科需要向智能体暴露一个“工单 SLA 估算器”工具 `estimate_sla`。请你：
1. 使用 `server.register_tool(...)` 注册 `estimate_sla`，要求必填参数为 `severity`（字符串，如 `"P0"` / `"P1"`）和 `affected_users`（整数）。
2. 当 `severity == "P0"` 时返回 `{"sla_minutes": 15, "priority": "critical"}`，否则返回 `{"sla_minutes": 120, "priority": "normal"}`。
3. 使用 `MCPClient` 完成 `initialize()` -> `list_tools()` -> `call_tool("estimate_sla", ...)`，并验证缺少必填参数 `affected_users` 时会抛出 `MCPClientError`（错误码 `-32602`）。

### 参考答案：
```python
import json
from zhishu_agent import INVALID_PARAMS, MCPClient, MCPClientError, MCPServer

server = MCPServer(name="sla-mcp")

def handle_estimate_sla(args: dict) -> dict:
    if args["severity"] == "P0":
        return {"sla_minutes": 15, "priority": "critical", "users": args["affected_users"]}
    return {"sla_minutes": 120, "priority": "normal", "users": args["affected_users"]}

server.register_tool(
    name="estimate_sla",
    description="根据故障等级和受影响人数估算 SLA 响应时间",
    input_schema={
        "type": "object",
        "properties": {
            "severity": {"type": "string"},
            "affected_users": {"type": "integer"},
        },
        "required": ["severity", "affected_users"],
    },
    handler=handle_estimate_sla,
)

client = MCPClient(server=server)
client.initialize()
assert [t["name"] for t in client.list_tools()] == ["estimate_sla"]

res = client.call_tool("estimate_sla", {"severity": "P0", "affected_users": 500})
payload = json.loads(res["content"][0]["text"])
assert payload["sla_minutes"] == 15 and payload["priority"] == "critical"

try:
    client.call_tool("estimate_sla", {"severity": "P1"})
    raise AssertionError("预期应抛出 MCPClientError")
except MCPClientError as exc:
    assert exc.code == INVALID_PARAMS

print("作业二校验通过！SLA 工具返回:", payload)
```

---

## 作业三：短期滑动窗口与 SQLite 长期记忆对比验证
**题目**：请你使用 `tempfile.TemporaryDirectory()` 与 `DualMemoryManager` 验证短期记忆与长期记忆的行为差异：
1. 创建 `window_size=2` 的 `DualMemoryManager`，向会话 `"s-hw3"` 连续写入 4 轮对话，断言 `get_short_term("s-hw3")` 仅保留最后 2 轮。
2. 调用 `remember()` 写入两条长期记忆（`"deploy_env"` 与 `"oncall_owner"`，命名空间 `"prod"`），随后重新实例化一个新的 `DualMemoryManager` 连接同一数据库文件（模拟进程重启）。
3. 验证新实例中 `get_short_term("s-hw3")` 为空（内存态随进程重启释放），而 `recall_key("deploy_env", namespace="prod")` 与 `search_long_term("部署环境", namespace="prod")` 依然能准确召回长期记忆。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import DualMemoryManager

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "hw3_memory.db"
    mem1 = DualMemoryManager(db_path=db_path, window_size=2)

    for i in range(1, 5):
        mem1.add_turn("s-hw3", "user", f"第 {i} 轮消息")

    short_turns = mem1.get_short_term("s-hw3")
    assert [t["content"] for t in short_turns] == ["第 3 轮消息", "第 4 轮消息"]

    mem1.remember("deploy_env", "生产环境运行在 Kubernetes 1.30 集群", namespace="prod", tags=["k8s", "部署"])
    mem1.remember("oncall_owner", "本周值班工程师为陈默", namespace="prod", tags=["值班", "运维"])

    # 模拟进程重启
    mem2 = DualMemoryManager(db_path=db_path, window_size=2)
    assert mem2.get_short_term("s-hw3") == []

    recalled = mem2.recall_key("deploy_env", namespace="prod")
    assert recalled is not None and "Kubernetes" in recalled["value"]

    hits = mem2.search_long_term("部署环境 k8s", namespace="prod", top_k=1)
    assert hits[0]["key"] == "deploy_env"
    print("作业三校验通过！长期记忆 Top-1 召回:", hits[0]["value"])
```
