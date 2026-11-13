"""Production FastAPI application for Project P03 Legal Compliance & Contract Review Agent."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .fde_pipeline import LegalFDEPipeline
from .llm_wiki import LegalLLMWiki
from .ontology import LegalOntologyRegistry


class WikiIngestRequest(BaseModel):
    doc_id: str
    title: str
    content: str
    doc_type: Literal["contract", "clause", "regulation"] = "contract"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractReviewRequest(BaseModel):
    contract_id: str
    title: str
    text: str
    counterparty: str = "Counterparty Corp."
    jurisdiction: str = "US-NY"
    liability_cap_usd: float | None = None
    requested_by: str = "legal_ops"


class ActionApproveRequest(BaseModel):
    action_id: str
    decision: Literal["approved", "rejected"]
    approver: str
    notes: str = ""


def create_app(wiki_dir: str | Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_wiki_dir = (
        Path(wiki_dir)
        if wiki_dir is not None
        else Path(os.environ.get("WIKI_DIR", Path(tempfile.gettempdir()) / "p03_legal_wiki"))
    )

    registry = LegalOntologyRegistry(seed_defaults=True)
    wiki = LegalLLMWiki(root_dir=resolved_wiki_dir, registry=registry)
    pipeline = LegalFDEPipeline(registry=registry, wiki=wiki)

    counters: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests": 0,
        "wiki_lints": 0,
        "contracts_reviewed": 0,
        "actions_decided": 0,
    }

    app = FastAPI(
        title="P03 Legal Compliance & Contract Review Agent",
        version="1.0.0",
        description="Offline deterministic Legal Ontology, LLM Wiki, and FDE Contract Review API.",
    )
    app.state.registry = registry
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.counters = counters

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        counters["requests_total"] += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p03-legal-contract"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        if not wiki.root_dir.exists() or not wiki.index_path.exists():
            raise HTTPException(status_code=503, detail="Wiki storage not ready")
        return {
            "status": "ready",
            "wiki_dir": str(wiki.root_dir),
            "regulations_count": len(registry.regulations),
        }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        pending = sum(1 for a in registry.actions.values() if a.status == "pending")
        return {
            **counters,
            "contracts_total": len(registry.contracts),
            "clauses_total": len(registry.clauses),
            "regulations_total": len(registry.regulations),
            "hitl_actions_pending": pending,
            "pii_masked_total": pipeline.pii_masked_total,
            "audit_events_total": len(pipeline.audit_trail),
        }

    @app.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        counters["wiki_ingests"] += 1
        result = wiki.ingest(
            doc_id=payload.doc_id,
            title=payload.title,
            content=payload.content,
            doc_type=payload.doc_type,
            metadata=payload.metadata,
        )
        pipeline.record_audit(
            event_type="WIKI_INGEST",
            actor="api",
            target_id=payload.doc_id,
            details={"doc_type": payload.doc_type, "entities": result["entities"]},
        )
        return result

    @app.api_route("/api/v1/wiki/lint", methods=["GET", "POST"])
    def wiki_lint() -> dict[str, Any]:
        counters["wiki_lints"] += 1
        return wiki.lint()

    @app.get("/api/v1/ontology/clauses")
    def list_ontology_clauses(
        risk_level: str | None = Query(default=None),
        contract_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        clauses = list(registry.clauses.values())
        if risk_level:
            clauses = [c for c in clauses if c.risk_level == risk_level]
        if contract_id:
            clauses = [c for c in clauses if c.contract_id == contract_id]
        return {
            "count": len(clauses),
            "clauses": [c.model_dump() for c in clauses],
        }

    @app.post("/api/v1/contracts/review")
    def review_contract(payload: ContractReviewRequest) -> dict[str, Any]:
        counters["contracts_reviewed"] += 1
        return pipeline.review_contract(
            contract_id=payload.contract_id,
            title=payload.title,
            raw_text=payload.text,
            counterparty=payload.counterparty,
            jurisdiction=payload.jurisdiction,
            liability_cap_usd=payload.liability_cap_usd,
            requested_by=payload.requested_by,
        )

    @app.post("/api/v1/actions/approve")
    def approve_action(payload: ActionApproveRequest) -> dict[str, Any]:
        try:
            action = pipeline.approve_action(
                action_id=payload.action_id,
                decision=payload.decision,
                approver=payload.approver,
                notes=payload.notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        counters["actions_decided"] += 1
        return {
            "action": action.model_dump(),
            "contract_status": (
                registry.contracts[action.contract_id].status
                if action.contract_id in registry.contracts
                else None
            ),
        }

    return app


app = create_app()
