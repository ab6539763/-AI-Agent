# 05 - Closing: Handover & Operational Runbook

## 1. Local & Container Deployment
### Local Run
```bash
.venv/bin/uvicorn projects.p07_devsecops_copilot.app.api:app --host 0.0.0.0 --port 8080
```
### Docker Compose
```bash
cd projects/p07_devsecops_copilot
docker compose up --build -d
```

## 2. SRE Operational Runbook
- **Liveness / Readiness Failure**: Check `GET /health` and `GET /ready`. Verify `P07_WIKI_DIR` is writable by non-root user `devsecops` (UID `10001`).
- **Pending HITL Backlog**: Query `GET /metrics` and inspect `actions_pending_hitl`. Review pending actions and submit decisions via `POST /api/v1/actions/approve`.
- **Wiki Hygiene Drift**: Schedule periodic calls to `GET /api/v1/wiki/lint` in CI/CD. Remediate any `services_without_runbooks`, `unpatched_critical_cves`, or `stale_postmortems` before release sign-off.

## 3. Handover Checklist
- [x] Ontology blast-radius traversal & CVSS gating implemented
- [x] Persistent Markdown LLM Wiki (`index.md`, `log.md`, `entities/*.md`) implemented
- [x] FDE secret redaction & HITL SRE approval gate implemented
- [x] Multi-stage non-root `Dockerfile` with `HEALTHCHECK` & `docker-compose.yml` ready
- [x] Full pytest suite passing 100%
