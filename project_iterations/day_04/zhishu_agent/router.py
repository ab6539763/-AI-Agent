"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 03 延续模块
功能：多轮交互路由与企业菜单调度器

业务背景：
命令行智能体需要清晰的功能路由表，将用户输入的指令编号映射到对应的业务模块。
"""

MENU_ROUTES: dict[str, str] = {
    "1": "profile",
    "2": "sanitize",
    "3": "tasks",
    "4": "models",
    "q": "exit",
}


def route_command(choice: str) -> str:
    """
    根据用户输入的菜单选项返回对应的内部路由标识。

    参数:
        choice (str): 用户输入的命令字符

    返回:
        str: 路由名称，未匹配时返回 "unknown"
    """
    normalized = choice.strip().lower()
    return MENU_ROUTES.get(normalized, "unknown")


def format_menu() -> str:
    """生成智枢平台命令行交互主菜单文本。"""
    lines = [
        "-" * 42,
        "智枢平台功能调度菜单 (v0.1.0-day04)",
        "  [1] 查看员工数字名片",
        "  [2] 测试 Prompt 清洗与脱敏",
        "  [3] 管理 Agent 任务队列 (TodoManager)",
        "  [4] 查看受支持的系统大模型配置",
        "  [q] 退出平台",
        "-" * 42,
    ]
    return "\n".join(lines)
