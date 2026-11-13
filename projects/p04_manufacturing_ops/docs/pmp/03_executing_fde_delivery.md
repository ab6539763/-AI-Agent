# 03. Executing: FDE Delivery & Architecture

## 1. End-to-End Execution Flow
1. **Telemetry Ingestion**: Edge IoT gateway posts equipment readings to `POST /api/v1/ops/incident`.
2. **Deterministic Diagnosis**: `ManufacturingOntologyRegistry.diagnose()` evaluates each metric against `TelemetryThreshold` (`warn` / `critical`) and resolves triggered `FaultCode`s to `MaintenanceSOP`s.
3. **Wiki Context & Persistence**: `ManufacturingFDEPipeline` queries `ManufacturingLLMWiki` for historical/procedural context and ingests an `Incident` page (`entities/INC-*.md`) linked via `[[wiki_links]]`.
4. **HITL Safety Gate**:
   - If `requires_shutdown=True`, an `OpsAction` (`EMERGENCY_SHUTDOWN`) is created in `PENDING_APPROVAL` state.
   - Equipment transitions to `FAULTED` immediately, and only transitions to `SHUTDOWN` once a safety officer calls `POST /api/v1/actions/approve` with `approved=true`.
   - Non-shutdown warnings issue an automated `CREATE_WORK_ORDER` action.

## 2. API Surface Summary
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/health` | `GET` | Liveness probe |
| `/ready` | `GET` | Readiness probe (verifies Wiki & Ontology) |
| `/metrics` | `GET` | Operational counters & HITL queue depth |
| `/api/v1/wiki/ingest` | `POST` | Ingest/update Markdown entity in Wiki |
| `/api/v1/wiki/lint` | `GET`/`POST` | Detect unmapped faults, outdated SOPs, orphan equipment |
| `/api/v1/ontology/diagnose` | `POST` | Run telemetry threshold & fault-to-SOP diagnosis |
| `/api/v1/ops/incident` | `POST` | Execute full FDE pipeline for an equipment incident |
| `/api/v1/actions/approve` | `POST` | Safety-officer HITL approval/rejection |
