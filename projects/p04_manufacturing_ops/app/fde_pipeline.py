"""Manufacturing Forward-Deployed Engineering (FDE) Pipeline.

Orchestrates:
1. Telemetry anomaly diagnosis via ManufacturingOntologyRegistry.
2. Root-cause & SOP retrieval from ManufacturingLLMWiki + Ontology.
3. Incident persistence into the Wiki knowledge graph.
4. Human-in-the-Loop (HITL) safety-officer approval gate for emergency
   shutdowns and high-risk actions, with full immutable audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.llm_wiki import ManufacturingLLMWiki
from app.ontology import (
    ActionStatus,
    ActionType,
    DiagnosisResult,
    EquipmentStatus,
    ManufacturingOntologyRegistry,
    OpsAction,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManufacturingFDEPipeline:
    """End-to-end deterministic FDE pipeline for industrial equipment ops."""

    def __init__(
        self,
        registry: ManufacturingOntologyRegistry,
        wiki: ManufacturingLLMWiki,
        sync_wiki_on_init: bool = True,
    ) -> None:
        self.registry = registry
        self.wiki = wiki
        self.actions: dict[str, OpsAction] = {}
        self.audit_trail: list[dict[str, Any]] = []
        if sync_wiki_on_init:
            self.wiki.ingest_from_ontology(self.registry)

    def _record_audit(
        self,
        event_type: str,
        equipment_id: str,
        detail: dict[str, Any],
        actor: str = "fde-pipeline",
    ) -> None:
        entry = {
            "audit_id": f"AUD-{uuid4().hex[:8].upper()}",
            "timestamp": _utc_now_iso(),
            "event_type": event_type,
            "equipment_id": equipment_id,
            "actor": actor,
            "detail": detail,
        }
        self.audit_trail.append(entry)

    def handle_incident(
        self,
        equipment_id: str,
        sensor_readings: dict[str, float] | None = None,
        fault_code: str | None = None,
        reporter: str = "iot-gateway",
    ) -> dict[str, Any]:
        """Diagnose equipment telemetry, retrieve SOPs from Wiki/Ontology, and gate actions."""
        diagnosis: DiagnosisResult = self.registry.diagnose(
            equipment_id=equipment_id,
            readings=sensor_readings or {},
            fault_code=fault_code,
        )

        # Retrieve relevant context from Wiki
        search_terms = [equipment_id]
        search_terms.extend(fc.code for fc in diagnosis.fault_codes)
        search_terms.extend(sop.sop_id for sop in diagnosis.sops)
        wiki_hits = self.wiki.query(" ".join(search_terms), top_k=5)

        incident_id = f"INC-{uuid4().hex[:8].upper()}"
        action: OpsAction | None = None

        if diagnosis.requires_shutdown:
            primary_fc = diagnosis.fault_codes[0].code if diagnosis.fault_codes else fault_code
            primary_sop = diagnosis.sops[0].sop_id if diagnosis.sops else None
            action = OpsAction(
                action_type=ActionType.EMERGENCY_SHUTDOWN,
                equipment_id=equipment_id,
                fault_code=primary_fc,
                sop_id=primary_sop,
                status=ActionStatus.PENDING_APPROVAL,
                requires_hitl=True,
                requested_by=reporter,
            )
            self.actions[action.action_id] = action
            self._record_audit(
                event_type="HITL_GATE_TRIGGERED",
                equipment_id=equipment_id,
                actor=reporter,
                detail={
                    "incident_id": incident_id,
                    "action_id": action.action_id,
                    "action_type": action.action_type.value,
                    "fault_code": primary_fc,
                    "sop_id": primary_sop,
                },
            )
        elif diagnosis.alerts or diagnosis.fault_codes:
            primary_fc = diagnosis.fault_codes[0].code if diagnosis.fault_codes else fault_code
            primary_sop = diagnosis.sops[0].sop_id if diagnosis.sops else None
            action = OpsAction(
                action_type=ActionType.CREATE_WORK_ORDER,
                equipment_id=equipment_id,
                fault_code=primary_fc,
                sop_id=primary_sop,
                status=ActionStatus.EXECUTED,
                requires_hitl=False,
                requested_by=reporter,
                approved_by="auto-policy",
                decision_reason="Non-critical alert; automated maintenance work order issued.",
                decided_at=_utc_now_iso(),
            )
            self.actions[action.action_id] = action
            self._record_audit(
                event_type="WORK_ORDER_CREATED",
                equipment_id=equipment_id,
                actor="auto-policy",
                detail={
                    "incident_id": incident_id,
                    "action_id": action.action_id,
                    "fault_code": primary_fc,
                    "sop_id": primary_sop,
                },
            )
        else:
            self._record_audit(
                event_type="TELEMETRY_NOMINAL",
                equipment_id=equipment_id,
                actor=reporter,
                detail={"incident_id": incident_id, "readings": sensor_readings or {}},
            )

        # Persist incident into Wiki
        links = [equipment_id]
        links.extend(fc.code for fc in diagnosis.fault_codes)
        links.extend(sop.sop_id for sop in diagnosis.sops)
        alert_summary = (
            "\n".join(f"- **{a.severity.value}**: {a.message}" for a in diagnosis.alerts)
            or "- No threshold violations."
        )
        self.wiki.ingest(
            entity_id=incident_id,
            entity_type="Incident",
            title=f"Incident on {equipment_id} ({diagnosis.highest_severity.value})",
            content=(
                f"Reporter: `{reporter}`\n\n"
                f"Requires Shutdown: `{diagnosis.requires_shutdown}`\n\n"
                f"### Alerts\n{alert_summary}"
            ),
            links=links,
            metadata={
                "equipment_id": equipment_id,
                "severity": diagnosis.highest_severity.value,
                "action_id": action.action_id if action else "",
            },
        )

        return {
            "incident_id": incident_id,
            "diagnosis": diagnosis.model_dump(),
            "wiki_context": wiki_hits,
            "action": action.model_dump() if action else None,
            "hitl_required": bool(action and action.requires_hitl),
        }

    def approve_action(
        self,
        action_id: str,
        approved: bool,
        safety_officer: str,
        reason: str = "",
    ) -> OpsAction:
        """Safety-officer HITL decision for a pending OpsAction."""
        action = self.actions.get(action_id)
        if action is None:
            raise KeyError(f"Unknown action_id: {action_id}")
        if action.status != ActionStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Action {action_id} is already finalized with status {action.status.value}"
            )

        action.approved_by = safety_officer
        action.decision_reason = reason or (
            "Approved by safety officer" if approved else "Rejected by safety officer"
        )
        action.decided_at = _utc_now_iso()

        if approved:
            action.status = ActionStatus.APPROVED
            if action.action_type == ActionType.EMERGENCY_SHUTDOWN:
                eq = self.registry.get_equipment(action.equipment_id)
                if eq is not None:
                    eq.status = EquipmentStatus.SHUTDOWN
        else:
            action.status = ActionStatus.REJECTED

        self._record_audit(
            event_type="HITL_DECISION",
            equipment_id=action.equipment_id,
            actor=safety_officer,
            detail={
                "action_id": action.action_id,
                "action_type": action.action_type.value,
                "decision": action.status.value,
                "reason": action.decision_reason,
            },
        )
        self.wiki._append_log(
            "HITL_DECISION",
            f"action={action.action_id} status={action.status.value} officer={safety_officer}",
        )
        return action

    def get_action(self, action_id: str) -> OpsAction | None:
        return self.actions.get(action_id)

    def get_pending_actions(self) -> list[OpsAction]:
        return [
            action
            for action in self.actions.values()
            if action.status == ActionStatus.PENDING_APPROVAL
        ]

    def get_audit_trail(self) -> list[dict[str, Any]]:
        return list(self.audit_trail)

    def generate_predictive_maintenance(
        self,
        samples: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Deterministic batch equipment health-score & MTBF maintenance schedule."""
        eval_items: list[dict[str, Any]] = list(samples or [])
        if not eval_items:
            eval_items = [
                {"equipment_id": eq_id, "readings": {}, "operating_hours": 120.0}
                for eq_id in sorted(self.registry.equipment.keys())
            ]

        schedules: list[dict[str, Any]] = []
        critical_count = 0

        for item in eval_items:
            equipment_id = str(item["equipment_id"])
            readings: dict[str, float] = dict(item.get("readings") or {})
            operating_hours = float(item.get("operating_hours") or 0.0)

            eq = self.registry.get_equipment(equipment_id)
            if eq is None:
                raise KeyError(f"Unknown equipment_id: {equipment_id}")

            # Evaluate without mutating equipment operational status if nominal,
            # or use registry.diagnose for deterministic fault/SOP resolution.
            prev_status = eq.status
            diag = self.registry.diagnose(equipment_id=equipment_id, readings=readings)
            eq.status = prev_status

            health_score = 100.0
            for metric, thresh in eq.thresholds.items():
                if metric not in readings:
                    continue
                val = float(readings[metric])
                if val >= thresh.critical:
                    health_score -= 45.0
                elif val >= thresh.warn:
                    span = max(thresh.critical - thresh.warn, 1e-6)
                    ratio = min(1.0, (val - thresh.warn) / span)
                    health_score -= 20.0 + (20.0 * ratio)
                elif thresh.warn > 0:
                    health_score -= min(10.0, (val / thresh.warn) * 10.0)

            health_score -= min(15.0, max(0.0, operating_hours) / 500.0)
            health_score = round(max(5.0, min(100.0, health_score)), 1)

            if health_score < 50.0:
                risk_tier = "CRITICAL"
                priority = "P0_IMMEDIATE"
                window_hours = 4
                critical_count += 1
            elif health_score < 75.0:
                risk_tier = "WARNING"
                priority = "P1_SCHEDULED_24H"
                window_hours = 24
            elif health_score < 90.0:
                risk_tier = "WATCH"
                priority = "P2_PREVENTIVE_72H"
                window_hours = 72
            else:
                risk_tier = "HEALTHY"
                priority = "P3_ROUTINE_WEEKLY"
                window_hours = 168

            mtbf_hours = round(
                max(24.0, (health_score / 100.0) * 1200.0 - operating_hours * 0.05),
                1,
            )

            recommended_sops = [sop.sop_id for sop in diag.sops] or list(eq.sop_ids)
            schedules.append(
                {
                    "equipment_id": eq.equipment_id,
                    "equipment_name": eq.name,
                    "line_id": eq.line_id,
                    "health_score": health_score,
                    "risk_tier": risk_tier,
                    "priority": priority,
                    "recommended_window_hours": window_hours,
                    "estimated_mtbf_hours": mtbf_hours,
                    "operating_hours": operating_hours,
                    "triggered_fault_codes": [fc.code for fc in diag.fault_codes],
                    "recommended_sops": recommended_sops,
                }
            )

        avg_health = (
            round(sum(s["health_score"] for s in schedules) / len(schedules), 1)
            if schedules
            else 100.0
        )

        self._record_audit(
            event_type="PREDICTIVE_MAINTENANCE_RUN",
            equipment_id=schedules[0]["equipment_id"] if len(schedules) == 1 else "PLANT-WIDE",
            actor="predictive-engine",
            detail={
                "equipment_evaluated": len(schedules),
                "average_health_score": avg_health,
                "critical_count": critical_count,
            },
        )

        return {
            "generated_at": _utc_now_iso(),
            "equipment_evaluated": len(schedules),
            "average_health_score": avg_health,
            "critical_count": critical_count,
            "schedules": schedules,
        }

