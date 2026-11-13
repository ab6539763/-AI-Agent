# 第九周综合测验与参考答案（Week 9 Assessment）

> **覆盖范围**：Day 51 ~ Day 57（LoRA / QLoRA 微调原理、SFT 数据集构建与清洗、LLaMA-Factory 实战、LoRA 权重合并与 GPTQ/AWQ/GGUF 量化、vLLM 高并发推理、Docker 容器化部署、LLM 安全与合规网关）
> **满分**：100 分（10 道单项选择题 × 6 分 + 2 道编程实战题 × 20 分）

---

## 第一部分：单项选择题（每题 6 分，共 60 分）

### 题目 1（LoRA 低秩自适应原理）
在 LoRA（Low-Rank Adaptation）微调中，旁路更新矩阵为 $\Delta W = \frac{\alpha}{r} B A$，其中 $B \in \mathbb{R}^{d \times r}$，$A \in \mathbb{R}^{r \times k}$。关于训练初始化策略，以下说法**正确**的是：
- A. $A$ 和 $B$ 都必须全零初始化，否则无法反向传播
- B. 通常 $A$ 采用高斯随机初始化，$B$ 采用全零初始化，以保证训练初始阶段 $\Delta W = 0$，不破坏基座模型原有输出分布
- C. $A$ 和 $B$ 都使用固定全 1 矩阵且全程冻结
- D. 秩 $r$ 必须大于隐藏层维度 $d$，才能降低显存占用

### 题目 2（QLoRA 显存优化三大支柱）
QLoRA 能够在单张 24GB 显存的消费级显卡上微调 32B/70B 级大模型，其核心依赖三项关键技术创新。以下哪一项**不属于** QLoRA 的三大核心技术？
- A. 4-bit NormalFloat（NF4）信息论最优量化数据类型
- B. 双重量化（Double Quantization，对量化常数再次进行 8-bit 量化）
- C. 分页优化器（Paged Optimizers，利用 NVIDIA 统一内存防止梯度检查点峰值 OOM）
- D. 将所有 Transformer 层权重转换为 FP64 双精度浮点进行梯度累积

### 题目 3（企业 SFT 数据集构建与质量控制）
在为“智枢企业智能体”构建领域微调（SFT）数据集时，以下工程实践最符合大模型微调黄金法则的是：
- A. 数据量越大越好，可以直接将未去重、含客户明文身份证和手机号的客服日志直接喂给模型训练
- B. 坚持“质量优先于数量”，执行 PII 敏感信息脱敏、语义去重、格式校验，并严格对齐目标推理模型的对话模板（Chat Template）
- C. 只需准备纯文本无结构语料，不需要区分 `system`、`user`、`assistant` 角色边界
- D. 训练集与验证集可以完全相同，以便在评测时获得 100% 的准确率

### 题目 4（LLaMA-Factory 微调配置）
使用 LLaMA-Factory 微调 Qwen2.5 系列模型时，若希望在有限显存下获得最佳的指令遵循与工具调用（Tool-Calling）泛化能力，关于 `template` 与 `lora_target` 配置，以下说法**正确**的是：
- A. `template` 可以随意填写为 `llama2`，不会影响 EOS 结束符与特殊 Token 识别
- B. 应将 `template` 设为与基座模型一致的 `qwen`，并将 `lora_target` 设为 `all` 以覆盖所有线性层（Attention + MLP）
- C. `lora_target` 只能设为 `lm_head`，绝对不能微调注意力投影层
- D. 启用 QLoRA 时必须把 `quantization_bit` 设为 `32`

### 题目 5（LoRA 权重合并与推理延迟）
微调完成后，在生产部署前通常执行 `merge_and_unload()`，将低秩适配器合并回基座权重 $W' = W + \frac{\alpha}{r}(B @ A)$。这样做的主要工程收益是：
- A. 消除推理期的旁路矩阵乘法开销，使模型计算图与原生基座一致，且避免未合并分支在后续 4-bit 量化时放大截断误差
- B. 让模型参数量翻倍，从而提升单次前向计算精度
- C. 合并后模型就不再需要任何 Tokenizer 即可处理中文
- D. 可以绕过所有内容安全审核直接对外服务

