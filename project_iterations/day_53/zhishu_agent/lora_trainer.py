"""Day 53: LLaMA-Factory LoRA Fine-Tuning Practice (v0.5.0-day53).

Provides:
- LoRATrainingConfig: Pydantic configuration model for LLaMA-Factory LoRA SFT.
- export_llamafactory_yaml: Export LoRATrainingConfig into a LLaMA-Factory YAML string.
- count_lora_trainable_params: Exact LoRA trainable parameter math & memory estimation.
- simulate_training_run: Deterministic train/eval loss curve simulator and overfitting/underfitting/diverging diagnostic.
"""

from __future__ import annotations

import math
from typing import Literal, Sequence

from pydantic import BaseModel, Field, field_validator


class LoRATrainingConfig(BaseModel):
    """LLaMA-Factory LoRA 微调核心配置模型."""

    model_name_or_path: str = Field(
        default="Qwen/Qwen2.5-7B-Instruct",
        min_length=1,
        description="基座模型名称或本地权重路径",
    )
    finetuning_type: Literal["lora"] = Field(
        default="lora",
        description="微调方式，本模块固定为 lora",
    )
    lora_rank: int = Field(
        default=8,
        ge=1,
        le=256,
        description="LoRA 低秩矩阵的秩 (r)",
    )
    lora_alpha: int = Field(
        default=16,
        ge=1,
        le=512,
        description="LoRA 缩放系数 (alpha)，实际缩放比例为 alpha / rank",
    )
    learning_rate: float = Field(
        default=1e-4,
        gt=0.0,
        le=1.0,
        description="初始学习率",
    )
    num_train_epochs: float = Field(
        default=3.0,
        gt=0.0,
        le=100.0,
        description="训练总轮数 (Epochs)",
    )
    per_device_train_batch_size: int = Field(
        default=4,
        ge=1,
        le=512,
        description="单卡每次前向传播的 micro-batch 大小",
    )
    gradient_accumulation_steps: int = Field(
        default=4,
        ge=1,
        le=512,
        description="梯度累积步数",
    )
    template: str = Field(
        default="qwen",
        min_length=1,
        description="LLaMA-Factory 对话模板名称（如 qwen, llama3, chatglm3）",
    )
    dataset: str = Field(
        default="zhishu_enterprise_sft",
        min_length=1,
        description="训练数据集名称（对应 dataset_info.json 中的键）",
    )
    cutoff_len: int = Field(
        default=2048,
        ge=128,
        le=32768,
        description="最大序列截断长度",
    )
    lora_target: str = Field(
        default="all",
        min_length=1,
        description="注入 LoRA 的目标线性层（如 all 或 q_proj,v_proj）",
    )
    val_size: float = Field(
        default=0.1,
        gt=0.0,
        lt=0.5,
        description="验证集切分比例",
    )
    logging_steps: int = Field(default=10, ge=1)
    save_steps: int = Field(default=100, ge=1)
    eval_steps: int = Field(default=50, ge=1)
    bf16: bool = Field(default=True, description="是否开启 bf16 混合精度训练")
    output_dir: str = Field(
        default="saves/qwen2.5-7b/lora/zhishu-sft",
        min_length=1,
        description="Checkpoint 与日志输出目录",
    )

    @field_validator("model_name_or_path", "template", "dataset", "lora_target", "output_dir")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("字段不能为空白字符串")
        return cleaned

    @property
    def lora_scaling(self) -> float:
        """LoRA 实际权重缩放因子 alpha / rank."""
        return round(self.lora_alpha / self.lora_rank, 4)

    def effective_batch_size(self, num_gpus: int = 1) -> int:
        """计算全局有效批次大小 (Effective Batch Size)."""
        if num_gpus < 1:
            raise ValueError("num_gpus 必须大于等于 1")
        return self.per_device_train_batch_size * self.gradient_accumulation_steps * num_gpus


