"""Production FastAPI application for Project P04: Manufacturing Ops Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.fde_pipeline import ManufacturingFDEPipeline
from app.llm_wiki import ManufacturingLLMWiki
from app.ontology import ActionStatus, ManufacturingOntologyRegistry


class WikiIngestRequest(BaseModel):
    entity_id: str
    entity_type: str
    title: str
    content: str
    links: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnoseRequest(BaseModel):
    equipment_id: str
    readings: dict[str, float] = Field(default_factory=dict)
    fault_code: str | None = None


class IncidentRequest(BaseModel):
    equipment_id: str
    sensor_readings: dict[str, float] = Field(default_factory=dict)
    fault_code: str | None = None
    reporter: str = "iot-gateway"


class ApproveActionRequest(BaseModel):
    action_id: str
    approved: bool
    safety_officer: str
    reason: str = ""


def create_app(
    wiki_dir: str | Path | None = None,
    registry: ManufacturingOntologyRegistry | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    resolved_wiki_dir = Path(
        wiki_dir
        or os.environ.get("WIKI_DIR")
        or (Path(__file__).resolve().parent.parent / "data" / "wiki")
    )
    ont_registry = registry or ManufacturingOntologyRegistry(seed_defaults=True)
    wiki = ManufacturingLLMWiki(resolved_wiki_dir)
    pipeline = ManufacturingFDEPipeline(
        registry=ont_registry,
        wiki=wiki,
        sync_wiki_on_init=True,
    )

    metrics_state: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "diagnoses_total": 0,
        "incidents_total": 0,
        "hitl_approvals_total": 0,
        "hitl_rejections_total": 0,
    }

    app = FastAPI(
        title="P04 Smart Manufacturing & Equipment Ops Agent",
        version="1.0.0",
        description="Offline deterministic Manufacturing Ontology + LLM Wiki + HITL FDE Pipeline.",
    )
    app.state.registry = ont_registry
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.metrics = metrics_state

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        metrics_state["requests_total"] += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p04-manufacturing-ops"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        wiki_ready = wiki.wiki_dir.exists() and wiki.index_path.exists()
        eq_count = len(ont_registry.equipment)
        if not wiki_ready or eq_count == 0:
            raise HTTPException(status_code=503, detail="Service dependencies not ready")
        wiki_pages = len(list(wiki.entities_dir.glob("*.md")))
        return {
            "status": "ready",
            "equipment_count": eq_count,
            "wiki_pages": wiki_pages,
        }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        pending_actions = sum(
            1
            for a in pipeline.actions.values()
            if a.status == ActionStatus.PENDING_APPROVAL
        )
        return {
            **metrics_state,
            "equipment_count": len(ont_registry.equipment),
            "fault_codes_count": len(ont_registry.fault_codes),
            "sops_count": len(ont_registry.sops),
            "pending_hitl_actions": pending_actions,
            "audit_trail_entries": len(pipeline.audit_trail),
        }

    @app.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        path = wiki.ingest(
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            title=payload.title,
            content=payload.content,
            links=payload.links,
            metadata=payload.metadata,
        )
        metrics_state["wiki_ingests_total"] += 1
        return {
            "status": "ingested",
            "entity_id": payload.entity_id,
            "path": str(path),
        }

    @app.api_route("/api/v1/wiki/lint", methods=["GET", "POST"])
    def wiki_lint() -> dict[str, Any]:
        metrics_state["wiki_lints_total"] += 1
        return wiki.lint(registry=ont_registry)

    @app.post("/api/v1/ontology/diagnose")
    def ontology_diagnose(payload: DiagnoseRequest) -> dict[str, Any]:
        metrics_state["diagnoses_total"] += 1
        try:
            result = ont_registry.diagnose(
                equipment_id=payload.equipment_id,
                readings=payload.readings,
                fault_code=payload.fault_code,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return result.model_dump()

    @app.post("/api/v1/ops/incident")
    def ops_incident(payload: IncidentRequest) -> dict[str, Any]:
        metrics_state["incidents_total"] += 1
        try:
            return pipeline.handle_incident(
                equipment_id=payload.equipment_id,
                sensor_readings=payload.sensor_readings,
                fault_code=payload.fault_code,
                reporter=payload.reporter,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/actions/approve")
    def actions_approve(payload: ApproveActionRequest) -> dict[str, Any]:
        try:
            action = pipeline.approve_action(
                action_id=payload.action_id,
                approved=payload.approved,
                safety_officer=payload.safety_officer,
                reason=payload.reason,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if payload.approved:
            metrics_state["hitl_approvals_total"] += 1
        else:
            metrics_state["hitl_rejections_total"] += 1

        eq = ont_registry.get_equipment(action.equipment_id)
        return {
            "action": action.model_dump(),
            "equipment_status": eq.status.value if eq else None,
            "audit_trail_count": len(pipeline.audit_trail),
        }

    return app


app = create_app()
