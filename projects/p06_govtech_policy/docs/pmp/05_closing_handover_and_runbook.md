# 05. 收尾：交付清单与运维手册 (Closing: Handover & Runbook)

## 1. 交付物清单
- 应用核心：`projects/p06_govtech_policy/app/{__init__.py,ontology.py,llm_wiki.py,fde_pipeline.py,api.py}`
- 部署与入口：`projects/p06_govtech_policy/{main.py,Dockerfile,docker-compose.yml,.env.example}`
- PMP 全生命周期文档：`projects/p06_govtech_policy/docs/pmp/01..05.md`
- 自动化测试：`projects/p06_govtech_policy/tests/test_p06_govtech.py`

## 2. 本地与容器化运行指南 (Runbook)
### 本地开发启动
```bash
.venv/bin/python -m uvicorn projects.p06_govtech_policy.app.api:app --host 0.0.0.0 --port 8006
```
### 运行自动化测试
```bash
.venv/bin/python -m pytest projects/p06_govtech_policy/tests -v
```
### Docker Compose 部署
```bash
cd projects/p06_govtech_policy
cp .env.example .env
docker compose up -d --build
```

## 3. 日常运维 SOP
1. **每日知识库巡检**：定时调用 `POST /api/v1/wiki/lint`，若 `healthy=false`，优先处理 `conflicting_thresholds`（错误级）与 `expired_policies`（告警级）。
2. **HITL 工单积压处理**：关注 `/metrics` 中的 `hitl_pending`，督促对应部门经办人通过 `/api/v1/actions/approve` 完成签批。
3. **审计日志归档**：定期备份 `GOVTECH_DATA_DIR/audit.jsonl` 与 `GOVTECH_DATA_DIR/wiki/log.md` 以满足政务合规留痕要求。
