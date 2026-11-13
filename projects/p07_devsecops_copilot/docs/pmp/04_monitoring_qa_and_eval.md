# 04 - Monitoring, QA & Evaluation

## 1. Automated Verification Strategy
All components are verified 100% offline using `pytest` and FastAPI `TestClient` with isolated `tmp_path` directories:
1. **Ontology Blast-Radius & CVSS Gating**: Verifies multi-hop upstream propagation, `tier-0` detection, and `BLOCK_DEPLOY` when unpatched CVSS >= 9.0.
2. **LLM Wiki Ingest, Query & Lint**: Verifies `index.md`, `log.md`, and `entities/<id>.md` persistence, `[[wiki_links]]` resolution, and detection of missing runbooks, unpatched critical CVEs, and stale postmortems.
3. **Secret Redaction Guardrail**: Verifies deterministic redaction of `sk-...`, `ghp_...`, `AKIA...`, `Bearer ...`, and `password=...` tokens.
4. **HITL SRE Approval Gate**: Verifies production `rollback`/`quarantine` enters `PENDING_APPROVAL`, blocks auto-execution, and transitions to `EXECUTED` or `REJECTED` with audit trail entries upon SRE decision.
5. **FastAPI Production Endpoints & Middleware**: Verifies `/health`, `/ready`, `/metrics`, `X-Request-ID` header propagation, and all `/api/v1/...` routes.

## 2. Observability Metrics
- `requests_total`: Total HTTP requests served.
- `last_latency_ms`: Most recent request processing latency in milliseconds.
- `actions_pending_hitl`: Number of production actions awaiting SRE approval.
- `audit_events_total`: Total immutable audit records generated.
