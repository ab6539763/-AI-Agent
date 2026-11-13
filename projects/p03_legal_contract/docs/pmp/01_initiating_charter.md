# 01 Initiating: Project Charter — P03 Legal Compliance & Contract Review Agent

## 1. Project Overview
- **Project Name**: P03 法律合规与合同审查智能体 (Legal Compliance & Contract Review Agent)
- **Sponsor**: General Counsel & Enterprise Risk Office
- **Execution Mode**: 100% Offline Deterministic Engine (Zero External API Dependencies)

## 2. Business Objectives
1. Automate first-pass clause extraction, risk scoring, and redline generation for commercial contracts (MSA, DPA, NDA, SaaS).
2. Map contract clauses deterministically to regulatory frameworks (`GDPR-Art28`, `PIPL-Art38`, `CCPA-1798.100`, `SOC2-CC6.1`, `CIVIL-CODE-584`) and flag superseded regulations (`EU-DPD-95/46/EC`).
3. Enforce PII/confidentiality masking before knowledge persistence and require Human-in-the-Loop (HITL) General Counsel sign-off for high/critical risk clauses.
4. Maintain an auditable, Markdown-based Legal LLM Wiki (`index.md`, `log.md`, `entities/<id>.md`) with `[[wiki_links]]` and automated `lint()` governance.

## 3. Scope & Boundaries
- **In Scope**: Legal Ontology Registry, Markdown LLM Wiki (`ingest`, `query`, `lint`), FDE Contract Review Pipeline, FastAPI service (`/health`, `/ready`, `/metrics`, `/api/v1/*`), containerized deployment, and pytest suite.
- **Out of Scope**: External LLM network calls, binding e-signature execution, court filing integrations.

## 4. Stakeholders & RACI
| Role | Responsibility |
| :--- | :--- |
| General Counsel | Final HITL approver for `high`/`critical` risk clauses |
| Legal Ops | Contract ingestion, wiki maintenance, lint triage |
| Forward-Deployed Engineer (FDE) | Ontology rules, PII masking, pipeline & API delivery |
| InfoSec / Compliance | Audit trail & PII redaction verification |
