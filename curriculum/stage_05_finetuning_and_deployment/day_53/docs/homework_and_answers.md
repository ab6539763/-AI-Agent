# Day 53 课后作业与参考答案

## 作业一：Effective Batch Size 计算与 LLaMA-Factory YAML 配置生成
**题目**：在单机 4 卡（`num_gpus=4`）环境下使用 LLaMA-Factory 微调 `Qwen/Qwen2.5-7B-Instruct`，受限于单卡显存，设置 `per_device_train_batch_size=2`，但业务要求全局有效批次大小（Effective Batch Size）必须达到 `64`。请你：
1. 计算所需的 `gradient_accumulation_steps`。
2. 实例化 `LoRATrainingConfig`（`lora_rank=16`, `lora_alpha=32`, `learning_rate=2e-4`, `num_train_epochs=3.0`, `template="qwen"`）。
3. 调用 `export_llamafactory_yaml(config)` 导出 YAML，并断言配置中包含正确的 `gradient_accumulation_steps`、`lora_rank: 16` 与 `template: qwen`。

### 参考答案：
```python
from zhishu_agent import LoRATrainingConfig, export_llamafactory_yaml

# Effective Batch Size = per_device_train_batch_size * gradient_accumulation_steps * num_gpus
# 64 = 2 * grad_accum * 4  =>  grad_accum = 8
config = LoRATrainingConfig(
    model_name_or_path="Qwen/Qwen2.5-7B-Instruct",
    finetuning_type="lora",
    lora_rank=16,
    lora_alpha=32,
    learning_rate=2e-4,
    num_train_epochs=3.0,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    template="qwen",
)

assert config.effective_batch_size(num_gpus=4) == 64
yaml_str = export_llamafactory_yaml(config)
assert "gradient_accumulation_steps: 8" in yaml_str
assert "lora_rank: 16" in yaml_str
assert "template: qwen" in yaml_str
print("作业一校验通过！Effective BS =", config.effective_batch_size(num_gpus=4))
```

---

## 作业二：LoRA Rank / Alpha 缩放与可训练参数量核算
**题目**：某 7B 模型具有 `hidden_size=3584`、`num_hidden_layers=28`，基座总参数量为 `7,615,616,512`。现在我们将 LoRA 注入到每层的 4 个注意力投影矩阵 `("q_proj", "k_proj", "v_proj", "o_proj")` 中，分别对比 `lora_rank=8` 与 `lora_rank=32` 时的可训练参数量。请你使用 `count_lora_trainable_params` 验证：
1. `lora_rank=8` 时，可训练参数量恰好等于 `28 * 4 * 2 * 8 * 3584 = 6,422,528`（约占基座的 `0.0843%`）。
2. `lora_rank=32` 时，可训练参数量与 FP16 显存占用均为 `lora_rank=8` 时的 4 倍。

### 参考答案：
```python
from zhishu_agent import count_lora_trainable_params

stats_r8 = count_lora_trainable_params(
    hidden_size=3584,
    num_hidden_layers=28,
    lora_rank=8,
    target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
    base_model_params=7_615_616_512,
)
stats_r32 = count_lora_trainable_params(
    hidden_size=3584,
    num_hidden_layers=28,
    lora_rank=32,
    target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
    base_model_params=7_615_616_512,
)

assert stats_r8.trainable_params == 6_422_528
assert stats_r32.trainable_params == stats_r8.trainable_params * 4
assert round(stats_r32.lora_memory_fp16_mb / stats_r8.lora_memory_fp16_mb, 2) == 4.0
print(f"作业二校验通过！r=8 参数占比 {stats_r8.trainable_percentage}%, r=32 参数占比 {stats_r32.trainable_percentage}%")
```

---

## 作业三：Loss 曲线诊断（欠拟合 vs 健康收敛 vs 过拟合）
**题目**：在微调实验复盘中，工程师常常需要通过 `train_loss` 与 `eval_loss` 的走势定位超参问题。请你使用 `simulate_training_run` 构造三组实验并断言其诊断结论：
1. **欠拟合组**：`lora_rank=2, lora_alpha=4, learning_rate=1e-6, num_train_epochs=0.5, dataset_size=1000`，断言 `diagnosis == "underfitting"`。
2. **健康收敛组**：`lora_rank=8, lora_alpha=16, learning_rate=1e-4, num_train_epochs=3.0, dataset_size=1000`，断言 `diagnosis == "healthy"`。
3. **过拟合组**：`lora_rank=64, lora_alpha=128, learning_rate=2e-4, num_train_epochs=10.0, dataset_size=200`，断言 `diagnosis == "overfitting"` 且 `final_eval_loss > best_eval_loss`。

### 参考答案：
```python
from zhishu_agent import LoRATrainingConfig, simulate_training_run

res_under = simulate_training_run(
    LoRATrainingConfig(lora_rank=2, lora_alpha=4, learning_rate=1e-6, num_train_epochs=0.5),
    dataset_size=1000,
)
res_healthy = simulate_training_run(
    LoRATrainingConfig(lora_rank=8, lora_alpha=16, learning_rate=1e-4, num_train_epochs=3.0),
    dataset_size=1000,
)
res_over = simulate_training_run(
    LoRATrainingConfig(lora_rank=64, lora_alpha=128, learning_rate=2e-4, num_train_epochs=10.0),
    dataset_size=200,
)

assert res_under.diagnosis == "underfitting"
assert res_healthy.diagnosis == "healthy"
assert res_over.diagnosis == "overfitting"
assert res_over.final_eval_loss > res_over.best_eval_loss
print("作业三校验通过！三组诊断结果:", res_under.diagnosis, res_healthy.diagnosis, res_over.diagnosis)
```
