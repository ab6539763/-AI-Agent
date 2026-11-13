# 01. Initiating: Project Charter — P04 智能制造与工业设备运维智能体

## 1. Project Overview
- **Project Code**: P04-MFG-OPS
- **Project Name**: 智能制造与工业设备运维智能体 (Smart Manufacturing & Industrial Equipment Ops Agent)
- **Sponsor**: Plant Operations & Reliability Engineering
- **Delivery Mode**: 100% Offline Deterministic Runtime (No external LLM API keys required)

## 2. Business Objectives
1. **Zero Unplanned Critical Downtime**: Detect CNC spindle overheating, axis vibration spikes, and hydraulic pressure surges in real time via deterministic telemetry threshold rules.
2. **Traceable Root-Cause & SOP Retrieval**: Unify structured `ManufacturingOntologyRegistry` with a Markdown-persisted `ManufacturingLLMWiki` (`[[wiki_links]]`) so every alert maps to an auditable Standard Operating Procedure (SOP).
3. **Safety-First Human-in-the-Loop (HITL)**: Enforce mandatory safety-officer approval before executing `EMERGENCY_SHUTDOWN` actions on production equipment.

## 3. Scope & Boundaries
- **In Scope**:
  - Manufacturing Ontology (`Equipment`, `SensorAlert`, `FaultCode`, `MaintenanceSOP`, `OpsLink`, `OpsAction`).
  - File-backed LLM Wiki (`index.md`, `log.md`, `entities/<id>.md`) with `ingest()`, `query()`, and `lint()`.
  - FDE Pipeline with HITL approval gate and immutable audit trail.
  - Production FastAPI service (`/health`, `/ready`, `/metrics`, `/api/v1/*`) + Docker deployment.
- **Out of Scope**:
  - Direct PLC/OPC-UA hardware write-back without HITL gate.
  - Cloud-hosted external LLM inference.

## 4. Key Stakeholders
| Role | Responsibility |
| :--- | :--- |
| Plant Safety Officer | Approves or rejects `EMERGENCY_SHUTDOWN` HITL actions |
| Reliability Engineer | Maintains `FaultCode` -> `MaintenanceSOP` mappings and Wiki lint health |
| Forward-Deployed Engineer (FDE) | Delivers Ontology, Wiki, Pipeline, and FastAPI service |
| Shift Supervisor | Monitors equipment status (`OPERATIONAL`, `DEGRADED`, `FAULTED`, `SHUTDOWN`) |
