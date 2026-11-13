# Week 5 综合能力测评与参考答案（LangChain、LCEL、Memory 与 RAG 核心工程）

> **测评范围**：第三阶段 Day 25 – Day 31（LangChain 核心抽象、LCEL 管道编排、多会话记忆隔离、文档加载与切分、向量数据库与 Retriever、RAG 调优与评估）。  
> **题型设置**：10 道单项选择题（每题 6 分，共 60 分）+ 2 道实战编程题（每题 20 分，共 40 分），满分 100 分。

---

## 第一部分：单项选择题（10 题，每题 6 分）

### 第 1 题（LangChain 消息抽象）
在 LangChain 统一消息协议中，以下哪种消息类型专门用于向大模型下达全局角色设定、行为准则与安全约束？
- A. `HumanMessage`
- B. `AIMessage`
- C. `SystemMessage`
- D. `FunctionMessage`

### 第 2 题（LCEL 管道编排）
在 LCEL（LangChain Expression Language）中，表达式 `chain = prompt | llm | parser` 能够成立的核心 Python 语法机制是：
- A. 重载 `__add__` 与 `__radd__` 魔术方法
- B. 重载 `__or__` 与 `__ror__` 魔术方法
- C. 使用元类自动拦截函数调用
- D. 通过装饰器 `@pipeline` 改写 AST 语法树

### 第 3 题（LCEL 并行与透传）
在构建 RAG 问答链时，若需要将用户原始问题 `question` 透传给下游 Prompt，同时并发执行 `retriever` 检索上下文，最标准、最优雅的 LCEL 写法是：
- A. `{"context": retriever, "question": RunnablePassthrough()} | prompt | llm`
- B. `retriever | prompt | llm`
- C. `RunnableSequence(retriever, prompt, llm)`
- D. `prompt | retriever | llm`

### 第 4 题（多租户记忆隔离）
在企业级智能体服务中，为了防止不同部门或不同用户的对话历史“串台”，同时避免服务端重启后记忆丢失，以下哪种架构设计最合理？
- A. 使用模块级全局变量 `GLOBAL_HISTORY = []` 存储所有消息
- B. 使用基于 `session_id` 分区的持久化存储（如 SQLite `(session_id, id)` 复合索引或 Redis Hash/List）
- C. 把历史消息直接写死在 `SystemMessage` 模板中
- D. 每次请求都新建一个无状态模型实例并丢弃全部历史

### 第 5 题（上下文窗口压缩策略）
当多轮对话长度逼近大模型上下文窗口上限时，如果既想保留最近几轮的精确对话细节，又不想让早期的关键背景信息完全丢失，应该采用哪种记忆策略？
- A. `WindowMemory`（仅保留最近 K 轮，直接丢弃早期消息）
- B. `TokenBufferMemory`（超限后从头截断）
- C. `SummaryBufferMemory`（近期保留原文 + 早期历史压缩为摘要）
- D. 无限扩容 `max_tokens` 参数

### 第 6 题（文档切分与重叠窗口）
在使用 `RecursiveCharacterTextSplitter` 或滑动窗口切分企业制度文档时，设置 `chunk_overlap > 0`（如 `chunk_size=500, chunk_overlap=80`）的主要工程目的是：
- A. 故意增加向量库存储空间占用
- B. 防止关键语义或答案恰好跨越切分边界而被“腰斩”，保证上下文连续性
- C. 让所有切片的长度完全相等
- D. 跳过文档中的标点符号

### 第 7 题（向量化与余弦相似度）
在 `LocalEmbedding` 中，先将词元映射到固定维度向量，再执行 **L2 归一化（L2 Normalization）** 后，两个向量的点积（Dot Product）等价于：
- A. 欧氏距离（Euclidean Distance）
- B. 曼哈顿距离（Manhattan Distance）
- C. 余弦相似度（Cosine Similarity）
- D. 编辑距离（Levenshtein Distance）

### 第 8 题（向量库元数据过滤）
在带有权限控制的企业知识库检索中，为什么推荐采用 **Pre-filtering（先按元数据过滤，再计算相似度取 Top-K）** 而不是 Post-filtering（先取全库 Top-K，再过滤元数据）？
- A. Pre-filtering 不需要计算向量
- B. Post-filtering 可能导致全库 Top-K 恰好都不满足过滤条件，最终返回空结果或不足 K 条
- C. Pre-filtering 会自动忽略 `top_k` 参数
- D. Post-filtering 无法支持 `$gte` 等比较操作符

### 第 9 题（ANN / HNSW 索引直觉）
生产级向量数据库（如 Chroma、Milvus、Qdrant）在百万级向量规模下广泛采用 **HNSW** 索引，其核心思想是：
- A. 对所有向量逐一进行暴力全表扫描以保证 100% 精确
- B. 构建分层可导航小世界图（多层跳表），以极微小的召回率损失换取 $O(\log N)$ 级别的毫秒级近似最近邻检索
- C. 将向量转换为 SQL 字符串后使用 `LIKE '%...%'` 查询
- D. 每次查询前重新训练一次大模型

