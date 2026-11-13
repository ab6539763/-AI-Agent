# 03. 项目执行：FDE 前线部署工程与 API 交付

## 1. FDE 五步交付闭环实施
1. **Shadowing & Discovery**：锁定高频缺货 SKU（如 `SKU-1001`）与季节性需求激增场景（`seasonality_factor >= 1.2`）。
2. **Ontology & Data Mapping**：在 `app/ontology.py` 中通过 Pydantic v2 固化 `SKU`、`Warehouse`、`Supplier`、`DemandForecast`、`SupplyLink`、`SupplyAction` 及 `RetailOntologyRegistry`。
3. **Rapid Vertical Slice**：打通 `RetailLLMWiki`（`ingest` / `query` / `lint`）与 `RetailFDEPipeline`（异常检测 → 补货推理 → 毛利护栏 → HITL 审批 → 审计）。
4. **Production Hardening**：
   - `app/api.py` 注入 `X-Request-ID` 链路追踪中间件与请求计数/延迟统计。
   - `Dockerfile` 采用 `python:3.12-slim` 多阶段构建、非 root 用户 `appuser`（UID 10001）与 `HEALTHCHECK`。
5. **Handover**：输出 `.env.example`、`docker-compose.yml` 与全套运维文档。

## 2. 核心 API 契约
| 方法与路径 | 说明 |
| :--- | :--- |
| `GET /health` | 存活探针，返回 `{"status": "ok"}` |
| `GET /ready` | 就绪探针，返回已加载 SKU/仓库/供应商与 Wiki 页面数 |
| `GET /metrics` | 可观测指标（请求数、延迟、待审批 HITL 数、缺货风险数、审计事件数） |
| `POST /api/v1/wiki/ingest` | 增量编译文档至 `RetailLLMWiki` 并更新 `index.md` 与 `log.md` |
| `GET /api/v1/wiki/lint` | 巡检缺货风险、冲突促销规则、孤立 SKU 与断链 |
| `GET /api/v1/ontology/inventory` | 查询全量或指定 SKU 的安全库存与交期检查结果 |
| `POST /api/v1/supply/replenish` | 执行 FDE 补货/调价推理与毛利/HITL 门禁 |
| `POST /api/v1/actions/approve` | 买手对 `PENDING_APPROVAL` 动作执行批准或驳回 |
