"""Production FastAPI Application for Project P01: FinTech Research & Compliance Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.fde_pipeline import FinTechFDEPipeline
from app.llm_wiki import FinTechLLMWiki
from app.ontology import OntologyRegistry


class WikiIngestRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: Optional[str] = None


class ResearchQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    issuer_id: Optional[str] = None
    actor_role: str = Field(default="analyst")
    financials: Optional[dict[str, float]] = None
    period: str = Field(default="2025-Q4")


class ActionApproveRequest(BaseModel):
    action_id: str = Field(..., min_length=1)
    decision: str = Field(..., pattern=r"^(approve|reject)$")
    actor_role: str = Field(..., min_length=1)
    approver: str = Field(..., min_length=1)
    comment: str = Field(default="")


def create_app(data_dir: Optional[Path | str] = None) -> FastAPI:
    resolved_dir = Path(
        data_dir or os.environ.get("P01_DATA_DIR", "/tmp/p01_fintech_research_data")
    )
    wiki = FinTechLLMWiki(resolved_dir / "wiki")
    ontology = OntologyRegistry()
    pipeline = FinTechFDEPipeline(
        wiki=wiki,
        ontology=ontology,
        audit_log_path=resolved_dir / "audit_trail.jsonl",
    )

    metrics_state: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "research_queries_total": 0,
        "guardrail_blocks_total": 0,
        "actions_decided_total": 0,
    }

    app = FastAPI(
        title="P01 FinTech Research & Compliance Agent",
        version="1.0.0",
        description="Offline deterministic FinTech investment research, Ontology, LLM Wiki, and HITL compliance API.",
    )
    app.state.pipeline = pipeline
    app.state.wiki = wiki
    app.state.ontology = ontology
    app.state.metrics = metrics_state

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        metrics_state["requests_total"] += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    def _error_response(request: Request, status_code: int, error: str, detail: str) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status_code,
            content={"error": error, "detail": detail, "request_id": req_id},
            headers={"X-Request-ID": req_id} if req_id else {},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return _error_response(request, 400, "BadRequest", str(exc))

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
        return _error_response(request, 404, "NotFound", str(exc))

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        return _error_response(request, 403, "Forbidden", str(exc))

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(request, 500, "InternalServerError", str(exc))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p01-fintech-research"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        is_ready = wiki.index_path.exists() and wiki.entities_dir.exists()
        return {
            "status": "ready" if is_ready else "not_ready",
            "issuers_count": len(ontology.issuers),
            "wiki_pages_count": len(list(wiki.entities_dir.glob("*.md"))),
        }

    @app.get("/metrics")
    def get_metrics() -> dict[str, Any]:
        return {
            **metrics_state,
            "ontology_issuers": len(ontology.issuers),
            "ontology_links": len(ontology.links),
            "audit_events": len(pipeline.read_audit_trail()),
        }

    @app.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        res = pipeline.ingest_document(
            doc_id=payload.doc_id,
            title=payload.title,
            content=payload.content,
            entities=payload.entities,
            timestamp=payload.timestamp,
        )
        metrics_state["wiki_ingests_total"] += 1
        return res

    @app.get("/api/v1/wiki/lint")
    def wiki_lint(
        stale_days: int = Query(default=90, ge=1, le=3650),
        reference_date: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        metrics_state["wiki_lints_total"] += 1
        return wiki.lint(stale_days=stale_days, reference_date=reference_date)

    @app.get("/api/v1/ontology/graph")
    def ontology_graph(
        issuer_id: Optional[str] = Query(default=None),
        max_depth: int = Query(default=2, ge=1, le=5),
    ) -> dict[str, Any]:
        if issuer_id:
            return ontology.traverse_graph(issuer_id, max_depth=max_depth)
        return ontology.to_graph_dict()

    @app.post("/api/v1/research/query")
    def research_query(payload: ResearchQueryRequest) -> dict[str, Any]:
        metrics_state["research_queries_total"] += 1
        res = pipeline.run_research(
            question=payload.question,
            issuer_id=payload.issuer_id,
            actor_role=payload.actor_role,
            financials=payload.financials,
            period=payload.period,
        )
        if res.get("status") == "blocked":
            metrics_state["guardrail_blocks_total"] += 1
        return res

    @app.post("/api/v1/actions/approve")
    def actions_approve(payload: ActionApproveRequest) -> dict[str, Any]:
        res = pipeline.approve_action(
            action_id=payload.action_id,
            decision=payload.decision,
            actor_role=payload.actor_role,
            approver=payload.approver,
            comment=payload.comment,
        )
        metrics_state["actions_decided_total"] += 1
        return res

    return app


app = create_app()
