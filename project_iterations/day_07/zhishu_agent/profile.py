"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 01 继承模块
功能：AI 员工数字名片与开发环境自检工具
"""

import platform
import sys


def get_environment_info() -> dict[str, str]:
    """
    获取当前 Python 开发环境信息，用于新员工入职环境自检。

    返回:
        dict[str, str]: 包含 Python 版本、操作系统与解释器路径的字典
    """
    return {
        "python_version": platform.python_version(),
        "os_info": f"{platform.system()} {platform.release()}",
        "executable": sys.executable,
    }


def build_employee_card(
    name: str,
    role: str,
    years_exp: int,
    hourly_cost: float,
    llm_enabled: bool,
) -> str:
    """
    根据输入的基本信息，生成格式化的企业数字名片字符串。
    """
    status_label = "已开通 [OK]" if llm_enabled else "未开通 [LOCKED]"
    border = "=" * 46
    lines = [
        border,
        "   星辰数科 · 智枢平台数字名片 (v0.1.0-day07)",
        border,
        f"姓名 / 标识 : {name}",
        f"所属岗位    : {role}",
        f"工程经验    : {years_exp} 年",
        f"资源预算    : ¥{hourly_cost:.2f} / 小时",
        f"大模型权限  : {status_label}",
        border,
    ]
    return "\n".join(lines)
