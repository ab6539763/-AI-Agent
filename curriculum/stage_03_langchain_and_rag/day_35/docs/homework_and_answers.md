# Day 35 课后作业与参考答案

## 作业一：使用 `SimpleDirectoryReader` 与 `VectorStoreIndex` 构建企业知识库索引
**题目**：星辰数科需要将本地知识库目录（包含 `hr_policy.md` 和 `security_ops.txt` 两个文件）快速接入 LlamaIndex 流水线。请你编写一段 Python 脚本：
1. 使用 `tempfile.TemporaryDirectory` 模拟企业知识库目录并写入上述两份文档。
2. 调用 `SimpleDirectoryReader` 加载文档，并打印每篇文档的 `doc_id` 与 `file_name`。
3. 使用 `VectorStoreIndex.from_documents(docs, chunk_size=60, chunk_overlap=10)` 构建索引，打印生成的 `Node` 总数以及第一个 `Node` 的 `relationships` 关系字典。

### 参考答案：
```python
from pathlib import Path
import tempfile
from zhishu_agent import SimpleDirectoryReader, VectorStoreIndex

with tempfile.TemporaryDirectory() as tmpdir:
    kb = Path(tmpdir)
    (kb / "hr_policy.md").write_text(
        "星辰数科年假制度：入职满1年员工每年享有5天带薪年假。申请年假需提前3个工作日在OA审批。",
        encoding="utf-8",
    )
    (kb / "security_ops.txt").write_text(
        "生产环境严禁直接执行 DROP TABLE 或 Redis KEYS * 命令，所有变更需经过工单审批。",
        encoding="utf-8",
    )

    docs = SimpleDirectoryReader(kb).load_data()
    for d in docs:
        print(d.doc_id, d.metadata["file_name"])

    index = VectorStoreIndex.from_documents(docs, chunk_size=60, chunk_overlap=10)
    print("Node 总数:", len(index.nodes))
    print("首个 Node 关系链:", index.nodes[0].relationships)
```
**原理解析**：`SimpleDirectoryReader` 自动过滤非目标扩展名并保留文件路径元数据；`VectorStoreIndex.from_documents()` 在后台一次性完成切片（Chunking）、特征向量编码与节点入库，同时为同一文档的相邻 `Node` 自动建立 `SOURCE`、`PREVIOUS`、`NEXT` 关系链，便于后续做上下文扩展检索。

---

## 作业二：`QueryEngine` 与 `ChatEngine` 的本质区别与多轮追问实战
**题目**：在客服机器人场景中，用户先问 `"星辰数科入职满1年员工有多少天年假？"`，紧接着追问 `"申请它需要提前几天？"`。
1. 请分别使用 `index.as_query_engine()` 和 `index.as_chat_engine()` 处理这两轮提问，对比两者的输出差异。
2. 解释为什么 `QueryEngine` 在第二轮容易“丢失上下文”，而 `ChatEngine` 能准确命中 `"提前3个工作日"`，并说明 `chat_engine.reset()` 的适用场景。

### 参考答案：
```python
from zhishu_agent import Document, VectorStoreIndex

docs = [
    Document(
        text="星辰数科年假制度：入职满1年员工每年享有5天带薪年假。申请年假需提前3个工作日在OA审批。",
        metadata={"file_name": "hr_policy.md"},
    )
]
index = VectorStoreIndex.from_documents(docs)

# 1. QueryEngine（无状态）
qe = index.as_query_engine()
print("QE Turn 1:", qe.query("星辰数科入职满1年员工有多少天年假？").response)
print("QE Turn 2:", qe.query("申请它需要提前几天？").response)

# 2. ChatEngine（有状态）
ce = index.as_chat_engine()
print("CE Turn 1:", ce.chat("星辰数科入职满1年员工有多少天年假？").response)
res2 = ce.chat("申请它需要提前几天？")
print("CE Turn 2 改写检索词:", res2.metadata["condensed_query"])
print("CE Turn 2:", res2.response)

ce.reset()  # 切换新会话或新话题时重置历史
```
**原理解析**：`QueryEngine` 是**无状态（Stateless）**的，每次调用 `query()` 相互独立，面对 `"申请它需要提前几天？"` 这类包含代词“它”的短追问时，检索器无法知道“它”指代“年假”；而 `ChatEngine` 是**有状态（Stateful）**的，它维护 `chat_history`，并在 `condense_question` 模式下将上一轮核心上下文与当前追问融合改写，从而精准检索到“申请年假需提前3个工作日”。当用户开启新话题或切换账号会话时，应调用 `reset()` 避免旧历史污染新检索。

---

## 作业三：LangChain vs LlamaIndex 技术选型矩阵决策
**题目**：星辰数科即将立项三个新项目，请你调用 `compare_frameworks(use_case=...)` 并结合架构选型矩阵，为每个项目给出推荐技术栈与理由：
- **项目 A（企业制度知识库问答助手）**：接入 5,000 份 PDF/Markdown 制度文件，要求支持精确溯源与多文档汇总。
- **项目 B（自动化运维值班 Agent）**：需要对接监控告警 API、执行故障诊断脚本、在关键变更前挂起等待人工审批（HITL）。
- **项目 C（智枢全能企业助手）**：既要能精准检索海量私有文档，又要能根据检索结果自动创建 Jira 工单并发送飞书通知。

### 参考答案：
```python
from zhishu_agent import compare_frameworks

for case in ("enterprise_rag", "multi_agent_workflow", "hybrid"):
    res = compare_frameworks(use_case=case)
    rec = res["recommendation"]
    print(f"[{case}] 推荐: {rec['recommended']} -> {rec['reason']}")
```
**选型决策矩阵结论**：
1. **项目 A（`enterprise_rag`）**：推荐 **LlamaIndex**。核心痛点在于大规模异构文档的索引质量、父子节点关系管理与响应合成（`compact` / `tree_summarize`），LlamaIndex 开箱即用程度最高。
2. **项目 B（`multi_agent_workflow`）**：推荐 **LangChain + LangGraph**。核心痛点在于多工具调度、条件分支循环与人工介入（HITL）状态持久化，LangGraph 的状态图编排能力最具优势。
3. **项目 C（`hybrid`）**：推荐 **LlamaIndex（检索索引层）+ LangChain/LangGraph（Agent 编排层）**。将 LlamaIndex 的 `QueryEngine` 封装为 LangChain `Tool`，由 LangGraph 智能体统一调度知识查询、工单创建与消息通知，兼顾检索深度与编排灵活度。
