"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 01 迭代模块
功能：AI 员工数字名片与开发环境自检工具

业务背景：
星辰数科启动「智枢平台」研发第一天，所有新入职工程师与平台虚拟 AI 助手
都需要注册一张标准的「数字名片」，包含姓名、岗位、工龄、主攻技术栈与是否具备大模型权限。
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

    参数:
        name (str): 员工或 AI 助手名称
        role (str): 岗位名称，例如 "AI 应用开发工程师"
        years_exp (int): 从业年限（整数 int）
        hourly_cost (float): 算力/人力预估时薪或预算（浮点数 float）
        llm_enabled (bool): 是否已开通企业大模型 API 权限（布尔值 bool）

    返回:
        str: 排版整洁的多行数字名片文本
    """
    # 使用三元表达式将布尔值转换为中文友好的状态标签
    status_label = "已开通 [OK]" if llm_enabled else "未开通 [LOCKED]"

    # 拼接名片边框与字段内容（Day 01 重点演示基本数据类型与字符串输出）
    border = "=" * 46
    lines = [
        border,
        "   星辰数科 · 智枢平台数字名片 (v0.1.0-day01)",
        border,
        f"姓名 / 标识 : {name}",
        f"所属岗位    : {role}",
        f"工程经验    : {years_exp} 年",
        f"资源预算    : ¥{hourly_cost:.2f} / 小时",
        f"大模型权限  : {status_label}",
        border,
    ]
    return "\n".join(lines)


def interactive_cli() -> None:
    """
    命令行交互入口：引导用户输入信息并打印数字名片。
    """
    print("欢迎来到智枢企业级智能体平台 (ZhiShu-Agent) 初始化向导！\n")

    # 1. 使用 input() 获取用户输入（input 返回值恒为 str 类型）
    name = input("请输入你的姓名（例如 陈默）：").strip() or "陈默"
    role = input("请输入你的岗位（例如 AI应用开发工程师）：").strip() or "AI应用开发工程师"

    # 2. 类型转换：将字符串转为 int 和 float
    raw_years = input("请输入你的编程经验年数（整数，如 0）：").strip() or "0"
    years_exp = int(raw_years)

    raw_budget = input("请输入你的每日 API 测试预算（元/小时，如 5.5）：").strip() or "5.5"
    hourly_cost = float(raw_budget)

    # 3. 布尔值转换：判断用户是否输入 y/yes
    raw_llm = input("是否已申请 DeepSeek/Qwen API Key？(y/n)：").strip().lower()
    llm_enabled = raw_llm in ("y", "yes", "是")

    # 4. 生成并打印数字名片
    card = build_employee_card(
        name=name,
        role=role,
        years_exp=years_exp,
        hourly_cost=hourly_cost,
        llm_enabled=llm_enabled,
    )
    print("\n" + card)


if __name__ == "__main__":
    # 打印当前环境自检结果
    env = get_environment_info()
    print(f"[环境自检] Python {env['python_version']} | 系统: {env['os_info']}")
    interactive_cli()
