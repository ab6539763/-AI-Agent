# 05 收尾阶段：验收报告、运维 Runbook 与移交清单

## 1. 项目验收报告 (Acceptance Report)

- **功能验收**：Ontology、LLM Wiki、FDE Pipeline 与 FastAPI 接口全部按契约实现，离线确定性运行通过。
- **安全与合规验收**：PII 自动脱敏、MNPI 请求阻断、HITL 合规官双人复核前置条件校验均已验证。
- **测试验收**：`pytest projects/p01_fintech_research/tests -v` 100% 通过。

---

## 2. 运维 Runbook (Operations Runbook)

### 本地启动与验证
```bash
# 1. 运行离线 CLI 演示
.venv/bin/python projects/p01_fintech_research/main.py --mode demo

# 2. 启动 HTTP 服务
PYTHONPATH=projects/p01_fintech_research .venv/bin/python projects/p01_fintech_research/main.py --mode serve --port 8000

# 3. 健康与就绪检查
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

### 常见故障排查
1. **403 Forbidden (HITL 审批失败)**：检查调用方 `actor_role` 是否为 `compliance_officer` / `chief_risk_officer` / `admin`，且发行人存在满足 `min_severity` 的 `RiskSignal`。
2. **Wiki Lint 报告 `conflicting_metrics`**：核对 `wiki/entities/<id>.md` 中 `## Observations` 的 `doc_id`，确认最新权威财报后重新入库修正。

---

## 3. 移交清单 (Handover Checklist)

- [x] 核心源码：`app/ontology.py`, `app/llm_wiki.py`, `app/fde_pipeline.py`, `app/api.py`
- [x] 启动与容器化：`main.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`
- [x] 自动化测试：`tests/test_p01_fintech.py`
- [x] PMP 全生命周期文档：`docs/pmp/01_*.md` 至 `05_*.md`
