"""Day 51 核心模块：模型微调决策树与 GPU 显存预算计算器 (v0.5.0-day51)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

BYTES_PER_GIB = 1024**3

METHOD_ALIASES: dict[str, str] = {
    "full": "Full-FP16",
    "full-fp16": "Full-FP16",
    "full_fp16": "Full-FP16",
    "lora": "LoRA-FP16",
    "lora-fp16": "LoRA-FP16",
    "lora_fp16": "LoRA-FP16",
    "qlora": "QLoRA-4bit",
    "qlora-4bit": "QLoRA-4bit",
    "qlora_4bit": "QLoRA-4bit",
}


@dataclass(frozen=True)
class StrategyRecommendation:
    """模型适配策略推荐结果（Prompt / RAG / LoRA / QLoRA）."""

    strategy: str
    hybrid_with_rag: bool
    rationale: str
    estimated_cost_tier: str
    next_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VRAMBreakdown:
    """训练显存分项估算结果（单位：GB / GiB）."""

    params_billion: float
    method: str
    batch_size: int
    seq_len: int
    lora_rank: int
    trainable_params_million: float
    weights_gb: float
    gradients_gb: float
    optimizer_gb: float
    activations_gb: float
    overhead_gb: float
    total_gb: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GPURecommendation:
    """GPU 算力选型推荐结果."""

    vram_gb: float
    tier: str
    gpu_count: int
    estimated_hourly_usd: float
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recommend_adaptation_strategy(
    needs_fresh_knowledge: bool,
    needs_style_or_format: bool,
    has_labeled_data: bool,
    latency_budget_ms: int = 2000,
) -> StrategyRecommendation:
    """根据业务需求与约束条件，决策 Prompt / RAG / LoRA / QLoRA 最佳适配路径.

    Args:
        needs_fresh_knowledge: 是否需要高频更新或实时外部知识（如企业最新制度、日报、行情）。
        needs_style_or_format: 是否需要严格遵循特定领域风格、语气或结构化输出格式。
        has_labeled_data: 是否已具备高质量标注微调数据集（通常建议 >= 500~1000 条）。
        latency_budget_ms: 端到端推理延迟预算（毫秒），必须大于 0。

    Returns:
        StrategyRecommendation: 包含推荐策略、是否联动 RAG、工程理由与落地步骤。
    """
    if latency_budget_ms <= 0:
        raise ValueError("latency_budget_ms 必须大于 0")

    # 1. 仅需要动态/实时知识，无需改变模型内在风格或格式 -> RAG
    if needs_fresh_knowledge and not needs_style_or_format:
        return StrategyRecommendation(
            strategy="RAG",
            hybrid_with_rag=True,
            rationale=(
                "业务核心诉求为高频动态知识注入，无需改变基座模型内在表达风格。"
                "微调无法解决实时知识遗忘与更新成本问题，应优先采用 RAG 外挂检索增强。"
            ),
            estimated_cost_tier="低（零训练成本，仅检索与推理开销）",
            next_steps=[
                "构建企业文档切片与向量索引流水线（BGE/Hybrid Search）",
                "结合重排序（Reranker）与引用溯源 Prompt 模板降低幻觉",
            ],
        )

    # 2. 需要风格/格式定制（可能同时需要动态知识）
    if needs_style_or_format:
        if not has_labeled_data:
            strategy = "RAG" if needs_fresh_knowledge else "Prompt"
            return StrategyRecommendation(
                strategy=strategy,
                hybrid_with_rag=needs_fresh_knowledge,
                rationale=(
                    f"虽然存在风格或格式定制需求，但当前缺少高质量标注微调数据（has_labeled_data=False），"
                    f"直接微调易导致过拟合或灾难性遗忘。建议先用 {strategy} + Few-Shot 快速上线并沉淀标注集。"
                ),
                estimated_cost_tier="低（零训练成本，快速验证）",
                next_steps=[
                    "使用 Few-Shot 示例与 JSON Schema 约束输出格式",
                    "收集线上 Bad Case 与人工修正样本，积累 >= 500 条高质量 SFT 数据后再微调",
                ],
            )

        # 已具备标注数据，进入参数高效微调分支（LoRA vs QLoRA）
        hybrid_note = "建议搭配 RAG 注入实时外部知识（RAG + 微调混合架构）。" if needs_fresh_knowledge else ""
        if latency_budget_ms < 500:
            return StrategyRecommendation(
                strategy="LoRA",
                hybrid_with_rag=needs_fresh_knowledge,
                rationale=(
                    f"已具备标注数据且延迟预算严格（{latency_budget_ms}ms < 500ms）。"
                    "采用 LoRA-FP16 微调后可将旁路权重无损合并（merge_and_unload）回 FP16 基座，"
                    f"避免 4-bit 反量化推理延迟开销。{hybrid_note}".strip()
                ),
                estimated_cost_tier="中（单卡 24G~80G FP16 微调，推理零额外延迟）",
                next_steps=[
                    "使用 PEFT LoRA-FP16 在全注意力与 MLP 投影层进行 SFT 训练",
                    "训练完成后合并权重并通过 vLLM FP16/FP8 部署以满足低延迟 SLA",
                ],
            )

        return StrategyRecommendation(
            strategy="QLoRA",
            hybrid_with_rag=needs_fresh_knowledge,
            rationale=(
                f"已具备标注数据且延迟预算充裕（{latency_budget_ms}ms >= 500ms）。"
                "QLoRA（4-bit NF4 基座 + LoRA 适配器 + Paged AdamW）可降低约 70% 训练显存，"
                f"是企业私有化垂类微调性价比最高的首选方案。{hybrid_note}".strip()
            ),
            estimated_cost_tier="极低（消费级 24G 单卡即可微调 7B~14B 模型）",
            next_steps=[
                "使用 bitsandbytes NF4 双重量化加载基座模型并挂载 LoRA 适配器",
                "开启 Gradient Checkpointing 与 Paged AdamW-8bit 完成 SFT 微调",
            ],
        )

    # 3. 既不需要实时知识，也不需要特定风格/格式 -> Prompt
    return StrategyRecommendation(
        strategy="Prompt",
        hybrid_with_rag=False,
        rationale=(
            "通用能力即可满足需求，无需实时知识注入或特定格式微调。"
            "优先通过系统提示词工程（System Prompt + CoT + Few-Shot）实现最快交付与最低维护成本。"
        ),
        estimated_cost_tier="极低（零训练与检索基础设施成本）",
        next_steps=[
            "编写结构化 System Prompt 并在验证集上评测基线准确率",
            "如后续出现长尾格式稳定性问题，再补充样本并演进至 LoRA/QLoRA",
        ],
    )


def normalize_training_method(method: str) -> str:
    """将用户输入的微调方法别名归一化为标准名称."""
    key = method.strip().lower()
    if key not in METHOD_ALIASES:
        raise ValueError(
            f"不支持的微调方法 '{method}'，可选值: Full-FP16, LoRA-FP16, QLoRA-4bit"
        )
    return METHOD_ALIASES[key]


def estimate_training_vram_gb(
    params_billion: float,
    method: str = "QLoRA-4bit",
    batch_size: int = 1,
    seq_len: int = 2048,
    lora_rank: int = 16,
) -> VRAMBreakdown:
    """估算大模型微调训练显存需求（Weights + Gradients + AdamW Optimizer + Activations + Overhead）.

    Args:
        params_billion: 模型总参数量（单位：十亿 / Billion，如 7.0 代表 7B）。
        method: 微调方法，支持 'Full-FP16', 'LoRA-FP16', 'QLoRA-4bit'（及简写 full/lora/qlora）。
        batch_size: 单卡微批次大小（micro_batch_size）。
        seq_len: 训练序列长度（tokens）。
        lora_rank: LoRA 低秩矩阵秩（r），仅对 LoRA-FP16 / QLoRA-4bit 生效。

    Returns:
        VRAMBreakdown: 显存各分项及总计（单位：GB / GiB）。
    """
    if params_billion <= 0:
        raise ValueError("params_billion 必须大于 0")
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    if seq_len <= 0:
        raise ValueError("seq_len 必须大于 0")

    norm_method = normalize_training_method(method)
    if norm_method in {"LoRA-FP16", "QLoRA-4bit"} and lora_rank <= 0:
        raise ValueError("使用 LoRA / QLoRA 时 lora_rank 必须大于 0")

    total_params = params_billion * 1e9
    # LoRA 可训练参数比例近似：r=16 时约为总参数的 0.8%（覆盖 attention + MLP 投影层）
    trainable_ratio = min(0.05, 0.0005 * lora_rank)
    trainable_params = total_params if norm_method == "Full-FP16" else total_params * trainable_ratio

    if norm_method == "Full-FP16":
        weights_bytes = total_params * 2.0
        gradients_bytes = total_params * 2.0
        # 混合精度 AdamW：FP32 主权重备份 (4B) + 一阶矩 m (4B) + 二阶矩 v (4B) = 12 B/param
        optimizer_bytes = total_params * 12.0
        activation_multiplier = 1.5
    elif norm_method == "LoRA-FP16":
        weights_bytes = total_params * 2.0 + trainable_params * 2.0
        gradients_bytes = trainable_params * 2.0
        optimizer_bytes = trainable_params * 12.0
        activation_multiplier = 1.0
    else:  # QLoRA-4bit
        # 4-bit NF4 双重量化平均约 0.55 B/param + FP16 LoRA 适配器权重
        weights_bytes = total_params * 0.55 + trainable_params * 2.0
        gradients_bytes = trainable_params * 2.0
        # Paged AdamW 8-bit：FP32 主权重 (4B) + 8-bit m/v (2B) = 6 B/trainable_param
        optimizer_bytes = trainable_params * 6.0
        activation_multiplier = 1.0

    weights_gb = weights_bytes / BYTES_PER_GIB
    gradients_gb = gradients_bytes / BYTES_PER_GIB
    optimizer_gb = optimizer_bytes / BYTES_PER_GIB

    # 开启 Gradient Checkpointing 下的激活值显存近似模型
    activations_gb = (
        batch_size
        * (seq_len / 2048.0)
        * (1.2 + 0.35 * (params_billion**0.65))
        * activation_multiplier
    )
    # PyTorch CUDA 上下文与显存碎片预留
    overhead_gb = 1.0
    total_gb = weights_gb + gradients_gb + optimizer_gb + activations_gb + overhead_gb

    return VRAMBreakdown(
        params_billion=round(params_billion, 3),
        method=norm_method,
        batch_size=batch_size,
        seq_len=seq_len,
        lora_rank=0 if norm_method == "Full-FP16" else lora_rank,
        trainable_params_million=round(trainable_params / 1e6, 2),
        weights_gb=round(weights_gb, 2),
        gradients_gb=round(gradients_gb, 2),
        optimizer_gb=round(optimizer_gb, 2),
        activations_gb=round(activations_gb, 2),
        overhead_gb=round(overhead_gb, 2),
        total_gb=round(total_gb, 2),
    )


def recommend_gpu(vram_gb: float) -> GPURecommendation:
    """根据预估训练显存（GB）推荐满足安全余量的 GPU 硬件规格."""
    if vram_gb <= 0:
        raise ValueError("vram_gb 必须大于 0")

    if vram_gb <= 22.0:
        return GPURecommendation(
            vram_gb=round(vram_gb, 2),
            tier="RTX 4090 24G",
            gpu_count=1,
            estimated_hourly_usd=0.45,
            notes="单张消费级 RTX 4090 (24GB) 即可满足显存需求并保留安全余量，性价比最优。",
        )
    if vram_gb <= 38.0:
        return GPURecommendation(
            vram_gb=round(vram_gb, 2),
            tier="A100 40G",
            gpu_count=1,
            estimated_hourly_usd=1.40,
            notes="超出 24GB 消费卡上限，推荐单张 A100 40GB 数据中心级显卡（支持高带宽 BF16）。",
        )
    if vram_gb <= 76.0:
        return GPURecommendation(
            vram_gb=round(vram_gb, 2),
            tier="A100 80G",
            gpu_count=1,
            estimated_hourly_usd=2.10,
            notes="需大显存单卡承载，推荐 A100 80GB（或 H100 80GB）避免多卡通信开销。",
        )

    gpu_count = max(2, math.ceil(vram_gb / 72.0))
    return GPURecommendation(
        vram_gb=round(vram_gb, 2),
        tier="Multi-GPU",
        gpu_count=gpu_count,
        estimated_hourly_usd=round(2.10 * gpu_count, 2),
        notes=(
            f"超出单卡 80GB 物理显存上限，建议采用 {gpu_count}x A100 80G "
            "配合 DeepSpeed ZeRO-3 / FSDP 分布式切分优化器与参数。"
        ),
    )
