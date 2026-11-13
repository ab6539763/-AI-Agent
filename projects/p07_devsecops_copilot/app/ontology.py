"""DevSecOps Ontology: services, CVEs, incidents, runbooks, dependencies, and blast-radius gating."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


SeverityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
IncidentSeverity = Literal["SEV-1", "SEV-2", "SEV-3", "SEV-4"]
IncidentStatus = Literal["OPEN", "MITIGATED", "RESOLVED"]
ActionStatus = Literal["PENDING_APPROVAL", "APPROVED", "REJECTED", "EXECUTED"]


def cvss_to_severity(score: float) -> SeverityLevel:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


@dataclass
class Service:
    service_id: str
    name: str
    tier: str = "tier-1"
    owner_team: str = "platform-sre"
    environment: str = "prod"
    runbook_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class CVE:
    cve_id: str
    service_id: str
    cvss_score: float
    patched: bool = False
    description: str = ""
    remediation: str = ""
    severity: SeverityLevel = field(init=False)

    def __post_init__(self) -> None:
        self.severity = cvss_to_severity(self.cvss_score)


@dataclass
class Incident:
    incident_id: str
    title: str
    service_id: str
    severity: IncidentSeverity = "SEV-2"
    status: IncidentStatus = "OPEN"
    summary: str = ""
    postmortem_updated_at: Optional[str] = None
    cve_ids: list[str] = field(default_factory=list)


@dataclass
class Runbook:
    runbook_id: str
    title: str
    service_id: str
    steps: list[str] = field(default_factory=list)
    owner: str = "sre-oncall"


@dataclass
class DependencyLink:
    source_service_id: str
    target_service_id: str
    relation: str = "depends_on"
    criticality: Literal["hard", "soft"] = "hard"


@dataclass
class OpsAction:
    action_id: str
    action_type: str
    target_service_id: str
    environment: str = "prod"
    requires_hitl: bool = True
    status: ActionStatus = "PENDING_APPROVAL"
    requested_by: str = "fde-copilot"
    approved_by: Optional[str] = None
    reason: str = ""
    created_at: str = ""
    decided_at: Optional[str] = None


class DevSecOpsOntologyRegistry:
    """In-memory graph registry for DevSecOps entities, blast-radius traversal, and CVSS gating."""

    def __init__(self) -> None:
        self.services: dict[str, Service] = {}
        self.cves: dict[str, CVE] = {}
        self.incidents: dict[str, Incident] = {}
        self.runbooks: dict[str, Runbook] = {}
        self.dependencies: list[DependencyLink] = []
        self.ops_actions: dict[str, OpsAction] = {}

    def register_service(self, service: Service) -> Service:
        self.services[service.service_id] = service
        return service

    def register_cve(self, cve: CVE) -> CVE:
        self.cves[cve.cve_id] = cve
        return cve

    def register_incident(self, incident: Incident) -> Incident:
        self.incidents[incident.incident_id] = incident
        return incident

    def register_runbook(self, runbook: Runbook) -> Runbook:
        self.runbooks[runbook.runbook_id] = runbook
        if runbook.service_id in self.services and not self.services[runbook.service_id].runbook_id:
            self.services[runbook.service_id].runbook_id = runbook.runbook_id
        return runbook

    def add_dependency(self, link: DependencyLink) -> DependencyLink:
        self.dependencies.append(link)
        return link

    def register_action(self, action: OpsAction) -> OpsAction:
        self.ops_actions[action.action_id] = action
        return action

    def compute_blast_radius(self, service_id: str, max_depth: int = 5) -> dict[str, Any]:
        """Compute upstream impacted services (services that depend on service_id) and downstream deps."""
        if service_id not in self.services:
            raise KeyError(f"Unknown service_id: {service_id}")

        # Build reverse adjacency: target -> list of (source, link)
        reverse_adj: dict[str, list[DependencyLink]] = {}
        forward_adj: dict[str, list[DependencyLink]] = {}
        for link in self.dependencies:
            reverse_adj.setdefault(link.target_service_id, []).append(link)
            forward_adj.setdefault(link.source_service_id, []).append(link)

        visited: dict[str, int] = {service_id: 0}
        impacted_upstream: list[dict[str, Any]] = []
        queue: deque[tuple[str, int, list[str]]] = deque([(service_id, 0, [service_id])])

        while queue:
            current, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            for link in reverse_adj.get(current, []):
                caller = link.source_service_id
                if caller not in visited:
                    next_depth = depth + 1
                    visited[caller] = next_depth
                    new_path = [*path, caller]
                    svc = self.services.get(caller)
                    impacted_upstream.append(
                        {
                            "service_id": caller,
                            "name": svc.name if svc else caller,
                            "tier": svc.tier if svc else "unknown",
                            "depth": next_depth,
                            "criticality": link.criticality,
                            "propagation_path": list(reversed(new_path)),
                        }
                    )
                    queue.append((caller, next_depth, new_path))

        downstream = [
            {
                "service_id": link.target_service_id,
                "relation": link.relation,
                "criticality": link.criticality,
            }
            for link in forward_adj.get(service_id, [])
        ]

        tier0_impacted = [
            item["service_id"] for item in impacted_upstream if item["tier"] == "tier-0"
        ]
        if self.services[service_id].tier == "tier-0" and service_id not in tier0_impacted:
            tier0_impacted.insert(0, service_id)

        active_cves = [
            {
                "cve_id": cve.cve_id,
                "cvss_score": cve.cvss_score,
                "severity": cve.severity,
            }
            for cve in self.cves.values()
            if cve.service_id == service_id and not cve.patched
        ]

        cvss_gate = self.evaluate_cvss_gate(service_id)

        return {
            "root_service_id": service_id,
            "root_tier": self.services[service_id].tier,
            "impacted_upstream": impacted_upstream,
            "total_impacted_services": len(impacted_upstream),
            "tier0_impacted": tier0_impacted,
            "downstream_dependencies": downstream,
            "active_cves": active_cves,
            "cvss_gate": cvss_gate,
        }

    def evaluate_cvss_gate(self, service_id: str, block_threshold: float = 9.0) -> dict[str, Any]:
        """Gate deployments/changes based on unpatched CVE CVSS scores."""
        if service_id not in self.services:
            raise KeyError(f"Unknown service_id: {service_id}")

        unpatched = [
            cve for cve in self.cves.values() if cve.service_id == service_id and not cve.patched
        ]
        max_cvss = max((c.cvss_score for c in unpatched), default=0.0)
        blocking = [
            {"cve_id": c.cve_id, "cvss_score": c.cvss_score, "severity": c.severity}
            for c in unpatched
            if c.cvss_score >= block_threshold
        ]
        if blocking:
            decision = "BLOCK_DEPLOY"
        elif max_cvss >= 7.0:
            decision = "WARN"
        else:
            decision = "PASS"

        return {
            "service_id": service_id,
            "blocked": len(blocking) > 0,
            "max_cvss": max_cvss,
            "block_threshold": block_threshold,
            "blocking_cves": blocking,
            "gate_decision": decision,
        }

    def seed_default_topology(self) -> None:
        """Populate a deterministic enterprise microservice topology for demo & readiness."""
        if self.services:
            return
        self.register_service(
            Service("svc-auth", "Auth Identity Gateway", tier="tier-0", owner_team="sec-core", runbook_id="rb-auth")
        )
        self.register_service(
            Service("svc-payment", "Payment Ledger API", tier="tier-0", owner_team="fintech-sre", runbook_id="rb-payment")
        )
        self.register_service(
            Service("svc-checkout", "Checkout Orchestrator", tier="tier-1", owner_team="commerce-sre", runbook_id="rb-checkout")
        )
        self.register_service(
            Service("svc-web-portal", "Enterprise Web Portal", tier="tier-1", owner_team="frontend-platform", runbook_id=None)
        )

        self.add_dependency(DependencyLink("svc-payment", "svc-auth", "depends_on", "hard"))
        self.add_dependency(DependencyLink("svc-checkout", "svc-payment", "depends_on", "hard"))
        self.add_dependency(DependencyLink("svc-web-portal", "svc-checkout", "calls", "hard"))
        self.add_dependency(DependencyLink("svc-web-portal", "svc-auth", "depends_on", "hard"))

        self.register_runbook(
            Runbook(
                "rb-auth",
                "Auth Gateway Failover Runbook",
                "svc-auth",
                steps=["Check JWKS cache hit rate", "Verify Redis cluster health", "Trigger regional failover if p99 > 500ms"],
            )
        )
        self.register_runbook(
            Runbook(
                "rb-payment",
                "Payment Ledger Rollback Runbook",
                "svc-payment",
                steps=["Freeze batch settlements", "Verify DB replication lag", "Execute canary rollback via SRE gate"],
            )
        )
        self.register_runbook(
            Runbook(
                "rb-checkout",
                "Checkout Degradation Runbook",
                "svc-checkout",
                steps=["Enable circuit breaker for payment timeouts", "Drain unhealthy pods"],
            )
        )

        self.register_cve(
            CVE(
                "CVE-2026-1042",
                "svc-auth",
                cvss_score=9.4,
                patched=False,
                description="JWT signature bypass under malformed kid header",
                remediation="Upgrade auth-jwt-lib to 4.2.1",
            )
        )
        self.register_cve(
            CVE(
                "CVE-2026-0811",
                "svc-checkout",
                cvss_score=6.5,
                patched=True,
                description="Verbose error stacktrace in checkout debug endpoint",
                remediation="Disable debug handler in prod",
            )
        )
        self.register_incident(
            Incident(
                "INC-2026-001",
                "Auth Token Validation Latency Spike",
                "svc-auth",
                severity="SEV-1",
                status="RESOLVED",
                summary="Redis connection pool exhaustion caused 5xx across checkout and portal.",
                postmortem_updated_at="2026-09-01",
                cve_ids=["CVE-2026-1042"],
            )
        )
