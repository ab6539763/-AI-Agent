# Day 33 课后作业与参考答案

## 作业一：BM25 与向量检索的互补性实战
**题目**：在企业运维知识库中，用户经常输入包含精确错误码（如 `ERR_NGX_502`、`OOMKilled`）或纯语义描述的提问。请你基于 `project_iterations/day_33` 中的 `BM25Retriever` 与 `VectorRetriever`：
1. 构造至少 3 条包含不同部门/错误码的 `Document`。
2. 分别使用 `BM25Retriever` 和 `VectorRetriever` 对 `"ERR_NGX_502 排查"` 进行检索，对比两者的 Top-2 结果与得分量纲差异。
3. 简述为什么不能直接把 BM25 分数和余弦相似度分数相加，而需要引入 RRF。

### 参考答案：
```python
from zhishu_agent import BM25Retriever, Document, VectorRetriever

docs = [
    Document(id="ops-502", page_content="错误码 ERR_NGX_502 排查手册：检查上游 Pod 与 keepalive_timeout。"),
    Document(id="ops-net", page_content="网关流量监控与负载均衡健康检查配置指南。"),
    Document(id="hr-001", page_content="员工年假与病假审批流程说明。"),
]

bm25 = BM25Retriever(docs)
vector = VectorRetriever(docs)

query = "ERR_NGX_502 排查"
print("BM25:", [(d.id, s) for d, s in bm25.retrieve_with_scores(query, top_k=2)])
print("Vector:", [(d.id, s) for d, s in vector.retrieve_with_scores(query, top_k=2)])
```
**原理解析**：BM25 得分受语料库大小、IDF 与文档长度影响，范围通常是无界的（例如 `0 ~ 20+`）；而向量余弦相似度严格落在 `[-1, 1]` 之间。两者量纲完全不同，直接相加会导致数值更大的 BM25 主导结果（或受异常高分文档支配）。RRF 只依赖“排名（Rank）”而非原始分数，因此无需归一化即可稳健融合。

---

## 作业二：RRF（倒数排名融合）公式计算与 `k` 参数理解
**题目**：假设在某次检索中，文档 `doc_b` 在 BM25 中排名第 2，在 Vector 中排名第 2；而文档 `doc_a` 仅在 BM25 中排名第 1（未进入 Vector 结果）。
1. 当平滑常数 $k = 60$ 时，请手算 `doc_b` 与 `doc_a` 的 RRF 得分，说明谁会排在前面。
2. 使用 `reciprocal_rank_fusion([list_bm25, list_vec], k=60)` 编程验证你的计算结果。
3. 简述平滑常数 $k$ 的作用：如果把 $k$ 从 `60` 改小为 `1`，会对排名产生什么影响？

### 参考答案：
- **手算结果（$k=60$）**：
  - $\text{RRF}(\text{doc\_b}) = \frac{1}{60 + 2} + \frac{1}{60 + 2} = \frac{2}{62} \approx 0.032258$
  - $\text{RRF}(\text{doc\_a}) = \frac{1}{60 + 1} = \frac{1}{61} \approx 0.016393$
  - 因此 `doc_b` 因双路共识加权排在第一位。

```python
from zhishu_agent import Document, reciprocal_rank_fusion

doc_a = Document(id="doc_a", page_content="A")
doc_b = Document(id="doc_b", page_content="B")
doc_c = Document(id="doc_c", page_content="C")

fused = reciprocal_rank_fusion([[doc_a, doc_b], [doc_c, doc_b]], k=60)
for doc, score in fused:
    print(f"{doc.id}: {score:.6f}")
```
**原理解析**：平滑常数 $k$（经典经验值为 `60`）用于控制头部排名与尾部排名的权重差距。当 $k=1$ 时，第 1 名得分 `1/2 = 0.5`，第 2 名得分 `1/3 = 0.333`，头部几名的差距被急剧放大，容易被单路检索器的 Top-1 霸榜；$k=60$ 则能让多路都排在前列的“共识文档”稳定胜出。

---

## 作业三：Parent-Child 父子文档切片策略（Small-to-Big）
**题目**：在实际企业手册中，一篇文档可能长达数千字。如果直接整篇向量化，细节信号会被稀释；如果切成 50 字的小块直接喂给 LLM，模型又缺乏完整上下文。请基于 `ParentDocumentRetriever`：
1. 构造 2 篇较长的企业文档，设置 `chunk_size=50`、`chunk_overlap=10` 写入检索器。
2. 调用 `retrieve_with_matched_children(...)` 检索某个具体细节问题，观察“命中子切片”与“返回父文档”的长度差异。
3. 说明如果多个子切片都属于同一篇父文档，`ParentDocumentRetriever` 应当如何处理？

### 参考答案：
```python
from zhishu_agent import Document, ParentDocumentRetriever

parents = [
    Document(
        id="manual-ops",
        page_content=(
            "第一章 巡检规范：每日上午检查集群节点状态。"
            "第二章 故障恢复：当 Pod 触发 OOMKilled（退出码 137）时，应核对 memory limits 并检查内存泄漏。"
            "第三章 值班制度：核心服务需保证 7x24 小时响应。"
        ),
    ),
    Document(
        id="manual-sec",
        page_content="安全基线：生产数据库禁止公网直接访问，必须通过堡垒机与动态令牌认证。",
    ),
]

retriever = ParentDocumentRetriever(chunk_size=50, chunk_overlap=10)
total_chunks = retriever.add_documents(parents)
print("生成子切片总数:", total_chunks)

for parent, child, score in retriever.retrieve_with_matched_children("OOMKilled 退出码 137", top_k=2):
    print(f"命中子切片({len(child.page_content)}字): {child.page_content}")
    print(f"返回父文档({len(parent.page_content)}字): {parent.page_content}")
```
**原理解析**：当同一篇父文档的多个子切片同时被检索命中时，必须依据 `parent_id` 进行**保序去重**（保留排名最高的那次触发即可），避免把同一篇长父文档重复塞入 LLM 的 Prompt 上下文中浪费 Token 预算。
