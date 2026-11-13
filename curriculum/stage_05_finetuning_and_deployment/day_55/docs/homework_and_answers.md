# Day 55 课后作业与参考答案

## 作业一：Ollama vs vLLM 核心原理对比（PagedAttention 与 Continuous Batching）
**题目**：智枢平台在本地开发阶段使用 Ollama，而在云端多租户高并发生产环境要求切换至 vLLM。请从以下两个核心技术维度解释为什么 vLLM 在高并发场景下具备压倒性吞吐优势：
1. **PagedAttention（分页注意力机制）** 如何解决传统静态 KV Cache 的显存浪费问题？
2. **Continuous Batching（连续批处理）** 相比传统 Static Batching（静态批处理）如何提升 GPU 利用率并降低排队延迟？

### 参考答案：
1. **PagedAttention 解决显存碎片**：
   - **传统静态分配的痛点**：推理引擎预先按 `max_model_len`（如 4096 或 8192 tokens）为每个请求分配一块连续的 KV Cache 显存。如果请求实际只生成了 200 个 Token，剩余 95% 的预留显存就被白白浪费（内部碎片），且无法共享系统提示词（System Prompt）的 Prefix KV。
   - **PagedAttention 方案**：借鉴操作系统的虚拟内存分页思想，将 KV Cache 切分为固定大小的 Block（如每块 16 tokens），物理显存按需动态申请、无需连续，通过 Block Table 映射到逻辑序列。这使显存利用率从不足 40% 提升至 **96%+**，从而能同时容纳数倍的并发 Batch Size。
2. **Continuous Batching 消除木桶效应**：
   - **Static Batching 的痛点**：同一批（Batch）内的请求必须等待最长的那个请求生成 `EOS` 后才能整体释放，短请求在 GPU 上空转等待；新到达的请求也必须等整批结束后才能进入。
   - **Continuous Batching 方案**：调度器在 **Iteration（单个 Token 解码步）** 粒度上工作。只要某个请求在当前步生成了结束符，立刻将其移出 Batch 并释放 Block，同时在下一解码步立即把排队中的新请求塞入 Batch（Prefill/Decode 调度），彻底消除等待木桶效应。

---

## 作业二：TTFT 与 TPS 指标权衡及业务 SLA 选型
**题目**：在私有化推理压测报告中，通常重点关注 **TTFT（Time To First Token，首字延迟）** 和 **TPS（Tokens Per Second，生成吞吐量）** 两个核心指标。
1. 请分别写出 TTFT 与 System TPS 的工程定义，并说明它们各自主要受模型推理哪两个阶段（Prefill vs Decode）的硬件瓶颈（Compute-bound vs Memory-bandwidth-bound）制约？
2. 针对智枢平台的两个业务场景——**场景 A：前端智能客服实时流式对话** 与 **场景 B：夜间万级历史工单离线批量摘要**，分别应优先优化哪项指标？

### 参考答案：
1. **指标定义与硬件瓶颈**：
   - **TTFT（首字延迟）**：从客户端发出请求到收到第 1 个生成 Token 的耗时。主要由 **Prefill（预填充）阶段** 决定——需要对整个输入 Prompt 并行做矩阵乘法计算，属于 **算力受限（Compute-bound）**，并发排队或长上下文都会显著拉高 TTFT。
   - **TPS（生成吞吐量）**：单位时间内系统输出的总 Token 数（`total_completion_tokens / wall_time`）。主要由 **Decode（自回归逐字解码）阶段** 决定——每生成一个新 Token 都要把整个模型权重和 KV Cache 从显存搬运到计算核心，属于 **显存带宽受限（Memory-bandwidth-bound）**；通过 Continuous Batching 增大并发 Batch Size 可以摊薄权重读取开销，大幅拉高 System TPS。
2. **业务 SLA 优化优先级**：
   - **场景 A（实时流式客服）**：优先优化 **TTFT（建议 < 300~500 ms）** 与单流输出速度（保证比人类阅读速度更快，> 20 tok/s）。首字响应慢会让用户产生“卡死”错觉。
   - **场景 B（离线批量工单摘要）**：用户无实时等待感知，优先最大化 **System TPS（系统总吞吐量）**，应尽可能调高 vLLM 并发数（`max_num_seqs`）以吃满 GPU 算力与显存带宽，降低单位 Token 的算力成本。

---

## 作业三：OpenAI 兼容协议客户端无缝切换实践
**题目**：假设智枢平台已有业务代码通过 `OpenAICompatibleGateway` 调用本地 Ollama 服务。现在需要将其切换至生产环境的 vLLM 集群（地址 `http://10.0.8.12:8000/v1`，模型 `Qwen/Qwen2.5-14B-Instruct-AWQ`）。请写出使用 `InferenceBackendConfig` 与 `OpenAICompatibleGateway` 完成无缝切换的 Python 代码，并说明为什么“统一 OpenAI 协议网关”是企业 AI 架构的最佳实践。

### 参考答案：
```python
from zhishu_agent import InferenceBackendConfig, OpenAICompatibleGateway

# 1. 本地开发阶段：Ollama
ollama_cfg = InferenceBackendConfig.ollama_default()
gateway = OpenAICompatibleGateway(ollama_cfg)
dev_res = gateway.chat_completions([{"role": "user", "content": "测试工单分类"}])

# 2. 生产上线阶段：仅替换配置，业务调用代码零改动
vllm_prod_cfg = InferenceBackendConfig.vllm_default(
    model_name="Qwen/Qwen2.5-14B-Instruct-AWQ",
    base_url="http://10.0.8.12:8000/v1",
    max_concurrency=64,
)
gateway.switch_backend(vllm_prod_cfg)
prod_res = gateway.chat_completions([{"role": "user", "content": "测试工单分类"}])
gateway.close()
```
**架构价值**：
- **厂商与引擎解耦**：无论是云端 API（OpenAI / DeepSeek / 通义千问）、本地个人引擎（Ollama / LM Studio），还是企业集群引擎（vLLM / TGI / SGLang），均暴露标准的 `/v1/chat/completions` 接口。
- **平滑灰度与容灾降级**：网关层只需通过配置中心热更新 `base_url`、`api_key` 与 `model_name`，即可实现跨机房容灾、AB 灰度测试与算力降本迁移，业务层 Agent 逻辑 **0 行代码修改**。
