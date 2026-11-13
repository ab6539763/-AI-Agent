# Day 32 课后作业与参考答案

## 作业一：Multi-Query 多路召回与 RRF 去重排序
**题目**：在企业知识库中，用户同一意图常有多种表达方式（如“年假几天” vs “带薪休假天数标准”）。单一 Query 检索容易漏召回。请你基于 `project_iterations/day_32`：
1. 构建一个包含至少 3 条文档的 `LocalVectorStore`，并通过 `as_retriever(search_kwargs={"k": 2})` 获取基础检索器。
2. 使用 `MultiQueryRetriever(retriever=base_retriever, num_queries=3)` 调用 `retrieve_with_details("年假几天", k=2)`，打印生成的 3 条查询变体以及去重后的文档 ID 列表。
3. 简述为什么 `MultiQueryRetriever` 推荐使用 RRF（Reciprocal Rank Fusion）而不是直接把多路结果简单拼接。

### 参考答案：
```python
from zhishu_agent import Document, LocalVectorStore, MultiQueryRetriever

store = LocalVectorStore()
store.add_documents([
    Document(id="hr-1", page_content="员工入职满1年享受5天带薪年假，满10年享受10天。"),
    Document(id="hr-2", page_content="考勤异常需在每月最后一天前在 OA 提交补卡。"),
    Document(id="fin-1", page_content="差旅住宿标准为一线城市每晚600元。"),
])

base_retriever = store.as_retriever(search_kwargs={"k": 2})
mq = MultiQueryRetriever(retriever=base_retriever, num_queries=3)

docs, variants = mq.retrieve_with_details("年假几天", k=2)
print("生成的查询变体:", variants)
print("RRF 去重召回 ID:", [d.id for d in docs])
assert len(docs) == len({d.id for d in docs})
```
**原理解析**：如果简单拼接多路检索结果，不仅会出现大量重复切片浪费上下文窗口，还会导致排名靠后的无关文档挤占名额；RRF 通过公式 $\sum \frac{1}{k + \text{rank}}$ 累加排名倒数，既能自动去重，又能让被多个查询变体共同命中的高相关文档稳居前列。

---

## 作业二：HyDE（Hypothetical Document Embeddings）直觉与实战
**题目**：当工程师提问“Pod 老是 OOM 怎么办”时，问题本身很短且口语化，而知识库里的文档是长篇专业排查手册，两者直接算向量相似度往往偏低。请你：
1. 用自己的话解释 HyDE（假设文档向量检索）的核心直觉：为什么“用假设答案去搜真实文档”往往比“用问题直接搜文档”更准？
2. 使用 `HyDERetriever` 对上述提问执行 `retrieve_with_hypothesis("Pod 老是 OOM 怎么办")`，打印生成的假设文档与召回的 Top-1 文档 ID，并演示如何传入 `llm_fn` 接入自定义大模型生成逻辑。

### 参考答案：
```python
from zhishu_agent import Document, HyDERetriever, LocalVectorStore

store = LocalVectorStore()
store.add_documents([
    Document(
        id="it-oom",
        page_content="Kubernetes Pod 内存溢出（OOMKilled）排查手册：检查 limits.memory 与 JVM -Xmx 参数，通过 heap dump 排查内存泄漏。",
        metadata={"department": "it"},
    ),
    Document(
        id="hr-leave",
        page_content="带薪年假需提前3个工作日申请。",
        metadata={"department": "hr"},
    ),
])

# 1. 默认本地假设文档生成
hyde = HyDERetriever(vector_store=store, k=1)
hypo, docs = hyde.retrieve_with_hypothesis("Pod 老是 OOM 怎么办")
print("假设文档:", hypo)
print("召回结果:", [d.id for d in docs])

# 2. 传入自定义 llm_fn 钩子
custom_hyde = HyDERetriever(
    vector_store=store,
    llm_fn=lambda prompt: "容器发生 OOMKilled 内存溢出时，应核查 limits.memory、JVM -Xmx 与 heap dump。",
    k=1,
)
print("自定义 LLM 召回:", [d.id for d in custom_hyde.retrieve("Pod 老是 OOM 怎么办")])
```
**原理解析**：向量检索本质上是在比较两段文本在语义空间中的“叙事风格与词汇分布”。“问题”和“答案”属于不同的句式与词汇分布，而 HyDE 先让大模型脑补出一段“像知识库文档一样的假设答案”，把**问题-文档匹配**转化为**文档-文档匹配（Answer-to-Answer）**，从而大幅提升语义对齐度。

---

## 作业三：上下文压缩（Context Compression）与信噪比优化
**题目**：向量检索通常以 Chunk（例如 500 字切片）为单位返回结果，其中可能只有 1~2 句话真正回答了用户问题，其余都是无关背景或“Lost in the Middle”噪音。请你：
1. 构造一篇包含 3 句话的混合文档（其中 1 句讲“差旅住宿报销标准”，另外 2 句讲“办公用品领用”和“食堂菜单”）。
2. 使用 `ContextCompressor(min_score=0.2, max_sentences_per_doc=1)` 对提问 `"一线城市出差住宿报销上限是多少"` 进行压缩。
3. 验证无关句子被剔除，并打印 `original_chars`、`compressed_chars` 与 `compression_ratio`。思考 `drop_empty=True` 与 `drop_empty=False` 的适用场景差异。

### 参考答案：
```python
from zhishu_agent import ContextCompressor, Document

noisy_doc = Document(
    id="mix-001",
    page_content=(
        "办公用品每周二下午在行政前台统一领用。"
        "一线城市出差住宿报销上限为每晚600元，需提供合规电子发票。"
        "公司食堂每周五提供免费下午茶。"
    ),
)

compressor = ContextCompressor(min_score=0.20, max_sentences_per_doc=1)
compressed_list = compressor.compress_documents("一线城市出差住宿报销上限是多少", [noisy_doc], drop_empty=True)

res = compressed_list[0]
print("压缩后文本:", res.page_content)
print("原字符数:", res.metadata["original_chars"], "-> 压缩后:", res.metadata["compressed_chars"])
print("压缩率:", res.metadata["compression_ratio"])
assert "600元" in res.page_content
assert "食堂" not in res.page_content
```
**原理解析**：`drop_empty=True` 适合严格去噪场景（若整篇文档没有一句达到相关性阈值，直接整篇丢弃，避免垃圾上下文污染 LLM）；`drop_empty=False` 则适合高召回兜底场景（即使所有句子得分都偏低，仍保留得分最高的一句作为保底上下文）。
