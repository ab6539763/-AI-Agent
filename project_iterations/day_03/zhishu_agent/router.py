"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 03 迭代模块
功能：多轮交互路由、权限分级校验、批量 Prompt 清洗与企业菜单调度器

业务背景：
星辰数科在完成名片注册（Day 01）与 Prompt 脱敏（Day 02）后，需要一个统一的
CLI 交互调度中心，根据员工工龄、大模型权限与算力预算进行权限分级（VIP / STANDARD / DENIED），
并支持批量清洗用户输入的 Prompt 队列以及生成常规文本矩阵测试输出。
"""

from zhishu_agent.profile import build_employee_card, get_environment_info
from zhishu_agent.sanitizer import sanitize_prompt


def check_access_level(years_exp: int, llm_enabled: bool, budget: float) -> str:
    """
    使用嵌套 if/elif/else 判断员工的智枢平台访问权限等级。

    规则：
    1. 若未开通大模型权限（llm_enabled 为 False），直接返回 "DENIED"。
    2. 若已开通大模型权限：
       - 工龄 >= 3 年 且 预算 >= 50.0 -> 返回 "VIP"
       - 预算 > 0 且（工龄 >= 1 年 或 预算 >= 10.0）-> 返回 "STANDARD"
       - 其他情况（例如预算 <= 0 或工龄不足且预算过低）-> 返回 "DENIED"

    参数:
        years_exp (int): 工程经验年数
        llm_enabled (bool): 是否已开通大模型权限
        budget (float): 可用算力预算（元/小时）

    返回:
        str: "VIP" / "STANDARD" / "DENIED"
    """
    if llm_enabled:
        if years_exp >= 3 and budget >= 50.0:
            return "VIP"
        elif budget > 0 and (years_exp >= 1 or budget >= 10.0):
            return "STANDARD"
        else:
            return "DENIED"
    else:
        return "DENIED"


def batch_clean_prompts(
    prompts: list[str],
    stop_keyword: str = "STOP",
) -> list[str]:
    """
    批量清洗 Prompt 列表：
    - 使用 for 循环遍历每条原始 Prompt
    - 遇到空字符串或纯空白字符串时使用 continue 跳过
    - 遇到停止词（strip 后等于 stop_keyword）时使用 break 立即终止处理
    - 其余文本调用 sanitize_prompt() 完成清洗与脱敏后收集返回

    参数:
        prompts (list[str]): 原始 Prompt 字符串列表
        stop_keyword (str): 终止批处理的关键词，默认为 "STOP"

    返回:
        list[str]: 清洗脱敏后的有效 Prompt 列表
    """
    cleaned_list: list[str] = []
    for raw_prompt in prompts:
        stripped = raw_prompt.strip()
        if not stripped:
            continue
        if stripped == stop_keyword:
            break
        cleaned_list.append(sanitize_prompt(stripped))
    return cleaned_list


def generate_multiplication_table(n: int = 9) -> str:
    """
    使用经典嵌套 for 循环生成 n x n 下三角乘法口诀表（用于终端排版与循环教学）。

    参数:
        n (int): 乘法表阶数，默认为 9（须 >= 1）

    返回:
        str: 格式化后的多行乘法口诀表文本
    """
    if n < 1:
        raise ValueError("阶数 n 必须为大于等于 1 的整数")

    rows: list[str] = []
    for i in range(1, n + 1):
        cols: list[str] = []
        for j in range(1, i + 1):
            cols.append(f"{j}×{i}={i * j:<2}")
        rows.append("  ".join(cols).rstrip())
    return "\n".join(rows)


def run_menu_dispatch(choice: str, context: dict) -> str:
    """
    CLI 菜单路由调度器：根据用户选择分发到对应业务模块。

    参数:
        choice (str): 用户输入的菜单编号（"1" / "2" / "3" / "4" / "0"）
        context (dict): 当前会话上下文数据（用户信息、Prompt 列表等）

    返回:
        str: 调度执行后的文本结果
    """
    normalized = choice.strip()

    if normalized == "1":
        name = context.get("name", "陈默")
        role = context.get("role", "AI 应用开发工程师")
        years_exp = int(context.get("years_exp", 2))
        budget = float(context.get("budget", 12.5))
        llm_enabled = bool(context.get("llm_enabled", True))

        card = build_employee_card(
            name=name,
            role=role,
            years_exp=years_exp,
            hourly_cost=budget,
            llm_enabled=llm_enabled,
        )
        level = check_access_level(
            years_exp=years_exp,
            llm_enabled=llm_enabled,
            budget=budget,
        )
        return f"{card}\n当前平台权限等级: {level}"

    elif normalized == "2":
        prompts = context.get("prompts", [])
        stop_keyword = context.get("stop_keyword", "STOP")
        cleaned = batch_clean_prompts(prompts, stop_keyword=stop_keyword)
        if not cleaned:
            return "[批量清洗结果] 未收集到有效 Prompt。"
        formatted = "\n".join(f"  {idx}. {item}" for idx, item in enumerate(cleaned, start=1))
        return f"[批量清洗结果] 共处理 {len(cleaned)} 条有效 Prompt：\n{formatted}"

    elif normalized == "3":
        n = int(context.get("n", 9))
        return generate_multiplication_table(n=n)

    elif normalized == "4":
        env = get_environment_info()
        return (
            f"[环境自检] Python {env['python_version']} | "
            f"系统: {env['os_info']} | 解释器: {env['executable']}"
        )

    elif normalized in ("0", "q", "exit"):
        return "感谢使用智枢企业级智能体平台 (v0.1.0-day03)，再见！"

    else:
        return f"[提示] 无效的菜单选项 '{choice}'，请输入 0-4 之间的数字。"