def export_llamafactory_yaml(config: LoRATrainingConfig) -> str:
    """将 LoRATrainingConfig 导出为标准 LLaMA-Factory 训练 YAML 配置字符串."""
    lr_str = f"{config.learning_rate:.1e}" if config.learning_rate < 1e-2 else str(config.learning_rate)
    bf16_str = "true" if config.bf16 else "false"
    lines = [
        "### model",
        f"model_name_or_path: {config.model_name_or_path}",
        "trust_remote_code: true",
        "",
        "### method",
        "stage: sft",
        "do_train: true",
        f"finetuning_type: {config.finetuning_type}",
        f"lora_rank: {config.lora_rank}",
        f"lora_alpha: {config.lora_alpha}",
        f"lora_target: {config.lora_target}",
        "",
        "### dataset",
        f"dataset: {config.dataset}",
        f"template: {config.template}",
        f"cutoff_len: {config.cutoff_len}",
        "preprocessing_num_workers: 4",
        "",
        "### output",
        f"output_dir: {config.output_dir}",
        f"logging_steps: {config.logging_steps}",
        f"save_steps: {config.save_steps}",
        "plot_loss: true",
        "overwrite_output_dir: true",
        "",
        "### train",
        f"per_device_train_batch_size: {config.per_device_train_batch_size}",
        f"gradient_accumulation_steps: {config.gradient_accumulation_steps}",
        f"learning_rate: {lr_str}",
        f"num_train_epochs: {config.num_train_epochs}",
        "lr_scheduler_type: cosine",
        "warmup_ratio: 0.1",
        f"bf16: {bf16_str}",
        "",
        "### eval",
        f"val_size: {config.val_size}",
        "per_device_eval_batch_size: 2",
        "eval_strategy: steps",
        f"eval_steps: {config.eval_steps}",
        "",
    ]
    return "\n".join(lines)


class LoRAParamStats(BaseModel):
    """LoRA 可训练参数统计结果."""

    hidden_size: int
    num_hidden_layers: int
    lora_rank: int
    target_modules: list[str]
    params_per_layer: int
    trainable_params: int
    total_base_params: int
    trainable_ratio: float
    trainable_percentage: float
    lora_memory_fp16_mb: float
    module_breakdown: dict[str, int]


def count_lora_trainable_params(
    hidden_size: int,
    num_hidden_layers: int,
    lora_rank: int,
    target_modules: Sequence[str] | int = ("q_proj", "k_proj", "v_proj", "o_proj"),
    base_model_params: int | None = None,
    intermediate_size: int | None = None,
    num_attention_heads: int | None = None,
    num_key_value_heads: int | None = None,
) -> LoRAParamStats:
    """计算 Transformer 模型注入 LoRA 后的可训练参数量与占比.

    对于单个线性层 W in R^{d_out x d_in}，LoRA 旁路矩阵 A(r x d_in) 与 B(d_out x r)
    的总参数量为 r * (d_in + d_out)。
    若未显式传入 intermediate_size 或 GQA 头数，则按标准方阵 d_in = d_out = hidden_size
    计算，即每个目标模块每层贡献 2 * lora_rank * hidden_size 个可训练参数。
    """
    if hidden_size < 1:
        raise ValueError("hidden_size 必须为正整数")
    if num_hidden_layers < 1:
        raise ValueError("num_hidden_layers 必须为正整数")
    if lora_rank < 1:
        raise ValueError("lora_rank 必须为正整数")

    if isinstance(target_modules, int):
        if target_modules < 1:
            raise ValueError("target_modules 数量必须大于等于 1")
        module_names = [f"proj_{idx + 1}" for idx in range(target_modules)]
    else:
        module_names = [m.strip() for m in target_modules if m.strip()]
        if not module_names:
            raise ValueError("target_modules 不能为空")

    kv_out_dim = hidden_size
    if (
        num_attention_heads is not None
        and num_key_value_heads is not None
        and num_attention_heads > 0
        and num_key_value_heads > 0
    ):
        head_dim = hidden_size // num_attention_heads
        kv_out_dim = head_dim * num_key_value_heads

    module_breakdown: dict[str, int] = {}
    params_per_layer = 0

    for mod in module_names:
        if mod in {"k_proj", "v_proj"}:
            d_in, d_out = hidden_size, kv_out_dim
        elif mod in {"gate_proj", "up_proj"} and intermediate_size is not None:
            d_in, d_out = hidden_size, intermediate_size
        elif mod == "down_proj" and intermediate_size is not None:
            d_in, d_out = intermediate_size, hidden_size
        else:
            d_in, d_out = hidden_size, hidden_size

        mod_params_per_layer = lora_rank * (d_in + d_out)
        module_breakdown[mod] = mod_params_per_layer * num_hidden_layers
        params_per_layer += mod_params_per_layer

    trainable_params = params_per_layer * num_hidden_layers

    if base_model_params is None:
        # 近似估算标准 Transformer 骨架参数量（约 12 * L * H^2）
        total_base_params = 12 * num_hidden_layers * (hidden_size ** 2)
    else:
        if base_model_params < 1:
            raise ValueError("base_model_params 必须为正整数")
        total_base_params = base_model_params

    trainable_ratio = trainable_params / total_base_params
    trainable_percentage = round(trainable_ratio * 100.0, 4)
    # fp16/bf16 下每个参数占 2 Bytes
    lora_memory_fp16_mb = round((trainable_params * 2) / (1024 * 1024), 4)

    return LoRAParamStats(
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        lora_rank=lora_rank,
        target_modules=module_names,
        params_per_layer=params_per_layer,
        trainable_params=trainable_params,
        total_base_params=total_base_params,
        trainable_ratio=trainable_ratio,
        trainable_percentage=trainable_percentage,
        lora_memory_fp16_mb=lora_memory_fp16_mb,
        module_breakdown=module_breakdown,
    )


