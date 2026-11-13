# 04. 项目监控：QA 质量门禁、本体一致性与评估报告

## 1. 质量门禁矩阵（QA Gate Matrix）
| 测试维度 | 验证方法 | 预期标准 |
| :--- | :--- | :--- |
| 本体安全库存与交期检查 | `RetailOntologyRegistry.check_safety_stock()` | 准确识别 `CRITICAL`/`WARNING`/`HEALTHY` 与 `lead_time_breach` |
| LLM Wiki 编译与溯源 | `ingest()` + `query()` | 持久化 `index.md`、`log.md`、`entities/*.md` 与 `[[wiki_links]]` |
| LLM Wiki 一致性巡检 | `lint()` | 检出缺货风险、冲突促销折扣/叠加规则、孤立 SKU |
| 毛利护栏 | `plan_replenishment(proposed_price=...)` | 低于 `min_margin_pct` 时返回 `BLOCKED` 并记录审计 |
| HITL 买手审批门禁 | `plan_replenishment()` + `approve_action()` | 大额 PO/大幅调价进入 `PENDING_APPROVAL`，批准后更新库存/价格 |
| FastAPI 生产接口 | `TestClient` + `tmp_path` | `/health` `/ready` `/metrics` `/api/v1/...` 全部 200 且返回 `X-Request-ID` |

## 2. 确定性与 FinOps 成本评估
- **LLM 推理成本**：本系统采用 100% 离线确定性规则与图谱检索引擎，推理成本为 `\$0.00 / 1K requests`，无外部 Token 消耗与网络抖动。
- **P95 延迟**：本地内存本体检索与 Markdown 持久化响应延迟 `< 15ms`。
