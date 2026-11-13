# 04 — Monitoring, QA & Offline Evaluation

## 1. Deterministic QA Strategy
All verification runs 100% offline with zero external API calls using `pytest` and FastAPI `TestClient` with `tmp_path` isolation:

| Test Area | Verification Objective |
| --- | --- |
| Clinical Ontology | Verify `warfarin + ibuprofen` blocks, `warfarin + aspirin` warns major, `penicillin` allergy blocks `amoxicillin` |
| LLM Wiki Ingest & Query | Verify `entities/<id>.md`, `[[wiki_links]]`, `index.md`, `log.md`, and ranked `query()` retrieval |
| LLM Wiki Lint | Verify detection of `conflicting_dosage_guidelines`, `orphan_conditions`, and `missing_citations` |
| PHI De-identification | Verify SSN, phone, email, MRN, date, and patient name masking in complaints, notes, and audit logs |
| Emergency Triage & HITL | Verify red-flag escalation (`chest_pain`, hypoxia), HITL `approved`/`rejected` sign-off, and JSONL audit trail |
| FastAPI Production Endpoints | Verify `/health`, `/ready`, `/metrics`, `/api/v1/*`, and `X-Request-ID` header propagation |

## 2. Runtime Observability
- **Request Correlation**: Every HTTP request is assigned or echoes `X-Request-ID`.
- **Operational Metrics (`/metrics`)**:
  - `requests_total`
  - `wiki_ingests_total`
  - `wiki_lints_total`
  - `interaction_checks_total`
  - `blocked_interactions_total`
  - `triage_total`
  - `hitl_approvals_total`
- **Compliance Audit Trail**: JSONL log (`P02_AUDIT_LOG_PATH`) records `CLINICAL_TRIAGE` and `HITL_SIGNOFF` events with de-identified notes only.
