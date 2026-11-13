"""Day 51 单元测试：微调决策树、训练显存估算与 GPU 选型推荐."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    estimate_training_vram_gb,
    recommend_adaptation_strategy,
    recommend_gpu,
)


def test_decision_tree_prompt_and_rag() -> None:
    """验证通用任务走 Prompt、纯实时知识任务走 RAG、无标注数据的风格任务先走 Prompt/RAG."""
    p_rec = recommend_adaptation_strategy(
        needs_fresh_knowledge=False,
        needs_style_or_format=False,
        has_labeled_data=False,
        latency_budget_ms=1500,
    )
    assert p_rec.strategy == "Prompt"
    assert p_rec.hybrid_with_rag is False

    rag_rec = recommend_adaptation_strategy(
        needs_fresh_knowledge=True,
        needs_style_or_format=False,
        has_labeled_data=True,
        latency_budget_ms=1500,
    )
    assert rag_rec.strategy == "RAG"
    assert rag_rec.hybrid_with_rag is True

    no_data_style = recommend_adaptation_strategy(
        needs_fresh_knowledge=False,
        needs_style_or_format=True,
        has_labeled_data=False,
        latency_budget_ms=1000,
    )
    assert no_data_style.strategy == "Prompt"


def test_decision_tree_lora_vs_qlora() -> None:
    """验证具备标注数据时，低延迟 SLA 选 LoRA，高性价比预算选 QLoRA，且可标记 RAG 联动."""
    lora_rec = recommend_adaptation_strategy(
        needs_fresh_knowledge=False,
        needs_style_or_format=True,
        has_labeled_data=True,
        latency_budget_ms=300,
    )
    assert lora_rec.strategy == "LoRA"
    assert lora_rec.hybrid_with_rag is False

    qlora_hybrid = recommend_adaptation_strategy(
        needs_fresh_knowledge=True,
        needs_style_or_format=True,
        has_labeled_data=True,
        latency_budget_ms=1200,
    )
    assert qlora_hybrid.strategy == "QLoRA"
    assert qlora_hybrid.hybrid_with_rag is True


def test_vram_estimation_qwen_7b_ordering() -> None:
    """验证 Qwen2.5-7B 在 Full-FP16 / LoRA-FP16 / QLoRA-4bit 下的显存分项与大小关系."""
    full = estimate_training_vram_gb(7.0, method="Full-FP16", batch_size=1, seq_len=2048)
    lora = estimate_training_vram_gb(7.0, method="LoRA-FP16", batch_size=1, seq_len=2048, lora_rank=16)
    qlora = estimate_training_vram_gb(7.0, method="QLoRA-4bit", batch_size=1, seq_len=2048, lora_rank=16)

    assert full.total_gb > lora.total_gb > qlora.total_gb
    # Full-FP16 的 AdamW 优化器状态应远大于权重本身（12B/param vs 2B/param）
    assert full.optimizer_gb > full.weights_gb * 5
    # LoRA 与 QLoRA 的梯度与优化器显存应远小于 Full-FP16
    assert lora.optimizer_gb < 2.0
    assert qlora.weights_gb < 5.0
    assert qlora.total_gb < 12.0


def test_vram_scales_with_batch_and_seq_len() -> None:
    """验证 batch_size 与 seq_len 增大时激活值显存线性增长."""
    base = estimate_training_vram_gb(7.0, method="qlora", batch_size=1, seq_len=2048, lora_rank=16)
    larger = estimate_training_vram_gb(7.0, method="qlora", batch_size=4, seq_len=4096, lora_rank=16)

    assert larger.weights_gb == base.weights_gb
    assert larger.activations_gb == pytest.approx(base.activations_gb * 8, rel=0.02)
    assert larger.total_gb > base.total_gb


def test_recommend_gpu_tiers_and_validation() -> None:
    """验证 GPU 选型四档边界与非法参数校验."""
    assert recommend_gpu(16.5).tier == "RTX 4090 24G"
    assert recommend_gpu(30.0).tier == "A100 40G"
    assert recommend_gpu(65.0).tier == "A100 80G"

    multi = recommend_gpu(110.0)
    assert multi.tier == "Multi-GPU"
    assert multi.gpu_count >= 2

    with pytest.raises(ValueError):
        recommend_adaptation_strategy(False, False, False, latency_budget_ms=0)
    with pytest.raises(ValueError):
        estimate_training_vram_gb(7.0, method="unknown_method")
    with pytest.raises(ValueError):
        estimate_training_vram_gb(-1.0, method="qlora")
    with pytest.raises(ValueError):
        recommend_gpu(0.0)
