"""Day 54 单元测试：LoRA 权重合并、微调前后评测与量化体积估算."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    EvalCase,
    build_default_eval_cases,
    compare_quantization_formats,
    estimate_quantized_size_gb,
    evaluate_before_after,
    merge_lora_weights,
)


def test_merge_lora_weights_exact_math_and_immutability() -> None:
    base_w = [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
    ]
    lora_b = [
        [1.0, 0.0],
        [0.0, 2.0],
    ]  # (2, 2)
    lora_a = [
        [0.5, -0.5, 1.0],
        [0.25, 0.5, -0.25],
    ]  # (2, 3)

    # scale = alpha / r = 8 / 2 = 4.0
    # B @ A = [[0.5, -0.5, 1.0], [0.5, 1.0, -0.5]]
    # scaled = [[2.0, -2.0, 4.0], [2.0, 4.0, -2.0]]
    # W' = [[3.0, 0.0, 7.0], [6.0, 9.0, 4.0]]
    merged = merge_lora_weights(base_w, lora_a, lora_b, lora_alpha=8, lora_rank=2)
    assert merged == [
        [3.0, 0.0, 7.0],
        [6.0, 9.0, 4.0],
    ]
    # 确认不会原地修改 base_w
    assert base_w == [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
    ]


def test_merge_lora_weights_validation_errors() -> None:
    with pytest.raises(ValueError, match="lora_rank"):
        merge_lora_weights([[1.0]], [[1.0]], [[1.0]], lora_alpha=16, lora_rank=0)

    with pytest.raises(ValueError, match="秩维度不匹配"):
        merge_lora_weights(
            [[1.0, 2.0]],
            [[0.1, 0.2]],  # rank=1
            [[0.3]],
            lora_alpha=16,
            lora_rank=2,
        )

    with pytest.raises(ValueError, match="维度不兼容"):
        merge_lora_weights(
            [[1.0, 2.0]],       # (1, 2)
            [[0.1, 0.2]],       # (1, 2) -> rank=1
            [[0.3], [0.4]],     # (2, 1) -> m_b=2 != m=1
            lora_alpha=16,
            lora_rank=1,
        )


def test_evaluate_before_after_default_suite() -> None:
    cases = build_default_eval_cases()
    report = evaluate_before_after(cases)

    assert report["total_cases"] == 5
    assert report["finetuned_accuracy"] == 1.0
    assert report["finetuned_format_compliance"] == 1.0
    assert report["finetuned_accuracy"] > report["base_accuracy"]
    assert report["finetuned_format_compliance"] > report["base_format_compliance"]
    assert report["accuracy_delta"] > 0
    assert report["format_compliance_delta"] > 0
    assert report["improved"] is True
    assert len(report["case_details"]) == 5


def test_evaluate_before_after_custom_dict_and_empty() -> None:
    custom_cases = [
        {
            "case_id": "c1",
            "expected_answer": '{"status": "ok"}',
            "base_output": "status is ok",
            "finetuned_output": '{"status": "ok"}',
            "expected_format": "json",
            "required_keys": ["status"],
        },
        EvalCase(
            case_id="c2",
            prompt="sql",
            expected_answer="SELECT id FROM users;",
            base_output="SELECT id FROM users;",
            finetuned_output="SELECT id FROM users;",
            expected_format="sql",
        ),
    ]
    report = evaluate_before_after(custom_cases)
    assert report["base_accuracy"] == 0.5
    assert report["finetuned_accuracy"] == 1.0
    assert report["base_format_compliance"] == 0.5
    assert report["finetuned_format_compliance"] == 1.0

    with pytest.raises(ValueError, match="不能为空"):
        evaluate_before_after([])


def test_estimate_quantized_size_gb_and_aliases() -> None:
    fp16 = estimate_quantized_size_gb(7.0, "FP16")
    gptq = estimate_quantized_size_gb(7.0, "GPTQ-4bit")
    awq = estimate_quantized_size_gb(7.0, "AWQ-4bit")
    q4_km = estimate_quantized_size_gb(7.0, "GGUF-Q4_K_M")
    q8_0 = estimate_quantized_size_gb(7.0, "Q8_0")
    gguf_q8 = estimate_quantized_size_gb(7.0, "GGUF-Q8_0")

    assert fp16 == pytest.approx(14.0, rel=1e-3)
    assert gptq == awq
    assert gptq < q4_km < q8_0 < fp16
    assert q8_0 == gguf_q8
    assert estimate_quantized_size_gb(14.0, "FP16") == pytest.approx(28.0, rel=1e-3)

    with pytest.raises(ValueError, match="params_billion"):
        estimate_quantized_size_gb(0, "FP16")

    with pytest.raises(ValueError, match="不支持的量化格式"):
        estimate_quantized_size_gb(7.0, "INT2-UNKNOWN")


def test_compare_quantization_formats() -> None:
    rows = compare_quantization_formats(7.0)
    formats = [r["quant_format"] for r in rows]
    assert formats == ["FP16", "GPTQ-4bit", "AWQ-4bit", "GGUF-Q4_K_M", "GGUF-Q8_0"]
    for row in rows:
        assert row["size_gb"] > 0
        assert row["recommended_vram_gb"] > row["size_gb"]
        assert row["compression_vs_fp16"] >= 1.0
