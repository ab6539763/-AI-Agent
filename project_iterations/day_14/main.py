"""Day 14 平台启动入口：命令行多轮对话 AI 助手 (v0.1.0-day14)"""
import sys
from pathlib import Path

# 支持直接 python project_iterations/day_14/main.py 启动
DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.chat_assistant import MultiTurnAssistant
from zhishu_agent.exceptions import CommandError, ZhiShuError


def run_cli(assistant: MultiTurnAssistant | None = None) -> None:
    """启动交互式命令行多轮对话循环。"""
    bot = assistant or MultiTurnAssistant()
    mode_label = "Mock 离线模拟模式" if bot.client.is_mock else "Live 在线 API 模式"

    print("=" * 60)
    print(f"🤖 智枢企业级智能体平台 v0.1.0-day14 · 命令行多轮对话 AI 助手")
    print(f"   当前模型: {bot.client.model_name} | 运行模式: {mode_label}")
    print("   可用指令: /clear  /save <path>  /load <path>  /stats  /help  /exit")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n你: ")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 检测到退出信号，再见！")
            break

        if not user_input.strip():
            continue

        try:
            should_continue, output = bot.process_input(user_input)
        except CommandError as exc:
            print(f"⚠️  指令错误: {exc}")
            continue
        except ZhiShuError as exc:
            print(f"❌ 平台异常: {exc}")
            continue

        if output:
            prefix = "AI: " if not user_input.strip().startswith("/") else ""
            print(f"{prefix}{output}")

        if not should_continue:
            break


if __name__ == "__main__":
    run_cli()
