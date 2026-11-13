# 高频技术面试题精讲（五大核心维度实战指南）

> 本文档面向 **AI Application Engineer / Agent Engineer / RAG Engineer** 岗位技术面试，按「**核心结论 -> 底层原理 -> 工程取舍 -> 智枢项目实战结合点**」结构整理五大高频模块核心题精讲，配合 Day 67 `interview_bank.py` 模拟笔试系统使用效果最佳。

---

## 一、Transformer 与大模型原理

### 1. 为什么 Self-Attention 在计算点积后要除以 $\sqrt{d_k}$？
- **核心结论**：防止点积结果方差随维度 $d_k$ 增大而膨胀，避免 Softmax 进入梯度极小的饱和区。
- **底层原理**：假设 $Q, K$ 各分量独立同分布且 $\mu=0, \sigma^2=1$，则 $q \cdot k = \sum_{i=1}^{d_k} q_i k_i$ 的均值为 $0$、方差为 $d_k$。当 $d_k=128$ 时标准差达 $\sqrt{128}\approx 11.3$，大值会使 Softmax 输出接近 one-hot，反向传播梯度趋近于 0。除以 $\sqrt{d_k}$ 将方差重新拉回 1。

### 2. 什么是 KV Cache？它解决了什么瓶颈，又带来什么代价？
- **核心结论**：以显存换计算，消除自回归 Decode 阶段历史 Token 的重复 $K, V$ 投影计算。
- **底层原理**：Decode 每生成一个新 Token 仅需计算当前 Token 的 $q_t$ 与历史所有 $K_{\le t}, V_{\le t}$ 的注意力。缓存历史 $K, V$ 后，单步注意力计算复杂度从 $O(n^2)$ 降至 $O(n)$。
- **工程代价与优化**：显存占用随 `batch_size * seq_len * num_layers * num_heads` 线性增长，推理从 Compute-Bound 转向 **Memory-Bound**；主流优化包括 **GQA/MQA**（共享 KV 头）与 vLLM 的 **PagedAttention**（分页管理消除显存碎片）。

### 3. RoPE（旋转位置编码）的核心优势是什么？
- **核心结论**：用绝对位置旋转矩阵的形式，在注意力内积中自然表达相对位置 $(m-n)$，兼具优秀的长文本外推能力。
- **工程应用**：直接作用在 $Q, K$ 上，无需改动 Attention 主结构；配合 NTK-aware / YaRN 缩放可将 4K/8K 模型外推至 32K–128K 上下文。

### 4. Pre-LN 与 Post-LN 的训练稳定性差异
- **核心结论**：Pre-LN 保留了一条直通的恒等残差路径，梯度可无损回传至浅层，无需复杂 Warmup 即可稳定训练深层大模型（LLaMA/Qwen 均采用 Pre-LN）。

---

## 二、RAG 检索增强与定量评估

### 1. 为什么采用 BM25 + Dense Vector 混合检索并用 RRF 融合？
- **痛点互补**：Dense 向量擅长语义同义匹配，但对**股票代码、型号、人名、报错码**等字面精确词召回较弱；BM25 基于词频与 IDF 擅长精确关键词匹配。
- **RRF（Reciprocal Rank Fusion）公式**：$\text{Score}(d) = \sum_{i} \frac{1}{k + \text{rank}_i(d)}$（通常 $k=60$）。仅依赖排序名次而非原始分数，彻底规避了 BM25（无界）与 Cosine（$[-1, 1]$）量纲不一致的归一化难题。

### 2. 两阶段检索（Bi-Encoder 粗排 + Cross-Encoder 精排）的取舍
- **Bi-Encoder**：Query 与 Document 独立编码，可离线预计算向量并构建 HNSW/FAISS 索引，实现毫秒级 Top-50 召回，但缺乏词级交叉交互。
- **Cross-Encoder**：将 `[CLS] Query [SEP] Doc` 拼接联合编码，保留全交叉注意力交互，相关性判断极准；但无法离线索引，只能对粗排 Top-50 做精排重排（Rerank）以控制 P95 延迟。

### 3. RAGAS 四大核心评估指标
| 指标 | 评估对象 | 核心含义 |
| :--- | :--- | :--- |
| **Context Precision** | 检索侧 | 召回片段中真正相关的片段是否排在靠前位置 |
| **Context Recall** | 检索侧 | 支撑标准答案所需的证据片段是否被成功召回 |
| **Faithfulness** | 生成侧 | 生成回答中的每条陈述能否由检索上下文推出（防幻觉） |
| **Answer Relevance** | 生成侧 | 生成回答是否正面、完整地切中用户提问 |