### 题目 6（模型量化选型：GPTQ / AWQ / GGUF）
某企业计划在配备 NVIDIA L40S（48GB 显存）的 Linux 服务器上使用 **vLLM** 部署高并发 32B 模型，同时研发同学想在本地 MacBook（Apple Silicon 统一内存）上使用 **llama.cpp / Ollama** 进行离线调试。最合理的量化格式组合是：
- A. 服务端使用 FP32，Mac 本地使用 GPTQ-4bit
- B. 服务端使用 **AWQ-4bit 或 GPTQ-4bit**（~4.25 bpw），Mac 本地使用 **GGUF-Q4_K_M**（~4.85 bpw）
- C. 服务端与 Mac 本地全部使用未量化的 FP16（约 64GB，均无法装入）
- D. 全部使用 1-bit 随机二值化

### 题目 7（vLLM 高并发推理引擎）
vLLM 相比传统 HuggingFace `transformers.generate()` 在高并发场景下吞吐量提升数倍至十数倍，其最核心的两项引擎级优化技术是：
- A. PagedAttention（分页显存管理，消除 KV Cache 碎片）与 Continuous Batching（连续批处理，迭代级动态调度请求）
- B. 关闭 KV Cache 并在每一步重新计算全部历史 Token
- C. 将所有请求强制改为单线程串行排队，等待最长序列生成完毕后再统一返回
- D. 将模型权重全部存放在机械硬盘上按需读取

### 题目 8（Docker Compose 私有化编排）
在通过 `docker-compose.yml` 编排 vLLM 推理服务与智枢网关容器时，以下哪项配置是生产级部署**必须具备**的？
- A. 将 30GB 模型权重直接 `COPY` 进基础镜像层，每次改一行网关代码都重新构建 30GB 镜像
- B. 通过 `volumes` 挂载宿主机模型目录、配置 `deploy.resources.reservations.devices` 透传 GPU，并定义 `healthcheck` 健康检查与服务依赖顺序
- C. 在 `docker-compose.yml` 中硬编码生产数据库明文 root 密码并提交到 Git 仓库
- D. 容器内所有进程必须以特权模式（`privileged: true`）运行

### 题目 9（PII 脱敏正则匹配顺序）
在使用正则表达式实现 `PIIDesensitizer` 对混合文本同时脱敏 **18 位身份证号**、**16~19 位银行卡号** 和 **11 位手机号** 时，正确的匹配优先级顺序与边界策略应该是：
- A. 先匹配 11 位手机号，再匹配 18 位身份证号，不需要数字边界断言
- B. 按长度与结构严格度从高到低匹配（**18 位身份证号 → 16~19 位银行卡号 → 11 位手机号 → 邮箱**），并配合 `(?<!\d)...(?!\d)` 负向环视防止长数字串被局部截断误伤
- C. 随机顺序匹配即可，正则引擎会自动理解语义
- D. 直接把所有连续数字全部替换为 `*`

### 题目 10（大模型备案合规与成本硬熔断）
在智枢企业级安全合规网关（`ComplianceGateway`）中，关于 **审计日志** 与 **租户成本熔断** 的设计，以下做法**最符合**生产合规要求的是：
- A. 将用户输入的明文身份证、银行卡直接写入 `audit.log` 方便排查
- B. 审计日志仅记录输入原文的 **SHA-256 摘要**、**二次强制脱敏后的文本预览** 与 **算法备案编号（`filing_record_id`）**；租户日成本达到配额上限时触发 **硬熔断（Circuit Breaker）**，在推理前 Fail-Fast 拦截
- C. 当租户超出预算后，继续调用 GPU 推理，仅在月底邮件通知财务
- D. 只要开启了 HTTPS，就不需要任何输入输出内容安全审核

---

## 第二部分：编程实战题（每题 20 分，共 40 分）

### 编程题 1：实现中国大陆手机号与 18 位身份证号脱敏器
请实现函数 `redact_cn_pii(text: str) -> str`：
- 识别文本中的 **18 位中国大陆身份证号**（末位支持数字或 `X`/`x`），保留前 6 位与后 4 位，中间 8 位替换为 `********`（如 `110101********123X`）。
- 识别文本中的 **11 位中国大陆手机号**（`1[3-9]\d{9}`），保留前 3 位与后 4 位，中间 4 位替换为 `****`（如 `138****5678`）。
- 必须使用数字边界断言 `(?<!\d)...(?!\d)`，确保身份证号内部的连续 11 位数字不会被手机号正则二次误匹配。

