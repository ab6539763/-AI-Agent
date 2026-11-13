"""Day 01 平台启动入口"""
from zhishu_agent.profile import get_environment_info, interactive_cli

if __name__ == "__main__":
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day01 | Python {env['python_version']}")
    interactive_cli()
