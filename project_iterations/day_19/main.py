"""Day 19 平台启动入口：Pure-API Function Calling 演示与交互式 CLI (v0.2.0-day19)"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.tool_calling import ToolCallingAgentLoop


def run_demo() -> None:
    """运行内置 Function Calling 多场景演示。"""
    agent = ToolCallingAgentLoop()
    mode = "Mock 离线模拟模式" if agent.is_mock else "Live 在线 API 模式"
    print("=" * 64)
    print(f"🤖 智枢企业级智能体平台 v0.2.0-day19 · Pure-API Function Calling")
    print(f"   运行模式: {mode} | 已注册工具: {', '.join(agent.registry.list_tools())}")
    print("=" * 64)

    queries = [
        "帮我查一下北京今天的天气，顺便算一下 (120 + 80) * 3 / 4 等于多少？",
        "查询一下员工陈默的部门和邮箱。",
        "你好，请介绍一下什么是 Function Calling？",
    ]
    for q in queries:
        print(f"\n[用户] {q}")
        res = agent.run(q)
        print(f"[轮次] {res.rounds} 轮 | [调用工具数] {len(res.executed_tools)} | [Tokens] {res.total_tokens}")
        for tc in res.executed_tools:
            print(f"  -> 工具 {tc['name']}({tc['arguments']}) => {tc['output']}")
        print(f"[助手] {res.answer}")


if __name__ == "__main__":
    run_demo()