### 4. Chunking 切分策略与常见陷阱
- `chunk_size` 过小导致语义碎片化、上下文丢失；过大则引入无关噪声稀释向量表达。
- 建议保留 10%–20% `chunk_overlap` 防止跨块实体/因果句被截断，或采用 **Parent-Child（小块检索、大块召回）** 策略。

---

## 三、Agent 架构与 Tool Use

### 1. ReAct vs Plan-and-Execute 范式对比
- **ReAct（Reasoning + Acting）**：`Thought -> Action -> Observation` 单步闭环，对环境反馈适应力强，但长链路任务每步都要调用 LLM，延迟高且易偏航。
- **Plan-and-Execute**：先由 Planner 拆解全局子任务清单，再由 Executor 逐步执行，减少大模型调用次数与成本；缺点是遇到意外工具报错时需触发 Re-plan。

### 2. 高可靠 Function Calling 防护三件套
1. **契约校验**：使用 Pydantic / JSON Schema 强校验工具入参，校验失败将可读错误作为 `Observation` 喂回模型自纠。
2. **防死循环熔断**：设置 `max_iterations`、Token 预算与相同参数重复调用检测。
3. **高风险拦截**：不可逆写操作必须绑定幂等键并触发 **HITL 人工审批**。

### 3. Human-in-the-Loop（HITL）挂起与断点恢复
- 不能在 HTTP 请求中长阻塞等待人工点击！应采用**状态机 + 持久化检查点**：拦截高风险工具调用 -> 将上下文与参数写入数据库置为 `pending` -> 释放连接并推送审批卡片 -> 人工通过带幂等校验的接口触发 `pending -> approved/rejected` 流转 -> 异步恢复 Agent 执行。

### 4. MCP（Model Context Protocol）的价值
- 标准化大模型应用（Client）与外部工具/数据源（Server）的通信协议，将 $M \times N$ 定制胶水适配降维为 $M + N$ 生态复用，统一暴露 `Tools`、`Resources`、`Prompts` 三类原语。

---

## 四、Python 异步编程与 FastAPI

### 1. `async def` 路由中调用同步阻塞库（如 `requests`）的后果与解法
- **后果**：阻塞当前 Worker 进程的单线程 `asyncio` 事件循环（Event Loop），导致整个服务无法并发处理其他请求。
- **解法**：优先替换为原生异步库（`httpx`、`asyncpg`）；若必须调用同步 SDK，使用 `await asyncio.to_thread(fn)` 放入线程池，或将路由声明为普通同步 `def`（FastAPI 会自动调度至 AnyIO 线程池）。

### 2. 为什么 LLM 流式输出首选 SSE 而非 WebSocket？
- LLM 生成是典型的“客户端一次请求 -> 服务端持续单向吐出 Token”模型，**SSE** 基于标准 HTTP，天然兼容 Nginx 反向代理、负载均衡、Header 鉴权且内置断线重连；WebSocket 适合高频双向实时交互，但状态维护与水平扩展成本更高。

### 3. Pydantic v2 与 Python GIL
- **Pydantic v2**：Rust 内核（`pydantic-core`）带来数倍性能提升，同时自动生成 OpenAPI 与 LLM Function Calling 所需的 JSON Schema。
- **GIL（全局解释器锁）**：限制纯 Python 多线程利用多核并行执行 CPU 密集型字节码，但 I/O 等待时会释放 GIL；CPU 密集型任务可通过多进程（`uvicorn --workers`）或 C/Rust 扩展（NumPy/PyTorch）绕过。

---

## 五、大模型工程、测试与安全

### 1. 防范 Prompt 注入与 PII 泄露的纵深防御
1. **边界隔离**：System Prompt 与不可信用户输入/外部检索文本严格分隔并加定界符标记。
2. **护栏脱敏（Guardrails）**：在网关与输出侧利用正则/NER 识别手机号、身份证、密钥等 PII 并脱敏拦截。
3. **最小权限**：工具执行不盲信模型参数，敏感操作强制走 RBAC 权限校验与 HITL 审批。

### 2. 可观测性（Observability）与 FinOps 降本
- 建设基于 OpenTelemetry 的全链路 Trace（`Request -> Retrieval -> LLM -> Tool`），重点监控 **TTFT（首字延迟）**、TPOT、工具失败率与分租户 Token 成本。
- 降本三板斧：**语义缓存（Semantic Cache）**、**大小模型路由分级**、**长对话摘要与 Context 裁剪**。

### 3. 无外部 API 环境下的 CI/CD 自动化测试
- 通过依赖注入抽象 `LLMProvider` 接口，在 `pytest` 中注入确定性的 `FakeLLM/MockClient`，稳定回归路由决策、Tool Schema 校验、HITL 状态机与异常兜底；发版前配合离线 **Golden Dataset** 验证核心指标基线。
