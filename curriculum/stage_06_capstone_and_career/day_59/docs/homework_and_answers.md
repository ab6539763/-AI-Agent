# Day 59 课后作业与参考答案（Capstone Day 1）

## 作业一：企业 Markdown 财报与合规文档元数据规范设计
**题目**：在企业知识库建设中，如果直接将 `.md` 文件按固定字符数（如每 500 字）粗暴切分且不保留元数据，在回答“2025 财年合规部有哪些费用报销红线？”时会出现什么问题？请结合 `CapstoneKBInitializer` 的实现，说明如何通过 **Frontmatter + 标题分节** 解决该问题。

### 参考答案：
1. **粗暴切分的核心缺陷**：
   - **跨财年/跨部门混杂（Metadata 缺失）**：检索阶段无法通过 `fiscal_year="FY2025"` 或 `department="compliance"` 进行前置过滤，容易把 2024 年旧制度或研发部预算混入上下文，诱发大模型幻觉。
   - **语义截断**：固定字符切分会在章节标题或制度条款中间切断，导致切片丢失所属章节标题（`section_heading`），降低检索相关性。
2. **`CapstoneKBInitializer` 的工程解法**：
   - **YAML Frontmatter 显式标注**：在 `.md` 顶部声明 `department`、`fiscal_year`、`doc_type`、`title`，由 `extract_metadata()` 解析并注入每个 `KBChunk`。
   - **标题感知分节（`parse_markdown`）**：优先按 `#`~`####` 标题划分语义边界并记录 `section_heading`；仅当单节内容超过 `chunk_size` 时才启用带 `chunk_overlap` 的滑动窗口切分，且优先在换行或句号处断开。

---

## 作业二：结构化 CSV 财务台账的 RAG 切片策略
**题目**：为什么不能把一个 200 行的财务预算台账 `.csv` 文件直接当作普通纯文本按行或按字符切分？`CapstoneKBInitializer.parse_csv()` 是如何处理的？

### 参考答案：
1. **直接切分的问题**：
   - CSV 第一行是列名（如 `department,fiscal_year,quarter,budget_cny,actual_cny`），第 2 批及以后的切片如果丢失表头，大模型将无法理解数字列分别代表“预算”还是“实际支出”，导致数值问答完全失效。
2. **`parse_csv()` 的处理方式**：
   - 使用 `csv.DictReader` 将每一行映射为 `列名: 值` 的自描述键值对（如 `department: finance | fiscal_year: FY2025 | budget_cny: 12000000`）。
   - 按 `rows_per_csv_chunk`（如每 10 行）聚合为一个带有表名与行号范围说明的文本块，既保留完整字段语义，又控制单个切片的 Token 长度。

---

## 作业三：SQLite 索引幂等写入与元数据过滤实战
**题目**：编写一段 Python 代码，使用 `CapstoneKBInitializer` 对指定目录构建知识库并持久化至 `kb_index.sqlite`，随后：
1. 重复执行一次 `save_sqlite_index()` 验证写入幂等性（总行数不变）；
2. 调用 `query_sqlite()` 查询 `department="finance"` 且 `fiscal_year="FY2025"` 的切片并打印切片 ID 与章节标题。

### 参考答案：
```python
from pathlib import Path
import tempfile
from zhishu_agent import CapstoneKBInitializer

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    corpus_dir = base / "corpus"
    db_path = base / "kb_index.sqlite"

    CapstoneKBInitializer.create_sample_corpus(corpus_dir)
    init = CapstoneKBInitializer(chunk_size=300, chunk_overlap=40)

    chunks, stats = init.build_and_persist(
        input_dir=corpus_dir,
        sqlite_path=db_path,
    )
    # 幂等重复写入验证
    init.save_sqlite_index(chunks, db_path)
    all_rows = init.query_sqlite(db_path, limit=100)
    assert len(all_rows) == len(chunks)

    # 元数据精确过滤检索
    finance_hits = init.query_sqlite(
        db_path=db_path,
        department="finance",
        fiscal_year="FY2025",
    )
    for row in finance_hits:
        print(row["chunk_id"], row["section_heading"], row["doc_type"])
```
