"""Production FastAPI application for Project P05: Retail & Supply Chain Growth Agent."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .fde_pipeline import RetailFDEPipeline
from .llm_wiki import RetailLLMWiki
from .ontology import ActionStatus, RetailOntologyRegistry
from .supply_optimizer import EOQOptimizer, WarehouseAllocator


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


class MarginSimItem(BaseModel):
    sku_id: str
    promo_discount_pct: float | None = Field(default=None, ge=0.0, le=0.95)
    proposed_price: float | None = Field(default=None, gt=0)
    projected_units: int | None = Field(default=None, ge=0)


class MarginSimulateRequest(BaseModel):
    items: list[MarginSimItem] | None = None
    global_discount_pct: float | None = Field(default=None, ge=0.0, le=0.95)
    actor: str = "merchandiser-sim"


class EOQOptimizeRequest(BaseModel):
    sku_id: str | None = None
    ordering_cost: float = Field(default=85.0, gt=0)
    holding_cost_rate: float = Field(default=0.24, gt=0, le=1.0)
    service_level: float = Field(default=0.95, ge=0.5, le=0.999)
    daily_demand_override: float | None = Field(default=None, gt=0)
    lead_time_override: int | None = Field(default=None, ge=1)
    promo_lift_pct: float = Field(default=0.0, ge=0.0, le=3.0)


class RebalanceRequest(BaseModel):
    sku_ids: list[str] | None = None
    stock_matrix: dict[str, dict[str, int]] | None = None
    target_cover_days: float = Field(default=10.0, gt=0)
    transfer_cost_per_unit: float = Field(default=1.85, ge=0)
    min_transfer_qty: int = Field(default=5, ge=1)


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
    eoq_optimizer = EOQOptimizer()
    warehouse_allocator = WarehouseAllocator()

    app = FastAPI(
        title="P05 Retail & Supply Chain Growth Agent",
        version="2.0.0",
        description="Ontology + LLM Wiki + FDE Pipeline for Retail Replenishment & Dynamic Pricing",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.ontology = ontology
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.eoq_optimizer = eoq_optimizer
    app.state.warehouse_allocator = warehouse_allocator
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
            "skus": [s.model_dump() for s in ontology.skus.values()],
            "warehouses": [w.model_dump() for w in ontology.warehouses.values()],
            "suppliers": [s.model_dump() for s in ontology.suppliers.values()],
            "forecasts": [f.model_dump() for f in ontology.forecasts.values()],
        }

    @app.get("/api/v1/dashboard/overview")
    def dashboard_overview() -> dict[str, Any]:
        checks = ontology.check_all_inventory()
        stockout_alerts = sum(
            1 for c in checks if c.risk_level in {"CRITICAL", "WARNING"}
        )
        critical_alerts = sum(1 for c in checks if c.risk_level == "CRITICAL")
        pending_hitl = sum(
            1
            for a in ontology.actions.values()
            if a.status == ActionStatus.PENDING_APPROVAL
        )
        executed_actions = sum(
            1 for a in ontology.actions.values() if a.status == ActionStatus.EXECUTED
        )
        blocked_actions = sum(
            1 for a in ontology.actions.values() if a.status == ActionStatus.BLOCKED
        )
        wiki_pages = len(list(wiki.entities_dir.glob("*.md")))
        total_inventory_value = round(
            sum(s.current_stock * s.unit_cost for s in ontology.skus.values()), 2
        )
        return {
            "total_skus": len(ontology.skus),
            "stockout_alerts": stockout_alerts,
            "critical_alerts": critical_alerts,
            "warehouses": len(ontology.warehouses),
            "suppliers": len(ontology.suppliers),
            "wiki_pages": wiki_pages,
            "pending_hitl_pos": pending_hitl,
            "executed_actions": executed_actions,
            "blocked_actions": blocked_actions,
            "audit_logs": len(pipeline.audit_trail),
            "total_inventory_value": total_inventory_value,
        }

    @app.get("/api/v1/wiki/pages")
    def wiki_pages() -> dict[str, Any]:
        pages = []
        for page_path in sorted(wiki.entities_dir.glob("*.md")):
            text = page_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            first_heading = next(
                (ln.lstrip("# ").strip() for ln in lines if ln.startswith("# ")),
                page_path.stem,
            )
            title = (
                first_heading.split(":", 1)[1].strip()
                if ":" in first_heading
                else first_heading
            )
            type_match = re.search(r"^- Type:\s*(.+)$", text, re.MULTILINE)
            entity_type = type_match.group(1).strip() if type_match else "Entity"
            fact_lines = [
                ln.strip() for ln in lines if ln.strip().startswith("- [")
            ]
            preview = (
                " | ".join(fact_lines[:2])[:220]
                if fact_lines
                else " ".join(lines[:4])[:220]
            )
            pages.append(
                {
                    "id": page_path.stem,
                    "title": title,
                    "entity_type": entity_type,
                    "path": f"entities/{page_path.name}",
                    "preview": preview,
                    "content": text,
                }
            )
        return {"items": pages, "total": len(pages)}

    @app.get("/api/v1/wiki/query")
    def wiki_query(q: str = Query(..., min_length=1), top_k: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
        return wiki.query(question=q, top_k=top_k)

    @app.get("/api/v1/actions/pending")
    def actions_pending(include_all: bool = Query(default=False)) -> dict[str, Any]:
        actions = list(ontology.actions.values())
        if not include_all:
            actions = [a for a in actions if a.status == ActionStatus.PENDING_APPROVAL]
        actions.sort(key=lambda a: a.created_at, reverse=True)
        return {
            "items": [a.model_dump() for a in actions],
            "total": len(actions),
        }

    @app.get("/api/v1/audit/logs")
    def audit_logs(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        items = list(reversed(pipeline.audit_trail))[:limit]
        return {
            "items": items,
            "total": len(pipeline.audit_trail),
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

    @app.post("/api/v1/supply/margin-simulate")
    def supply_margin_simulate(payload: MarginSimulateRequest) -> dict[str, Any]:
        try:
            items = (
                [item.model_dump() for item in payload.items]
                if payload.items is not None
                else None
            )
            return pipeline.simulate_margin_scenarios(
                items=items,
                global_discount_pct=payload.global_discount_pct,
                actor=payload.actor,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/supply/eoq-optimize")
    def supply_eoq_optimize(payload: EOQOptimizeRequest) -> dict[str, Any]:
        try:
            res = eoq_optimizer.optimize_registry(
                ontology,
                sku_id=payload.sku_id,
                ordering_cost=payload.ordering_cost,
                holding_cost_rate=payload.holding_cost_rate,
                service_level=payload.service_level,
                daily_demand_override=payload.daily_demand_override,
                lead_time_override=payload.lead_time_override,
                promo_lift_pct=payload.promo_lift_pct,
            )
            return res.model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/supply/rebalance")
    def supply_rebalance(payload: RebalanceRequest) -> dict[str, Any]:
        try:
            res = warehouse_allocator.plan_rebalance(
                ontology,
                stock_matrix=payload.stock_matrix,
                sku_ids=payload.sku_ids,
                target_cover_days=payload.target_cover_days,
                transfer_cost_per_unit=payload.transfer_cost_per_unit,
                min_transfer_qty=payload.min_transfer_qty,
            )
            return res.model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
