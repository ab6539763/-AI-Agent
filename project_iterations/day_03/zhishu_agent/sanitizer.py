"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 02 迭代模块（沿用至 Day 03）
功能：Prompt 模板清洗与敏感词脱敏引擎
"""

import re

DEFAULT_SENSITIVE_WORDS: list[str] = ["密码", "密钥", "API_KEY", "sk-", "身份证", "手机号"]


def clean_prompt(text: str) -> str:
    """
    清洗 Prompt 文本：去除首尾空白，并将连续空白字符折叠为单个空格。
    """
    return re.sub(r"\s+", " ", text.strip())


def mask_sensitive_words(
    text: str,
    sensitive_words: list[str] | None = None,
    mask: str = "***",
) -> str:
    """
    对文本中的敏感词进行脱敏替换。
    """
    words = sensitive_words if sensitive_words is not None else DEFAULT_SENSITIVE_WORDS
    result = text
    for word in words:
        if word:
            result = result.replace(word, mask)
    return result


def sanitize_prompt(
    text: str,
    sensitive_words: list[str] | None = None,
) -> str:
    """
    一站式清洗并脱敏 Prompt 文本。
    """
    cleaned = clean_prompt(text)
    return mask_sensitive_words(cleaned, sensitive_words=sensitive_words)
