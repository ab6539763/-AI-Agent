# 04. Monitoring: QA, Lint Governance & Evaluation

## 1. Automated Verification Strategy
All verification runs 100% offline with `pytest` and FastAPI `TestClient` using isolated `tmp_path` directories:
- **Ontology Unit Tests**: Validate `check_telemetry()` warning/critical thresholds and `resolve_fault_to_sop()` accuracy.
- **LLM Wiki Persistence & Search**: Validate `index.md`, `log.md`, `entities/<id>.md`, and `[[wiki_links]]` extraction.
- **Wiki Lint Governance**: Inject unmapped fault codes, outdated SOP revisions (`v1.0` vs `v2.0`), and orphan equipment, confirming `lint()` flags all three categories.
- **HITL Safety Gate**: Verify `EMERGENCY_SHUTDOWN` remains `PENDING_APPROVAL` until approved by a safety officer, and verify rejection preserves equipment state without shutdown.
- **API & Middleware Contract**: Verify `X-Request-ID` propagation and all `/health`, `/ready`, `/metrics`, and `/api/v1/*` routes.

## 2. Continuous Knowledge Health Metrics
- `unmapped_fault_codes == 0`
- `outdated_sops == 0`
- `orphan_equipment == 0`
- `pending_hitl_actions` monitored via `GET /metrics`
