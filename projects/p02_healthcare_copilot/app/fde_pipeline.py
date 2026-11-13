"""Healthcare FDE Pipeline: PHI de-identification, red-flag triage, guardrails, HITL & audit."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Literal

from .llm_wiki import ClinicalLLMWiki
from .ontology import (
    ClinicalAction,
    ClinicalOntologyRegistry,
    InteractionCheckResult,
    PatientCase,
)


SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MRN_RE = re.compile(r"\b(?:MRN|PID)[:#\s-]*[A-Z0-9-]{4,14}\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b")
PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\b\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b|\b1[3-9]\d{9}\b"
)
NAME_RE = re.compile(
    r"(?P<prefix>(?:Patient|Name|姓名)\s*[:：]\s*)(?P<name>[A-Za-z\u4e00-\u9fff]+(?:\s+[A-Za-z]+){0,2})",
    re.IGNORECASE,
)


class HealthcareFDEPipeline:
    """End-to-end clinical decision support pipeline with HIPAA-style masking and HITL."""

    def __init__(
        self,
        registry: ClinicalOntologyRegistry | None = None,
        wiki: ClinicalLLMWiki | None = None,
        audit_log_path: Path | str | None = None,
    ) -> None:
        self.registry = registry or ClinicalOntologyRegistry()
        self.wiki = wiki
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None
        if self.audit_log_path:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._actions: dict[str, ClinicalAction] = {}
        self._audit_events: list[dict[str, Any]] = []

    @staticmethod
    def deidentify_phi(text: str) -> tuple[str, list[str]]:
        """Mask HIPAA Safe Harbor identifiers deterministically."""
        if not text:
            return "", []

        masked = text
        redacted: list[str] = []

        patterns: list[tuple[str, re.Pattern[str], Any]] = [
            ("SSN", SSN_RE, "[REDACTED_SSN]"),
            ("EMAIL", EMAIL_RE, "[REDACTED_EMAIL]"),
            ("MRN", MRN_RE, "[REDACTED_MRN]"),
            ("PHONE", PHONE_RE, "[REDACTED_PHONE]"),
            ("DATE", DATE_RE, "[REDACTED_DATE]"),
            ("NAME", NAME_RE, lambda m: f"{m.group('prefix')}[REDACTED_NAME]"),
        ]
        for label, pattern, repl in patterns:
            new_masked, count = pattern.subn(repl, masked)
            if count > 0:
                redacted.append(label)
                masked = new_masked

        return masked, redacted

    def _record_audit(
        self,
        event_type: str,
        case_id: str,
        action_id: str | None,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "case_id": case_id,
            "action_id": action_id,
            "details": details,
        }
        self._audit_events.append(event)
        if self.audit_log_path:
            with self.audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def _detect_red_flags(self, case: PatientCase) -> list[str]:
        reasons: list[str] = []
        for sym in case.symptoms:
            if self.registry.is_red_flag_symptom(sym):
                reasons.append(f"red_flag_symptom:{sym.symptom_id}")

        vitals = case.vital_signs
        if "spo2" in vitals and vitals["spo2"] < 90.0:
            reasons.append(f"critical_hypoxia:spo2={vitals['spo2']}")
        if "sbp" in vitals and vitals["sbp"] < 90.0:
            reasons.append(f"hypotension:sbp={vitals['sbp']}")
        if "hr" in vitals and (vitals["hr"] > 130.0 or vitals["hr"] < 40.0):
            reasons.append(f"critical_hr:hr={vitals['hr']}")
        if "temp_c" in vitals and vitals["temp_c"] >= 40.0:
            reasons.append(f"hyperpyrexia:temp_c={vitals['temp_c']}")
        return reasons

    def triage_case(
        self,
        case: PatientCase,
        proposed_med_ids: list[str] | None = None,
        raw_notes: str = "",
    ) -> dict[str, Any]:
        """Run PHI masking, red-flag triage, wiki lookup, ontology guardrails, and queue HITL."""
        proposed = proposed_med_ids or []
        masked_complaint, complaint_redacted = self.deidentify_phi(case.chief_complaint)
        masked_notes, notes_redacted = self.deidentify_phi(raw_notes)
        redacted_fields = sorted(set(complaint_redacted + notes_redacted))

        red_flags = self._detect_red_flags(case)
        interaction_result: InteractionCheckResult = (
            self.registry.evaluate_action_constraints(case, proposed)
        )

        wiki_hits: list[dict[str, Any]] = []
        if self.wiki is not None:
            query_str = " ".join(
                [masked_complaint]
                + case.conditions
                + [s.name for s in case.symptoms]
                + proposed
            ).strip()
            if query_str:
                wiki_hits = self.wiki.query(query_str, top_k=3)

        if red_flags:
            triage_level: Literal["emergency", "urgent", "routine"] = "emergency"
            action_type = "triage_escalation"
            risk_level = "critical"
        elif interaction_result.has_conflicts or any(
            s.severity == "severe" for s in case.symptoms
        ):
            triage_level = "urgent"
            action_type = "medication_order" if proposed else "diagnostic_workup"
            risk_level = "high"
        else:
            triage_level = "routine"
            action_type = "medication_order" if proposed else "diagnostic_workup"
            risk_level = "low" if not proposed else "medium"

        status = "blocked" if interaction_result.blocked else "pending_review"
        rationale_parts = [f"Triage={triage_level.upper()}"]
        if red_flags:
            rationale_parts.append(f"Red flags: {', '.join(red_flags)}")
        rationale_parts.append(interaction_result.summary)

        action = ClinicalAction(
            case_id=case.case_id,
            action_type=action_type,
            proposed_med_ids=proposed,
            rationale=" | ".join(rationale_parts),
            risk_level=risk_level,
            requires_hitl=True,
            status=status,
        )
        self._actions[action.action_id] = action

        self._record_audit(
            event_type="CLINICAL_TRIAGE",
            case_id=case.case_id,
            action_id=action.action_id,
            details={
                "triage_level": triage_level,
                "red_flags": red_flags,
                "redacted_phi_types": redacted_fields,
                "guardrail_blocked": interaction_result.blocked,
                "action_status": action.status,
            },
        )

        return {
            "case_id": case.case_id,
            "triage_level": triage_level,
            "emergency_escalated": bool(red_flags),
            "red_flags": red_flags,
            "deidentified_complaint": masked_complaint,
            "deidentified_notes": masked_notes,
            "redacted_phi_types": redacted_fields,
            "interaction_check": interaction_result.model_dump(),
            "wiki_references": wiki_hits,
            "proposed_action": action.model_dump(),
        }

    def approve_action(
        self,
        action_id: str,
        physician_id: str,
        decision: Literal["approved", "rejected"],
        notes: str = "",
    ) -> ClinicalAction:
        """Record HITL physician sign-off or rejection for a clinical action."""
        action = self._actions.get(action_id)
        if action is None:
            raise KeyError(f"Unknown action_id: {action_id}")
        if not physician_id.strip():
            raise ValueError("physician_id is required for HITL sign-off")
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")

        masked_notes, _ = self.deidentify_phi(notes)
        updated = action.model_copy(
            update={
                "status": decision,
                "reviewer_id": physician_id.strip(),
                "review_notes": masked_notes,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._actions[action_id] = updated

        self._record_audit(
            event_type="HITL_SIGNOFF",
            case_id=updated.case_id,
            action_id=updated.action_id,
            details={
                "decision": decision,
                "physician_id": updated.reviewer_id,
                "notes": masked_notes,
            },
        )
        return updated

    def get_action(self, action_id: str) -> ClinicalAction | None:
        return self._actions.get(action_id)

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_events)
