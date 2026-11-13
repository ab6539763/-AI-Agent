# 04. 监控：质量保障与评估体系 (Monitoring: QA & Evaluation)

## 1. 离线确定性测试矩阵 (`tests/test_p06_govtech.py`)
所有验证均基于 `pytest` 与 FastAPI `TestClient` + `tmp_path` 隔离目录，不依赖任何外部网络或 API Key：
1. **本体多规则评估与部门路由测试**：验证高新技术企业满足全部 4 条规则时判定 `eligible=True` 并路由至 `市科学技术局`；当营收或员工数不达标时精确指出 `failed_rules`。
2. **LLM Wiki 持久化与检索测试**：验证 `ingest()` 生成 `index.md`、`log.md` 与 `entities/<id>.md`（含 `[[wiki_links]]`），且 `query()` 能准确召回政策条款。
3. **Wiki Lint 巡检测试**：构造过期政策、同项目冲突补贴上限、孤立规则/悬空链接，验证 `lint()` 全部检出并标记 `healthy=False`。
4. **PII 脱敏与无依据拒答测试**：输入包含身份证号、USCC 与手机号的提问，验证输出 `masked_question` 无明文敏感信息；对虚构补贴诉求返回 `status="refused"`。
5. **HITL 签批与审计追溯测试**：验证高额补贴自动生成 `pending_approval` 动作，经办人签批后状态变为 `approved`，且 `audit_trail` 完整记录各阶段事件。
6. **FastAPI 全端点与 `X-Request-ID` 中间件测试**：覆盖 `/health`、`/ready`、`/metrics` 及全部 `/api/v1/*` 接口。

## 2. 线上可观测性指标 (`/metrics`)
- `requests_total`：HTTP 请求总量（配合 `X-Request-ID` 链路追踪）。
- `policy_asks_total` / `policy_refusals_total`：问答总量与拒答率监控（异常飙升提示知识库缺口）。
- `hitl_pending` / `hitl_approved`：人工复核积压与处理吞吐监控。
- `wiki_lints_total`：知识库定期巡检执行次数。
