# Day 66 课后作业与参考答案

## 作业一：使用 `audit_resume_bullets()` 诊断并重构个人简历
**题目**：某同学的简历初稿包含以下两条项目描述：
1. `"参与企业知识库问答系统开发，使用了大模型和向量数据库，效果良好。"`
2. `"负责 Agent 工具调用模块，解决了部分报错问题，提升了稳定性。"`

请调用 `audit_resume_bullets()` 检测这两条描述的具体问题，并将它们改写为符合 `STARBullet` 规范、且能通过质检器（`passed=True`）的高质量条目。

### 参考答案：
```python
from zhishu_agent.portfolio_builder import STARBullet, audit_resume_bullets

drafts = [
    "参与企业知识库问答系统开发，使用了大模型和向量数据库，效果良好。",
    "负责 Agent 工具调用模块，解决了部分报错问题，提升了稳定性。",
]
print("改写前质检:", audit_resume_bullets(drafts).flagged_bullets)  # 2 条均被标红

rewritten = [
    STARBullet(
        situation="企业知识库中专有名词与财务指标纯向量检索漏召回严重",
        task="主导重构混合检索与引用溯源链路",
        action="设计 BM25 + FAISS 向量双路召回与 RRF 融合排序，并接入 Cross-Encoder Rerank",
        result="Top-5 召回率从 68% 提升至 91%，P95 检索延迟降至 170ms",
        tech_stack=["RAG", "BM25", "FAISS", "RRF", "Rerank"],
        role_tags=["RAG Engineer"],
    ),
    STARBullet(
        situation="多工具并发调用存在参数越权与外部接口超时雪崩风险",
        task="构建高可靠 Agent 工具沙箱与 HITL 审批网关",
        action="基于 Pydantic 强类型校验、MCP 沙箱隔离与 FastAPI SSE 实现高风险挂起审批",
        result="工具调用异常率下降 82%，高风险操作 100% 强制人工复核，pytest 回归通过率 100%",
        tech_stack=["Agent", "MCP", "Pydantic", "HITL", "FastAPI", "SSE", "pytest"],
        role_tags=["Agent Engineer"],
    ),
]
report = audit_resume_bullets(rewritten)
assert report.passed_bullets == 2
```

---

## 作业二：为 GitHub 开源项目 README 补全至 100 分（Grade A）
**题目**：如果一个仓库的 `README.md` 只有项目名称、一段简介和 `pip install` 命令，调用 `audit_github_readme()` 大约能得多少分？缺少哪些关键维度？请写出补全后的最小可行结构。

### 参考答案：
- 仅包含 `pip install` 时，通常只能命中 `quickstart`（**20/100 分，等级 D**），缺少 `architecture_diagram`、`api_docs`、`eval_benchmarks`、`demo_gif` 与 `license` 共 5 项。
- **最小可行 100 分结构**需依次包含：
  1. 顶部 `![Demo](demo.gif)` 演示图（10 分）；
  2. `## Architecture` 内嵌 ```` ```mermaid ```` 架构图（20 分）；
  3. `## Quickstart` 可复制安装与 `pytest` 命令（20 分）；
  4. `## API` 核心接口路径（如 `POST /api/v1/capstone/chat/stream`）（20 分）；
  5. `## Benchmarks` 量化对比表（含 `Recall@5`、`P95 Latency`）（20 分）；
  6. `## License` 开源协议（如 `MIT License`）（10 分）。

---

## 作业三：针对不同目标岗位动态调整简历侧重点
**题目**：当同一份项目经历同时投递 **Agent Engineer** 与 **RAG Engineer** 两个岗位时，`generate_resume_markdown()` 是如何自动调整输出内容与项目排序的？

### 参考答案：
`generate_resume_markdown()` 会根据 `target_role` 映射到 `ROLE_PROFILES` 中的专属岗位画像：
1. **更换岗位标题与个人优势摘要**：分别突出 Multi-Agent 状态机/HITL/MCP 与 BM25/RRF/Rerank 评测体系；
2. **切换核心技术栈矩阵**：优先展示目标岗位最高频的 4 组核心技能；
3. **动态重排项目经历**：通过 `_bullet_role_relevance()` 计算每条 `STARBullet` 的 `role_tags` 匹配度与 `priority_keywords` 命中数，将最契合目标岗位的项目经历排在最前面。
