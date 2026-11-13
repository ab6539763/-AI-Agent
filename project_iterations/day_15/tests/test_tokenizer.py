"""Day 15 单元测试：Token 估算与多模型 API 成本核算。"""

import sys
from pathlib import Path

import pytest

DAY15_DIR = Path(__file__).resolve().parent.parent
if str(DAY15_DIR) not in sys.path:
    sys.path.insert(0, str(DAY15_DIR))

from zhishu_agent.tokenizer import (
    MODEL_PRICING,
    USD_TO_RMB,
    compare_models_cost,
    estimate_api_cost,
    estimate_tokens,
)


def test_estimate_tokens_empty_and_whitespace() -> None:
    """空字符串应返回 0，纯空白字符串至少返回 1。"""
    assert estimate_tokens("") == 0
    assert estimate_tokens(" ") == 1
    assert estimate_tokens("\n\t  ") == 1


def test_estimate_tokens_cjk_vs_ascii() -> None:
    """同等字符长度下，CJK 中文文本估算的 Token 密度应高于纯 ASCII 英文文本。"""
    cjk_text = "智枢企业级智能体平台"  # 10 个汉字 -> ceil(10 * 1.5) = 15
    ascii_text = "zhishu_ai!"  # 10 个 ASCII 字符 -> ceil(10 * 0.25) = 3

    assert estimate_tokens(cjk_text) == 15
    assert estimate_tokens(ascii_text) == 3
    assert estimate_tokens(cjk_text) > estimate_tokens(ascii_text)


def test_estimate_tokens_mixed_text_and_type_error() -> None:
    """混合文本（CJK + ASCII + 空格）应正确累加，非字符串输入应抛出 TypeError。"""
    mixed = "你好 AI"  # 2 CJK (3.0) + 1 space (0.1) + 2 ASCII (0.5) = 3.6 -> 4
    assert estimate_tokens(mixed) == 4

    with pytest.raises(TypeError):
        estimate_tokens(12345)  # type: ignore[arg-type]


def test_model_pricing_contains_required_models() -> None:
    """MODEL_PRICING 必须包含课程指定的 5 个主流大模型。"""
    expected_models = {
        "DeepSeek-V3",
        "Qwen-Plus",
        "GPT-4o",
        "Claude-3.5-Sonnet",
        "Llama-3.1-70B",
    }
    assert expected_models.issubset(MODEL_PRICING.keys())
    for model_name, info in MODEL_PRICING.items():
        assert info["input_per_1m_usd"] > 0, f"{model_name} 输入单价应大于 0"
        assert info["output_per_1m_usd"] > 0, f"{model_name} 输出单价应大于 0"


def test_estimate_api_cost_accuracy() -> None:
    """验证单模型成本核算的 Token 数量与 USD/RMB 金额计算准确性。"""
    prompt = "你好世界"  # 4 CJK -> 6 tokens
    completion = "Hello!"  # 6 ASCII -> ceil(1.5) = 2 tokens
    res = estimate_api_cost("GPT-4o", prompt, completion, usd_to_rmb=7.25)

    assert res["model"] == "GPT-4o"
    assert res["prompt_tokens"] == 6
    assert res["completion_tokens"] == 2
    assert res["total_tokens"] == 8

    expected_input_usd = (6 / 1_000_000) * 2.50
    expected_output_usd = (2 / 1_000_000) * 10.00
    expected_total_usd = expected_input_usd + expected_output_usd

    assert res["input_cost_usd"] == pytest.approx(expected_input_usd, rel=1e-6)
    assert res["output_cost_usd"] == pytest.approx(expected_output_usd, rel=1e-6)
    assert res["total_cost_usd"] == pytest.approx(expected_total_usd, rel=1e-6)
    assert res["total_cost_rmb"] == pytest.approx(expected_total_usd * USD_TO_RMB, rel=1e-6)


def test_estimate_api_cost_validation() -> None:
    """未知模型或非法汇率应抛出 ValueError。"""
    with pytest.raises(ValueError, match="未知模型"):
        estimate_api_cost("Unknown-Model", "hi", "hello")

    with pytest.raises(ValueError, match="usd_to_rmb"):
        estimate_api_cost("DeepSeek-V3", "hi", "hello", usd_to_rmb=0)


def test_compare_models_cost_sorted_and_filtered() -> None:
    """compare_models_cost 应按总费用升序排列，并支持指定模型子集。"""
    prompt = "请总结企业级智能体平台的核心架构。"
    completion = "核心架构包含路由层、工具调用层与记忆管理层。"

    all_results = compare_models_cost(prompt, completion)
    assert len(all_results) == len(MODEL_PRICING)
    costs = [r["total_cost_usd"] for r in all_results]
    assert costs == sorted(costs)
    assert all_results[0]["model"] in {"DeepSeek-V3", "Llama-3.1-70B"}
    assert all_results[-1]["model"] == "Claude-3.5-Sonnet"

    subset = compare_models_cost(prompt, completion, models=["GPT-4o", "Qwen-Plus"])
    assert [r["model"] for r in subset] == ["Qwen-Plus", "GPT-4o"]
