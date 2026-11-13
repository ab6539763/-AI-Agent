"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 02 延续模块
功能：Prompt 模板清洗与敏感词脱敏引擎

业务背景：
在企业级智能体对话前，必须对用户输入进行空白字符规范化与敏感信息（手机号、API Key 等）脱敏，
防止隐私数据直接泄露给外部大模型接口。
"""

import re


def sanitize_prompt(text: str) -> str:
    """
    清洗用户输入的 Prompt 文本：去除首尾空白，并将连续空白符压缩为单个空格。

    参数:
        text (str): 原始用户输入文本

    返回:
        str: 规范化后的安全文本
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned


def mask_sensitive_info(text: str) -> str:
    """
    对文本中的常见敏感信息进行脱敏处理：
    1. 中国大陆 11 位手机号（保留前 3 位与后 4 位）
    2. 形如 sk-xxxx 的 API 密钥

    参数:
        text (str): 待脱敏文本

    返回:
        str: 脱敏后的文本
    """
    # 脱敏手机号：例如 13812345678 -> 138****5678
    masked = re.sub(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)", r"\1****\2", text)
    # 脱敏 API Key：例如 sk-abcdef123456 -> sk-***
    masked = re.sub(r"sk-[A-Za-z0-9_-]{4,}", "sk-***", masked)
    return masked


def clean_and_mask(text: str) -> str:
    """组合清洗与脱敏流程，作为 Agent 输入预处理标准入口。"""
    return mask_sensitive_info(sanitize_prompt(text))
