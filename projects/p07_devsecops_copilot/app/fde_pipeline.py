"""FDE DevSecOps Pipeline: root-cause & blast-radius triage, secret redaction, HITL gate, audit trail."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import re
from typing import Any, Optional
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

    def get_dashboard_overview(self) -> dict[str, Any]:
        """Return enterprise DevSecOps KPIs and registered service inventory."""
        critical_cves = [
            cve
            for cve in self.registry.cves.values()
            if not cve.patched and (cve.cvss_score >= 9.0 or cve.severity == "CRITICAL")
        ]
        active_incidents = [
            inc for inc in self.registry.incidents.values() if inc.status != "RESOLVED"
        ]
        pending_actions = [
            act for act in self.registry.ops_actions.values() if act.status == "PENDING_APPROVAL"
        ]
        wiki_pages_count = len(list(self.wiki.entities_dir.glob("*.md")))
        services = [
            {
                "service_id": svc.service_id,
                "name": svc.name,
                "tier": svc.tier,
                "owner_team": svc.owner_team,
                "environment": svc.environment,
                "runbook_id": svc.runbook_id,
            }
            for svc in sorted(self.registry.services.values(), key=lambda s: s.service_id)
        ]
        return {
            "services_total": len(self.registry.services),
            "critical_cves_total": len(critical_cves),
            "active_incidents_total": len(active_incidents),
            "pending_hitl_rollbacks": len(pending_actions),
            "audit_logs_total": len(self.audit_trail),
            "wiki_pages_total": wiki_pages_count,
            "services": services,
        }

    def list_wiki_pages(self) -> list[dict[str, Any]]:
        """List all Runbook/Postmortem/Service/CVE Markdown wiki pages."""
        pages: list[dict[str, Any]] = []
        for path in sorted(self.wiki.entities_dir.glob("*.md")):
            info = self.wiki._parse_entity_header(path)
            text = path.read_text(encoding="utf-8")
            preview_lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.startswith("#") and not line.startswith("- **")
            ]
            preview = " ".join(preview_lines)[:220]
            pages.append(
                {
                    "id": info["entity_id"],
                    "entity_type": info["entity_type"],
                    "title": info["title"],
                    "path": f"entities/{path.name}",
                    "preview": preview,
                    "content": text,
                }
            )
        return pages

    def list_pending_actions(self) -> list[dict[str, Any]]:
        """List pending SRE HITL rollback/quarantine actions."""
        pending = [
            {
                "action_id": act.action_id,
                "action_type": act.action_type,
                "target_service_id": act.target_service_id,
                "environment": act.environment,
                "requires_hitl": act.requires_hitl,
                "status": act.status,
                "requested_by": act.requested_by,
                "reason": act.reason,
                "created_at": act.created_at,
            }
            for act in self.registry.ops_actions.values()
            if act.status == "PENDING_APPROVAL"
        ]
        pending.sort(key=lambda a: a["created_at"], reverse=True)
        return pending

    def list_audit_logs(self) -> list[dict[str, Any]]:
        """List secret-redacted audit log entries (newest first)."""
        return list(reversed(self.audit_trail))

    def _collect_downstream_services(self, service_id: str) -> list[str]:
        """Collect service_id and all transitive downstream dependencies."""
        forward_adj: dict[str, list[str]] = {}
        for link in self.registry.dependencies:
            forward_adj.setdefault(link.source_service_id, []).append(link.target_service_id)

        visited: list[str] = [service_id]
        seen = {service_id}
        queue: deque[str] = deque([service_id])
        while queue:
            current = queue.popleft()
            for dep in forward_adj.get(current, []):
                if dep not in seen:
                    seen.add(dep)
                    visited.append(dep)
                    queue.append(dep)
        return visited

    def evaluate_release_cve_gate(
        self,
        service_id: str,
        release_version: str = "v1.0.0",
        include_dependencies: bool = True,
        block_threshold: float = 9.0,
        dependency_cvss_overrides: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """Evaluate CI/CD release CVE gate across service and its downstream dependencies."""
        if service_id not in self.registry.services:
            raise KeyError(f"Unknown service_id: {service_id}")

        checked_services = (
            self._collect_downstream_services(service_id)
            if include_dependencies
            else [service_id]
        )
        blocking_cves: list[dict[str, Any]] = []
        max_cvss = 0.0

        for svc_id in checked_services:
            for cve in self.registry.cves.values():
                if cve.service_id == svc_id and not cve.patched:
                    max_cvss = max(max_cvss, cve.cvss_score)
                    if cve.cvss_score >= block_threshold:
                        blocking_cves.append(
                            {
                                "cve_id": cve.cve_id,
                                "service_id": cve.service_id,
                                "cvss_score": cve.cvss_score,
                                "severity": cve.severity,
                                "remediation": cve.remediation,
                            }
                        )

        for dep_name, score in (dependency_cvss_overrides or {}).items():
            max_cvss = max(max_cvss, score)
            if score >= block_threshold:
                blocking_cves.append(
                    {
                        "cve_id": f"CVE-OVERRIDE-{dep_name.upper()}",
                        "service_id": dep_name,
                        "cvss_score": score,
                        "severity": "CRITICAL" if score >= 9.0 else "HIGH",
                        "remediation": f"Upgrade {dep_name} to patched release",
                    }
                )

        decision = "BLOCK_DEPLOY" if blocking_cves else "ALLOW"
        audit_entry = self._record_audit(
            "CVE_GATE_EVALUATION",
            "ci-cd-gate",
            {
                "service_id": service_id,
                "release_version": release_version,
                "decision": decision,
                "max_cvss": max_cvss,
                "block_threshold": block_threshold,
                "checked_services": checked_services,
            },
        )

        return {
            "service_id": service_id,
            "release_version": release_version,
            "decision": decision,
            "allowed": decision == "ALLOW",
            "max_cvss": max_cvss,
            "block_threshold": block_threshold,
            "checked_services": checked_services,
            "blocking_cves": blocking_cves,
            "audit_id": audit_entry["audit_id"],
        }
