# 01 — Project Charter: 医疗健康与临床辅助决策智能体 (P02 Healthcare Copilot)

## 1. Project Overview & Business Case
- **Project Code**: P02-HC-COPILOT
- **Domain**: Healthcare & Clinical Decision Support (CDS)
- **Sponsor**: Clinical Informatics & Patient Safety Committee
- **Objective**: Build a 100% offline-deterministic, auditable Clinical Decision Support Copilot that combines a formal Clinical Ontology, a Markdown-backed Clinical LLM Wiki, and a HIPAA-aligned Forward-Deployed Engineering (FDE) pipeline with mandatory Human-in-the-Loop (HITL) physician sign-off.

## 2. Success Criteria (Measurable KPIs)
| Metric | Target | Verification Method |
| --- | --- | --- |
| Drug-Interaction & Allergy Detection Recall | 100% on ontology rules | Pytest deterministic test suite |
| PHI / HIPAA Safe Harbor Masking | 100% of SSN/Phone/Email/MRN/Date/Name | Regex unit & integration tests |
| Red-Flag Emergency Escalation Latency | < 50 ms offline | FastAPI `TestClient` benchmark |
| Wiki Lint Coverage | Detects conflicting dosages, orphan conditions, missing citations | `ClinicalLLMWiki.lint()` tests |
| HITL Physician Sign-Off Enforcement | 100% of clinical actions require explicit review | Pipeline & API status checks |

## 3. Scope & Boundaries
### In Scope
- Clinical Ontology (`PatientCase`, `Symptom`, `ClinicalGuideline`, `Medication`, `ContraindicationLink`, `ClinicalAction`, `ClinicalOntologyRegistry`).
- File-backed `ClinicalLLMWiki` (`index.md`, `log.md`, `entities/<id>.md` with `[[wiki_links]]`).
- `HealthcareFDEPipeline` (PHI de-identification, red-flag triage, interaction guardrails, HITL approval, JSONL audit log).
- Production FastAPI service with `/health`, `/ready`, `/metrics`, and `/api/v1/*` endpoints + `X-Request-ID` tracing.

### Out of Scope
- Autonomous prescription execution without physician sign-off.
- External cloud LLM API calls or internet-dependent knowledge retrieval.
- Direct EHR/HL7 FHIR live hospital database writes (simulated via `PatientCase` contracts).

## 4. Key Stakeholders & RACI
| Role | Responsibility |
| --- | --- |
| Clinical Lead (MD) | Approves ontology rules, red-flag criteria, and HITL sign-off workflows |
| Forward-Deployed Engineer (FDE) | Implements PHI masking, guardrails, FastAPI service, and audit logging |
| QA & Patient Safety Lead | Validates deterministic test coverage and zero-hallucination guarantees |
| Platform / DevSecOps | Maintains non-root Docker containerization, healthchecks, and runbooks |
