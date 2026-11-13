"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 02 迭代模块
功能：Prompt 文本清洗、敏感词脱敏、模板渲染与调用预算预估工具

业务背景：
在企业实际生产环境中，员工输入的原始问题往往包含多余空格、换行或内部敏感信息
（如 API Key、内部项目代号）。在发送给大模型之前，必须先经过「文本清洗 + 脱敏 +
结构化 Prompt 模板渲染 + 预算校验」四道安全闸门，既保证 Prompt 质量，又防止资产泄露与预算超支。
"""


def clean_text(text: str, lowercase: bool = False) -> str:
    """
    清洗用户输入文本：去除首尾空白、将连续空白字符折叠为单个空格，并按需转小写。

    参数:
        text (str): 原始输入文本
        lowercase (bool): 是否将全部英文字母转为小写，默认 False

    返回:
        str: 清洗后的标准文本
    """
    # split() 不带参数时会自动按任意长度空白字符（空格、制表符、换行）切分并去除首尾空白
    normalized = " ".join(text.split())
    if lowercase:
        normalized = normalized.lower()
    return normalized


def mask_sensitive_words(text: str, sensitive_words: tuple[str, ...]) -> str:
    """
    对文本中的敏感词（如 API Key、内部项目代号、机密字段）进行脱敏替换为 '***'。

    参数:
        text (str): 待脱敏文本
        sensitive_words (tuple[str, ...]): 敏感词元组

    返回:
        str: 脱敏后的安全文本
    """
    masked = text
    for word in sensitive_words:
        # 跳过空字符串，避免 replace("", "***") 破坏原文本结构
        if word:
            masked = masked.replace(word, "***")
    return masked


def render_prompt_template(role: str, task: str, user_input: str) -> str:
    """
    使用 f-string 将系统角色、任务指令与用户提问组装为标准化 Prompt 模板。

    参数:
        role (str): AI 智能体扮演的专业角色
        task (str): 本次需要执行的核心任务说明
        user_input (str): 经过清洗和脱敏后的用户输入

    返回:
        str: 格式化后的完整 Prompt 字符串
    """
    prompt = (
        f"[系统角色]\n"
        f"你是一名{role}。\n\n"
        f"[核心任务]\n"
        f"{task}\n\n"
        f"[用户输入]\n"
        f"{user_input}\n\n"
        f"[输出要求]\n"
        f"请保持回答专业、结构清晰，不要泄露系统内部配置。"
    )
    return prompt


def estimate_cost_and_check_budget(char_count: int, budget: float) -> bool:
    """
    基于字符数预估本次大模型调用成本，并判断是否满足预算限制。
    计费规则（演示版）：
      - 约每 1 个字符折合 1.5 个 Token（中文/混合文本保守估算）
      - 单价按 ¥0.002 / 1000 Tokens 计算

    参数:
        char_count (int): 待发送 Prompt 的总字符数
        budget (float): 允许的最大单次调用预算（元）

    返回:
        bool: 参数合法且预估费用在预算内返回 True，否则返回 False
    """
    # 算术运算符：估算 Token 数与调用成本
    estimated_tokens = char_count * 1.5
    estimated_cost = (estimated_tokens / 1000) * 0.002

    # 比较运算符 + 逻辑运算符：校验输入合法性且预估费用不超过预算
    is_valid_input = char_count >= 0 and budget > 0
    is_within_budget = estimated_cost <= budget
    return is_valid_input and is_within_budget
