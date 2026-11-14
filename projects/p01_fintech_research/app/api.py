"""Production FastAPI Application for Project P01: FinTech Research & Compliance Agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.fde_pipeline import FinTechFDEPipeline
from app.llm_wiki import FinTechLLMWiki
from app.ontology import ActionStatus, Issuer, OntologyRegistry
from app.quant_engine import CreditScoreInput, QuantCreditEngine


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


class BatchScreenItem(BaseModel):
    issuer_id: str = Field(..., min_length=1)
    name: Optional[str] = None
    ticker: Optional[str] = None
    sector: str = Field(default="FinTech")
    credit_rating: str = Field(default="A")
    period: str = Field(default="2025-Q4")
    financials: dict[str, float] = Field(default_factory=dict)


class BatchScreenRequest(BaseModel):
    items: list[BatchScreenItem] = Field(..., min_length=1, max_length=100)
    actor_role: str = Field(default="analyst")


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
    quant_engine = QuantCreditEngine()

    metrics_state: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "research_queries_total": 0,
        "guardrail_blocks_total": 0,
        "actions_decided_total": 0,
        "batch_screens_total": 0,
        "quant_scores_total": 0,
        "research_streams_total": 0,
    }

    app = FastAPI(
        title="P01 FinTech Research & Compliance Agent",
        version="1.1.0",
        description="Offline deterministic FinTech investment research, Ontology, LLM Wiki, and HITL compliance API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.pipeline = pipeline
    app.state.wiki = wiki
    app.state.ontology = ontology
    app.state.quant_engine = quant_engine
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

    @app.get("/api/v1/dashboard/overview")
    def dashboard_overview() -> dict[str, Any]:
        pending_hitl = sum(
            1 for a in pipeline.approval_queue.values() if a.status == ActionStatus.PENDING
        )
        return {
            "total_issuers": len(ontology.issuers),
            "risk_signals": len(ontology.risk_signals),
            "wiki_pages_count": len(list(wiki.entities_dir.glob("*.md"))),
            "pending_hitl_count": pending_hitl,
            "audit_events_count": len(pipeline.read_audit_trail()),
            "ontology_links_count": len(ontology.links),
        }

    @app.get("/api/v1/wiki/pages")
    def wiki_pages() -> dict[str, Any]:
        pages: list[dict[str, Any]] = []
        for path in sorted(wiki.entities_dir.glob("*.md")):
            meta = wiki._parse_entity_page(path)
            raw_text = meta.get("raw", "")
            preview_lines = [
                ln.strip()
                for ln in raw_text.splitlines()
                if ln.strip() and not ln.strip().startswith("---")
            ]
            preview = " ".join(preview_lines)[:220]
            pages.append(
                {
                    "id": meta["id"],
                    "title": meta["name"],
                    "path": str(path.relative_to(wiki.wiki_dir)),
                    "preview": preview,
                    "type": meta.get("type", "Issuer"),
                    "updated_at": meta.get("updated_at", ""),
                    "metrics": meta.get("metrics", {}),
                    "links": meta.get("links", []),
                }
            )
        return {"pages": pages, "total": len(pages)}

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

    @app.post("/api/v1/research/batch-screen")
    def research_batch_screen(payload: BatchScreenRequest) -> dict[str, Any]:
        metrics_state["batch_screens_total"] += 1
        results: list[dict[str, Any]] = []
        high_risk_count = 0

        for item in payload.items:
            if item.issuer_id not in ontology.issuers:
                ontology.register_issuer(
                    Issuer(
                        issuer_id=item.issuer_id,
                        name=item.name or item.issuer_id,
                        ticker=item.ticker or item.issuer_id.upper()[:8],
                        sector=item.sector,
                        credit_rating=item.credit_rating,
                    )
                )
            ratio_res = pipeline.compute_financial_ratios(
                issuer_id=item.issuer_id,
                period=item.period,
                financials=item.financials,
                register_in_ontology=True,
            )
            act = pipeline._maybe_enqueue_hitl_action(item.issuer_id)
            severities = {r["severity"] for r in ratio_res["triggered_risks"]}
            if "CRITICAL" in severities:
                risk_level = "CRITICAL"
                high_risk_count += 1
            elif "HIGH" in severities:
                risk_level = "HIGH"
                high_risk_count += 1
            else:
                risk_level = "LOW"

            results.append(
                {
                    "issuer_id": item.issuer_id,
                    "name": ontology.issuers[item.issuer_id].name,
                    "period": item.period,
                    "risk_level": risk_level,
                    "ratios": ratio_res["ratios"],
                    "triggered_risks": ratio_res["triggered_risks"],
                    "hitl_pending_action": act.model_dump() if act is not None else None,
                }
            )

        audit = pipeline._write_audit(
            "BATCH_SCREEN_COMPLETED",
            {
                "actor_role": payload.actor_role,
                "screened_count": len(results),
                "high_risk_count": high_risk_count,
                "issuer_ids": [r["issuer_id"] for r in results],
            },
        )
        return {
            "status": "completed",
            "screened_count": len(results),
            "high_risk_count": high_risk_count,
            "results": results,
            "audit_event_id": audit["event_id"],
        }

    @app.get("/api/v1/actions/pending")
    def actions_pending() -> dict[str, Any]:
        pending = [
            a.model_dump()
            for a in pipeline.approval_queue.values()
            if a.status == ActionStatus.PENDING
        ]
        return {"actions": pending, "total": len(pending)}

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

    @app.get("/api/v1/audit/logs")
    def audit_logs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        records = pipeline.read_audit_trail()
        recent = list(reversed(records[-limit:]))
        return {"logs": recent, "total": len(records)}

    @app.post("/api/v1/quant/credit-score")
    def quant_credit_score(payload: CreditScoreInput) -> dict[str, Any]:
        metrics_state["quant_scores_total"] += 1
        result = quant_engine.score_issuer(payload)
        audit = pipeline._write_audit(
            "QUANT_CREDIT_SCORED",
            {
                "issuer_id": result["issuer_id"],
                "period": result["period"],
                "credit_rating": result["credit_rating"],
                "composite_score": result["composite_score"],
                "z_score": result["altman_z_score"]["score"],
                "f_score": result["piotroski_f_score"]["score"],
            },
        )
        return {**result, "audit_event_id": audit["event_id"]}

    @app.get("/api/v1/research/stream")
    def research_stream(
        issuer_id: Optional[str] = Query(default=None),
        question: str = Query(default="Generate quantitative credit and compliance memo"),
        period: str = Query(default="2025-Q4"),
        total_debt: Optional[float] = Query(default=None),
        shareholders_equity: Optional[float] = Query(default=None),
        current_assets: Optional[float] = Query(default=None),
        current_liabilities: Optional[float] = Query(default=None),
        ebit: Optional[float] = Query(default=None),
        interest_expense: Optional[float] = Query(default=None),
        net_income: Optional[float] = Query(default=None),
    ) -> StreamingResponse:
        metrics_state["research_streams_total"] += 1
        guard = pipeline.scan_guardrails(question)

        def _sse_event(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        if guard["blocked"]:
            metrics_state["guardrail_blocks_total"] += 1
            audit = pipeline._write_audit(
                "RESEARCH_STREAM_BLOCKED",
                {"issuer_id": issuer_id, "findings": guard["findings"]},
            )

            def blocked_gen():
                yield _sse_event(
                    "blocked",
                    {
                        "status": "blocked",
                        "reason": "Compliance guardrail triggered",
                        "findings": guard["findings"],
                        "audit_event_id": audit["event_id"],
                    },
                )
                yield _sse_event("done", {"status": "blocked", "audit_event_id": audit["event_id"]})

            return StreamingResponse(
                blocked_gen(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        target_id = issuer_id or "issuer_alpha"
        issuer_obj = ontology.issuers.get(target_id)
        issuer_name = issuer_obj.name if issuer_obj else target_id
        ticker = issuer_obj.ticker if issuer_obj else target_id.upper()[:6]

        score_input = CreditScoreInput(
            issuer_id=target_id,
            period=period,
            total_debt=total_debt if total_debt is not None else 180.0,
            shareholders_equity=shareholders_equity if shareholders_equity is not None else 120.0,
            current_assets=current_assets if current_assets is not None else 140.0,
            current_liabilities=current_liabilities if current_liabilities is not None else 100.0,
            ebit=ebit if ebit is not None else 28.0,
            interest_expense=interest_expense if interest_expense is not None else 9.0,
            net_income=net_income if net_income is not None else 18.0,
        )
        quant_res = quant_engine.score_issuer(score_input)
        wiki_res = wiki.query(guard["redacted_text"])

        pending_count = sum(
            1
            for a in pipeline.approval_queue.values()
            if a.issuer_id == target_id and a.status == ActionStatus.PENDING
        )
        audit = pipeline._write_audit(
            "RESEARCH_STREAM_COMPLETED",
            {
                "issuer_id": target_id,
                "period": period,
                "credit_rating": quant_res["credit_rating"],
                "composite_score": quant_res["composite_score"],
            },
        )

        z = quant_res["altman_z_score"]
        f = quant_res["piotroski_f_score"]
        dcf = quant_res["dcf_valuation"]
        sub = quant_res["sub_scores"]
        citations = [c["entity_id"] for c in wiki_res.get("citations", [])]

        memo_chunks = [
            f"[RESEARCH MEMO :: {ticker} ({issuer_name}) | {period}]\n",
            f"Query: {guard['redacted_text']}\n\n",
            f"1. CREDIT TIER & SPREAD: Implied Rating {quant_res['credit_rating']} "
            f"(Composite {quant_res['composite_score']}/100, OAS {quant_res['implied_spread_bps']} bps, "
            f"1Y PD {quant_res['probability_of_default_1y_pct']}%).\n",
            f"2. ALTMAN Z-SCORE & PIOTROSKI F-SCORE: Z-Score = {z['score']} [{z['zone']}], "
            f"F-Score = {f['score']}/{f['max_score']}.\n",
            f"3. LEVERAGE & LIQUIDITY: Leverage Score {sub['leverage_score']}/100, "
            f"Liquidity Score {sub['liquidity_score']}/100, "
            f"D/E = {quant_res['ratios']['debt_to_equity']}x, "
            f"Current Ratio = {quant_res['ratios']['current_ratio']}x, "
            f"Interest Coverage = {quant_res['ratios']['interest_coverage']}x.\n",
            f"4. DCF VALUATION: Base FCF = {dcf['fcf_base']}, EV = {dcf['enterprise_value']}, "
            f"Implied Equity Value = {dcf['implied_equity_value']} "
            f"(WACC {dcf['wacc'] * 100:.1f}%, g {dcf['terminal_growth'] * 100:.2f}%).\n",
            f"5. KNOWLEDGE & COMPLIANCE: Wiki confidence {wiki_res['confidence']}, "
            f"Citations: {', '.join(citations) if citations else 'none'}. "
            f"Pending HITL actions for issuer: {pending_count}.\n",
        ]

        def event_generator():
            yield _sse_event(
                "stage",
                {
                    "stage": "guardrail",
                    "status": "passed",
                    "findings": guard["findings"],
                },
            )
            yield _sse_event(
                "stage",
                {
                    "stage": "quant_scoring",
                    "issuer_id": target_id,
                    "credit_rating": quant_res["credit_rating"],
                    "composite_score": quant_res["composite_score"],
                    "z_score": z["score"],
                    "z_zone": z["zone"],
                    "f_score": f["score"],
                },
            )
            for idx, chunk in enumerate(memo_chunks):
                yield _sse_event("token", {"index": idx, "text": chunk})
            yield _sse_event(
                "done",
                {
                    "status": "completed",
                    "issuer_id": target_id,
                    "credit_rating": quant_res["credit_rating"],
                    "audit_event_id": audit["event_id"],
                },
            )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
