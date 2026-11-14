"""Pytest suite for Project P04: Smart Manufacturing & Equipment Ops Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from app.fde_pipeline import ManufacturingFDEPipeline
from app.llm_wiki import ManufacturingLLMWiki
from app.ontology import (
    ActionStatus,
    ActionType,
    EquipmentStatus,
    ManufacturingOntologyRegistry,
    Severity,
)
from app.telemetry_stream import (
    TelemetryRingBuffer,
    WorkOrderStateMachine,
    WorkOrderStatus,
)


def test_ontology_telemetry_diagnosis_and_fault_to_sop_resolution() -> None:
    registry = ManufacturingOntologyRegistry(seed_defaults=True)

    # Warning level temperature on CNC-LINE1-01 (warn=75, critical=90)
    warn_diag = registry.diagnose("CNC-LINE1-01", readings={"temperature_c": 80.0})
    assert warn_diag.highest_severity == Severity.WARNING
    assert warn_diag.requires_shutdown is False
    assert warn_diag.equipment_status == EquipmentStatus.DEGRADED
    assert any(fc.code == "ERR-CNC-402" for fc in warn_diag.fault_codes)
    assert any(sop.sop_id == "SOP-CNC-001" for sop in warn_diag.sops)

    # Critical level temperature & vibration
    crit_diag = registry.diagnose(
        "CNC-LINE1-01",
        readings={"temperature_c": 95.5, "vibration_mms": 8.2},
    )
    assert crit_diag.highest_severity == Severity.CRITICAL
    assert crit_diag.requires_shutdown is True
    assert crit_diag.equipment_status == EquipmentStatus.FAULTED
    fault_codes = {fc.code for fc in crit_diag.fault_codes}
    assert {"ERR-CNC-401", "ERR-VIB-301"}.issubset(fault_codes)
    sop_ids = {sop.sop_id for sop in crit_diag.sops}
    assert {"SOP-CNC-001", "SOP-VIB-002"}.issubset(sop_ids)


def test_llm_wiki_ingest_persistence_and_query(tmp_path: Path) -> None:
    wiki = ManufacturingLLMWiki(tmp_path / "wiki")
    page_path = wiki.ingest(
        entity_id="CNC-LINE1-01",
        entity_type="Equipment",
        title="5-Axis CNC Machining Center #1",
        content="Spindle cooling system requires [[SOP-CNC-001]] on overheat.",
        links=["SOP-CNC-001", "ERR-CNC-401"],
        metadata={"line_id": "LINE-1"},
    )
    assert page_path.exists()
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()

    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    log_text = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "[[CNC-LINE1-01]]" in index_text
    assert "INGEST" in log_text

    hits = wiki.query("spindle cooling CNC-LINE1-01")
    assert len(hits) == 1
    assert hits[0]["entity_id"] == "CNC-LINE1-01"
    assert "SOP-CNC-001" in hits[0]["wiki_links"]
    assert "ERR-CNC-401" in hits[0]["wiki_links"]


def test_llm_wiki_lint_detects_unmapped_faults_outdated_sops_and_orphans(
    tmp_path: Path,
) -> None:
    wiki = ManufacturingLLMWiki(tmp_path / "wiki")

    # 1. Unmapped fault code (no SOP link)
    wiki.ingest(
        entity_id="ERR-UNMAPPED-999",
        entity_type="FaultCode",
        title="Unmapped Servo Fault",
        content="Servo drive overcurrent with no SOP yet.",
        links=[],
        metadata={"recommended_sop_id": ""},
    )
    # 2. Outdated SOP revision
    wiki.ingest(
        entity_id="SOP-OLD-001",
        entity_type="MaintenanceSOP",
        title="Legacy Conveyor Belt Check",
        content="Old revision procedure.",
        links=[],
        metadata={"revision": "v1.0", "latest_revision": "v2.0"},
    )
    # 3. Orphan equipment (no [[wiki_links]])
    wiki.ingest(
        entity_id="CONV-ORPHAN-01",
        entity_type="Equipment",
        title="Orphan Transfer Conveyor",
        content="No SOPs or fault codes linked.",
        links=[],
    )

    report = wiki.lint()
    assert report["healthy"] is False
    assert "ERR-UNMAPPED-999" in report["unmapped_fault_codes"]
    assert "SOP-OLD-001" in report["outdated_sops"]
    assert "CONV-ORPHAN-01" in report["orphan_equipment"]
    assert report["counts"]["total_issues"] >= 3


def test_fde_pipeline_emergency_shutdown_hitl_approval_and_audit(tmp_path: Path) -> None:
    registry = ManufacturingOntologyRegistry(seed_defaults=True)
    wiki = ManufacturingLLMWiki(tmp_path / "wiki")
    pipeline = ManufacturingFDEPipeline(registry=registry, wiki=wiki)

    incident = pipeline.handle_incident(
        equipment_id="CNC-LINE1-01",
        sensor_readings={"temperature_c": 96.0},
        reporter="edge-plc-01",
    )
    assert incident["hitl_required"] is True
    action_data = incident["action"]
    assert action_data is not None
    assert action_data["action_type"] == ActionType.EMERGENCY_SHUTDOWN.value
    assert action_data["status"] == ActionStatus.PENDING_APPROVAL.value

    # Equipment should be FAULTED, NOT yet SHUTDOWN before safety-officer approval
    eq = registry.get_equipment("CNC-LINE1-01")
    assert eq is not None
    assert eq.status == EquipmentStatus.FAULTED

    # Safety officer approves emergency shutdown
    approved_action = pipeline.approve_action(
        action_id=action_data["action_id"],
        approved=True,
        safety_officer="officer-zhang",
        reason="Verified thermal camera hotspot; shutting down line.",
    )
    assert approved_action.status == ActionStatus.APPROVED
    assert approved_action.approved_by == "officer-zhang"
    assert eq.status == EquipmentStatus.SHUTDOWN

    audit = pipeline.get_audit_trail()
    event_types = [e["event_type"] for e in audit]
    assert "HITL_GATE_TRIGGERED" in event_types
    assert "HITL_DECISION" in event_types


def test_fde_pipeline_hitl_rejection_keeps_equipment_out_of_shutdown(
    tmp_path: Path,
) -> None:
    registry = ManufacturingOntologyRegistry(seed_defaults=True)
    wiki = ManufacturingLLMWiki(tmp_path / "wiki")
    pipeline = ManufacturingFDEPipeline(registry=registry, wiki=wiki)

    incident = pipeline.handle_incident(
        equipment_id="MOLD-LINE2-01",
        sensor_readings={"pressure_bar": 225.0},
        reporter="edge-plc-02",
    )
    action_id = incident["action"]["action_id"]

    rejected = pipeline.approve_action(
        action_id=action_id,
        approved=False,
        safety_officer="officer-li",
        reason="Sensor calibration drift confirmed; manual bleed in progress.",
    )
    assert rejected.status == ActionStatus.REJECTED
    eq = registry.get_equipment("MOLD-LINE2-01")
    assert eq is not None
    assert eq.status == EquipmentStatus.FAULTED


def test_fastapi_endpoints_and_request_id_middleware(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "api_wiki")
    client = TestClient(app)

    # 1. Health & Ready & Request-ID propagation
    r_health = client.get("/health", headers={"X-Request-ID": "req-p04-001"})
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert r_health.headers["X-Request-ID"] == "req-p04-001"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert "X-Request-ID" in r_ready.headers

    # 2. Wiki ingest & lint
    r_ingest = client.post(
        "/api/v1/wiki/ingest",
        json={
            "entity_id": "SOP-TEST-01",
            "entity_type": "MaintenanceSOP",
            "title": "Test SOP",
            "content": "Step 1: Inspect.",
            "links": ["CNC-LINE1-01"],
            "metadata": {"revision": "v2.0", "latest_revision": "v2.0"},
        },
    )
    assert r_ingest.status_code == 200
    assert r_ingest.json()["entity_id"] == "SOP-TEST-01"

    r_lint = client.post("/api/v1/wiki/lint")
    assert r_lint.status_code == 200
    assert r_lint.json()["healthy"] is True

    # 3. Ontology diagnose
    r_diag = client.post(
        "/api/v1/ontology/diagnose",
        json={"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 92.0}},
    )
    assert r_diag.status_code == 200
    assert r_diag.json()["requires_shutdown"] is True

    # 4. Incident + HITL approve
    r_inc = client.post(
        "/api/v1/ops/incident",
        json={
            "equipment_id": "CNC-LINE1-01",
            "sensor_readings": {"vibration_mms": 9.0},
            "reporter": "scada-node-1",
        },
    )
    assert r_inc.status_code == 200
    inc_body = r_inc.json()
    assert inc_body["hitl_required"] is True
    action_id = inc_body["action"]["action_id"]

    r_approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "approved": True,
            "safety_officer": "officer-wang",
            "reason": "Confirmed vibration spike",
        },
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["action"]["status"] == "APPROVED"
    assert r_approve.json()["equipment_status"] == "SHUTDOWN"

    # 5. Metrics
    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    m = r_metrics.json()
    assert m["incidents_total"] == 1
    assert m["hitl_approvals_total"] == 1
    assert m["pending_hitl_actions"] == 0


def test_api_error_handling_for_missing_equipment_and_double_approval(
    tmp_path: Path,
) -> None:
    app = create_app(wiki_dir=tmp_path / "err_wiki")
    client = TestClient(app)

    r_missing = client.post(
        "/api/v1/ontology/diagnose",
        json={"equipment_id": "UNKNOWN-EQ", "readings": {"temperature_c": 50.0}},
    )
    assert r_missing.status_code == 404

    r_inc = client.post(
        "/api/v1/ops/incident",
        json={"equipment_id": "CNC-LINE1-01", "sensor_readings": {"temperature_c": 95.0}},
    )
    action_id = r_inc.json()["action"]["action_id"]

    r_first = client.post(
        "/api/v1/actions/approve",
        json={"action_id": action_id, "approved": True, "safety_officer": "officer-a"},
    )
    assert r_first.status_code == 200

    # Second approval on already-decided action should return 409 Conflict
    r_second = client.post(
        "/api/v1/actions/approve",
        json={"action_id": action_id, "approved": False, "safety_officer": "officer-b"},
    )
    assert r_second.status_code == 409


def test_cors_headers_and_dashboard_overview(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "cors_wiki")
    client = TestClient(app)

    r_preflight = client.options(
        "/api/v1/dashboard/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_preflight.status_code == 200
    assert r_preflight.headers.get("access-control-allow-origin") == "*"

    r_overview = client.get(
        "/api/v1/dashboard/overview",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r_overview.status_code == 200
    assert r_overview.headers.get("access-control-allow-origin") == "*"
    data = r_overview.json()
    assert data["equipment_count"] >= 2
    assert data["fault_codes_count"] >= 4
    assert data["sops_count"] >= 3
    assert data["wiki_pages_count"] >= 9
    assert data["pending_hitl_shutdowns"] == 0
    assert data["audit_logs_count"] == 0


def test_wiki_pages_pending_actions_and_audit_logs(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "enterprise_wiki")
    client = TestClient(app)

    r_pages = client.get("/api/v1/wiki/pages")
    assert r_pages.status_code == 200
    pages_body = r_pages.json()
    assert pages_body["total"] >= 9
    first_page = pages_body["pages"][0]
    assert {"id", "title", "path", "preview"}.issubset(first_page.keys())

    # Trigger HITL emergency shutdown
    r_inc = client.post(
        "/api/v1/ops/incident",
        json={
            "equipment_id": "CNC-LINE1-01",
            "sensor_readings": {"temperature_c": 95.0},
            "reporter": "plc-line1",
        },
    )
    assert r_inc.status_code == 200
    action_id = r_inc.json()["action"]["action_id"]

    r_pending = client.get("/api/v1/actions/pending")
    assert r_pending.status_code == 200
    assert r_pending.json()["total"] == 1
    assert r_pending.json()["actions"][0]["action_id"] == action_id

    # Approve and verify pending clears and audit logs record both events
    r_app = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "approved": True,
            "safety_officer": "officer-chen",
            "reason": "Verified thermal anomaly",
        },
    )
    assert r_app.status_code == 200

    r_pending_after = client.get("/api/v1/actions/pending")
    assert r_pending_after.status_code == 200
    assert r_pending_after.json()["total"] == 0

    r_audit = client.get("/api/v1/audit/logs")
    assert r_audit.status_code == 200
    logs = r_audit.json()["logs"]
    event_types = [entry["event_type"] for entry in logs]
    assert "HITL_GATE_TRIGGERED" in event_types
    assert "HITL_DECISION" in event_types


def test_predictive_maintenance_batch_and_error_handling(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "pm_wiki")
    client = TestClient(app)

    # Default empty body evaluates all seeded equipment
    r_default = client.post("/api/v1/ops/predictive-maintenance", json={})
    assert r_default.status_code == 200
    default_body = r_default.json()
    assert default_body["equipment_evaluated"] >= 2
    assert len(default_body["schedules"]) >= 2

    # Batch telemetry evaluation with critical and nominal equipment
    r_batch = client.post(
        "/api/v1/ops/predictive-maintenance",
        json={
            "samples": [
                {
                    "equipment_id": "CNC-LINE1-01",
                    "readings": {"temperature_c": 95.0, "vibration_mms": 8.5},
                    "operating_hours": 1500.0,
                },
                {
                    "equipment_id": "MOLD-LINE2-01",
                    "readings": {"pressure_bar": 120.0, "temperature_c": 55.0},
                    "operating_hours": 100.0,
                },
            ]
        },
    )
    assert r_batch.status_code == 200
    batch_body = r_batch.json()
    assert batch_body["equipment_evaluated"] == 2
    assert batch_body["critical_count"] == 1
    cnc_sched = next(
        s for s in batch_body["schedules"] if s["equipment_id"] == "CNC-LINE1-01"
    )
    mold_sched = next(
        s for s in batch_body["schedules"] if s["equipment_id"] == "MOLD-LINE2-01"
    )
    assert cnc_sched["risk_tier"] == "CRITICAL"
    assert cnc_sched["health_score"] < mold_sched["health_score"]
    assert cnc_sched["estimated_mtbf_hours"] < mold_sched["estimated_mtbf_hours"]

    # Unknown equipment returns 404
    r_unknown = client.post(
        "/api/v1/ops/predictive-maintenance",
        json={"samples": [{"equipment_id": "NO-SUCH-EQ", "readings": {}}]},
    )
    assert r_unknown.status_code == 404


def test_telemetry_ring_buffer_zscore_anomaly_detection() -> None:
    ring = TelemetryRingBuffer(window_size=10, z_threshold=2.5, min_samples=5)

    # Seed 6 nominal baseline samples for CNC-LINE1-01
    baseline_samples = [
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 62.0, "vibration_mms": 2.0}},
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 62.5, "vibration_mms": 2.1}},
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 61.8, "vibration_mms": 1.9}},
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 62.2, "vibration_mms": 2.0}},
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 62.1, "vibration_mms": 2.05}},
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 62.3, "vibration_mms": 1.95}},
    ]
    baseline_res = ring.ingest_batch(baseline_samples)
    assert baseline_res["ingested_count"] == 6
    assert baseline_res["anomaly_count"] == 0

    # Inject sudden spindle overheat + vibration spike
    spike_res = ring.ingest_batch(
        [
            {
                "equipment_id": "CNC-LINE1-01",
                "readings": {"temperature_c": 88.5, "vibration_mms": 6.8},
            }
        ]
    )
    assert spike_res["anomaly_count"] == 2
    anomalous_metrics = {a["metric"] for a in spike_res["anomalies"]}
    assert anomalous_metrics == {"temperature_c", "vibration_mms"}
    for anomaly in spike_res["anomalies"]:
        assert anomaly["z_score"] >= 2.5

    # Constant hydraulic pressure baseline should also detect sudden surge
    for _ in range(5):
        ring.ingest_sample("MOLD-LINE2-01", {"pressure_bar": 140.0})
    surge_res = ring.ingest_sample("MOLD-LINE2-01", {"pressure_bar": 215.0})
    assert surge_res["anomaly_detected"] is True
    assert surge_res["anomalies"][0]["metric"] == "pressure_bar"


def test_work_order_state_machine_loto_transitions() -> None:
    import pytest

    sm = WorkOrderStateMachine(seed_defaults=False)
    wo = sm.create_work_order(
        equipment_id="CNC-LINE1-01",
        title="Spindle Bearing Replacement",
        fault_code="ERR-CNC-401",
        sop_id="SOP-CNC-001",
    )
    assert wo.status == WorkOrderStatus.OPEN

    # Invalid jump OPEN -> LOCKOUT_TAGOUT must fail
    with pytest.raises(ValueError):
        sm.transition(wo.work_order_id, WorkOrderStatus.LOCKOUT_TAGOUT, actor="tech-a")

    # Valid LOTO sequence: OPEN -> ASSIGNED -> LOCKOUT_TAGOUT -> VERIFIED -> CLOSED
    wo = sm.transition(wo.work_order_id, "ASSIGNED", actor="lead-1", assigned_to="tech-wang")
    assert wo.status == WorkOrderStatus.ASSIGNED
    assert wo.assigned_to == "tech-wang"

    wo = sm.transition(
        wo.work_order_id,
        WorkOrderStatus.LOCKOUT_TAGOUT,
        actor="tech-wang",
        loto_tag_id="LOTO-480V-09",
    )
    assert wo.status == WorkOrderStatus.LOCKOUT_TAGOUT
    assert wo.loto_tag_id == "LOTO-480V-09"

    wo = sm.transition(wo.work_order_id, WorkOrderStatus.VERIFIED, actor="safety-officer-1")
    assert wo.status == WorkOrderStatus.VERIFIED
    assert wo.verified_by == "safety-officer-1"

    wo = sm.transition(wo.work_order_id, WorkOrderStatus.CLOSED, actor="shift-supervisor")
    assert wo.status == WorkOrderStatus.CLOSED
    assert len(wo.history) == 5

    # Unknown work order raises KeyError
    with pytest.raises(KeyError):
        sm.transition("WO-DOES-NOT-EXIST", WorkOrderStatus.ASSIGNED)


def test_api_telemetry_ingest_batch_and_workorder_transitions(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "scada_wiki")
    client = TestClient(app)

    # 1. Ingest 5 baseline samples then 1 spike via /api/v1/telemetry/ingest-batch
    samples = [
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 60.0 + i * 0.1, "vibration_mms": 2.0}}
        for i in range(5)
    ]
    samples.append(
        {"equipment_id": "CNC-LINE1-01", "readings": {"temperature_c": 94.0, "vibration_mms": 7.9}}
    )
    r_batch = client.post("/api/v1/telemetry/ingest-batch", json={"samples": samples})
    assert r_batch.status_code == 200
    batch_data = r_batch.json()
    assert batch_data["ingested_count"] == 6
    assert batch_data["anomaly_count"] == 2
    assert "CNC-LINE1-01" in batch_data["equipment_snapshots"]

    # Unknown equipment in telemetry batch -> 404
    r_bad_eq = client.post(
        "/api/v1/telemetry/ingest-batch",
        json={"samples": [{"equipment_id": "UNKNOWN-CELL", "readings": {"temperature_c": 50.0}}]},
    )
    assert r_bad_eq.status_code == 404

    # 2. Transition seeded work order WO-LOTO-101: OPEN -> ASSIGNED -> LOCKOUT_TAGOUT
    r_assign = client.post(
        "/api/v1/workorders/transition",
        json={
            "work_order_id": "WO-LOTO-101",
            "target_status": "ASSIGNED",
            "actor": "shift-lead",
            "assigned_to": "tech-zhao",
        },
    )
    assert r_assign.status_code == 200
    assert r_assign.json()["work_order"]["status"] == "ASSIGNED"

    # Invalid skip ASSIGNED -> CLOSED -> 409 Conflict
    r_skip = client.post(
        "/api/v1/workorders/transition",
        json={"work_order_id": "WO-LOTO-101", "target_status": "CLOSED", "actor": "shift-lead"},
    )
    assert r_skip.status_code == 409

    # Unknown work order -> 404
    r_missing_wo = client.post(
        "/api/v1/workorders/transition",
        json={"work_order_id": "WO-MISSING", "target_status": "ASSIGNED", "actor": "shift-lead"},
    )
    assert r_missing_wo.status_code == 404


