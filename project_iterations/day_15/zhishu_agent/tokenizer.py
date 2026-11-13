"""大模型 Token 估算与多模型 API 成本核算模块。

提供基于字符类型（CJK 中日韩字符 vs ASCII 字符与空白符）的离线 Token 估算，
以及面向企业预算管控的多模型 API 成本计算与横向对比功能。
"""

from __future__ import annotations

import math
from typing import Any

USD_TO_RMB: float = 7.25

# 各主流大模型每百万 Token 价格（单位：USD / 1M tokens）
MODEL_PRICING: dict[str, dict[str, Any]] = {
    "DeepSeek-V3": {
        "provider": "DeepSeek",
        "input_per_1m_usd": 0.27,
        "output_per_1m_usd": 1.10,
        "context_window": 65536,
    },
    "Qwen-Plus": {
        "provider": "Alibaba Cloud",
        "input_per_1m_usd": 0.40,
        "output_per_1m_usd": 1.20,
        "context_window": 131072,
    },
    "Llama-3.1-70B": {
        "provider": "Meta (Hosted)",
        "input_per_1m_usd": 0.59,
        "output_per_1m_usd": 0.79,
        "context_window": 131072,
    },
    "GPT-4o": {
        "provider": "OpenAI",
        "input_per_1m_usd": 2.50,
        "output_per_1m_usd": 10.00,
        "context_window": 128000,
    },
    "Claude-3.5-Sonnet": {
        "provider": "Anthropic",
        "input_per_1m_usd": 3.00,
        "output_per_1m_usd": 15.00,
        "context_window": 200000,
    },
}


def _is_cjk_char(ch: str) -> bool:
    """判断字符是否为 CJK（中日韩统一表意文字及常见全角标点）。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def estimate_tokens(text: str) -> int:
    """估算给定文本的 Token 数量（区分 CJK 与 ASCII/空白字符）。

    经验规则（贴近 BPE 分词器统计规律）：
    - CJK 字符及全角标点：约 1.5 tokens / 字符
    - ASCII 非空白字符：约 0.25 tokens / 字符（约 4 字符 = 1 token）
    - 空白字符（空格、制表符、换行等）：约 0.1 tokens / 字符
    - 其他 Unicode 字符：约 1.0 token / 字符

    Args:
        text: 待估算的输入字符串。

    Returns:
        估算的 Token 整数数量；空字符串返回 0，非空字符串至少返回 1。

    Raises:
        TypeError: 当传入非字符串类型时抛出。
    """
    if not isinstance(text, str):
        raise TypeError(f"text 必须为 str 类型，当前为 {type(text).__name__}")

    if not text:
        return 0

    cjk_count = 0
    ascii_non_space_count = 0
    whitespace_count = 0
    other_count = 0

    for ch in text:
        if _is_cjk_char(ch):
            cjk_count += 1
        elif ch.isspace():
            whitespace_count += 1
        elif ch.isascii():
            ascii_non_space_count += 1
        else:
            other_count += 1

    raw_tokens = (
        cjk_count * 1.5
        + ascii_non_space_count * 0.25
        + whitespace_count * 0.1
        + other_count * 1.0
    )
    return max(1, math.ceil(raw_tokens))


def estimate_api_cost(
    model: str,
    prompt_text: str,
    completion_text: str,
    usd_to_rmb: float = USD_TO_RMB,
) -> dict[str, Any]:
    """根据模型定价与输入输出文本，估算单次 API 调用的 Token 与费用（USD / RMB）。

    Args:
        model: 模型名称，必须存在于 `MODEL_PRICING` 中。
        prompt_text: 输入提示词文本。
        completion_text: 模型生成的输出文本。
        usd_to_rmb: 美元兑人民币汇率，默认 7.25。

    Returns:
        包含模型名、Token 明细及 USD/RMB 费用的字典。

    Raises:
        ValueError: 当模型不存在或汇率 <= 0 时抛出。
    """
    if model not in MODEL_PRICING:
        available = ", ".join(MODEL_PRICING.keys())
        raise ValueError(f"未知模型 '{model}'，可选模型: {available}")
    if usd_to_rmb <= 0:
        raise ValueError(f"usd_to_rmb 必须大于 0，当前为 {usd_to_rmb}")

    pricing = MODEL_PRICING[model]
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    total_tokens = prompt_tokens + completion_tokens

    input_cost_usd = (prompt_tokens / 1_000_000) * pricing["input_per_1m_usd"]
    output_cost_usd = (completion_tokens / 1_000_000) * pricing["output_per_1m_usd"]
    total_cost_usd = input_cost_usd + output_cost_usd

    return {
        "model": model,
        "provider": pricing["provider"],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": round(input_cost_usd, 8),
        "output_cost_usd": round(output_cost_usd, 8),
        "total_cost_usd": round(total_cost_usd, 8),
        "input_cost_rmb": round(input_cost_usd * usd_to_rmb, 8),
        "output_cost_rmb": round(output_cost_usd * usd_to_rmb, 8),
        "total_cost_rmb": round(total_cost_usd * usd_to_rmb, 8),
    }


def compare_models_cost(
    prompt_text: str,
    completion_text: str,
    models: list[str] | None = None,
    usd_to_rmb: float = USD_TO_RMB,
) -> list[dict[str, Any]]:
    """横向对比多个模型在相同输入输出下的成本，并按总费用从低到高排序。

    Args:
        prompt_text: 输入提示词文本。
        completion_text: 模型输出文本。
        models: 待对比的模型名称列表；为 None 时对比 `MODEL_PRICING` 全部模型。
        usd_to_rmb: 美元兑人民币汇率，默认 7.25。

    Returns:
        按 `total_cost_usd` 升序排列的成本字典列表。
    """
    target_models = list(MODEL_PRICING.keys()) if models is None else models
    results = [
        estimate_api_cost(
            model=m,
            prompt_text=prompt_text,
            completion_text=completion_text,
            usd_to_rmb=usd_to_rmb,
        )
        for m in target_models
    ]
    results.sort(key=lambda item: item["total_cost_usd"])
    return results
