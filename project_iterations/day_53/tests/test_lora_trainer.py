"""Day 53 单元测试：LLaMA-Factory LoRA 配置、参数数学与 Loss 曲线诊断."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (  # noqa: E402
    LoRATrainingConfig,
    count_lora_trainable_params,
    export_llamafactory_yaml,
    simulate_training_run,
)


def test_lora_config_defaults_and_validation() -> None:
    """验证 LoRATrainingConfig 默认值、Effective Batch Size 与非法参数拦截."""
    cfg = LoRATrainingConfig()
    assert cfg.finetuning_type == "lora"
    assert cfg.template == "qwen"
    assert cfg.lora_scaling == 2.0
    assert cfg.effective_batch_size(num_gpus=1) == 16
    assert cfg.effective_batch_size(num_gpus=4) == 64

    with pytest.raises(ValidationError):
        LoRATrainingConfig(finetuning_type="full")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        LoRATrainingConfig(lora_rank=0)

    with pytest.raises(ValidationError):
        LoRATrainingConfig(learning_rate=-1e-4)


def test_export_llamafactory_yaml() -> None:
    """验证导出的 YAML 包含 LLaMA-Factory 必需字段与正确值."""
    cfg = LoRATrainingConfig(
        model_name_or_path="Qwen/Qwen2.5-7B-Instruct",
        lora_rank=16,
        lora_alpha=32,
        learning_rate=2e-4,
        num_train_epochs=4.0,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        template="qwen",
    )
    yaml_text = export_llamafactory_yaml(cfg)
    assert "model_name_or_path: Qwen/Qwen2.5-7B-Instruct" in yaml_text
    assert "finetuning_type: lora" in yaml_text
    assert "lora_rank: 16" in yaml_text
    assert "lora_alpha: 32" in yaml_text
    assert "learning_rate: 2.0e-04" in yaml_text
    assert "per_device_train_batch_size: 2" in yaml_text
    assert "gradient_accumulation_steps: 8" in yaml_text
    assert "template: qwen" in yaml_text


def test_count_lora_trainable_params() -> None:
    """验证 LoRA 可训练参数量计算公式与 GQA/MLP 细分统计."""
    # 标准方阵投影: 4 modules * 2 * r(8) * H(3584) * L(28) = 6,422,528
    stats = count_lora_trainable_params(
        hidden_size=3584,
        num_hidden_layers=28,
        lora_rank=8,
        target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
        base_model_params=7_615_616_512,
    )
    assert stats.params_per_layer == 4 * 2 * 8 * 3584
    assert stats.trainable_params == 28 * 4 * 2 * 8 * 3584
    assert 0.05 < stats.trainable_percentage < 0.2
    assert stats.lora_memory_fp16_mb > 0

    # 含 GQA 与 MLP 的精细统计
    gqa_stats = count_lora_trainable_params(
        hidden_size=3584,
        num_hidden_layers=28,
        lora_rank=8,
        target_modules=("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"),
        base_model_params=7_615_616_512,
        intermediate_size=18944,
        num_attention_heads=28,
        num_key_value_heads=4,
    )
    assert gqa_stats.trainable_params > stats.trainable_params
    assert "gate_proj" in gqa_stats.module_breakdown

    with pytest.raises(ValueError):
        count_lora_trainable_params(hidden_size=0, num_hidden_layers=28, lora_rank=8)


def test_simulate_training_run_diagnoses() -> None:
    """验证健康收敛、欠拟合、过拟合与梯度发散四类诊断结果."""
    # 1. 健康收敛
    healthy_cfg = LoRATrainingConfig(
        lora_rank=8,
        lora_alpha=16,
        learning_rate=1e-4,
        num_train_epochs=3.0,
    )
    healthy_res = simulate_training_run(healthy_cfg, dataset_size=1000)
    assert healthy_res.diagnosis == "healthy"
    assert healthy_res.final_train_loss < healthy_res.history[0].train_loss
    assert healthy_res.generalization_gap < 0.25

    # 2. 欠拟合（epoch 太少 + 学习率太低）
    underfit_cfg = LoRATrainingConfig(
        lora_rank=2,
        lora_alpha=4,
        learning_rate=1e-6,
        num_train_epochs=0.5,
    )
    underfit_res = simulate_training_run(underfit_cfg, dataset_size=1000)
    assert underfit_res.diagnosis == "underfitting"
    assert underfit_res.final_train_loss > 1.30

    # 3. 过拟合（小数据集 + 高 epoch + 大 rank）
    overfit_cfg = LoRATrainingConfig(
        lora_rank=64,
        lora_alpha=128,
        learning_rate=2e-4,
        num_train_epochs=10.0,
    )
    overfit_res = simulate_training_run(overfit_cfg, dataset_size=200)
    assert overfit_res.diagnosis == "overfitting"
    assert overfit_res.final_eval_loss > overfit_res.best_eval_loss

    # 4. 梯度发散（学习率过高）
    diverging_cfg = LoRATrainingConfig(
        lora_rank=8,
        lora_alpha=32,
        learning_rate=2e-2,
        num_train_epochs=3.0,
    )
    diverging_res = simulate_training_run(diverging_cfg, dataset_size=1000)
    assert diverging_res.diagnosis == "diverging"
