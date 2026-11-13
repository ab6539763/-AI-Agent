# 03 — Executing: FDE Delivery & Safety Architecture

## 1. End-to-End FDE Pipeline Flow
Every clinical request traverses `HealthcareFDEPipeline.triage_case()` in deterministic stages:

1. **PHI De-identification (`deidentify_phi`)**:
   - Masks `SSN`, `EMAIL`, `MRN`, `PHONE`, `DATE`, and `Patient/Name/姓名` prefixes before clinical notes or complaints are persisted or logged.
2. **Red-Flag Emergency Triage**:
   - Evaluates `Symptom.is_red_flag`, `Symptom.severity == "critical"`, and vital sign thresholds (`spo2 < 90`, `sbp < 90`, `hr > 130` or `< 40`, `temp_c >= 40.0`).
   - Automatically escalates to `triage_level = "emergency"` and `risk_level = "critical"`.
3. **Wiki Knowledge Grounding**:
   - Queries `ClinicalLLMWiki` (`entities/*.md`) using token overlap across title, metadata, and body to surface cited guidelines.
4. **Ontology Constraint Guardrail**:
   - Invokes `ClinicalOntologyRegistry.evaluate_action_constraints()` to detect:
     - Drug-drug interactions (e.g., `warfarin` + `ibuprofen` -> `contraindicated` / `blocked=True`).
     - Allergy cross-reactivity (e.g., `penicillin` allergy vs `amoxicillin`).
     - Condition contraindications (e.g., `peptic_ulcer` vs `aspirin`).
5. **HITL Physician Sign-Off & Audit Trail**:
   - Generates a `ClinicalAction` (`pending_review` or `blocked`) requiring explicit `approve_action(action_id, physician_id, decision, notes)`.
   - Appends immutable JSONL events (`CLINICAL_TRIAGE`, `HITL_SIGNOFF`) to the audit log.

## 2. Production API Surface
- `GET /health`: Liveness probe.
- `GET /ready`: Readiness probe reporting ontology & wiki counts.
- `GET /metrics`: Request, ingest, lint, interaction, block, triage, and HITL counters.
- `POST /api/v1/wiki/ingest`: Persist Markdown entity with `[[wiki_links]]` and update `index.md` / `log.md`.
- `GET /api/v1/wiki/lint`: Audit wiki for conflicting dosages, orphan conditions, and missing citations.
- `POST /api/v1/ontology/check-interaction`: Standalone drug/allergy/condition constraint check.
- `POST /api/v1/clinical/triage`: Full FDE triage + guardrail execution.
- `POST /api/v1/actions/approve`: Physician HITL sign-off endpoint.
- Middleware: `X-Request-ID` correlation header propagated on every HTTP response.
