"""Day 53 平台启动入口：LLaMA-Factory LoRA 微调配置生成、参数量计算与 Loss 曲线诊断 (v0.5.0-day53)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    LoRATrainingConfig,
    count_lora_trainable_params,
    export_llamafactory_yaml,
    simulate_training_run,
)


def main() -> None:
    """演示 LoRA 配置导出、参数量核算与三类训练曲线诊断."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.5.0-day53 · LLaMA-Factory LoRA 微调实战")
    print("=" * 72)

    config = LoRATrainingConfig(
        model_name_or_path="Qwen/Qwen2.5-7B-Instruct",
        lora_rank=8,
        lora_alpha=16,
        learning_rate=1e-4,
        num_train_epochs=3.0,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        template="qwen",
    )

    print("\n[1] 生成 LLaMA-Factory YAML 配置:")
    print(export_llamafactory_yaml(config))

    print("[2] Qwen2.5-7B 尺度 LoRA 可训练参数量核算:")
    stats = count_lora_trainable_params(
        hidden_size=3584,
        num_hidden_layers=28,
        lora_rank=config.lora_rank,
        target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
        base_model_params=7_615_616_512,
    )
    print(
        f"  可训练参数: {stats.trainable_params:,} / {stats.total_base_params:,} "
        f"({stats.trainable_percentage:.4f}%), FP16 显存: {stats.lora_memory_fp16_mb} MB"
    )

    print("\n[3] 模拟训练与 Loss 曲线诊断:")
    result = simulate_training_run(config, dataset_size=1000, num_gpus=1)
    print(result.summary_markdown())


if __name__ == "__main__":
    main()
