# Day 29 课后作业与参考答案

## 作业一：元数据过滤（Metadata Filtering）与多租户权限隔离
**题目**：在星辰数科企业知识库中，HR 制度、财务报销和 IT 运维文档混存在同一个 `LocalVectorStore` 集合中。如果普通研发员工提问“规范”，不能把高敏感的财务或 HR 机密文档混入结果。请你：
1. 向 `LocalVectorStore` 写入至少 3 条分别带有 `department="hr"`、`department="finance"`、`department="it"` 元数据的文档。
2. 使用 `filter_metadata={"department": "it", "year": {"$gte": 2025}}` 检索，验证只返回符合条件的技术文档。
3. 简述为什么向量检索中推荐“先过滤再检索（Pre-filtering）”而不是“先召回 Top-K 再过滤（Post-filtering）”。

### 参考答案：
```python
from zhishu_agent import Document, LocalVectorStore

store = LocalVectorStore(collection_name="corp_kb")
store.add_documents([
    Document(id="hr-1", page_content="员工薪酬保密规范", metadata={"department": "hr", "year": 2025}),
    Document(id="it-1", page_content="旧版 Git 分支管理规范", metadata={"department": "it", "year": 2023}),
    Document(id="it-2", page_content="新版微服务日志脱敏规范", metadata={"department": "it", "year": 2025}),
])

results = store.similarity_search(
    query="规范",
    k=3,
    filter_metadata={"department": "it", "year": {"$gte": 2025}},
)
for doc in results:
    print(doc.id, doc.metadata, doc.page_content)
# 输出: it-2 {'department': 'it', 'year': 2025} 新版微服务日志脱敏规范
```
**原理解析**：如果采用 Post-filtering（先取全库 Top-3 再按部门过滤），当全库 Top-3 恰好全属于 HR 部门时，过滤后结果会变成空列表 `[]`，导致召回严重不足；而 Pre-filtering 先把候选集缩小到合法部门，再在子集中取 Top-K，既保障了权限隔离又保证了召回数量。

---

## 作业二：Top-K 参数（`k`）选择与 Retriever 阈值调优
**题目**：在 RAG 系统中，`k` 值过大容易引入无关噪音（Lost in the Middle），`k` 值过小又可能漏掉关键上下文。请基于 `LocalVectorStore`：
1. 演示分别以 `k=1` 和 `k=3` 调用 `similarity_search_with_score("年假制度", k=...)`，观察召回数量与相似度分数的递减规律。
2. 通过 `store.as_retriever(search_kwargs={"k": 2})` 创建检索器，并在单次 `retriever.invoke("...", k=1)` 调用中动态覆盖 `k` 值。

### 参考答案：
```python
from zhishu_agent import Document, LocalVectorStore

store = LocalVectorStore()
store.add_texts(
    texts=[
        "年假制度：入职满1年享受5天带薪年假。",
        "病假制度：需提供三甲医院诊断证明。",
        "食堂菜单：每周三提供免费水果。",
    ],
    ids=["d1", "d2", "d3"],
)

for doc, score in store.similarity_search_with_score("年假制度", k=3):
    print(f"{doc.id} -> score={score:.4f} | {doc.page_content}")

retriever = store.as_retriever(search_kwargs={"k": 2})
print("默认 k=2 召回:", [d.id for d in retriever.invoke("年假制度")])
print("临时覆盖 k=1:", [d.id for d in retriever.invoke("年假制度", k=1)])
```
**调优建议**：生产环境下，经验默认值为 `k=3` 或 `k=4`；同时应结合 `similarity_search_with_score` 设置最低相似度阈值（如 `score >= 0.2`），避免完全不相关的文档被硬塞进 Prompt。

---

## 作业三：向量库 JSON 持久化（`save` / `load`）与维度校验
**题目**：在真实服务中，每次重启进程都重新调用 Embedding 模型编码百万文档既耗时又烧钱。请编写一段脚本：
1. 使用 `tempfile.TemporaryDirectory` 作为持久化目录，实例化 `LocalVectorStore` 并写入 2 条文档。
2. 调用 `save()` 落盘为 JSON 文件，再使用 `LocalVectorStore.load(...)` 从磁盘恢复一个新实例，验证新实例的 `count()` 与检索结果与原实例完全一致。
3. 思考：如果加载时传入了一个维度 `dim=64` 的 `LocalEmbedding`，而 JSON 文件中存储的是 `dim=128` 的向量，会发生什么？为什么？

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import LocalEmbedding, LocalVectorStore

with tempfile.TemporaryDirectory() as tmp:
    store = LocalVectorStore(collection_name="ops_kb", persist_directory=tmp)
    store.add_texts(["K8s Pod OOMKilled 排查指南", "Nginx 502 Bad Gateway 处理手册"], ids=["k8s-1", "ngx-1"])
    saved_path = store.save()

    restored = LocalVectorStore.load(saved_path)
    assert restored.count() == 2
    assert restored.similarity_search("Pod OOM", k=1)[0].id == "k8s-1"
    print("持久化恢复成功，文件大小:", Path(saved_path).stat().st_size, "bytes")

    # 维度不匹配校验
    try:
        LocalVectorStore.load(saved_path, embedding_function=LocalEmbedding(dim=64))
    except ValueError as exc:
        print("拦截维度不匹配:", exc)
```
**原理解析**：余弦相似度计算要求查询向量与文档向量处于完全相同的向量空间（维度与编码模型一致）。如果库内存储的是 128 维向量，而查询时用 64 维编码器生成查询向量，两者无法做点积运算，因此在 `load()` 阶段就必须抛出 `ValueError` 提前拦截。
