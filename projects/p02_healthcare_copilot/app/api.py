"""Production FastAPI application for Project P02 Healthcare Copilot."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .fde_pipeline import HealthcareFDEPipeline
from .llm_wiki import ClinicalLLMWiki
from .ontology import ClinicalOntologyRegistry, PatientCase


class WikiIngestRequest(BaseModel):
    doc_id: str
    title: str
    content: str
    entity_type: str = "guideline"
    condition: str | None = None
    medication: str | None = None
    dose_mg: float | None = None
    citation: str | None = None
    related_ids: list[str] = Field(default_factory=list)


class InteractionCheckRequest(BaseModel):
    proposed_med_ids: list[str]
    active_med_ids: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class ClinicalTriageRequest(BaseModel):
    patient_case: PatientCase
    proposed_med_ids: list[str] = Field(default_factory=list)
    raw_notes: str = ""


class ActionApproveRequest(BaseModel):
    action_id: str
    physician_id: str
    decision: Literal["approved", "rejected"]
    notes: str = ""


def create_app(
    wiki_dir: Path | str | None = None,
    audit_log_path: Path | str | None = None,
) -> FastAPI:
    """Factory creating a configured FastAPI instance with isolated state."""
    resolved_wiki_dir = Path(
        wiki_dir or os.environ.get("P02_WIKI_DIR", "/tmp/p02_healthcare_copilot/wiki")
    )
    resolved_audit_path = Path(
        audit_log_path
        or os.environ.get("P02_AUDIT_LOG_PATH", "/tmp/p02_healthcare_copilot/audit.jsonl")
    )

    registry = ClinicalOntologyRegistry(seed_defaults=True)
    wiki = ClinicalLLMWiki(resolved_wiki_dir)
    pipeline = HealthcareFDEPipeline(
        registry=registry, wiki=wiki, audit_log_path=resolved_audit_path
    )

    metrics: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "interaction_checks_total": 0,
        "blocked_interactions_total": 0,
        "triage_total": 0,
        "hitl_approvals_total": 0,
    }

    application = FastAPI(
        title="P02 Healthcare & Clinical Decision Support Copilot",
        version="1.0.0",
        description="Offline deterministic Clinical Ontology, LLM Wiki, and FDE HITL Copilot.",
    )
    application.state.registry = registry
    application.state.wiki = wiki
    application.state.pipeline = pipeline
    application.state.metrics = metrics

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        metrics["requests_total"] += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": "p02-healthcare-copilot"}

    @application.get("/ready")
    def ready() -> dict[str, Any]:
        return {
            "status": "ready",
            "ontology_medications": len(registry.medications),
            "ontology_contraindications": len(registry.contraindications),
            "wiki_entities": len(wiki.list_entities()),
        }

    @application.get("/metrics")
    def get_metrics() -> dict[str, int]:
        return dict(metrics)

    @application.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        try:
            entity = wiki.ingest(
                doc_id=payload.doc_id,
                title=payload.title,
                content=payload.content,
                entity_type=payload.entity_type,
                condition=payload.condition,
                medication=payload.medication,
                dose_mg=payload.dose_mg,
                citation=payload.citation,
                related_ids=payload.related_ids,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metrics["wiki_ingests_total"] += 1
        return {"status": "ingested", "entity": entity}

    @application.get("/api/v1/wiki/lint")
    def wiki_lint() -> dict[str, Any]:
        metrics["wiki_lints_total"] += 1
        return wiki.lint()

    @application.post("/api/v1/ontology/check-interaction")
    def check_interaction(payload: InteractionCheckRequest) -> dict[str, Any]:
        metrics["interaction_checks_total"] += 1
        result = registry.check_interactions(
            proposed_med_ids=payload.proposed_med_ids,
            active_med_ids=payload.active_med_ids,
            allergies=payload.allergies,
            conditions=payload.conditions,
        )
        if result.blocked:
            metrics["blocked_interactions_total"] += 1
        return result.model_dump()

    @application.post("/api/v1/clinical/triage")
    def clinical_triage(payload: ClinicalTriageRequest) -> dict[str, Any]:
        metrics["triage_total"] += 1
        result = pipeline.triage_case(
            case=payload.patient_case,
            proposed_med_ids=payload.proposed_med_ids,
            raw_notes=payload.raw_notes,
        )
        if result["interaction_check"]["blocked"]:
            metrics["blocked_interactions_total"] += 1
        return result

    @application.post("/api/v1/actions/approve")
    def approve_action(payload: ActionApproveRequest) -> dict[str, Any]:
        try:
            action = pipeline.approve_action(
                action_id=payload.action_id,
                physician_id=payload.physician_id,
                decision=payload.decision,
                notes=payload.notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metrics["hitl_approvals_total"] += 1
        return {"status": action.status, "action": action.model_dump()}

    return application


app = create_app()
