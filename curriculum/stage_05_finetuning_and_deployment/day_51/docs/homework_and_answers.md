# Day 51 课后作业与参考答案

## 作业一：Prompt vs RAG vs Fine-Tuning 业务场景决策
**题目**：星辰数科接到三个客户需求，请调用 `recommend_adaptation_strategy` 给出技术路线推荐并说明理由：
1. **场景 A（HR 制度问答机器人）**：制度文件每周更新（`needs_fresh_knowledge=True`），输出普通自然语言即可（`needs_style_or_format=False`），无标注集，延迟预算 `1500ms`。
2. **场景 B（金融合规摘要生成器）**：知识相对稳定（`needs_fresh_knowledge=False`），必须严格输出特定 JSON 报告结构与投行专业术语风格（`needs_style_or_format=True`），已有 3000 条人工标注样本（`has_labeled_data=True`），延迟预算 `1200ms`。
3. **场景 C（高频风控实时分类器）**：规则稳定（`needs_fresh_knowledge=False`），需严格输出特定标签格式（`needs_style_or_format=True`），已有 5000 条标注数据（`has_labeled_data=True`），要求 P99 延迟 `< 300ms`（`latency_budget_ms=300`）。

### 参考答案：
```python
from zhishu_agent import recommend_adaptation_strategy

case_a = recommend_adaptation_strategy(
    needs_fresh_knowledge=True,
    needs_style_or_format=False,
    has_labeled_data=False,
    latency_budget_ms=1500,
)
assert case_a.strategy == "RAG"

case_b = recommend_adaptation_strategy(
    needs_fresh_knowledge=False,
    needs_style_or_format=True,
    has_labeled_data=True,
    latency_budget_ms=1200,
)
assert case_b.strategy == "QLoRA"

case_c = recommend_adaptation_strategy(
    needs_fresh_knowledge=False,
    needs_style_or_format=True,
    has_labeled_data=True,
    latency_budget_ms=300,
)
assert case_c.strategy == "LoRA"

print("作业一校验通过！", case_a.strategy, case_b.strategy, case_c.strategy)
```
**解析**：
- 场景 A 仅需动态知识注入，微调无法低成本应对每周变更的制度文件，因此选 **RAG**。
- 场景 B 需定制风格与格式且有标注数据，延迟预算充裕，**QLoRA** 可节省 ~70% 训练显存，性价比最优。
- 场景 C 对推理延迟有严格 SLA（`< 500ms`），**LoRA-FP16** 训练后可将旁路权重无损合并回 FP16 基座，避免 4-bit 反量化开销。

---

## 作业二：Qwen2.5-7B 的 LoRA-FP16 与 QLoRA-4bit 显存精确对比
**题目**：使用 `estimate_training_vram_gb` 计算 **Qwen2.5-7B**（`params_billion=7.0`, `lora_rank=16`）在以下两种配置下的显存分项与总显存：
1. `batch_size=1, seq_len=2048` 对比 `Full-FP16`、`LoRA-FP16`、`QLoRA-4bit`。
2. 当上下文扩展至 `batch_size=4, seq_len=4096` 时，对比 `LoRA-FP16` 与 `QLoRA-4bit` 的激活值（`activations_gb`）与总显存变化。

### 参考答案：
```python
from zhishu_agent import estimate_training_vram_gb

full_1 = estimate_training_vram_gb(7.0, method="Full-FP16", batch_size=1, seq_len=2048)
lora_1 = estimate_training_vram_gb(7.0, method="LoRA-FP16", batch_size=1, seq_len=2048, lora_rank=16)
qlora_1 = estimate_training_vram_gb(7.0, method="QLoRA-4bit", batch_size=1, seq_len=2048, lora_rank=16)

assert full_1.total_gb > 100.0
assert lora_1.total_gb < 20.0
assert qlora_1.total_gb < 10.0

lora_4 = estimate_training_vram_gb(7.0, method="LoRA-FP16", batch_size=4, seq_len=4096, lora_rank=16)
qlora_4 = estimate_training_vram_gb(7.0, method="QLoRA-4bit", batch_size=4, seq_len=4096, lora_rank=16)

assert lora_4.activations_gb > lora_1.activations_gb * 7.5
assert lora_4.total_gb > 24.0   # 24G 单卡已放不下
assert qlora_4.total_gb > 22.0  # 4-bit 权重虽小，但大 batch*seq_len 激活值仍逼近/超过 24G 警戒线

print(f"bs=1,seq=2048 -> Full:{full_1.total_gb}G | LoRA:{lora_1.total_gb}G | QLoRA:{qlora_1.total_gb}G")
print(f"bs=4,seq=4096 -> LoRA:{lora_4.total_gb}G | QLoRA:{qlora_4.total_gb}G")
```

---

## 作业三：多模型规格 GPU 算力选型与预算评估
**题目**：结合 `estimate_training_vram_gb` 与 `recommend_gpu`，为以下三个任务选出最合适的 GPU 规格：
1. `Qwen2.5-7B` + `QLoRA-4bit`（`batch_size=1, seq_len=2048`）
2. `Qwen2.5-7B` + `LoRA-FP16`（`batch_size=4, seq_len=4096`）
3. `Qwen2.5-7B` + `Full-FP16`（`batch_size=1, seq_len=2048`）

### 参考答案：
```python
from zhishu_agent import estimate_training_vram_gb, recommend_gpu

v1 = estimate_training_vram_gb(7.0, method="QLoRA-4bit", batch_size=1, seq_len=2048)
v2 = estimate_training_vram_gb(7.0, method="LoRA-FP16", batch_size=4, seq_len=4096)
v3 = estimate_training_vram_gb(7.0, method="Full-FP16", batch_size=1, seq_len=2048)

g1, g2, g3 = recommend_gpu(v1.total_gb), recommend_gpu(v2.total_gb), recommend_gpu(v3.total_gb)

assert g1.tier == "RTX 4090 24G"
assert g2.tier == "A100 40G"
assert g3.tier == "Multi-GPU" and g3.gpu_count >= 2

print("作业三校验通过！", g1.tier, g2.tier, f"{g3.tier} x{g3.gpu_count}")
```
