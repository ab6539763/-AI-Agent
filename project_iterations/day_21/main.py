"""Day 21 平台启动入口：Week 3 综合迷你项目（多轮记忆 + 工具调用 + 流式输出）演示 (v0.2.0-day21)"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.integrated_agent import IntegratedAgent


def run_demo() -> None:
    """运行多轮对话 + 并行工具调用 + 生成器流式输出综合演示。"""
    agent = IntegratedAgent()
    mode = "Mock 离线模拟模式" if agent.is_mock else "Live 在线 API 模式"
    print("=" * 68)
    print("🤖 智枢企业级智能体平台 v0.2.0-day21 · Week 3 综合集成引擎")
    print(f"   运行模式: {mode} | 已注册工具: {', '.join(agent.registry.list_tools())}")
    print("=" * 68)

    turns = [
        "你好，我叫陈默，正在测试智枢集成引擎。",
        "帮我查一下北京今天的天气，顺便算一下 (120 + 80) * 3 / 4 等于多少？",
        "我叫什么名字？",
        "刚才我查了哪个城市的天气？",
    ]

    for idx, query in enumerate(turns, start=1):
        print(f"\n--- 第 {idx} 轮 ---")
        print(f"[用户] {query}")
        print("[助手(流式)] ", end="", flush=True)
        for chunk in agent.stream_reply(query):
            print(chunk, end="", flush=True)
        print()
        if agent.last_run and agent.last_run.executed_tools:
            for tc in agent.last_run.executed_tools:
                print(f"  ↳ 工具调用: {tc['name']}({tc['arguments']}) => {tc['output']}")

    print("\n" + "=" * 68)
    print(
        f"会话统计: 总轮数={agent.turn_count} | 消息数={len(agent.messages)} | 累计 Tokens={agent.total_tokens}"
    )


if __name__ == "__main__":
    run_demo()
