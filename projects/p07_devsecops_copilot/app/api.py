"""Production FastAPI application for Project P07 DevSecOps Copilot."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .fde_pipeline import DevSecOpsFDEPipeline
from .llm_wiki import DevSecOpsLLMWiki
from .ontology import DevSecOpsOntologyRegistry


class WikiIngestRequest(BaseModel):
    entity_type: str = Field(..., examples=["service"])
    entity_id: str = Field(..., examples=["svc-billing"])
    title: str = Field(..., examples=["Billing Service"])
    content: str = Field(..., examples=["Handles invoice generation and webhooks."])
    metadata: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)


class IncidentTriageRequest(BaseModel):
    service_id: str = Field(..., examples=["svc-auth"])
    symptom: str = Field(..., examples=["502 Bad Gateway with Bearer secret_token_123456"])
    severity: str = Field(default="SEV-2")
    proposed_action: str = Field(default="rollback")
    environment: str = Field(default="prod")
    requested_by: str = Field(default="fde-copilot")


class ActionApproveRequest(BaseModel):
    action_id: str
    approved: bool
    approver: str = Field(..., examples=["sre-lead-alice"])
    comment: str = Field(default="")


class CveGateRequest(BaseModel):
    service_id: str = Field(..., examples=["svc-checkout"])
    release_version: str = Field(default="v1.0.0")
    include_dependencies: bool = Field(default=True)
    block_threshold: float = Field(default=9.0, ge=0.0, le=10.0)
    dependency_cvss_overrides: dict[str, float] = Field(default_factory=dict)


def create_app(
    wiki_dir: Optional[str | Path] = None,
    seed_demo: bool = True,
) -> FastAPI:
    """Factory for the P07 DevSecOps Copilot FastAPI service."""
    resolved_wiki_dir = Path(
        wiki_dir or os.environ.get("P07_WIKI_DIR", "/tmp/p07_devsecops_wiki")
    )

    registry = DevSecOpsOntologyRegistry()
    if seed_demo:
        registry.seed_default_topology()

    wiki = DevSecOpsLLMWiki(resolved_wiki_dir)
    if seed_demo:
        wiki.sync_from_ontology(registry)

    pipeline = DevSecOpsFDEPipeline(registry=registry, wiki=wiki)

    metrics_state: dict[str, Any] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "triage_total": 0,
        "approvals_total": 0,
        "cve_gates_total": 0,
        "last_latency_ms": 0.0,
    }

    app = FastAPI(
        title="P07 Enterprise DevSecOps Copilot",
        version="2.0.0",
        description="Deterministic DevSecOps Ontology, LLM Wiki, and FDE Triage/HITL API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = registry
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.metrics = metrics_state

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid4().hex[:12]}"
        start = time.perf_counter()
        metrics_state["requests_total"] += 1
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
        metrics_state["last_latency_ms"] = elapsed_ms
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p07-devsecops-copilot"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return {
            "status": "ready",
            "wiki_dir": str(wiki.root_dir),
            "services_count": len(registry.services),
            "cves_count": len(registry.cves),
        }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        pending_actions = sum(
            1 for a in registry.ops_actions.values() if a.status == "PENDING_APPROVAL"
        )
        return {
            **metrics_state,
            "services_registered": len(registry.services),
            "actions_pending_hitl": pending_actions,
            "audit_events_total": len(pipeline.audit_trail),
        }

    @app.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        path = wiki.ingest(
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            title=payload.title,
            content=payload.content,
            metadata=payload.metadata,
            links=payload.links,
        )
        metrics_state["wiki_ingests_total"] += 1
        return {
            "status": "ingested",
            "entity_id": payload.entity_id,
            "path": str(path),
            "index_path": str(wiki.index_path),
        }

    @app.get("/api/v1/wiki/lint")
    def wiki_lint(
        reference_date: str = Query(default="2026-11-13"),
        stale_days: int = Query(default=30, ge=1),
    ) -> dict[str, Any]:
        metrics_state["wiki_lints_total"] += 1
        return wiki.lint(registry=registry, reference_date=reference_date, stale_days=stale_days)

    @app.get("/api/v1/ontology/blast-radius")
    def ontology_blast_radius(
        service_id: str = Query(...),
        max_depth: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, Any]:
        try:
            return registry.compute_blast_radius(service_id=service_id, max_depth=max_depth)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/incidents/triage")
    def incidents_triage(payload: IncidentTriageRequest) -> dict[str, Any]:
        try:
            result = pipeline.triage_incident(
                service_id=payload.service_id,
                symptom=payload.symptom,
                severity=payload.severity,
                proposed_action=payload.proposed_action,
                environment=payload.environment,
                requested_by=payload.requested_by,
            )
            metrics_state["triage_total"] += 1
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/actions/approve")
    def actions_approve(payload: ActionApproveRequest) -> dict[str, Any]:
        try:
            result = pipeline.approve_action(
                action_id=payload.action_id,
                approved=payload.approved,
                approver=payload.approver,
                comment=payload.comment,
            )
            metrics_state["approvals_total"] += 1
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/dashboard/overview")
    def dashboard_overview() -> dict[str, Any]:
        return pipeline.get_dashboard_overview()

    @app.get("/api/v1/wiki/pages")
    def wiki_pages() -> dict[str, Any]:
        pages = pipeline.list_wiki_pages()
        return {"pages": pages, "total": len(pages)}

    @app.get("/api/v1/actions/pending")
    def actions_pending() -> dict[str, Any]:
        actions = pipeline.list_pending_actions()
        return {"actions": actions, "total": len(actions)}

    @app.get("/api/v1/audit/logs")
    def audit_logs() -> dict[str, Any]:
        logs = pipeline.list_audit_logs()
        return {"logs": logs, "total": len(logs)}

    @app.post("/api/v1/security/cve-gate")
    def security_cve_gate(payload: CveGateRequest) -> dict[str, Any]:
        try:
            result = pipeline.evaluate_release_cve_gate(
                service_id=payload.service_id,
                release_version=payload.release_version,
                include_dependencies=payload.include_dependencies,
                block_threshold=payload.block_threshold,
                dependency_cvss_overrides=payload.dependency_cvss_overrides,
            )
            metrics_state["cve_gates_total"] += 1
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