class LossPoint(BaseModel):
    """单个采样步的训练/验证损失点."""

    step: int
    epoch: float
    train_loss: float
    eval_loss: float


DiagnosisType = Literal["healthy", "underfitting", "overfitting", "diverging"]


class TrainingSimulationResult(BaseModel):
    """LoRA 训练仿真与 Loss 曲线诊断结果."""

    model_name_or_path: str
    effective_batch_size: int
    steps_per_epoch: int
    total_steps: int
    lora_scaling: float
    history: list[LossPoint]
    final_train_loss: float
    final_eval_loss: float
    best_eval_loss: float
    best_step: int
    generalization_gap: float
    diagnosis: DiagnosisType
    recommendations: list[str]

    def summary_markdown(self) -> str:
        """生成可读的 Markdown 诊断摘要."""
        rec_lines = "\n".join(f"- {item}" for item in self.recommendations)
        return (
            f"### LoRA 训练仿真诊断报告 (`{self.model_name_or_path}`)\n"
            f"- **Effective Batch Size**: `{self.effective_batch_size}` "
            f"(`steps_per_epoch={self.steps_per_epoch}`, `total_steps={self.total_steps}`)\n"
            f"- **LoRA Scaling (alpha/rank)**: `{self.lora_scaling}`\n"
            f"- **Final Train Loss**: `{self.final_train_loss:.4f}` | "
            f"**Final Eval Loss**: `{self.final_eval_loss:.4f}` | "
            f"**Best Eval Loss**: `{self.best_eval_loss:.4f}` (step {self.best_step})\n"
            f"- **Generalization Gap (Eval - Train)**: `{self.generalization_gap:.4f}`\n"
            f"- **Diagnosis**: `{self.diagnosis}`\n"
            f"- **调优建议**:\n{rec_lines}"
        )


