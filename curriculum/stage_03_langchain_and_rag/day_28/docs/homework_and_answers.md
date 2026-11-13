# Day 28 课后作业与参考答案

## 作业一：`chunk_size` 与 `chunk_overlap` 参数调优实战
**题目**：在 RAG 系统中，切分窗口 `chunk_size` 过小会导致上下文残缺，过大则会稀释向量检索精度并浪费 LLM Token；而 `chunk_overlap` 则用于在相邻 Chunk 之间保留衔接上下文。请基于 Day 28 的 `RecursiveCharacterTextSplitter`：
1. 对一段包含 4 句企业报销规范的中文文本，分别使用 `(chunk_size=35, chunk_overlap=0)` 与 `(chunk_size=35, chunk_overlap=10)` 进行切分，对比输出的 Chunk 数量与边界衔接效果。
2. 解释为什么工程上必须强制校验 `chunk_overlap < chunk_size`，如果允许 `chunk_overlap >= chunk_size` 会发生什么问题？

### 参考答案：
```python
from zhishu_agent.document_loader import RecursiveCharacterTextSplitter

text = (
    "员工出差前需在OA系统提交审批。审批通过后可预订协议酒店。"
    "归来后7个工作日内需上传电子发票。财务审核无误后3个工作日内打款。"
)

s_no_overlap = RecursiveCharacterTextSplitter(chunk_size=35, chunk_overlap=0)
s_with_overlap = RecursiveCharacterTextSplitter(chunk_size=35, chunk_overlap=10)

print("=== overlap=0 ===")
for idx, c in enumerate(s_no_overlap.split_text(text)):
    print(f"[{idx}] {c}")

print("\n=== overlap=10 ===")
for idx, c in enumerate(s_with_overlap.split_text(text)):
    print(f"[{idx}] {c}")
```
**原理解析**：
- 当 `chunk_overlap=10` 时，相邻两个 Chunk 之间会保留上一句或上一片段的尾部上下文，避免跨句指代（如“审批通过后”）在切分边界处丢失主语。
- 滑动窗口每次前进的步长为 `step = chunk_size - chunk_overlap`。若 `chunk_overlap >= chunk_size`，步长将 `<= 0`，窗口无法向前推进，会导致切分器陷入**死循环**或不断重复输出相同片段。

---

## 作业二：使用 `MarkdownHeaderTextSplitter` 进行结构化标题切分
**题目**：企业内部有大量 Markdown 格式的技术文档（如《智枢部署手册》），其中既包含 `#`、`##`、`###` 多级标题，又包含带有 `# 注释` 的 Python/Shell 代码块。请使用 `MarkdownHeaderTextSplitter`：
1. 切分一段包含二级标题、三级标题与 Python 代码块的 Markdown 文本。
2. 验证代码块中的 `# 注释` 不会被错误切分，且当文档从 `## 架构`（含 `### 存储`）切换到 `## 运维` 时，旧的 `Header 3` 元数据会被正确清除。

### 参考答案：
```python
from zhishu_agent.document_loader import MarkdownHeaderTextSplitter

md_doc = """# 智枢部署手册
## 架构
系统采用微服务架构。
### 存储
使用 SQLite 存储会话。
```python
# 这是配置注释，不能当成 Header 1
DB_PATH = "/data/zhishu.db"
```
## 运维
使用 Docker Compose 一键启动。"""

splitter = MarkdownHeaderTextSplitter()
chunks = splitter.split_text(md_doc)

for i, doc in enumerate(chunks):
    print(f"Chunk {i}: metadata={doc.metadata}")
    print(f"  content={doc.page_content!r}")
```
**预期结果**：
- 代码块中的 `# 这是配置注释，不能当成 Header 1` 被完整保留在 `Header 3: "存储"` 的 Chunk 正文中。
- 最后一个 Chunk（`## 运维`）的 `metadata` 为 `{"Header 1": "智枢部署手册", "Header 2": "运维"}`，不再残留 `"Header 3": "存储"`，从而保证下游向量库按章节过滤检索时的准确性。

---

## 作业三：文档加载与切分全链路中的元数据（Metadata）保留与溯源
**题目**：在企业级 RAG 问答中，用户不仅关心“答案是什么”，还要求 AI 给出**引用来源**（例如文件名、行号、章节标题与分片序号）。请结合 `MarkdownLoader` 与 `MarkdownHeaderTextSplitter.split_documents()`：
1. 演示从磁盘读取一个 `.md` 文件并完成切分。
2. 说明 `split_documents()` 在合并原始 `Document.metadata` 与新生成的标题/分片元数据时，为什么要使用 `dict(doc.metadata)` 拷贝而非直接修改原字典？

### 参考答案：
```python
from pathlib import Path
from tempfile import TemporaryDirectory
from zhishu_agent.document_loader import MarkdownHeaderTextSplitter, MarkdownLoader

with TemporaryDirectory() as tmp:
    md_path = Path(tmp) / "security_policy.md"
    md_path.write_text(
        "# 信息安全规范\n\n## 密码策略\n密码长度不少于 12 位。\n\n## 权限审计\n每季度开展一次权限复核。",
        encoding="utf-8",
    )

    raw_docs = MarkdownLoader(md_path).load()
    splitter = MarkdownHeaderTextSplitter()
    chunk_docs = splitter.split_documents(raw_docs)

    for doc in chunk_docs:
        print(doc.metadata)
        # 输出同时包含: source, file_name, loader, title, Header 1, Header 2, chunk_index, chunk_total
```
**原理解析**：
- 在 Python 中字典是**可变对象（Mutable）**。如果多个切分后的 Chunk 共享或直接修改原始 `doc.metadata` 引用，会导致所有 Chunk 的 `chunk_index`、`Header 2` 等字段互相覆盖，同时污染原始 `Document` 对象。
- 通过 `merged_meta = dict(doc.metadata)` 创建独立副本后再 `update()`，既完整保留了上游 Loader 注入的 `source`、`file_name`、`title` 溯源信息，又安全地追加了下游切分器的 `Header 1/2/3` 与 `chunk_index` 元数据。
