# Day 58 课后作业与参考答案

## 作业一：从 8 大赛道中选定毕业项目并编写合格的 `TechnicalProposal`
**题目**：请从 `CAPSTONE_TOPICS` 的 8 大行业赛道（如 `企业财报分析系统`、`法律咨询助手`、`电商智能客服` 等）中选择一个你最感兴趣的方向，构造一份能够通过 `review_proposal()` 校验（状态为 `APPROVED`、总分 `>= 90`）的 `TechnicalProposal` 实例，并说明该赛道最核心的 **1 项行业安全护栏** 是什么。

### 参考答案（以“企业财报分析系统”为例）：
```python
from zhishu_agent import TechnicalProposal, review_proposal

proposal = TechnicalProposal(
    project_title="智枢·上市公司财报智能投研系统",
    author="陈默",
    topic_name="企业财报分析系统",
    problem_statement="解决投研人员手工翻阅百页年报、跨公司财务口径对齐耗时且易算错的痛点。",
    target_users=["行业研究员", "企业财务分析师"],
    knowledge_sources=["A股/港股上市公司年报 PDF", "企业会计准则与财务指标口径词典"],
    chunking_strategy="财报表格转 Markdown/JSON 结构化解析 + 按章节父子索引混合检索",
    embedding_model="BAAI/bge-m3 + BAAI/bge-reranker-v2-m3",
    agent_framework="LangGraph Stateful Multi-Agent",
    tools=["sec_filing_parser", "financial_ratio_calc", "chart_data_exporter"],
    memory_strategy="Redis 会话上下文 + PostgreSQL Checkpointer 多轮对比状态持久化",
    guardrails=[
        "所有财务比率与同比/环比数值计算强制交由 Python 工具执行，严禁 LLM 心算",
        "输出末尾自动附加非投资建议合规免责声明",
        "接入 ComplianceGateway 防止内部敏感研报数据外泄",
    ],
    eval_metrics=["财务指标抽取 F1 >= 0.92", "数值计算零误差率 100%", "RAGAS Faithfulness >= 0.90"],
    model_serving="vLLM + Qwen2.5-7B-Instruct-AWQ",
    deployment_stack=["FastAPI", "Docker Compose", "Qdrant", "Redis", "Prometheus"],
    budget_limit_cny=80.0,
)

res = review_proposal(proposal)
assert res.status == "APPROVED"
assert res.overall_score == 100
print(res.summary)
```
**核心行业安全护栏说明**：
金融财报分析场景对数值准确性零容忍。核心护栏是 **“计算与推理分离”**——LLM 仅负责意图理解、指标定位与归因总结，所有加减乘除、同比环比及财务比率计算必须强制路由至 `financial_ratio_calc`（Python 沙箱/确定性函数）执行，同时在输出层附带“仅供参考，不构成投资建议”的合规声明。

---

## 作业二：诊断并修复一份被拦截的残缺技术方案
**题目**：某同学提交了如下开题提案，请预测 `review_proposal()` 的返回状态、缺失维度，并解释为什么在工程上不能让该提案直接进入开发阶段：
```python
draft = TechnicalProposal(
    project_title="极速医疗问答",
    author="小李",
    topic_name="医疗健康科普助手",
    problem_statement="回答患者常见病症问题",
    knowledge_sources=["百度百科医疗词条"],
    chunking_strategy="固定 500 字切分",
    embedding_model="bge-small-zh",
    agent_framework="ReAct",
    tools=["web_search"],
    memory_strategy="InMemory",
)
```

### 参考答案：
1. **评审结果预测**：
   - `overall_score` 为 **50/100**（RAG 25 分 + Agent 25 分 + Guardrails 0 分 + Deployment 0 分）。
   - `status` 为 **`NEEDS_REVISION`**，存在两条阻塞项：`[Guardrails] 缺少 guardrails, eval_metrics` 与 `[Deployment] 缺少 model_serving, deployment_stack, budget_limit_cny`。
2. **深层工程隐患分析（为什么不能直接立项）**：
   - **医疗合规红线缺失**：医疗健康科普助手若无“严禁下达临床诊断/开具处方”与“急重症红旗症状（如胸痛、呼吸困难）立即提示拨打 120”的护栏，极易产生严重安全事故。
   - **数据源权威性不足**：`百度百科` 属于非权威 UGC 语料，应替换为卫健委临床指南或权威医学教材，并配合 `RAGAS Faithfulness` 评测忠实度。
   - **生产部署与成本失控风险**：缺少 `vLLM`/推理方案、容器编排栈与 `budget_limit_cny` 日预算熔断，项目最终只能停留在本地脚本阶段，无法完成 Stage 5/6 要求的私有化交付。

---

## 作业三：设计你自己的 1-on-1 架构评审检查清单（Checklist）
**题目**：在 Day 58 的 1-on-1 评审中，导师通常会围绕“数据源可信度、工具边界、兜底降级、成本可观测”四个问题追问。请结合你选定的赛道，为每个问题写出 1 条可落地的验证标准。

### 参考答案：
1. **数据源可信度**：所有入库文档必须携带 `source_id`、`publish_date` 与 `section` 元数据，回答中必须输出可点击或可核验的原文引用片段。
2. **工具边界**：为每个工具定义严格的 Pydantic 入参 Schema 与超时/重试策略（如 `timeout=5s, max_retries=2`），写操作或高风险操作需人工确认（Human-in-the-Loop）。
3. **兜底降级**：当检索相关性得分（Reranker Score）低于阈值（如 `0.35`）或外部工具超时时，触发确定性拒答模板或转人工工单，严禁模型“硬编”答案。
4. **成本可观测**：接入 Day 57 的 `ComplianceGateway` 与 `CostBudgetMonitor`，为每个租户设置日预算上限，并记录每次请求的 Token 消耗与 P95 延迟。