def simulate_training_run(
    config: LoRATrainingConfig,
    dataset_size: int = 1000,
    num_gpus: int = 1,
) -> TrainingSimulationResult:
    """确定性模拟 LoRA 训练过程并输出 Loss 曲线与拟合状态诊断.

    诊断逻辑：
    1. diverging（梯度爆炸/发散）：有效学习率（learning_rate * max(1, alpha/rank/2)）过高，Loss 震荡上升。
    2. underfitting（欠拟合）：训练轮数过少、学习率过低或 rank 过小导致模型未充分收敛，Train/Eval Loss 均较高。
    3. overfitting（过拟合）：训练轮数过多（或小数据集配合大 rank），Train Loss 极低而 Eval Loss 先降后升、泛化间隔拉大。
    4. healthy（健康收敛）：Train/Eval Loss 同步平滑下降且泛化间隔处于合理区间。
    """
    if dataset_size < 1:
        raise ValueError("dataset_size 必须大于等于 1")
    if num_gpus < 1:
        raise ValueError("num_gpus 必须大于等于 1")

    eff_bs = config.effective_batch_size(num_gpus=num_gpus)
    steps_per_epoch = max(1, math.ceil(dataset_size / eff_bs))
    total_steps = max(1, int(round(steps_per_epoch * config.num_train_epochs)))

    # 采样 10 个均匀观测点（含起点与终点）
    num_points = 10
    sample_steps: list[int] = []
    for i in range(num_points):
        step = max(1, round((i + 1) * total_steps / num_points))
        if not sample_steps or step > sample_steps[-1]:
            sample_steps.append(step)
    if sample_steps[-1] != total_steps:
        sample_steps[-1] = total_steps

    scaling = config.lora_alpha / config.lora_rank
    effective_lr = config.learning_rate * max(0.5, scaling / 2.0)

    # 确定性模式判定参数
    is_diverging = effective_lr >= 5e-3
    capacity_score = (config.num_train_epochs / 3.0) * (
        min(1.8, max(0.35, math.log2(max(2, config.lora_rank)) / 3.0))
    )
    lr_factor = min(1.5, max(0.15, math.log10(max(1e-7, config.learning_rate) * 1e7) / 3.0))
    convergence_power = capacity_score * lr_factor

    # 小数据集 + 高 epoch / 高 rank 会放大过拟合倾向
    data_pressure = max(0.6, min(2.0, 800.0 / max(100, dataset_size)))
    overfit_intensity = max(0.0, (config.num_train_epochs - 4.0) * 0.12 * data_pressure)
    if config.lora_rank >= 32 and config.num_train_epochs >= 4.0:
        overfit_intensity += 0.14

    initial_loss = 2.45
    history: list[LossPoint] = []

    for idx, step in enumerate(sample_steps):
        progress = (idx + 1) / len(sample_steps)  # 0.1 -> 1.0
        epoch = round((step / total_steps) * config.num_train_epochs, 2)

        if is_diverging:
            oscillation = 0.25 * math.sin(idx * 1.9)
            train_loss = round(initial_loss + 0.85 * (progress ** 1.3) + oscillation, 4)
            eval_loss = round(train_loss + 0.35 + 0.15 * progress, 4)
        else:
            decay = math.exp(-2.1 * convergence_power * progress)
            floor_train = max(0.18, 0.42 - 0.03 * min(config.num_train_epochs, 8.0))
            train_loss = floor_train + (initial_loss - floor_train) * decay

            # 正常泛化间隙
            base_gap = 0.08 + 0.04 * progress
            # 过拟合反弹项：通常在训练中后期（progress > 0.45）开始抬头
            rebound = overfit_intensity * (max(0.0, progress - 0.40) ** 1.4) * 2.2
            eval_loss = train_loss + base_gap + rebound

            train_loss = round(train_loss, 4)
            eval_loss = round(eval_loss, 4)

        history.append(
            LossPoint(
                step=step,
                epoch=epoch,
                train_loss=train_loss,
                eval_loss=eval_loss,
            )
        )

    final_point = history[-1]
    best_point = min(history, key=lambda pt: pt.eval_loss)
    gap = round(final_point.eval_loss - final_point.train_loss, 4)
    eval_rebound = round(final_point.eval_loss - best_point.eval_loss, 4)

    if is_diverging or final_point.train_loss > initial_loss:
        diagnosis: DiagnosisType = "diverging"
        recommendations = [
            "学习率或 LoRA 缩放系数过高，建议将 learning_rate 下调至 1e-4 ~ 3e-4。",
            "检查 lora_alpha / lora_rank 比例，建议保持在 1.0 ~ 2.0 之间并开启梯度裁剪 (max_grad_norm: 1.0)。",
        ]
    elif final_point.train_loss > 1.30 and gap < 0.20:
        diagnosis = "underfitting"
        recommendations = [
            "当前模型未充分拟合训练分布，建议适当提高 num_train_epochs（如 3.0 ~ 4.0）。",
            "若学习率过低（< 2e-5）或 lora_rank 过小（<= 4），建议将 learning_rate 调至 1e-4 并提升 lora_rank 至 8 或 16。",
        ]
    elif gap >= 0.25 or eval_rebound >= 0.08:
        diagnosis = "overfitting"
        recommendations = [
            f"验证集损失在 step {best_point.step} 达到最优 ({best_point.eval_loss:.4f}) 后出现回升，建议开启 Early Stopping 或减少 num_train_epochs。",
            "可适当增大数据集规模、增加 lora_dropout (如 0.05 ~ 0.1) 或降低 lora_rank。",
        ]
    else:
        diagnosis = "healthy"
        recommendations = [
            "训练损失与验证损失同步平稳收敛，泛化间隙健康，当前超参配置可直接用于生产微调。",
            f"建议保留 step {best_point.step} 对应的最佳 Checkpoint（eval_loss={best_point.eval_loss:.4f}）。",
        ]

    return TrainingSimulationResult(
        model_name_or_path=config.model_name_or_path,
        effective_batch_size=eff_bs,
        steps_per_epoch=steps_per_epoch,
        total_steps=total_steps,
        lora_scaling=config.lora_scaling,
        history=history,
        final_train_loss=final_point.train_loss,
        final_eval_loss=final_point.eval_loss,
        best_eval_loss=best_point.eval_loss,
        best_step=best_point.step,
        generalization_gap=gap,
        diagnosis=diagnosis,
        recommendations=recommendations,
    )
