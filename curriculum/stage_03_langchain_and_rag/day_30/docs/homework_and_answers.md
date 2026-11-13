# Day 30 课后作业与参考答案

## 作业一：引用格式化（Citation Formatting）与来源溯源展示
**题目**：在企业知识库问答中，用户不仅关心答案本身，还希望点击 `[1]`、`[2]` 查看原文出处与可信度分数。请基于 `RAGPipeline`：
1. 写入两条分别来自 `《员工手册》` 与 `《信息安全规范》` 的文档。
2. 调用 `answer_with_citations("年假有多少天？")`，遍历返回的 `RAGAnswer.citations`，将引用列表格式化为标准 Markdown 脚注形式：
   `[index] 来源: {source} (ID: {doc_id}, 相似度: {score:.4f}) -> 片段: {snippet}`。

### 参考答案：
```python
from zhishu_agent import Document, RAGPipeline

pipeline = RAGPipeline(min_score_threshold=0.15, default_k=2)
pipeline.ingest_documents([
    Document(
        id="hr-1",
        page_content="员工入职满1年享受5天带薪年假，满10年享受10天带薪年假。",
        metadata={"source": "《员工手册》"},
    ),
    Document(
        id="sec-1",
        page_content="办公电脑离开座位超过5分钟需锁定屏幕。",
        metadata={"source": "《信息安全规范》"},
    ),
])

res = pipeline.answer_with_citations("年假有多少天？")
print("回答:\n", res.answer)
print("\n参考来源:")
for c in res.citations:
    print(f"[{c.index}] 来源: {c.source} (ID: {c.doc_id}, 相似度: {c.score:.4f}) -> 片段: {c.snippet}")
```
**原理解析**：`Citation` 将 `index`、`source`、`doc_id`、`score` 与 `snippet` 结构化封装，前端或下游对话系统可以据此渲染可点击的高亮引用角标，提升企业用户对 AI 回答的信任度。

---

## 作业二：低相似度兜底阈值（`min_score_threshold`）调优实验
**题目**：如果 `min_score_threshold` 设置过高，正常问题会被误拒（False Negative）；如果设置过低，无关问题会强行拼接不相干文档（False Positive）。请编写实验脚本：
1. 向 `RAGPipeline` 写入一条 IT 运维文档（如 Redis `SCAN` 规范）。
2. 对同一无关问题（如 `"今天食堂午饭吃什么？"`），分别以 `min_score_threshold=0.0` 和 `min_score_threshold=0.20` 调用 `answer_with_citations`，对比 `grounded` 状态与 `answer` 输出的差异。
3. 总结在生产环境中如何通过评估集确定最优阈值。

### 参考答案：
```python
from zhishu_agent import Document, RAGPipeline

pipeline = RAGPipeline()
pipeline.ingest_documents([
    Document(
        id="it-1",
        page_content="生产环境 Redis 严禁使用 KEYS *，请使用 SCAN 分批遍历。",
        metadata={"source": "《SRE 运维手册》"},
    )
])

query = "今天食堂午饭吃什么？"
res_loose = pipeline.answer_with_citations(query, min_score_threshold=0.0)
res_strict = pipeline.answer_with_citations(query, min_score_threshold=0.20)

print("阈值=0.0  -> grounded:", res_loose.grounded, "| max_score:", res_loose.max_score)
print("阈值=0.20 -> grounded:", res_strict.grounded, "| answer:", res_strict.answer)
```
**调优建议**：生产环境下应构建包含“域内正样本（50条）”与“域外负样本（50条）”的评测集，统计不同阈值下的拒答准确率（Precision/Recall）与 F1 分数，选取能拦截绝大多数域外噪声且正样本误拒率低于 2% 的拐点作为默认 `min_score_threshold`。

---

## 作业三：防幻觉 RAG Prompt 设计与 `llm_fn` 注入测试
**题目**：Prompt 工程是控制大模型忠实于检索上下文的关键。请：
1. 调用 `build_rag_prompt(query, retrieved_docs)` 查看 Day 30 默认 Prompt 的三段式结构（角色与防幻觉规则、`【参考上下文】`、`【用户问题】`）。
2. 编写一个自定义的 `mock_llm(prompt: str) -> str` 函数，验证当传入 `RAGPipeline(..., llm_fn=mock_llm)` 时，流水线确实将构造好的带 `[1]` 编号上下文的 Prompt 传给了大模型，并返回模型生成的带引用回答。

### 参考答案：
```python
from zhishu_agent import Document, RAGPipeline

def mock_llm(prompt: str) -> str:
    assert "【参考上下文】" in prompt
    assert "[1]" in prompt
    return "根据《财务报销制度》，一线城市住宿标准为每晚600元以内 [1]。"

pipeline = RAGPipeline(min_score_threshold=0.10, llm_fn=mock_llm)
pipeline.ingest_documents([
    Document(
        id="fin-1",
        page_content="一线城市出差酒店住宿报销上限为每晚600元，需附电子发票。",
        metadata={"source": "《财务报销制度》"},
    )
])

ans = pipeline.answer_with_citations("一线城市出差住宿标准是多少？")
print("grounded:", ans.grounded)
print("answer:", ans.answer)
print("citations count:", len(ans.citations))
```
**原理解析**：优秀的 RAG Prompt 必须明确三件事：（1）**边界约束**（只能基于参考上下文回答，禁止外部脑补）；（2）**格式约束**（要求在结论后标注 `[1]`、`[2]` 来源编号）；（3）**拒答出口**（上下文不足时明确输出 `"我不知道/知识库中未找到相关信息"`）。