### 第 10 题（RAG 检索评估指标）
假设在一次 RAG 评测中共有 2 条测试问题：第 1 题在 Top-3 检索结果中的**第 1 位**命中相关切片，第 2 题在 Top-3 检索结果中的**第 2 位**命中相关切片。则本次实验的 `Hit Rate@3` 和 `MRR` 分别为：
- A. `Hit Rate@3 = 1.0`, `MRR = 0.5`
- B. `Hit Rate@3 = 0.5`, `MRR = 0.75`
- C. `Hit Rate@3 = 1.0`, `MRR = 0.75`
- D. `Hit Rate@3 = 0.75`, `MRR = 1.0`

---

## 第二部分：实战编程题（2 题，每题 20 分）

### 编程题 1：实现带防呆校验的 `TuningConfig` 与滑动窗口切分函数 `chunk_text`
**题目要求**：
1. 定义 `@dataclass(frozen=True)` 类 `TuningConfig(chunk_size: int, chunk_overlap: int, top_k: int)`，在 `__post_init__` 中校验：`chunk_size > 0`、`0 <= chunk_overlap < chunk_size`、`top_k > 0`，不满足时抛出 `ValueError`。
2. 实现函数 `chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]`：去除首尾空白，若文本为空返回 `[]`，否则按步长 `chunk_size - chunk_overlap` 切分，确保每个切片长度不超过 `chunk_size`。

### 编程题 2：计算 RAG 检索指标 `compute_retrieval_metrics`
**题目要求**：
给定每条 Query 的“首条相关切片排名列表” `first_relevant_ranks: list[int | None]`（其中 `int` 为 1-indexed 排名，如 `1`、`2`、`3`；`None` 表示 Top-K 内未命中），实现函数 `compute_retrieval_metrics(first_relevant_ranks: list[int | None]) -> dict[str, float]`，返回 `{"hit_rate": ..., "mrr": ...}`。若输入为空列表，抛出 `ValueError`。

---

## 第三部分：参考答案与深度解析

### 一、单项选择题答案速查与解析

| 题号 | 答案 | 核心解析 |
| :--- | :---: | :--- |
| **1** | **C** | `SystemMessage` 用于设定系统级人设、规则与安全护栏；`HumanMessage` 代表用户输入，`AIMessage` 代表模型回复。 |
| **2** | **B** | Python 的按位或运算符 `|` 对应 `__or__` 与 `__ror__` 魔术方法，LCEL 通过重载它们将组件拼接为 `RunnableSequence`。 |
| **3** | **A** | `RunnablePassthrough()` 将原始输入原封不动传递给 `"question"`，同时与 `"context": retriever` 组成 `RunnableParallel` 并行字典。 |
| **4** | **B** | 多租户隔离必须以 `session_id` 为逻辑/物理分区键，并借助 SQLite/Redis 等持久化介质防止重启丢数据。 |
| **5** | **C** | `SummaryBufferMemory` 兼顾“近期窗口高保真”与“远期历史摘要压缩”，是企业长对话的标准折中方案。 |
| **6** | **B** | 重叠窗口让相邻切片共享边界文本，避免完整句子或关键数值被切分点拆散导致检索漏召回。 |
| **7** | **C** | 当向量满足 $\|a\|_2 = \|b\|_2 = 1$ 时，$\cos(\theta) = \frac{a \cdot b}{\|a\|_2 \|b\|_2} = a \cdot b$，点积即余弦相似度。 |
| **8** | **B** | Post-filtering 在过滤阶段会丢弃不符合条件的候选，极易导致返回条数少于 `k` 甚至为空。 |
| **9** | **B** | HNSW 通过多层图结构实现“高层长跳粗定位 + 底层稠密精搜”，将检索复杂度降至近似 $O(\log N)$。 |
| **10** | **C** | 两题均在 Top-3 内命中，故 `Hit Rate@3 = (1 + 1) / 2 = 1.0`；倒数排名分别为 `1/1 = 1.0` 与 `1/2 = 0.5`，故 `MRR = (1.0 + 0.5) / 2 = 0.75`。 |

---

### 二、实战编程题参考实现

#### 编程题 1 参考代码
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TuningConfig:
    chunk_size: int
    chunk_overlap: int
    top_k: int

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")
        if self.top_k <= 0:
            raise ValueError("top_k 必须大于 0")


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("非法的切分参数")
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start += step
    return chunks
```

#### 编程题 2 参考代码
```python
def compute_retrieval_metrics(first_relevant_ranks: list[int | None]) -> dict[str, float]:
    if not first_relevant_ranks:
        raise ValueError("first_relevant_ranks 不能为空")

    total = len(first_relevant_ranks)
    hits = sum(1 for r in first_relevant_ranks if r is not None and r > 0)
    rr_sum = sum(1.0 / r for r in first_relevant_ranks if r is not None and r > 0)

    return {
        "hit_rate": hits / total,
        "mrr": rr_sum / total,
    }
```