### 编程题 2：实现租户级大模型日预算硬熔断器
请实现类 `DailyBudgetBreaker`：
- 初始化参数：`daily_limit_cny: float`（每日预算上限，必须 `> 0`）。
- 方法 `allow_request(tenant_id: str) -> bool`：若该租户当前已触发熔断（累计消费 `>= daily_limit_cny`），返回 `False`，否则返回 `True`。
- 方法 `charge(tenant_id: str, cost_cny: float) -> bool`：累加租户当日消费（`cost_cny < 0` 应抛出 `ValueError`）；若累加后达到或超过 `daily_limit_cny`，触发熔断并返回 `False`（表示本次计费后已熔断），否则返回 `True`。
- 方法 `reset(tenant_id: str) -> None`：重置指定租户的累计消费与熔断状态。

---

## 第三部分：参考答案与解析

### 单选题答案速查表

| 题号 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **答案** | **B** | **D** | **B** | **B** | **A** | **B** | **A** | **B** | **B** | **B** |

### 单选题逐题精析
1. **B**：LoRA 中 $A$ 高斯随机初始化、$B$ 全零初始化，确保训练起点 $\Delta W = B A = 0$，模型初始行为与基座完全一致，训练平稳。
2. **D**：QLoRA 的三大支柱是 NF4 量化、Double Quantization（双重量化）和 Paged Optimizers，绝不会使用耗费 4 倍显存的 FP64。
3. **B**：企业微调必须先做 PII 脱敏与清洗去重，高质量少样本往往优于脏数据大样本，且对话模板必须与推理期一致。
4. **B**：`template` 决定特殊 Token（如 `<|im_start|>` / `<|im_end|>`）拼接方式；`lora_target: all` 覆盖全部线性层，效果通常优于仅微调 `q_proj, v_proj`。
5. **A**：合并后消除旁路矩阵乘法延迟，同时让 GPTQ/AWQ 校准量化针对单一完整权重矩阵 $W'$ 进行，避免截断误差放大。
6. **B**：vLLM 在 NVIDIA GPU 上对 AWQ/GPTQ-4bit 有高度优化的 CUDA Kernel；Apple Silicon 与 CPU 场景则首选 llama.cpp 的 GGUF 格式（如 `Q4_K_M`）。
7. **A**：PagedAttention 解决显存碎片与并发容量瓶颈，Continuous Batching 解决静态批处理的长尾等待问题。
8. **B**：模型权重应通过 Volume 挂载实现镜像与权重解耦，并配置 GPU 资源预留与健康检查。
9. **B**：18 位身份证和 16~19 位银行卡内部都可能包含 `1[3-9]\d{9}` 子串，必须按“长模式优先 + 前后非数字边界”顺序脱敏。
10. **B**：结合《生成式 AI 服务管理暂行办法》与《个人信息保护法》，审计日志需“可追溯且无明文 PII”；配额硬熔断可在推理前阻断异常消耗。

---

### 编程题参考实现

#### 编程题 1 参考代码
```python
import re

_ID_CARD_RE = re.compile(
    r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
)
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")


def redact_cn_pii(text: str) -> str:
    masked = _ID_CARD_RE.sub(lambda m: f"{m.group(1)[:6]}********{m.group(1)[-4:]}", text)
    masked = _PHONE_RE.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[-4:]}", masked)
    return masked
```

#### 编程题 2 参考代码
```python
class DailyBudgetBreaker:
    def __init__(self, daily_limit_cny: float) -> None:
        if daily_limit_cny <= 0:
            raise ValueError("daily_limit_cny 必须大于 0")
        self.daily_limit_cny = float(daily_limit_cny)
        self._usage: dict[str, float] = {}
        self._tripped: set[str] = set()

    def allow_request(self, tenant_id: str) -> bool:
        return tenant_id not in self._tripped

    def charge(self, tenant_id: str, cost_cny: float) -> bool:
        if cost_cny < 0:
            raise ValueError("cost_cny 不能为负数")
        total = self._usage.get(tenant_id, 0.0) + cost_cny
        self._usage[tenant_id] = total
        if total >= self.daily_limit_cny:
            self._tripped.add(tenant_id)
            return False
        return True

    def reset(self, tenant_id: str) -> None:
        self._usage.pop(tenant_id, None)
        self._tripped.discard(tenant_id)
```
