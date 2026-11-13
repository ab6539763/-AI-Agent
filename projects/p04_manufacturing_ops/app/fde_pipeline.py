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

    def get_audit_trail(self) -> list[dict[str, Any]]:
        return list(self.audit_trail)
