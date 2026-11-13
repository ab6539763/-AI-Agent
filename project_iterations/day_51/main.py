"""Day 51 平台启动入口：模型适配决策树与 GPU 显存预算评估演示 (v0.5.0-day51)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    estimate_training_vram_gb,
    recommend_adaptation_strategy,
    recommend_gpu,
)


def main() -> None:
    """演示企业垂类模型微调可行性决策树与 Qwen2.5-7B 显存预算评估."""
    print("=" * 72)
    print("🧮 智枢企业级智能体平台 v0.5.0-day51 · 微调决策树与 GPU 显存计算器")
    print("=" * 72)

    print("\n[1] 业务场景策略决策演示:")
    scenarios = [
        ("企业实时制度问答", True, False, False, 1500),
        ("金融研报固定格式生成（高延迟容忍）", False, True, True, 1200),
        ("客服工单毫秒级分类（低延迟 SLA）", False, True, True, 300),
        ("通用文案润色助手", False, False, False, 2000),
    ]
    for name, fresh, style, labeled, budget in scenarios:
        rec = recommend_adaptation_strategy(fresh, style, labeled, budget)
        print(f"  - {name} -> 推荐: {rec.strategy} (RAG联动={rec.hybrid_with_rag})")

    print("\n[2] Qwen2.5-7B (batch_size=1, seq_len=2048, lora_rank=16) 显存对比:")
    for method in ["Full-FP16", "LoRA-FP16", "QLoRA-4bit"]:
        vram = estimate_training_vram_gb(7.0, method=method, batch_size=1, seq_len=2048, lora_rank=16)
        gpu = recommend_gpu(vram.total_gb)
        print(
            f"  - {vram.method:10s} | 总显存={vram.total_gb:6.2f} GB "
            f"(权重={vram.weights_gb:.2f}, 梯度={vram.gradients_gb:.2f}, "
            f"优化器={vram.optimizer_gb:.2f}, 激活={vram.activations_gb:.2f}) "
            f"-> {gpu.tier} x{gpu.gpu_count}"
        )


if __name__ == "__main__":
    main()
