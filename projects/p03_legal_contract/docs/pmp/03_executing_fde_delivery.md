# 03 Executing: FDE Delivery & Architecture

## 1. End-to-End Execution Flow
1. **PII & Confidentiality Masking**: `LegalFDEPipeline.mask_pii()` redacts emails (`[EMAIL_REDACTED]`), SSNs (`[ID_REDACTED]`), IBAN/account numbers (`[ACCOUNT_REDACTED]`), and phone numbers (`[PHONE_REDACTED]`) prior to clause registration and wiki persistence.
2. **Clause Extraction & Classification**: `extract_clauses()` splits contract text into discrete clauses, runs `LegalOntologyRegistry.classify_clause_risk()`, extracts USD liability caps, and maps each clause to `Regulation` nodes.
3. **Redline & HITL Escalation**: Any clause scored `high` or `critical` automatically generates a pending `LegalAction` (`GENERAL_COUNSEL_APPROVAL`) and sets the contract status to `pending_gc_approval`.
4. **Markdown Wiki Sync**: `LegalLLMWiki` materializes `entities/<id>.md` with `[[wiki_links]]`, rebuilds `index.md`, and appends an immutable entry to `log.md`.
5. **General Counsel Decision**: `POST /api/v1/actions/approve` records `approved`/`rejected` decisions, updates contract status, and appends to both `audit_trail` and `log.md`.

## 2. API Contract Summary
- `GET /health` — Liveness probe
- `GET /ready` — Readiness probe (verifies wiki storage & seeded regulations)
- `GET /metrics` — Operational counters (`requests_total`, `contracts_reviewed`, `pii_masked_total`, `hitl_actions_pending`)
- `POST /api/v1/wiki/ingest` — Ingest contract, clause, or regulation into Markdown wiki
- `GET|POST /api/v1/wiki/lint` — Run wiki integrity & compliance lint
- `GET /api/v1/ontology/clauses` — Query registered clauses by `risk_level` or `contract_id`
- `POST /api/v1/contracts/review` — Execute full FDE contract review pipeline
- `POST /api/v1/actions/approve` — Submit General Counsel HITL approval/rejection
