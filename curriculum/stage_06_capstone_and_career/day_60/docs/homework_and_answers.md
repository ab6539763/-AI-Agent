# Day 60 课后作业与参考答案

## 作业一：RRF（倒数排序融合）与直接分数加权的对比分析
**题目**：在 `CapstoneRAGEngine` 中，为什么不直接用 `0.5 * bm25_score + 0.5 * vector_score` 融合两路检索结果，而要采用 `reciprocal_rank_fusion`（默认 `k=60`）？请结合分数分布特征与代码参数说明 `k` 值的工程意义。

### 参考答案：
1. **量纲与分布差异**：
   - `BM25Index` 得分取决于词频 TF、逆文档频率 IDF 与文档长度归一化，取值无固定上界（通常在 `0 ~ 30+` 之间波动）。
   - `VectorIndex` 余弦相似度严格位于 `[-1.0, 1.0]` 区间。若直接线性加权，BM25 的绝对数值会完全淹没向量相似度。
2. **RRF 的优势与 `k=60` 的意义**：
   - RRF 公式为 $\sum \frac{w_i}{k + \text{rank}_i}$，仅依赖排名（1-indexed）而非原始分数，天然具备量纲无关性。
   - 平滑常数 `k=60` 控制头部排名的衰减斜率：既能让同时在 BM25 与向量两路排名前列的文档获得显著叠加优势，又能避免第 1 名与第 2 名之间分差过大导致单路误召霸榜。

---

## 作业二：行内引用一致性校验（Citation Integrity）
**题目**：企业级 RAG 上线前，QA 团队要求确保模型回答中出现的每一个行内引用编号 `[i]` 都必须能在 `RAGResponse.citations` 中找到对应溯源切片，严禁出现“幻觉引用编号”（如正文写了 `[3]` 但只返回了 2 条引用）。请编写一段 Python 校验函数验证 `CapstoneRAGEngine.query` 的输出。

### 参考答案：
```python
import re
from zhishu_agent import CapstoneRAGEngine, KnowledgeChunk

def verify_citation_integrity(engine: CapstoneRAGEngine, question: str) -> None:
    resp = engine.query(question)
    inline_ids = {int(m) for m in re.findall(r"\[(\d+)\]", resp.answer)}
    valid_ids = {c.citation_id for c in resp.citations}

    if resp.refused:
        assert resp.citations == [], "拒答状态下不应返回任何引用"
        assert not inline_ids, "拒答文案中不应包含行内引用编号"
    else:
        assert inline_ids.issubset(valid_ids), f"发现未定义的行内引用: {inline_ids - valid_ids}"
        assert len(resp.citations) >= 1, "非拒答结果至少应包含 1 条有效引用"
```

---

## 作业三：低置信度拒答阈值（`min_confidence`）调优实践
**题目**：某业务线反馈：当 `min_confidence=0.60` 时，大量正常口语化提问被误拒（Recall 过低）；当 `min_confidence=0.05` 时，域外问题（如“今天天气如何”）又会强行拼凑无关文档回答（幻觉率上升）。请说明如何利用 `CrossReranker` 的 `rerank_score` 与业务测试集确定合理的 `min_confidence` 阈值区间。

### 参考答案：
1. **构建两类黄金评测集**：
   - **域内正样本集（In-Domain）**：覆盖员工口语化问法、精确错误码查询（如 `ERR_502`）等应当回答的问题，记录各自的 `top_rerank_score` 分布（本项目中通常落在 `0.35 ~ 0.75`）。
   - **域外负样本集（Out-of-Domain）**：覆盖天气、股市、闲聊等知识库无答案问题，记录各自的 `top_rerank_score` 分布（本项目中通常低于 `0.20`）。
2. **寻找最优分离点**：
   - 将 `min_confidence` 设定在负样本 P95 分数之上、正样本 P5 分数之下的安全窗口（例如 `0.22 ~ 0.28`），并在 `RAGResponse.trace["top_rerank_score"]` 中持续观测线上得分分布以定期校准。
