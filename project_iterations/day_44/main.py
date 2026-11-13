"""Day 44 平台启动入口：MCP (Model Context Protocol) 与双层记忆架构演示 (v0.4.0-day44)."""

import json
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import MCPClient, create_memory_enabled_mcp_server


def main() -> None:
    """运行 Day 44 MCP 协议握手、工具调用、资源读取与双层记忆演示."""
    print("=" * 68)
    print("🔌 智枢企业级智能体平台 v0.4.0-day44 · MCP 协议与双层记忆架构")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "zhishu_memory.db"
        server, memory = create_memory_enabled_mcp_server(db_path=db_path, window_size=3)
        client = MCPClient(server=server)

        # 1. MCP 初始化握手
        init_res = client.initialize(client_name="zhishu-host-demo")
        print(f"\n[1] MCP 握手成功: server={init_res['serverInfo']['name']} protocol={init_res['protocolVersion']}")

        # 2. 发现工具与资源
        tools = client.list_tools()
        resources = client.list_resources()
        print(f"[2] 发现工具 ({len(tools)} 个):", [t["name"] for t in tools])
        print(f"[3] 发现资源 ({len(resources)} 个):", [r["uri"] for r in resources])

        # 3. 通过 MCP 工具写入长期记忆
        client.call_tool(
            "memory_store",
            {
                "key": "pref_lang",
                "value": "用户偏好使用 Python 3.11 与 FastAPI 构建微服务",
                "namespace": "user-chenmo",
                "tags": ["偏好", "技术栈"],
            },
        )
        client.call_tool(
            "memory_store",
            {
                "key": "project_rule",
                "value": "所有生产智能体必须经过人工审批门禁与审计日志落盘",
                "namespace": "user-chenmo",
                "tags": ["规范", "安全"],
            },
        )

        # 4. 短期滑动窗口写入（window_size=3，写入 4 轮后自动淘汰第 1 轮）
        session_id = "sess-001"
        memory.add_turn(session_id, "user", "你好，请介绍一下智枢平台。")
        memory.add_turn(session_id, "assistant", "智枢平台是企业级多智能体编排系统。")
        memory.add_turn(session_id, "user", "我们项目用什么语言和框架？")
        memory.add_turn(session_id, "assistant", "让我结合长期记忆为你检索技术栈偏好。")

        # 5. 通过 MCP 工具检索长期记忆 + 读取动态资源
        search_res = client.call_tool(
            "memory_search",
            {"query": "Python FastAPI 技术栈", "namespace": "user-chenmo", "top_k": 1},
        )
        print("\n[4] MCP memory_search 返回:", search_res["content"][0]["text"])

        stats_res = client.read_resource("memory://stats")
        print("[5] MCP 读取资源 memory://stats:", stats_res["contents"][0]["text"])

        # 6. 融合上下文
        ctx = memory.build_context(session_id, "Python 技术栈偏好", namespace="user-chenmo", top_k=1)
        print("\n[6] 融合双层记忆上下文:")
        print(json.dumps(ctx, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
