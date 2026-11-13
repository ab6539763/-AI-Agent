# 03 - Executing: FDE Delivery & Guardrail Architecture

## 1. End-to-End FDE Execution Flow
1. **Ingress & Sanitization**: Every incident symptom or operator comment passes through `redact_secrets()` before hitting the wiki, ontology correlation, or audit log.
2. **Graph & Wiki Correlation**:
   - `DevSecOpsOntologyRegistry.compute_blast_radius()` performs BFS over reverse `DependencyLink` edges to identify all upstream impacted services and `tier-0` exposure.
   - `DevSecOpsOntologyRegistry.evaluate_cvss_gate()` checks for unpatched CVEs with `cvss_score >= 9.0`.
   - `DevSecOpsLLMWiki.query()` retrieves relevant runbooks, historical incidents, and CVE pages.
3. **HITL Execution Gate**:
   - Destructive production actions (`rollback`, `quarantine` in `prod` or on `tier-0` services) are created in `PENDING_APPROVAL` state with `requires_hitl = True`.
   - Non-destructive actions (e.g., `notify`) or staging actions execute immediately (`EXECUTED`).
4. **SRE Approval & Audit Trail**:
   - `approve_action()` transitions `PENDING_APPROVAL` to `EXECUTED` (if approved) or `REJECTED`, recording `approved_by`, `decided_at`, and an immutable `audit_trail` entry.

## 2. API Surface Summary
| Method & Path | Purpose |
| :--- | :--- |
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe with ontology counts |
| `GET /metrics` | Request counts, latency, pending HITL actions |
| `POST /api/v1/wiki/ingest` | Ingest Markdown entity page with `[[wiki_links]]` |
| `GET /api/v1/wiki/lint` | Detect missing runbooks, unpatched critical CVEs, stale postmortems |
| `GET /api/v1/ontology/blast-radius` | Compute upstream blast radius and CVSS gate |
| `POST /api/v1/incidents/triage` | Run FDE triage with secret redaction and HITL gating |
| `POST /api/v1/actions/approve` | SRE approval/rejection of pending HITL action |
