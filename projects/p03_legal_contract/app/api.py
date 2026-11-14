"""Production FastAPI application for Project P03 Legal Compliance & Contract Review Agent."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .fde_pipeline import LegalFDEPipeline
from .llm_wiki import LegalLLMWiki
from .ontology import LegalOntologyRegistry
from .redline_engine import ObligationExtractor, RedlinePlaybookEngine


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


class ContractRedlineDiffRequest(BaseModel):
    contract_id: str = "diff_contract"
    title: str = "Contract Version Comparison"
    original_text: str
    revised_text: str
    requested_by: str = "legal_ops"


class ContractObligationsRequest(BaseModel):
    contract_id: str = "ctr_obligations"
    title: str = "Contract Obligation Calendar"
    text: str
    effective_date: str = "2026-01-01"
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
    playbook_engine = RedlinePlaybookEngine()
    obligation_extractor = ObligationExtractor()

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = registry
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.playbook_engine = playbook_engine
    app.state.obligation_extractor = obligation_extractor
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

    @app.get("/api/v1/dashboard/overview")
    def dashboard_overview() -> dict[str, Any]:
        high_risk_clauses = sum(
            1 for c in registry.clauses.values() if c.risk_level in ("high", "critical")
        )
        critical_risk_clauses = sum(
            1 for c in registry.clauses.values() if c.risk_level == "critical"
        )
        active_regulations = sum(
            1 for r in registry.regulations.values() if r.status == "active"
        )
        pending_gc_approvals = sum(
            1 for a in registry.actions.values() if a.status == "pending"
        )
        wiki_pages_count = len(list(wiki.entities_dir.glob("*.md")))
        return {
            "contracts_reviewed": counters["contracts_reviewed"],
            "contracts_total": len(registry.contracts),
            "clauses_total": len(registry.clauses),
            "high_risk_clauses": high_risk_clauses,
            "critical_risk_clauses": critical_risk_clauses,
            "active_regulations": active_regulations,
            "regulations_total": len(registry.regulations),
            "pending_gc_approvals": pending_gc_approvals,
            "audit_logs_count": len(pipeline.audit_trail),
            "pii_masked_total": pipeline.pii_masked_total,
            "wiki_pages_count": wiki_pages_count,
            "recent_contracts": [
                {
                    "id": c.id,
                    "title": c.title,
                    "counterparty": c.counterparty,
                    "jurisdiction": c.jurisdiction,
                    "status": c.status,
                }
                for c in list(registry.contracts.values())[-10:]
            ],
        }

    @app.get("/api/v1/wiki/pages")
    def list_wiki_pages() -> dict[str, Any]:
        pages: list[dict[str, Any]] = []
        for md_file in sorted(wiki.entities_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            title = lines[0].lstrip("# ").strip() if lines else md_file.stem
            preview = " ".join(lines[1:5])[:240] if len(lines) > 1 else ""
            pages.append(
                {
                    "id": md_file.stem,
                    "title": title,
                    "path": str(md_file.relative_to(wiki.root_dir)),
                    "preview": preview,
                }
            )
        return {"count": len(pages), "pages": pages}

    @app.get("/api/v1/ontology/regulations")
    def list_ontology_regulations() -> dict[str, Any]:
        regulations = [r.model_dump() for r in registry.regulations.values()]
        links = [lnk.model_dump() for lnk in registry.links.values()]
        return {
            "count": len(regulations),
            "regulations": regulations,
            "links_count": len(links),
            "links": links,
        }

    @app.get("/api/v1/actions/pending")
    def list_pending_actions() -> dict[str, Any]:
        pending = [a.model_dump() for a in registry.actions.values() if a.status == "pending"]
        return {"count": len(pending), "actions": pending}

    @app.get("/api/v1/audit/logs")
    def list_audit_logs(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        logs = list(reversed(pipeline.audit_trail))[:limit]
        return {"count": len(logs), "total": len(pipeline.audit_trail), "logs": logs}

    @app.post("/api/v1/contracts/redline-diff")
    def contract_redline_diff(payload: ContractRedlineDiffRequest) -> dict[str, Any]:
        return pipeline.compare_contract_versions(
            contract_id=payload.contract_id,
            title=payload.title,
            original_text=payload.original_text,
            revised_text=payload.revised_text,
            requested_by=payload.requested_by,
        )

    @app.post("/api/v1/contracts/obligations")
    def extract_contract_obligations(payload: ContractObligationsRequest) -> dict[str, Any]:
        masked_text, pii_count = pipeline.mask_pii(payload.text)
        timeline = obligation_extractor.extract_timeline(
            contract_id=payload.contract_id,
            title=payload.title,
            text=masked_text,
            effective_date=payload.effective_date,
        )
        audit_entry = pipeline.record_audit(
            event_type="OBLIGATIONS_EXTRACTED",
            actor=payload.requested_by,
            target_id=payload.contract_id,
            details={
                "total_obligations": timeline.total_obligations,
                "pii_masked_count": pii_count,
                "summary_counts": timeline.summary_counts,
            },
        )
        return {
            **timeline.model_dump(),
            "pii_masked_count": pii_count,
            "audit_entry": audit_entry,
        }

    @app.get("/api/v1/contracts/playbook")
    def get_redline_playbook(
        clause_type: str | None = Query(default=None),
    ) -> dict[str, Any]:
        entries = playbook_engine.list_entries(clause_type=clause_type)
        return {
            "count": len(entries),
            "clause_types": ["liability_cap", "indemnification", "ip_ownership", "termination"],
            "entries": [e.model_dump() for e in entries],
        }

    return app


app = create_app()
