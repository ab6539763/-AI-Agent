"""Production FastAPI application for Project P06: 政务服务与企业政策通智能体."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .fde_pipeline import GovTechFDEPipeline, PolicyAskResponse
from .llm_wiki import GovTechLLMWiki, LintReport
from .ontology import (
    CitizenProfile,
    EligibilityEvaluation,
    GovAction,
    GovOntologyRegistry,
    seed_default_ontology,
)


class WikiIngestRequest(BaseModel):
    doc_id: str
    title: str
    content: str
    department: str = "市政务服务和数据管理局"
    entity_type: str = "policy"
    program_id: str | None = None
    effective_date: str = "2026-01-01"
    expiry_date: str | None = None
    subsidy_threshold: float | None = None
    rule_ids: list[str] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    clauses: dict[str, str] = Field(default_factory=dict)


class WikiIngestResponse(BaseModel):
    doc_id: str
    path: str
    total_entities: int


class WikiLintRequest(BaseModel):
    reference_date: str | None = None


class EligibilityRequest(BaseModel):
    profile: CitizenProfile
    program_id: str | None = None


class EligibilityResponse(BaseModel):
    applicant_id: str
    evaluations: list[EligibilityEvaluation]


class PolicyAskRequest(BaseModel):
    question: str
    profile: CitizenProfile | None = None
    program_id: str | None = None
    create_hitl_action: bool = True


class ActionApproveRequest(BaseModel):
    action_id: str
    officer_id: str
    approved: bool
    note: str = ""


def _seed_wiki_from_registry(wiki: GovTechLLMWiki, registry: GovOntologyRegistry) -> None:
    if wiki.list_entities():
        return
    for pol in registry.policies.values():
        prog = next((p for p in registry.programs.values() if p.policy_id == pol.policy_id), None)
        rule_ids = [r.rule_id for r in registry.rules.values() if r.policy_id == pol.policy_id]
        wiki.ingest(
            doc_id=pol.policy_id,
            title=pol.title,
            content=pol.summary,
            department=pol.department,
            entity_type="policy",
            program_id=prog.program_id if prog else None,
            effective_date=pol.effective_date,
            expiry_date=pol.expiry_date,
            subsidy_threshold=prog.max_subsidy_amount if prog else None,
            rule_ids=rule_ids,
            related_ids=[prog.program_id] if prog else [],
            clauses=pol.clauses,
        )


def create_app(
    data_dir: Path | str | None = None,
    seed_defaults: bool = True,
) -> FastAPI:
    """Create and configure the P06 GovTech FastAPI application."""
    resolved_dir = Path(
        data_dir
        or os.getenv("GOVTECH_DATA_DIR")
        or Path(tempfile.gettempdir()) / "p06_govtech_data"
    )
    resolved_dir.mkdir(parents=True, exist_ok=True)

    registry = seed_default_ontology() if seed_defaults else GovOntologyRegistry()
    wiki = GovTechLLMWiki(resolved_dir / "wiki")
    if seed_defaults:
        _seed_wiki_from_registry(wiki, registry)
    pipeline = GovTechFDEPipeline(
        registry=registry,
        wiki=wiki,
        audit_log_path=resolved_dir / "audit.jsonl",
    )

    metrics: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "eligibility_checks_total": 0,
        "policy_asks_total": 0,
        "policy_refusals_total": 0,
        "hitl_approvals_total": 0,
    }

    application = FastAPI(
        title="P06 GovTech Policy & Citizen/Enterprise Service Agent",
        version="1.0.0",
        description="政务服务与企业政策通智能体：本体资格核验、政策知识库与合规人工复核",
    )

    application.state.registry = registry
    application.state.wiki = wiki
    application.state.pipeline = pipeline
    application.state.metrics = metrics

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid4())
        metrics["requests_total"] += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p06-govtech-policy"}

    @application.get("/ready")
    def ready() -> dict[str, Any]:
        return {
            "status": "ready",
            "policies": len(registry.policies),
            "programs": len(registry.programs),
            "rules": len(registry.rules),
            "wiki_entities": len(wiki.list_entities()),
        }

    @application.get("/metrics")
    def get_metrics() -> dict[str, Any]:
        pending = sum(
            1 for a in registry.actions.values() if a.status == "pending_approval"
        )
        approved = sum(1 for a in registry.actions.values() if a.status == "approved")
        return {
            **metrics,
            "hitl_pending": pending,
            "hitl_approved": approved,
            "audit_events_total": len(pipeline.audit_trail),
        }

    @application.post("/api/v1/wiki/ingest", response_model=WikiIngestResponse)
    def wiki_ingest(payload: WikiIngestRequest) -> WikiIngestResponse:
        path = wiki.ingest(
            doc_id=payload.doc_id,
            title=payload.title,
            content=payload.content,
            department=payload.department,
            entity_type=payload.entity_type,
            program_id=payload.program_id,
            effective_date=payload.effective_date,
            expiry_date=payload.expiry_date,
            subsidy_threshold=payload.subsidy_threshold,
            rule_ids=payload.rule_ids,
            related_ids=payload.related_ids,
            clauses=payload.clauses,
        )
        metrics["wiki_ingests_total"] += 1
        return WikiIngestResponse(
            doc_id=payload.doc_id,
            path=str(path),
            total_entities=len(wiki.list_entities()),
        )

    @application.post("/api/v1/wiki/lint", response_model=LintReport)
    def wiki_lint(payload: WikiLintRequest | None = None) -> LintReport:
        metrics["wiki_lints_total"] += 1
        ref_date = payload.reference_date if payload else None
        return wiki.lint(
            reference_date=ref_date,
            known_program_ids=set(registry.programs.keys()),
            known_rule_ids=set(registry.rules.keys()),
        )

    @application.post("/api/v1/ontology/eligibility", response_model=EligibilityResponse)
    def ontology_eligibility(payload: EligibilityRequest) -> EligibilityResponse:
        metrics["eligibility_checks_total"] += 1
        try:
            evals = registry.evaluate_eligibility(
                payload.profile, program_id=payload.program_id
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return EligibilityResponse(
            applicant_id=payload.profile.applicant_id,
            evaluations=evals,
        )

    @application.post("/api/v1/policy/ask", response_model=PolicyAskResponse)
    def policy_ask(payload: PolicyAskRequest) -> PolicyAskResponse:
        metrics["policy_asks_total"] += 1
        try:
            resp = pipeline.ask(
                question=payload.question,
                profile=payload.profile,
                program_id=payload.program_id,
                create_hitl_action=payload.create_hitl_action,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if resp.status == "refused":
            metrics["policy_refusals_total"] += 1
        return resp

    @application.post("/api/v1/actions/approve", response_model=GovAction)
    def approve_action(payload: ActionApproveRequest) -> GovAction:
        try:
            action = pipeline.approve_action(
                action_id=payload.action_id,
                officer_id=payload.officer_id,
                approved=payload.approved,
                note=payload.note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        metrics["hitl_approvals_total"] += 1
        return action

    return application


app = create_app()
