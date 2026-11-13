# 03 执行阶段：FDE 交付、API 契约与 Docker 部署

## 1. FDE 交付组件清单

| 模块 | 文件路径 | 核心职责 |
| --- | --- | --- |
| 本体引擎 | `app/ontology.py` | 实体建模、边 Schema 约束、BFS 遍历、HITL 前置条件校验 |
| 知识库引擎 | `app/llm_wiki.py` | Markdown 持久化、`[[wiki_links]]` 解析、冲突与过期 Lint |
| 生产流水线 | `app/fde_pipeline.py` | 财务比率计算、PII/MNPI 护栏、HITL 队列、JSONL 审计 |
| HTTP 服务 | `app/api.py` | FastAPI 工厂 `create_app()`、`X-Request-ID`、结构化异常 |
| 启动入口 | `main.py` | `--mode demo` 离线演示 / `--mode serve` Uvicorn 服务 |

---

## 2. REST API 契约 (API Contract)

| 方法与路径 | 说明 | 请求体 / 参数 | 响应要点 |
| --- | --- | --- | --- |
| `GET /health` | 存活探针 | 无 | `{"status": "ok"}` |
| `GET /ready` | 就绪探针 | 无 | `{"status": "ready", "issuers_count", "wiki_pages_count"}` |
| `GET /metrics` | 运行指标 | 无 | `requests_total`, `guardrail_blocks_total`, `audit_events` |
| `POST /api/v1/wiki/ingest` | 研报入库 | `doc_id, title, content, entities` | `pages_updated`, `links_created` |
| `GET /api/v1/wiki/lint` | 知识库巡检 | `?stale_days=90` | `orphan_pages`, `conflicting_metrics`, `stale_entries` |
| `GET /api/v1/ontology/graph` | 本体图谱 | `?issuer_id=...&max_depth=2` | `nodes`, `edges`, `summary` |
| `POST /api/v1/research/query` | 投研风控查询 | `question, issuer_id, financials` | `wiki`, `ratios`, `hitl_pending_action`, `audit_event_id` |
| `POST /api/v1/actions/approve` | HITL 审批 | `action_id, decision, actor_role, approver` | 更新后的 `ComplianceAction` 与审计 ID |

---

## 3. Docker 容器化部署

1. **安全基线**：`Dockerfile` 采用 `python:3.11-slim` 多阶段构建，创建非特权用户 `appuser` (UID `10001`) 运行进程。
2. **健康检查**：内置 `HEALTHCHECK` 每 30 秒探测 `http://127.0.0.1:8000/health`。
3. **编排启动**：
   ```bash
   docker compose up --build -d
   ```
