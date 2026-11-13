# 01 - Project Charter (Initiating): P07 Enterprise R&D Efficiency & DevSecOps Copilot

## 1. Project Overview
- **Project Name**: Project P07 — 企业研发效能与 DevSecOps 智能体 (Enterprise R&D Efficiency & DevSecOps Copilot)
- **Sponsor**: VP of Engineering & CISO
- **Delivery Lead**: Forward Deployed Engineer (FDE) & Platform SRE Team
- **Mode**: 100% Offline Deterministic Execution (Zero External API Keys)

## 2. Business Case & Problem Statement
Modern microservice architectures suffer from:
1. **Fragmented Dependency Visibility**: Incident responders struggle to assess upstream/downstream blast radius during SEV-1/SEV-2 outages.
2. **Unchecked Vulnerability Drift**: Critical CVEs (CVSS >= 9.0) are not systematically gated against production deployments.
3. **Stale Operational Knowledge**: Runbooks and postmortems decay without automated wiki linting, and sensitive credentials occasionally leak into incident tickets.

## 3. Objectives & Success Criteria
- **Ontology Graph**: Model `Service`, `CVE`, `Incident`, `Runbook`, `DependencyLink`, and `OpsAction` with deterministic BFS blast-radius traversal and CVSS severity gating.
- **Persistent LLM Wiki**: Maintain Markdown knowledge (`index.md`, `log.md`, `entities/<id>.md`) with `[[wiki_links]]`, supporting `ingest()`, `query()`, and `lint()`.
- **FDE Guardrailed Pipeline**: Enforce secret/token redaction on all incident symptoms and Human-in-the-Loop (HITL) SRE approval for production `rollback`/`quarantine` actions with full audit trail.
- **Production API & Packaging**: FastAPI service with `/health`, `/ready`, `/metrics`, `X-Request-ID` tracing, multi-stage non-root `Dockerfile`, and 100% passing pytest suite.

## 4. Stakeholders
| Role | Responsibility |
| :--- | :--- |
| **Platform SRE** | Approves/rejects production HITL rollback/quarantine actions; maintains runbooks |
| **AppSec Team** | Monitors CVSS >= 9.0 gating policies and CVE remediation SLAs |
| **FDE Copilot** | Executes deterministic triage, blast-radius analysis, and wiki synchronization |
| **Engineering Leads** | Reviews wiki lint reports for missing runbooks and stale postmortems |
