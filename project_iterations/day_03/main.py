"""Day 03 平台启动入口：交互式 while True 菜单调度"""

from zhishu_agent.profile import get_environment_info
from zhishu_agent.router import run_menu_dispatch


def print_menu() -> None:
    """打印智枢平台 Day 03 交互主菜单"""
    print("\n" + "=" * 46)
    print("  星辰数科 · 智枢平台调度中心 (v0.1.0-day03)")
    print("=" * 46)
    print("  [1] 生成数字名片与权限等级核验")
    print("  [2] 批量 Prompt 清洗与敏感词脱敏")
    print("  [3] 打印 9×9 乘法口诀表（循环训练）")
    print("  [4] 查看当前 Python 环境自检")
    print("  [0] 退出平台")
    print("=" * 46)


def interactive_loop() -> None:
    """基于 while True 的多轮交互主循环"""
    context: dict = {
        "name": "陈默",
        "role": "AI 应用开发工程师",
        "years_exp": 3,
        "budget": 60.0,
        "llm_enabled": True,
        "prompts": [
            "  帮我总结这份周报  ",
            "",
            "请检查 API_KEY 是否泄露",
            "STOP",
            "这条不会被处理",
        ],
        "n": 9,
    }

    while True:
        print_menu()
        choice = input("请选择功能编号 (0-4)：").strip()
        output = run_menu_dispatch(choice, context)
        print("\n" + output)
        if choice in ("0", "q", "exit"):
            break


if __name__ == "__main__":
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day03 | Python {env['python_version']}")
    interactive_loop()
