"""Production FastAPI application for Project P05: Retail & Supply Chain Growth Agent."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .fde_pipeline import RetailFDEPipeline
from .llm_wiki import RetailLLMWiki
from .ontology import ActionStatus, RetailOntologyRegistry


class WikiIngestRequest(BaseModel):
    doc_id: str
    title: str
    content: str
    entity_id: str | None = None
    entity_type: str = "SKU"
    links: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplenishRequest(BaseModel):
    sku_id: str
    requested_qty: int | None = Field(default=None, ge=0)
    proposed_price: float | None = Field(default=None, gt=0)
    actor: str = "fde-agent"


class ApproveActionRequest(BaseModel):
    action_id: str
    approved: bool
    approver: str
    comment: str = ""


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    resolved_dir = Path(
        data_dir
        or os.environ.get("P05_DATA_DIR", "/tmp/p05_retail_supply_data")
    )
    wiki_dir = resolved_dir / "wiki"

    ontology = RetailOntologyRegistry()
    ontology.seed_demo_data()
    wiki = RetailLLMWiki(wiki_dir=wiki_dir)
    pipeline = RetailFDEPipeline(ontology=ontology, wiki=wiki)
    pipeline.seed_wiki_from_ontology()

    app = FastAPI(
        title="P05 Retail & Supply Chain Growth Agent",
        version="1.0.0",
        description="Ontology + LLM Wiki + FDE Pipeline for Retail Replenishment & Dynamic Pricing",
    )

    app.state.ontology = ontology
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.metrics = {
        "requests_total": 0,
        "requests_by_path": {},
        "total_latency_ms": 0.0,
    }

    @app.middleware("http")
    async def request_id_and_metrics_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

        app.state.metrics["requests_total"] += 1
        path = request.url.path
        by_path = app.state.metrics["requests_by_path"]
        by_path[path] = by_path.get(path, 0) + 1
        app.state.metrics["total_latency_ms"] = round(
            app.state.metrics["total_latency_ms"] + elapsed_ms, 3
        )

        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "p05-retail-supply"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        wiki_pages = len(list(wiki.entities_dir.glob("*.md")))
        return {
            "status": "ready",
            "skus_loaded": len(ontology.skus),
            "warehouses_loaded": len(ontology.warehouses),
            "suppliers_loaded": len(ontology.suppliers),
            "wiki_pages": wiki_pages,
        }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        pending_hitl = sum(
            1
            for a in ontology.actions.values()
            if a.status == ActionStatus.PENDING_APPROVAL
        )
        inventory_checks = ontology.check_all_inventory()
        stockout_risks = sum(
            1 for c in inventory_checks if c.risk_level in {"CRITICAL", "WARNING"}
        )
        return {
            "requests_total": app.state.metrics["requests_total"],
            "requests_by_path": app.state.metrics["requests_by_path"],
            "total_latency_ms": app.state.metrics["total_latency_ms"],
            "skus_total": len(ontology.skus),
            "actions_total": len(ontology.actions),
            "hitl_pending": pending_hitl,
            "stockout_risks": stockout_risks,
            "audit_events": len(pipeline.audit_trail),
        }

    @app.post("/api/v1/wiki/ingest")
    def wiki_ingest(payload: WikiIngestRequest) -> dict[str, Any]:
        return wiki.ingest(
            doc_id=payload.doc_id,
            title=payload.title,
            content=payload.content,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            links=payload.links,
            metadata=payload.metadata,
        )

    @app.get("/api/v1/wiki/lint")
    def wiki_lint() -> dict[str, Any]:
        return wiki.lint(registry=ontology)

    @app.get("/api/v1/ontology/inventory")
    def ontology_inventory(sku_id: str | None = Query(default=None)) -> dict[str, Any]:
        if sku_id is not None:
            if sku_id not in ontology.skus:
                raise HTTPException(status_code=404, detail=f"Unknown SKU: {sku_id}")
            check = ontology.check_safety_stock(sku_id)
            return {
                "items": [check.model_dump()],
                "total": 1,
                "sku": ontology.skus[sku_id].model_dump(),
            }
        checks = ontology.check_all_inventory()
        return {
            "items": [c.model_dump() for c in checks],
            "total": len(checks),
        }

    @app.post("/api/v1/supply/replenish")
    def supply_replenish(payload: ReplenishRequest) -> dict[str, Any]:
        try:
            return pipeline.plan_replenishment(
                sku_id=payload.sku_id,
                requested_qty=payload.requested_qty,
                proposed_price=payload.proposed_price,
                actor=payload.actor,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/actions/approve")
    def actions_approve(payload: ApproveActionRequest) -> dict[str, Any]:
        try:
            return pipeline.approve_action(
                action_id=payload.action_id,
                approved=payload.approved,
                approver=payload.approver,
                comment=payload.comment,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
