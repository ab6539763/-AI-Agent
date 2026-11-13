# 05 — Closing: Handover & Operational Runbook

## 1. Handover Checklist
- [x] `app/ontology.py`: Clinical Ontology models & `ClinicalOntologyRegistry`
- [x] `app/llm_wiki.py`: `ClinicalLLMWiki` (`ingest`, `query`, `lint`, `index.md`, `log.md`, `entities/*.md`)
- [x] `app/fde_pipeline.py`: `HealthcareFDEPipeline` (PHI masking, emergency triage, guardrails, HITL, JSONL audit)
- [x] `app/api.py`: FastAPI service (`create_app()`, `app`, `X-Request-ID` middleware)
- [x] `Dockerfile` (multi-stage, non-root `appuser`, `HEALTHCHECK`), `docker-compose.yml`, `.env.example`, `main.py`
- [x] `tests/test_p02_healthcare.py`: 100% passing offline pytest suite

## 2. Local & Container Startup
### Local Python Virtualenv
```bash
PYTHONPATH=projects/p02_healthcare_copilot .venv/bin/python projects/p02_healthcare_copilot/main.py
```

### Docker Compose
```bash
cd projects/p02_healthcare_copilot
docker compose up --build -d
curl -s http://localhost:8000/health
```

## 3. Incident Response Runbook
| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `/ready` returns non-200 or `wiki_entities == 0` | Empty `P02_WIKI_DIR` volume on first boot | Ingest baseline clinical guidelines via `POST /api/v1/wiki/ingest` |
| `GET /api/v1/wiki/lint` reports `issues_found` | Conflicting dosage, broken `[[wiki_link]]`, or missing citation | Review `issues[]` in lint output; update offending entity via `ingest()` |
| High `blocked_interactions_total` spike | Unsafe medication combinations proposed | Inspect `audit.jsonl` `CLINICAL_TRIAGE` events and review clinical order templates |
| `404 Unknown action_id` on `/api/v1/actions/approve` | Service restarted (in-memory action store cleared) | Re-run `/api/v1/clinical/triage` to generate a fresh `action_id` |
