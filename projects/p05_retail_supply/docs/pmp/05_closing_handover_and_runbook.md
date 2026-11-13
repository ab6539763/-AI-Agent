# 05. 项目收尾：运维移交清单与应急 Runbook

## 1. 验收交付物清单
- [x] 核心代码：`app/ontology.py`、`app/llm_wiki.py`、`app/fde_pipeline.py`、`app/api.py`
- [x] 部署配置：`main.py`、`Dockerfile`、`docker-compose.yml`、`.env.example`
- [x] PMP 全周期文档：`docs/pmp/01_*.md` ~ `05_*.md`
- [x] 自动化测试：`tests/test_p05_retail.py`

## 2. 本地与容器启动命令
```bash
# 本地开发启动
.venv/bin/uvicorn projects.p05_retail_supply.app.api:app --host 0.0.0.0 --port 8005

# 运行自动化测试门禁
.venv/bin/python -m pytest projects/p05_retail_supply/tests -v

# Docker Compose 生产启动
docker compose -f projects/p05_retail_supply/docker-compose.yml up -d --build
```

## 3. 应急处理 Runbook
| 告警现象 | 排查步骤 | 恢复动作 |
| :--- | :--- | :--- |
| `/metrics` 中 `hitl_pending` 持续升高 | 查询待审批 `SupplyAction` 列表与买手审批队列 | 通知值班买手通过 `/api/v1/actions/approve` 审批或驳回 |
| `/api/v1/wiki/lint` 报告 `conflicting_promo_rules` | 查看 `wiki/entities/<id>.md` 与 `wiki/log.md` 变更来源 | 修正冲突促销文档并重新 `ingest` 覆盖 |
| `/api/v1/ontology/inventory` 出现 `CRITICAL` | 检查 `days_of_supply` 与 `lead_time_days` | 触发 `/api/v1/supply/replenish` 并走加急补货审批 |
