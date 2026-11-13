# Day 61 课后作业与参考答案（毕业设计开发日 3）

## 作业一：多工具协同与财务风险信号联动 RAG 检索
**题目**：在企业经营分析场景中，如果用户仅输入一句“帮我评估星辰制造科技 2026Q3 财报风险”，RAG 检索器往往无法直接命中“高杠杆预警”或“短期偿债压力”等专业风控文档。请结合 `CapstoneAgentOrchestrator.run()` 的实现，说明如何通过**工具结果驱动二次查询扩展（Tool-Driven Query Expansion）**来提升 RAG 召回准确率，并给出基于 `FinancialRatioTool` 与 `RAGSearchTool` 的联动代码。

### 参考答案：
1. **核心设计思路**：
   - 先调用 `FinancialRatioTool.calculate(metrics)` 计算量化比率并提取 `risk_flags`（如 `"高杠杆预警：资产负债率 82.5% >= 70%"`、`"短期偿债压力：流动比率 0.89 < 1.2"`）。
   - 将量化工具产出的 `risk_flags` 拼接到 `sanitized_query` 后再送入 `RAGSearchTool.search()`，使检索 query 自动携带“高杠杆”“流动比率”等高区分度领域词，从而精准召回 `DOC-RISK-001` 等风控指引。
2. **联动示例**：
   ```python
   from zhishu_agent import FinancialMetricsInput, FinancialRatioTool, RAGSearchTool

   fin_tool = FinancialRatioTool()
   rag_tool = RAGSearchTool()

   metrics = FinancialMetricsInput(
       company_name="星辰制造科技",
       period="2026Q3",
       revenue=10000.0,
       net_profit=200.0,
       total_assets=20000.0,
       total_liabilities=16500.0,
       shareholders_equity=3500.0,
       current_assets=4000.0,
       current_liabilities=4500.0,
   )
   fin_res = fin_tool.calculate(metrics)
   expanded_query = f"财报风险评估 {' '.join(fin_res.risk_flags)}"
   hits = rag_tool.search(expanded_query, top_k=2)
   assert hits[0].doc_id == "DOC-RISK-001"
   ```

---

## 作业二：SQLite 持久化记忆与 PII 脱敏落盘顺序设计
**题目**：某同学在开发智能体时，选择“先把用户原始提问写入 SQLite，等模型回复时再做 PII 脱敏”。请指出这种设计存在的安全隐患，并说明 `CapstoneAgentOrchestrator` 是如何通过“先脱敏、后落库”以及跨实例恢复来保障合规与持久化的。

### 参考答案：
1. **安全隐患**：
   - **明文落盘违反合规红线**：用户的手机号、身份证号、银行卡号及 `sk-...` 密钥会以明文形式永久保存在 SQLite 数据库文件与 WAL 日志中，一旦数据库备份或日志被导出，即构成 PII 泄漏事故。
   - **历史上下文污染**：后续轮次读取历史记忆拼接 Prompt 时，仍会把明文 PII 再次送入大模型或外部工具。
2. **`CapstoneAgentOrchestrator` 正确实践**：
   - 在 `run()` 入口第一时间调用 `self.compliance_guard.redact(user_query)` 得到 `sanitized_query`，**仅将脱敏后的文本写入 `conversation_messages` 表**。
   - 在生成高管报告草稿后再次执行 `self.compliance_guard.redact(draft)` 双重兜底。
   - 持久化存储于 `SQLiteMemoryStore` 后，即使销毁旧的 `CapstoneAgentOrchestrator` 对象并用新实例连接同一 `db_path`，`memory.get_history(session_id)` 仍可完整读取历史上下文。

---

## 作业三：HITL（Human-in-the-Loop）检查点状态机与幂等性保护
**题目**：为什么高管风险报告的自动发布流程必须引入 HITL 中断/恢复机制？如果在审批通过后，前端因为网络超时重试调用了两次 `resume(approval_id, approved=True, ...)`，系统应该如何处理？请写出完整的验证测试逻辑。

### 参考答案：
1. **引入 HITL 的工程必要性**：
   - 高管风险报告一旦对外发布或归档，具有法律与经营决策约束力；大模型或规则工具可能存在口径误判，因此必须由具备权责的人类专家（风控总监/财务总监）在发布前进行最终确认（`PENDING_APPROVAL -> APPROVED / REJECTED`）。
2. **重复调用（幂等性/防重）处理**：
   - `resume()` 在更新数据库前会校验 `checkpoint.status == ApprovalStatus.PENDING_APPROVAL`。
   - 第二次重试调用时，由于检查点状态已变更为 `APPROVED`（或 `REJECTED`），系统会立即抛出 `ValueError("审批检查点 ... 当前状态为 approved，无法重复审批")`，同时数据库 `published_reports` 表对 `approval_id` 设有 `UNIQUE` 约束，形成双层防重保护。
3. **验证测试逻辑**：
   ```python
   import pytest
   from zhishu_agent import ApprovalStatus, CapstoneAgentOrchestrator

   agent = CapstoneAgentOrchestrator(db_path=tmp_path / "hitl.db")
   pause = agent.run("sess-1", "发布风控报告", require_report_publish=True)
   assert pause.status == ApprovalStatus.PENDING_APPROVAL

   res1 = agent.resume(pause.approval_id, approved=True, reviewer="王总监")
   assert res1.status == ApprovalStatus.APPROVED

   with pytest.raises(ValueError, match="无法重复审批"):
       agent.resume(pause.approval_id, approved=True, reviewer="王总监")
   ```
