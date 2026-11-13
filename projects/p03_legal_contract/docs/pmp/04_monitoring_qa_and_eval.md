# 04 Monitoring: QA, Evaluation & Governance

## 1. Automated Verification Strategy
All components are verified 100% offline via `pytest` (`projects/p03_legal_contract/tests/test_p03_legal.py`) using `tmp_path` isolation and FastAPI `TestClient`:
- **Ontology Unit Tests**: Verify deterministic clause risk classification (`critical`/`high`/`medium`/`low`), liability cap extraction, and regulation mapping.
- **LLM Wiki Tests**: Verify `ingest()`, `query()`, `index.md`, `log.md`, `entities/<id>.md` (`[[wiki_links]]`), and `lint()` detection of:
  1. Superseded regulations (`EU-DPD-95/46/EC`)
  2. Unlinked clauses (no matched regulations)
  3. Conflicting liability caps (e.g., `$500,000` vs `unlimited` or `$100,000`)
- **FDE Pipeline & HITL Tests**: Verify PII redaction counts, redline suggestions, pending `LegalAction` creation, General Counsel approval/rejection, and audit trail completeness.
- **API & Middleware Tests**: Verify `/health`, `/ready`, `/metrics`, `X-Request-ID` propagation, and end-to-end `/api/v1/*` flows.

## 2. Continuous Wiki Governance (`lint()`)
Legal Ops should run `GET /api/v1/wiki/lint` on a scheduled cadence and after every bulk ingestion to ensure zero unresolved `superseded_regulations`, `unlinked_clauses`, or `conflicting_liability_caps`.
