"""Day 52 单元测试：指令微调数据集构建流水线 (v0.5.0-day52)."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    AlpacaSample,
    ShareGPTMessage,
    ShareGPTSample,
    alpaca_to_sharegpt,
    clean_and_deduplicate,
    clean_and_deduplicate_with_stats,
    compute_dataset_stats,
    export_jsonl,
    generate_customer_service_dataset,
    jaccard_similarity,
    load_jsonl,
    normalize_whitespace,
    sharegpt_to_alpaca,
)


def test_pydantic_models_validation() -> None:
    """测试 AlpacaSample 与 ShareGPTSample 的字段校验规则."""
    sample = AlpacaSample(
        instruction="查询订单物流状态",
        input="订单号：ZS20260001",
        output="您的订单已由顺丰速运发出，预计明日送达。",
        category="order_logistics",
    )
    assert sample.instruction == "查询订单物流状态"

    with pytest.raises(ValidationError):
        AlpacaSample(instruction="   ", output="有效回答")

    with pytest.raises(ValidationError):
        ShareGPTSample(
            conversations=[
                ShareGPTMessage(from_="human", value="你好"),
                ShareGPTMessage(from_="human", value="还在吗"),
            ]
        )


def test_alpaca_sharegpt_roundtrip_conversion() -> None:
    """测试 Alpaca 与 ShareGPT 格式的双向无损转换（含与不含 input）."""
    s_with_input = AlpacaSample(
        instruction="请协助核实退款进度",
        input="售后单号：RF20261001 | 金额：599元",
        output="您的 599 元退款已原路退回，预计 1-3 个工作日到账。",
        system="你是智枢智能客服助手。",
        category="refund_aftersales",
    )
    sg = alpaca_to_sharegpt(s_with_input)
    assert sg.conversations[0].from_ == "human"
    assert "输入：售后单号：RF20261001" in sg.conversations[0].value
    assert sg.conversations[1].from_ == "gpt"
    assert sharegpt_to_alpaca(sg) == s_with_input

    s_no_input = AlpacaSample(
        instruction="如何开通企业 SSO 单点登录？",
        input="",
        output="请进入安全中心上传 IdP 元数据 XML 并配置回调地址。",
        category="account_security",
    )
    sg2 = alpaca_to_sharegpt(s_no_input)
    assert sharegpt_to_alpaca(sg2) == s_no_input


def test_clean_and_deduplicate_pipeline() -> None:
    """测试空白规范化、最小长度过滤、精确去重与 Jaccard 近似去重."""
    assert normalize_whitespace("  你好\u200b   世界 \r\n\r\n\r\n 第二行  ") == "你好 世界\n\n第二行"
    assert jaccard_similarity("如何开具增值税专用发票", "如何开具增值税专用发票") == 1.0

    samples = [
        # 1. 正常样本（含多余空白，应被规范化后保留）
        AlpacaSample(
            instruction="  如何申请   数电增值税专用发票并推送到企业财务邮箱？\u200b ",
            input="",
            output=" 请在发票中心填写一般纳税人信息并提交开票申请。 ",
            category="invoice_billing",
        ),
        # 2. 精确重复（规范化后与第 1 条完全一致，应被过滤）
        AlpacaSample(
            instruction="如何申请 数电增值税专用发票并推送到企业财务邮箱？",
            input="",
            output="请在发票中心填写一般纳税人信息并提交开票申请。",
            category="invoice_billing",
        ),
        # 3. 近似重复（仅末尾多一个字，Jaccard >= 0.85，应被过滤）
        AlpacaSample(
            instruction="如何申请 数电增值税专用发票并推送到企业财务邮箱？谢谢",
            input="",
            output="请在发票中心填写一般纳税人信息并提交开票申请。",
            category="invoice_billing",
        ),
        # 4. 过短噪声样本（应被最小长度过滤）
        AlpacaSample(
            instruction="在吗",
            input="",
            output="在的",
            category="general",
        ),
        # 5. 另一条独立有效样本（应保留）
        AlpacaSample(
            instruction="企业账号原绑定手机号已停用，如何申诉换绑新手机号？",
            input="",
            output="请点击登录页「无法接收验证码」，通过实名身份核验与历史订单信息完成换绑。",
            category="account_security",
        ),
    ]

    cleaned, stats = clean_and_deduplicate_with_stats(samples)
    assert stats.input_count == 5
    assert stats.filtered_short_count == 1
    assert stats.exact_duplicate_count == 1
    assert stats.near_duplicate_count == 1
    assert stats.output_count == 2
    assert len(cleaned) == 2
    assert cleaned[0].instruction == "如何申请 数电增值税专用发票并推送到企业财务邮箱？"

    # 验证快捷函数 clean_and_deduplicate 返回一致结果
    assert clean_and_deduplicate(samples) == cleaned


def test_generate_customer_service_dataset_500() -> None:
    """测试 Self-Instruct 合成 500 条垂直客服数据集的规模、均衡性与唯一性."""
    dataset = generate_customer_service_dataset(count=500, seed=42)
    assert len(dataset) == 500

    cleaned, dedup_stats = clean_and_deduplicate_with_stats(dataset)
    assert dedup_stats.output_count == 500
    assert dedup_stats.exact_duplicate_count == 0
    assert dedup_stats.near_duplicate_count == 0

    ds_stats = compute_dataset_stats(cleaned)
    assert ds_stats.total_count == 500
    assert len(ds_stats.category_distribution) == 5
    assert all(cnt == 100 for cnt in ds_stats.category_distribution.values())
    assert 0.3 < ds_stats.with_input_ratio < 0.8

    # 测试注入脏数据后清洗流水线的拦截能力
    dirty_dataset = generate_customer_service_dataset(
        count=100, seed=7, include_dirty_ratio=0.2
    )
    _, dirty_stats = clean_and_deduplicate_with_stats(dirty_dataset)
    assert dirty_stats.input_count == 100
    assert dirty_stats.output_count == 80
    assert dirty_stats.exact_duplicate_count + dirty_stats.near_duplicate_count == 20


def test_export_and_load_jsonl(tmp_path: Path) -> None:
    """测试 Alpaca 与 ShareGPT JSONL 导出、回读校验与异常文件处理."""
    alpaca_samples = generate_customer_service_dataset(count=20, seed=99)
    sharegpt_samples = [alpaca_to_sharegpt(s) for s in alpaca_samples]

    alpaca_file = export_jsonl(alpaca_samples, tmp_path / "nested" / "alpaca.jsonl")
    sharegpt_file = export_jsonl(sharegpt_samples, tmp_path / "nested" / "sharegpt.jsonl")

    assert alpaca_file.exists()
    assert sharegpt_file.exists()
    assert '"from":"human"' in sharegpt_file.read_text(encoding="utf-8")

    loaded_alpaca = load_jsonl(alpaca_file, schema="alpaca")
    loaded_sharegpt = load_jsonl(sharegpt_file, schema="sharegpt")
    assert loaded_alpaca == alpaca_samples
    assert loaded_sharegpt == sharegpt_samples

    with pytest.raises(FileNotFoundError):
        load_jsonl(tmp_path / "nonexistent.jsonl")
