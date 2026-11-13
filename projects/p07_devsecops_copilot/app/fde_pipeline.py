"""FDE DevSecOps Pipeline: root-cause & blast-radius triage, secret redaction, HITL gate, audit trail."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from .llm_wiki import DevSecOpsLLMWiki
from .ontology import DevSecOpsOntologyRegistry, OpsAction


_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OPENAI_KEY", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("GITHUB_TOKEN", re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("AWS_ACCESS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("BEARER_TOKEN", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    (
        "CREDENTIAL_KV",
        re.compile(r"(?i)(password|passwd|secret|api_key|token)\s*[:=]\s*['\"]?([^\s'\"]{6,})['\"]?"),
    ),
]


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Deterministically redact secrets/tokens from logs, symptoms, and prompts."""
    redacted = text
    applied: list[str] = []
    for label, pattern in _SECRET_PATTERNS:
        if label == "CREDENTIAL_KV":
            if pattern.search(redacted):
                redacted = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED:{label}]", redacted)
                applied.append(label)
        else:
            if pattern.search(redacted):
                redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
                applied.append(label)
    return redacted, applied


class DevSecOpsFDEPipeline:
    """End-to-end deterministic FDE pipeline for DevSecOps incident triage & gated remediation."""

    HITL_ACTIONS = {"rollback", "quarantine"}

    def __init__(self, registry: DevSecOpsOntologyRegistry, wiki: DevSecOpsLLMWiki) -> None:
        self.registry = registry
        self.wiki = wiki
        self.audit_trail: list[dict[str, Any]] = []

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _record_audit(self, event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "audit_id": f"aud-{uuid4().hex[:10]}",
            "timestamp": self._now_iso(),
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
        }
        self.audit_trail.append(entry)
        return entry

    def triage_incident(
        self,
        service_id: str,
        symptom: str,
        severity: str = "SEV-2",
        proposed_action: str = "rollback",
        environment: str = "prod",
        requested_by: str = "fde-copilot",
    ) -> dict[str, Any]:
        """Analyze incident root cause & blast radius, redact secrets, and enforce HITL for prod rollback/quarantine."""
        if service_id not in self.registry.services:
            raise KeyError(f"Unknown service_id: {service_id}")

        redacted_symptom, redactions_applied = redact_secrets(symptom)
        blast_radius = self.registry.compute_blast_radius(service_id)
        cvss_gate = blast_radius["cvss_gate"]
        wiki_hits = self.wiki.query(f"{service_id} {redacted_symptom}", top_k=3)

        hypotheses: list[str] = []
        if blast_radius["active_cves"]:
            cve_ids = ", ".join(c["cve_id"] for c in blast_radius["active_cves"])
            hypotheses.append(f"Unpatched CVEs on {service_id}: {cve_ids} (max CVSS {cvss_gate['max_cvss']}).")
        if blast_radius["downstream_dependencies"]:
            deps = ", ".join(d["service_id"] for d in blast_radius["downstream_dependencies"])
            hypotheses.append(f"Potential cascading degradation from downstream dependencies: {deps}.")
        if not hypotheses:
            hypotheses.append(f"Localized runtime/config regression on {service_id} matching symptom.")

        normalized_action = proposed_action.lower().strip()
        requires_hitl = normalized_action in self.HITL_ACTIONS and (
            environment == "prod" or self.registry.services[service_id].tier == "tier-0"
        )
        action_status = "PENDING_APPROVAL" if requires_hitl else "EXECUTED"

        action = OpsAction(
            action_id=f"act-{uuid4().hex[:8]}",
            action_type=normalized_action,
            target_service_id=service_id,
            environment=environment,
            requires_hitl=requires_hitl,
            status=action_status,
            requested_by=requested_by,
            reason=redacted_symptom[:200],
            created_at=self._now_iso(),
        )
        self.registry.register_action(action)

        audit_entry = self._record_audit(
            "INCIDENT_TRIAGE",
            requested_by,
            {
                "service_id": service_id,
                "severity": severity,
                "action_id": action.action_id,
                "action_type": action.action_type,
                "requires_hitl": requires_hitl,
                "status": action.status,
                "redactions_applied": redactions_applied,
            },
        )
        self.wiki.append_log(
            "TRIAGE",
            f"Triaged {severity} on [[{service_id}]] -> action `{action.action_id}` ({action.status})",
        )

        return {
            "service_id": service_id,
            "severity": severity,
            "redacted_symptom": redacted_symptom,
            "redactions_applied": redactions_applied,
            "root_cause_hypotheses": hypotheses,
            "blast_radius": blast_radius,
            "cvss_gate": cvss_gate,
            "wiki_references": wiki_hits,
            "action": {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "target_service_id": action.target_service_id,
                "environment": action.environment,
                "requires_hitl": action.requires_hitl,
                "status": action.status,
                "created_at": action.created_at,
            },
            "audit_id": audit_entry["audit_id"],
        }

    def approve_action(
        self,
        action_id: str,
        approved: bool,
        approver: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """SRE HITL approval/rejection gate for pending production rollback/quarantine actions."""
        if action_id not in self.registry.ops_actions:
            raise KeyError(f"Unknown action_id: {action_id}")

        action = self.registry.ops_actions[action_id]
        redacted_comment, _ = redact_secrets(comment)
        action.approved_by = approver
        action.decided_at = self._now_iso()
        action.status = "EXECUTED" if approved else "REJECTED"

        audit_entry = self._record_audit(
            "HITL_DECISION",
            approver,
            {
                "action_id": action_id,
                "approved": approved,
                "final_status": action.status,
                "comment": redacted_comment,
            },
        )
        self.wiki.append_log(
            "HITL_DECISION",
            f"Action `{action_id}` on [[{action.target_service_id}]] -> {action.status} by `{approver}`",
        )

        return {
            "action_id": action.action_id,
            "action_type": action.action_type,
            "target_service_id": action.target_service_id,
            "status": action.status,
            "approved_by": action.approved_by,
            "decided_at": action.decided_at,
            "comment": redacted_comment,
            "audit_id": audit_entry["audit_id"],
        }
