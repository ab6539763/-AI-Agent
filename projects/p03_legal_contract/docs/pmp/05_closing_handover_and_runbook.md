# 05 Closing: Handover & Operational Runbook

## 1. Local Execution
```bash
# Run offline self-check
.venv/bin/python projects/p03_legal_contract/main.py --check

# Start FastAPI service
PYTHONPATH=projects/p03_legal_contract .venv/bin/python projects/p03_legal_contract/main.py --host 0.0.0.0 --port 8000

# Run full test suite
.venv/bin/python -m pytest projects/p03_legal_contract/tests -v
```

## 2. Container Deployment
```bash
cd projects/p03_legal_contract
cp .env.example .env
docker compose up --build -d
```
- The container runs as non-root user `appuser` (`UID 10001`).
- Built-in `HEALTHCHECK` polls `http://127.0.0.1:8000/health` every 30s.

## 3. Incident & Audit Runbook
- **High-Risk Contract Blocked**: Inspect `pending_actions` from `/api/v1/contracts/review` and submit General Counsel decision via `POST /api/v1/actions/approve`.
- **Lint Failures**: Call `GET /api/v1/wiki/lint` to inspect `superseded_regulations`, `unlinked_clauses`, and `conflicting_liability_caps`, then re-ingest updated clauses.
- **Audit Inspection**: Review `log.md` in `WIKI_DIR` and `/metrics` for `pii_masked_total` and `audit_events_total`.
