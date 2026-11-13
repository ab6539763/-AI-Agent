# 04 监控阶段：QA 门禁、一致性与成本监控

## 1. QA 自动化测试门禁 (Quality Gates)

所有交付代码必须通过 `pytest` 全量测试套件（`tests/test_p01_fintech.py`）：

| 测试维度 | 验证内容 | 目标通过率 |
| --- | --- | --- |
| **Ontology 校验与遍历** | 非法评级/非法边 Schema 拦截、BFS 图谱遍历、HITL 角色与严重度前置检查 | 100% |
| **LLM Wiki 引擎** | `index.md`/`log.md`/`entities/<id>.md` 持久化、跨文档指标冲突检测、孤立页与过期页 Lint | 100% |
| **FDE 护栏与比率工具** | PII（手机号/身份证/邮箱）自动脱敏、MNPI 内幕交易请求阻断、财务比率阈值触发风控 | 100% |
| **FastAPI 端到端** | `TestClient` 覆盖全部 8 个端点、`X-Request-ID` 透传、400/403/404 结构化错误 | 100% |

---

## 2. 数据一致性监控

- **Wiki 巡检 (`GET /api/v1/wiki/lint`)**：定期检查 `conflicting_metrics`（同实体同周期指标冲突）、`broken_links`（断链）与 `stale_entries`（超过 90 天未更新条目）。
- **审计追踪 (`audit_trail.jsonl`)**：每次入库、查询、护栏拦截与 HITL 审批均写入不可变 JSONL 记录，包含 `event_id`、`timestamp` 与 `actor_role`。

---

## 3. 成本与性能监控 (FinOps)

- **零 Token 成本**：100% 离线确定性架构，无需调用外部商业大模型 API，单次查询外部 Token 成本为 `0`。
- **可观测性指标 (`GET /metrics`)**：实时暴露 `requests_total`、`wiki_ingests_total`、`research_queries_total`、`guardrail_blocks_total` 与 `actions_decided_total`。
