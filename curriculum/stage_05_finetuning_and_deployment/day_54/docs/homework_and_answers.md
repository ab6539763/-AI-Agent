# Day 54 课后作业与参考答案

## 作业一：LoRA 权重合并公式推导与纯 Python 验证
**题目**：已知某线性层基座权重矩阵 $W \in \mathbb{R}^{2 \times 3}$，LoRA 降维矩阵 $A \in \mathbb{R}^{2 \times 3}$、升维矩阵 $B \in \mathbb{R}^{2 \times 2}$，配置超参数 $\alpha = 16$、$r = 2$。
1. 写出 LoRA 合并公式，并说明为什么合并后推理阶段可以实现“零额外延迟”。
2. 使用 `zhishu_agent.merge_lora_weights` 验证以下矩阵的合并结果，并断言原始矩阵 `base_w` 未被原地修改：
   - `base_w = [[1.0, 0.0, -1.0], [0.5, 2.0, 0.0]]`
   - `lora_b = [[0.25, 0.0], [0.0, -0.5]]`
   - `lora_a = [[1.0, 2.0, 0.0], [0.0, 1.0, -1.0]]`

### 参考答案：
1. **合并公式与零延迟原理**：
   $$W' = W + \frac{\alpha}{r} \cdot (B @ A)$$
   推理阶段前向计算 $y = Wx + \frac{\alpha}{r} B(Ax) = \left(W + \frac{\alpha}{r} B A\right) x = W'x$。由于利用了矩阵乘法的分配律，将旁路权重提前离线融合成单一权重矩阵 $W'$，推理时无需维护额外的 Adapter 分支与中间激活张量，因此推理延迟与参数量和原基座模型完全一致。
2. **Python 验证代码**：
```python
from zhishu_agent import merge_lora_weights

base_w = [[1.0, 0.0, -1.0], [0.5, 2.0, 0.0]]
lora_b = [[0.25, 0.0], [0.0, -0.5]]
lora_a = [[1.0, 2.0, 0.0], [0.0, 1.0, -1.0]]

# scale = 16 / 2 = 8.0
# B @ A = [[0.25, 0.5, 0.0], [0.0, -0.5, 0.5]]
# scale * (B @ A) = [[2.0, 4.0, 0.0], [0.0, -4.0, 4.0]]
# W' = [[3.0, 4.0, -1.0], [0.5, -2.0, 4.0]]
merged = merge_lora_weights(base_w, lora_a, lora_b, lora_alpha=16, lora_rank=2)
assert merged == [[3.0, 4.0, -1.0], [0.5, -2.0, 4.0]]
assert base_w == [[1.0, 0.0, -1.0], [0.5, 2.0, 0.0]]
print("作业一校验通过！W' =", merged)
```

---

## 作业二：GPTQ vs AWQ vs GGUF 生产量化选型决策
**题目**：智枢平台需要将微调后的 **14B 参数模型** 部署到以下三种不同硬件环境中，请结合 `estimate_quantized_size_gb(14, ...)` 的估算结果，分别为三个场景选择最合适的量化格式并说明理由：
- **场景 A**：云端生产集群（单张 NVIDIA A10G 24GB 显存，使用 vLLM 提供高并发 API 服务）。
- **场景 B**：政企客户内网服务器（无独立 GPU，仅 64GB 内存多核 CPU，使用 `llama.cpp` / Ollama 部署）。
- **场景 C**：研发团队 MacBook Pro（M3 Max 36GB 统一内存，要求极低精度损失作为本地评测基准）。

### 参考答案：
```python
from zhishu_agent import estimate_quantized_size_gb

for fmt in ["FP16", "GPTQ-4bit", "AWQ-4bit", "GGUF-Q4_K_M", "GGUF-Q8_0"]:
    print(f"{fmt:12s}: {estimate_quantized_size_gb(14, fmt):.3f} GB")
```
- **场景 A 推荐 `AWQ-4bit`（或 `GPTQ-4bit`，14B 体积约 7.44 GB）**：14B FP16 约 28 GB 无法放入 24GB A10G；而 AWQ-4bit 仅占 ~7.44 GB，留出超过 16 GB 显存给 vLLM 的 PagedAttention KV Cache 以支撑高并发。其中 **AWQ-4bit** 通过激活感知保护 1% 显著权重通道，跨领域泛化通常比依赖特定校准集的 GPTQ 更稳健，且在 vLLM Marlin 内核下吞吐极高。
- **场景 B 推荐 `GGUF-Q4_K_M`（14B 体积约 8.48 GB）**：GPTQ/AWQ 依赖 CUDA 算子，无法在纯 CPU 环境高效运行；`GGUF-Q4_K_M` 是 `llama.cpp` 的原生格式，利用 AVX2/AVX-512 指令集即可在纯 CPU 内存中流畅推理，兼顾速度与精度。
- **场景 C 推荐 `GGUF-Q8_0`（14B 体积约 14.88 GB）**：36GB 统一内存完全容纳 14.88 GB 的 `Q8_0` 权重及上下文缓存，且 8-bit 量化几乎无损（困惑度与 FP16 几乎一致），最适合作为本地高精度验收基准。

---

## 作业三：SFT / LoRA 微调过拟合（Overfitting）的识别与缓解策略
**题目**：在 Day 54 的微调前后评测中，某工程师发现微调模型在训练集上的格式合规率达到 100%，但在未见过的跨部门测试集上反而出现“答非所问、通用推理能力退化（灾难性遗忘）”的现象。请列出至少 **4 项工程级的过拟合缓解措施**。

### 参考答案：
1. **控制训练轮次与 Early Stopping**：SFT 阶段通常只需 `1 ~ 3 epochs`，监控独立验证集（Validation Loss 与业务准确率），一旦验证集指标不再上升立即停止训练，切忌盲目追求训练集 Loss 归零。
2. **混入通用指令与安全对齐回放数据（Data Replay Mix）**：在企业私域 SFT 数据中按 15%～30% 比例混入高质量通用指令数据（如多轮对话、数学/逻辑推理、拒绝回答模板），防止模型发生“灾难性遗忘”。
3. **调优 LoRA 正则化超参数**：适当降低 `lora_rank`（如从 64 降至 8 或 16）、增大 `lora_dropout`（如 `0.05 ~ 0.1`）与 `weight_decay`（如 `0.01`），限制低秩旁路对基座知识空间的过度偏移。
4. **提升数据多样性与去重清洗**：对同质化模板数据进行语义去重（MinHash / Embedding 聚类），增加多样化的同义改写、边界异常样本与负样本（如格式纠错、缺参追问），避免模型死记硬背固定句式。
