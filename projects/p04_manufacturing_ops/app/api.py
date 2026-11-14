"""Production FastAPI application for Project P04: Manufacturing Ops Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.fde_pipeline import ManufacturingFDEPipeline
from app.llm_wiki import WIKI_LINK_RE, ManufacturingLLMWiki
from app.ontology import ActionStatus, ManufacturingOntologyRegistry
from app.telemetry_stream import TelemetryRingBuffer, WorkOrderStateMachine


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


class TelemetrySample(BaseModel):
    equipment_id: str
    readings: dict[str, float] = Field(default_factory=dict)
    operating_hours: float = 0.0


class PredictiveMaintenanceRequest(BaseModel):
    samples: list[TelemetrySample] = Field(default_factory=list)


class TelemetryStreamSample(BaseModel):
    equipment_id: str
    readings: dict[str, float] = Field(default_factory=dict)
    timestamp: str | None = None


class TelemetryIngestBatchRequest(BaseModel):
    samples: list[TelemetryStreamSample] = Field(default_factory=list)


class WorkOrderCreateRequest(BaseModel):
    equipment_id: str
    title: str
    fault_code: str | None = None
    sop_id: str | None = None
    priority: str = "HIGH"
    actor: str = "scada-operator"
    notes: str = ""


class WorkOrderTransitionRequest(BaseModel):
    work_order_id: str
    target_status: str
    actor: str = "scada-operator"
    assigned_to: str | None = None
    loto_tag_id: str | None = None
    notes: str = ""


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
    telemetry_buffer = TelemetryRingBuffer(window_size=30, z_threshold=2.5, min_samples=5)
    work_order_sm = WorkOrderStateMachine(seed_defaults=True)

    metrics_state: dict[str, int] = {
        "requests_total": 0,
        "wiki_ingests_total": 0,
        "wiki_lints_total": 0,
        "diagnoses_total": 0,
        "incidents_total": 0,
        "hitl_approvals_total": 0,
        "hitl_rejections_total": 0,
        "telemetry_batches_total": 0,
        "telemetry_anomalies_total": 0,
        "workorder_transitions_total": 0,
    }

    app = FastAPI(
        title="P04 Smart Manufacturing & Equipment Ops Agent",
        version="1.2.0",
        description="Offline deterministic Manufacturing Ontology + IIoT SCADA Telemetry + LOTO Work-Order + HITL FDE Pipeline.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = ont_registry
    app.state.wiki = wiki
    app.state.pipeline = pipeline
    app.state.telemetry_buffer = telemetry_buffer
    app.state.work_order_sm = work_order_sm
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

    @app.get("/api/v1/dashboard/overview")
    def dashboard_overview() -> dict[str, Any]:
        wiki_pages_count = len(list(wiki.entities_dir.glob("*.md")))
        pending_actions = pipeline.get_pending_actions()
        status_breakdown: dict[str, int] = {}
        for eq in ont_registry.equipment.values():
            key = eq.status.value
            status_breakdown[key] = status_breakdown.get(key, 0) + 1

        return {
            "service": "p04-manufacturing-ops",
            "equipment_count": len(ont_registry.equipment),
            "fault_codes_count": len(ont_registry.fault_codes),
            "sops_count": len(ont_registry.sops),
            "wiki_pages_count": wiki_pages_count,
            "pending_hitl_shutdowns": len(pending_actions),
            "audit_logs_count": len(pipeline.audit_trail),
            "equipment_status_breakdown": status_breakdown,
            "equipment": [eq.model_dump() for eq in ont_registry.equipment.values()],
            "fault_codes": [fc.model_dump() for fc in ont_registry.fault_codes.values()],
            "sops": [sop.model_dump() for sop in ont_registry.sops.values()],
            "links": [lnk.model_dump() for lnk in ont_registry.links],
            "work_orders": [wo.model_dump() for wo in work_order_sm.list_work_orders()],
            "telemetry_snapshots": telemetry_buffer.get_all_snapshots(),
        }

    @app.get("/api/v1/wiki/pages")
    def wiki_pages() -> dict[str, Any]:
        pages: list[dict[str, Any]] = []
        for md_file in sorted(wiki.entities_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            meta, body = wiki._parse_frontmatter(text)
            entity_id = str(meta.get("entity_id", md_file.stem))
            title = str(meta.get("title", entity_id))
            entity_type = str(meta.get("entity_type", "Unknown"))
            updated_at = str(meta.get("updated_at", ""))
            clean_lines = [
                ln.strip()
                for ln in body.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            preview = " ".join(clean_lines)[:260]
            wiki_links = sorted(set(WIKI_LINK_RE.findall(body)))
            pages.append(
                {
                    "id": entity_id,
                    "title": title,
                    "entity_type": entity_type,
                    "path": str(md_file),
                    "preview": preview,
                    "updated_at": updated_at,
                    "wiki_links": wiki_links,
                    "content": body.strip(),
                }
            )
        return {"pages": pages, "total": len(pages)}

    @app.get("/api/v1/actions/pending")
    def actions_pending() -> dict[str, Any]:
        pending = [a.model_dump() for a in pipeline.get_pending_actions()]
        return {"actions": pending, "total": len(pending)}

    @app.get("/api/v1/audit/logs")
    def audit_logs() -> dict[str, Any]:
        logs = pipeline.get_audit_trail()
        return {"logs": logs, "total": len(logs)}

    @app.post("/api/v1/ops/predictive-maintenance")
    def ops_predictive_maintenance(
        payload: PredictiveMaintenanceRequest | None = None,
    ) -> dict[str, Any]:
        samples = [s.model_dump() for s in payload.samples] if payload else []
        try:
            return pipeline.generate_predictive_maintenance(samples=samples)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/telemetry/ingest-batch")
    def telemetry_ingest_batch(payload: TelemetryIngestBatchRequest) -> dict[str, Any]:
        for sample in payload.samples:
            if ont_registry.get_equipment(sample.equipment_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown equipment_id: {sample.equipment_id}",
                )
        metrics_state["telemetry_batches_total"] += 1
        result = telemetry_buffer.ingest_batch([s.model_dump() for s in payload.samples])
        if result["anomaly_count"] > 0:
            metrics_state["telemetry_anomalies_total"] += int(result["anomaly_count"])
            for anomaly in result["anomalies"]:
                pipeline._record_audit(
                    event_type="TELEMETRY_ZSCORE_ANOMALY",
                    equipment_id=anomaly["equipment_id"],
                    actor="telemetry-ring-buffer",
                    detail=anomaly,
                )
        return result

    @app.get("/api/v1/telemetry/snapshots")
    def telemetry_snapshots() -> dict[str, Any]:
        return {
            "snapshots": telemetry_buffer.get_all_snapshots(),
            "recent_anomalies": telemetry_buffer.get_recent_anomalies(),
        }

    @app.get("/api/v1/workorders")
    def list_workorders() -> dict[str, Any]:
        orders = [wo.model_dump() for wo in work_order_sm.list_work_orders()]
        return {"work_orders": orders, "total": len(orders)}

    @app.post("/api/v1/workorders")
    def create_workorder(payload: WorkOrderCreateRequest) -> dict[str, Any]:
        if ont_registry.get_equipment(payload.equipment_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown equipment_id: {payload.equipment_id}",
            )
        wo = work_order_sm.create_work_order(
            equipment_id=payload.equipment_id,
            title=payload.title,
            fault_code=payload.fault_code,
            sop_id=payload.sop_id,
            priority=payload.priority,
            actor=payload.actor,
            notes=payload.notes,
        )
        pipeline._record_audit(
            event_type="WORK_ORDER_CREATED",
            equipment_id=wo.equipment_id,
            actor=payload.actor,
            detail={"work_order_id": wo.work_order_id, "title": wo.title},
        )
        return {"work_order": wo.model_dump()}

    @app.post("/api/v1/workorders/transition")
    def transition_workorder(payload: WorkOrderTransitionRequest) -> dict[str, Any]:
        try:
            wo = work_order_sm.transition(
                work_order_id=payload.work_order_id,
                target_status=payload.target_status,
                actor=payload.actor,
                assigned_to=payload.assigned_to,
                loto_tag_id=payload.loto_tag_id,
                notes=payload.notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        metrics_state["workorder_transitions_total"] += 1
        pipeline._record_audit(
            event_type="WORK_ORDER_TRANSITION",
            equipment_id=wo.equipment_id,
            actor=payload.actor,
            detail={
                "work_order_id": wo.work_order_id,
                "status": wo.status.value,
                "loto_tag_id": wo.loto_tag_id,
                "assigned_to": wo.assigned_to,
            },
        )
        return {
            "work_order": wo.model_dump(),
            "audit_trail_count": len(pipeline.audit_trail),
        }

    return app


app = create_app()
