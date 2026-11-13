"""Day 54 平台启动入口：微调前后评测、LoRA 权重合并与量化选型演示 (v0.5.0-day54)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    build_default_eval_cases,
    compare_quantization_formats,
    evaluate_before_after,
    merge_lora_weights,
)


def main() -> None:
    """运行 Day 54 LoRA 合并、微调前后评测与量化体积估算全流程演示."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.5.0-day54 · 微调评测、LoRA 合并与量化")
    print("=" * 72)

    # 1. LoRA 权重合并演示: W' = W + (alpha / r) * (B @ A)
    base_w = [[1.0, 0.5, -0.5], [0.0, 1.0, 0.25]]
    lora_b = [[0.2, -0.1], [0.4, 0.2]]   # shape: (2, 2)
    lora_a = [[0.5, 0.0, 0.5], [0.0, 1.0, -0.5]]  # shape: (2, 3)
    merged_w = merge_lora_weights(base_w, lora_a, lora_b, lora_alpha=16, lora_rank=2)
    print("\n[1] LoRA 权重合并完成 (alpha=16, r=2, scale=8.0)")
    print("    Base W  :", base_w)
    print("    Merged W':", merged_w)

    # 2. 微调前后对比评测
    eval_report = evaluate_before_after(build_default_eval_cases())
    print("\n[2] 微调前后对比评测结果")
    print(f"    样本总数        : {eval_report['total_cases']}")
    print(
        f"    准确率 (Accuracy): Base={eval_report['base_accuracy']:.1%} -> "
        f"Fine-tuned={eval_report['finetuned_accuracy']:.1%} "
        f"(+{eval_report['accuracy_delta']:.1%})"
    )
    print(
        f"    格式合规率      : Base={eval_report['base_format_compliance']:.1%} -> "
        f"Fine-tuned={eval_report['finetuned_format_compliance']:.1%} "
        f"(+{eval_report['format_compliance_delta']:.1%})"
    )

    # 3. 7B / 14B 模型量化体积对比
    print("\n[3] 7B 参数模型不同量化格式体积与显存估算")
    for row in compare_quantization_formats(7.0):
        print(
            f"    {row['quant_format']:12s} | {row['bits_per_weight']:5.2f} bpw | "
            f"体积={row['size_gb']:6.3f} GB | 压缩比={row['compression_vs_fp16']:4.2f}x | "
            f"建议显存={row['recommended_vram_gb']:5.2f} GB"
        )


if __name__ == "__main__":
    main()
