"""Deterministic CycloneDX SBOM Scanner, Topological Blast-Radius Analyzer, and Blameless Postmortem Exporter."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from .fde_pipeline import redact_secrets
from .ontology import DevSecOpsOntologyRegistry, cvss_to_severity


@dataclass(frozen=True)
class PackageAdvisory:
    cve_id: str
    package_name: str
    affected_versions: tuple[str, ...]
    cvss_score: float
    fixed_version: str
    description: str

    @property
    def severity(self) -> str:
        return cvss_to_severity(self.cvss_score)


DEFAULT_ADVISORIES: tuple[PackageAdvisory, ...] = (
    PackageAdvisory(
        cve_id="CVE-2026-1042",
        package_name="auth-jwt-lib",
        affected_versions=("4.0.0", "4.1.0", "4.2.0"),
        cvss_score=9.4,
        fixed_version="4.2.1",
        description="JWT signature bypass under malformed kid header.",
    ),
    PackageAdvisory(
        cve_id="CVE-2026-2190",
        package_name="openssl-fips",
        affected_versions=("3.0.8", "3.0.9", "3.1.0"),
        cvss_score=9.1,
        fixed_version="3.1.2",
        description="Out-of-bounds read in TLS 1.3 handshake extension parser.",
    ),
    PackageAdvisory(
        cve_id="CVE-2026-1884",
        package_name="redis-async-pool",
        affected_versions=("2.3.0", "2.3.1"),
        cvss_score=7.8,
        fixed_version="2.3.4",
        description="Connection pool exhaustion via unclosed pipeline frames.",
    ),
    PackageAdvisory(
        cve_id="CVE-2026-0944",
        package_name="express-gateway",
        affected_versions=("4.18.0", "4.18.1", "4.18.2"),
        cvss_score=6.4,
        fixed_version="4.19.0",
        description="Header smuggling when behind misconfigured reverse proxy.",
    ),
    PackageAdvisory(
        cve_id="CVE-2026-0512",
        package_name="pydantic-core-compat",
        affected_versions=("1.10.1",),
        cvss_score=3.7,
        fixed_version="1.10.4",
        description="Minor regex backtracking on malformed email fields.",
    ),
)


def build_default_cyclonedx_sbom(service_id: str) -> dict[str, Any]:
    """Return a deterministic CycloneDX 1.5 SBOM for demo services."""
    catalog: dict[str, dict[str, Any]] = {
        "svc-auth": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "metadata": {
                "component": {
                    "bom-ref": "svc-auth@3.1.0",
                    "name": "svc-auth",
                    "version": "3.1.0",
                    "type": "application",
                }
            },
            "components": [
                {"bom-ref": "pkg:pypi/auth-jwt-lib@4.2.0", "name": "auth-jwt-lib", "version": "4.2.0", "type": "library"},
                {"bom-ref": "pkg:generic/openssl-fips@3.1.0", "name": "openssl-fips", "version": "3.1.0", "type": "library"},
                {"bom-ref": "pkg:pypi/redis-async-pool@2.3.1", "name": "redis-async-pool", "version": "2.3.1", "type": "library"},
            ],
            "dependencies": [
                {"ref": "svc-auth@3.1.0", "dependsOn": ["pkg:pypi/auth-jwt-lib@4.2.0", "pkg:pypi/redis-async-pool@2.3.1"]},
                {"ref": "pkg:pypi/auth-jwt-lib@4.2.0", "dependsOn": ["pkg:generic/openssl-fips@3.1.0"]},
                {"ref": "pkg:generic/openssl-fips@3.1.0", "dependsOn": []},
                {"ref": "pkg:pypi/redis-async-pool@2.3.1", "dependsOn": []},
            ],
        },
        "svc-checkout": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "metadata": {
                "component": {
                    "bom-ref": "svc-checkout@2.4.0",
                    "name": "svc-checkout",
                    "version": "2.4.0",
                    "type": "application",
                }
            },
            "components": [
                {"bom-ref": "pkg:npm/express-gateway@4.18.2", "name": "express-gateway", "version": "4.18.2", "type": "library"},
                {"bom-ref": "pkg:pypi/auth-jwt-lib@4.2.0", "name": "auth-jwt-lib", "version": "4.2.0", "type": "library"},
                {"bom-ref": "pkg:pypi/pydantic-core-compat@1.10.1", "name": "pydantic-core-compat", "version": "1.10.1", "type": "library"},
            ],
            "dependencies": [
                {"ref": "svc-checkout@2.4.0", "dependsOn": ["pkg:npm/express-gateway@4.18.2", "pkg:pypi/pydantic-core-compat@1.10.1"]},
                {"ref": "pkg:npm/express-gateway@4.18.2", "dependsOn": ["pkg:pypi/auth-jwt-lib@4.2.0"]},
                {"ref": "pkg:pypi/auth-jwt-lib@4.2.0", "dependsOn": []},
                {"ref": "pkg:pypi/pydantic-core-compat@1.10.1", "dependsOn": []},
            ],
        },
    }
    if service_id in catalog:
        return catalog[service_id]

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "metadata": {
            "component": {
                "bom-ref": f"{service_id}@1.0.0",
                "name": service_id,
                "version": "1.0.0",
                "type": "application",
            }
        },
        "components": [
            {"bom-ref": "pkg:pypi/redis-async-pool@2.3.1", "name": "redis-async-pool", "version": "2.3.1", "type": "library"},
            {"bom-ref": "pkg:pypi/pydantic-core-compat@1.10.1", "name": "pydantic-core-compat", "version": "1.10.1", "type": "library"},
        ],
        "dependencies": [
            {"ref": f"{service_id}@1.0.0", "dependsOn": ["pkg:pypi/redis-async-pool@2.3.1"]},
            {"ref": "pkg:pypi/redis-async-pool@2.3.1", "dependsOn": ["pkg:pypi/pydantic-core-compat@1.10.1"]},
            {"ref": "pkg:pypi/pydantic-core-compat@1.10.1", "dependsOn": []},
        ],
    }


class SBOMScanner:
    """Parses CycloneDX-style SBOMs, maps transitive CVEs, and computes topological blast-radius order."""

    def __init__(self, advisories: Optional[tuple[PackageAdvisory, ...]] = None) -> None:
        self.advisories = advisories if advisories is not None else DEFAULT_ADVISORIES

    def _match_advisories(self, name: str, version: str) -> list[PackageAdvisory]:
        matched: list[PackageAdvisory] = []
        norm_name = name.strip().lower()
        norm_version = version.strip()
        for adv in self.advisories:
            if adv.package_name.lower() == norm_name:
                if not adv.affected_versions or norm_version in adv.affected_versions:
                    matched.append(adv)
        return matched

    def scan(
        self,
        sbom_data: dict[str, Any],
        block_threshold: float = 9.0,
    ) -> dict[str, Any]:
        """Scan a CycloneDX-style SBOM and return transitive CVEs + topological blast-radius order."""
        metadata_comp = (sbom_data.get("metadata") or {}).get("component") or {}
        root_ref: Optional[str] = metadata_comp.get("bom-ref") or metadata_comp.get("name")

        components_by_ref: dict[str, dict[str, str]] = {}
        if root_ref:
            components_by_ref[root_ref] = {
                "ref": root_ref,
                "name": str(metadata_comp.get("name") or root_ref),
                "version": str(metadata_comp.get("version") or "0.0.0"),
                "type": str(metadata_comp.get("type") or "application"),
            }

        for comp in sbom_data.get("components") or []:
            ref = str(comp.get("bom-ref") or f"{comp.get('name', 'unknown')}@{comp.get('version', '0.0.0')}")
            components_by_ref[ref] = {
                "ref": ref,
                "name": str(comp.get("name") or ref),
                "version": str(comp.get("version") or "0.0.0"),
                "type": str(comp.get("type") or "library"),
            }

        forward_adj: dict[str, list[str]] = {ref: [] for ref in components_by_ref}
        reverse_adj: dict[str, list[str]] = {ref: [] for ref in components_by_ref}

        for dep in sbom_data.get("dependencies") or []:
            src = str(dep.get("ref") or "")
            if not src:
                continue
            if src not in components_by_ref:
                components_by_ref[src] = {"ref": src, "name": src, "version": "0.0.0", "type": "library"}
                forward_adj[src] = []
                reverse_adj[src] = []
            for target in dep.get("dependsOn") or []:
                tgt = str(target)
                if tgt not in components_by_ref:
                    components_by_ref[tgt] = {"ref": tgt, "name": tgt, "version": "0.0.0", "type": "library"}
                    forward_adj[tgt] = []
                    reverse_adj[tgt] = []
                if tgt not in forward_adj[src]:
                    forward_adj[src].append(tgt)
                if src not in reverse_adj[tgt]:
                    reverse_adj[tgt].append(src)

        if not root_ref and components_by_ref:
            # Pick nodes with in-degree 0 in forward_adj (top-level consumers)
            top_roots = [ref for ref, callers in reverse_adj.items() if not callers]
            root_ref = top_roots[0] if top_roots else next(iter(components_by_ref))

        # Compute BFS depth & shortest dependency path from root_ref
        depth_map: dict[str, int] = {}
        path_map: dict[str, list[str]] = {}
        if root_ref and root_ref in components_by_ref:
            depth_map[root_ref] = 0
            path_map[root_ref] = [root_ref]
            q: deque[str] = deque([root_ref])
            while q:
                cur = q.popleft()
                for nxt in forward_adj.get(cur, []):
                    if nxt not in depth_map:
                        depth_map[nxt] = depth_map[cur] + 1
                        path_map[nxt] = [*path_map[cur], nxt]
                        q.append(nxt)

        # Topological blast-radius order (Kahn's algorithm from leaf dependencies -> upstream consumers)
        # Edge u -> v in blast-radius graph means u is a dependency of v (so vulnerability in u impacts v).
        in_degree: dict[str, int] = {ref: len(forward_adj.get(ref, [])) for ref in components_by_ref}
        topo_queue: deque[str] = deque(sorted(ref for ref, deg in in_degree.items() if deg == 0))
        topological_blast_order: list[str] = []

        while topo_queue:
            node = topo_queue.popleft()
            topological_blast_order.append(node)
            for consumer in sorted(reverse_adj.get(node, [])):
                in_degree[consumer] -= 1
                if in_degree[consumer] == 0:
                    topo_queue.append(consumer)

        # Append any remaining nodes in case of dependency cycle
        if len(topological_blast_order) < len(components_by_ref):
            seen = set(topological_blast_order)
            for ref in sorted(components_by_ref):
                if ref not in seen:
                    topological_blast_order.append(ref)

        # Map direct and transitive CVEs
        findings: list[dict[str, Any]] = []
        severity_counts: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        vulnerable_refs: set[str] = set()

        for ref in topological_blast_order:
            comp = components_by_ref[ref]
            matched = self._match_advisories(comp["name"], comp["version"])
            if not matched:
                continue
            vulnerable_refs.add(ref)
            depth = depth_map.get(ref, 1)
            exposure = "direct" if depth <= 1 else "transitive"

            # Compute upstream consumers impacted by this vulnerable package
            impacted_consumers: list[str] = []
            visited_up: set[str] = {ref}
            up_q: deque[str] = deque([ref])
            while up_q:
                cur = up_q.popleft()
                for caller in reverse_adj.get(cur, []):
                    if caller not in visited_up:
                        visited_up.add(caller)
                        impacted_consumers.append(caller)
                        up_q.append(caller)

            for adv in matched:
                severity_counts[adv.severity] += 1
                findings.append(
                    {
                        "cve_id": adv.cve_id,
                        "package_ref": ref,
                        "package_name": comp["name"],
                        "package_version": comp["version"],
                        "cvss_score": adv.cvss_score,
                        "severity": adv.severity,
                        "exposure": exposure,
                        "depth": depth,
                        "dependency_path": path_map.get(ref, [ref]),
                        "impacted_consumers": impacted_consumers,
                        "fixed_version": adv.fixed_version,
                        "description": adv.description,
                    }
                )

        findings.sort(key=lambda item: (-item["cvss_score"], item["cve_id"]))
        max_cvss = max((f["cvss_score"] for f in findings), default=0.0)

        if max_cvss >= block_threshold:
            gate_decision = "BLOCK_DEPLOY"
        elif max_cvss >= 7.0:
            gate_decision = "WARN"
        else:
            gate_decision = "PASS"

        # Packages in the blast radius of any vulnerable component, ordered topologically
        blast_set: set[str] = set()
        for v_ref in vulnerable_refs:
            blast_set.add(v_ref)
            q_up: deque[str] = deque([v_ref])
            while q_up:
                cur = q_up.popleft()
                for caller in reverse_adj.get(cur, []):
                    if caller not in blast_set:
                        blast_set.add(caller)
                        q_up.append(caller)

        blast_radius_order = [ref for ref in topological_blast_order if ref in blast_set]

        return {
            "bom_format": sbom_data.get("bomFormat", "CycloneDX"),
            "spec_version": sbom_data.get("specVersion", "1.5"),
            "root_component": root_ref,
            "total_components": len(components_by_ref),
            "vulnerable_components": len(vulnerable_refs),
            "total_cves": len(findings),
            "max_cvss": max_cvss,
            "block_threshold": block_threshold,
            "gate_decision": gate_decision,
            "blocked": gate_decision == "BLOCK_DEPLOY",
            "severity_counts": severity_counts,
            "topological_blast_order": topological_blast_order,
            "blast_radius_order": blast_radius_order,
            "findings": findings,
        }


class PostmortemExporter:
    """Generates blameless SRE postmortem Markdown with timeline, root cause, blast radius, and action items."""

    def export(
        self,
        *,
        incident_id: str,
        title: str,
        service_id: str,
        severity: str = "SEV-1",
        commander: str = "sre-oncall",
        summary: str,
        root_cause: str,
        timeline: Optional[list[dict[str, str]]] = None,
        action_items: Optional[list[dict[str, str]]] = None,
        registry: Optional[DevSecOpsOntologyRegistry] = None,
        sbom_scan: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Export a secret-redacted blameless SRE postmortem in Markdown."""
        redactions: list[str] = []

        def _clean(text: str) -> str:
            cleaned, applied = redact_secrets(text)
            for label in applied:
                if label not in redactions:
                    redactions.append(label)
            return cleaned

        clean_title = _clean(title)
        clean_summary = _clean(summary)
        clean_root_cause = _clean(root_cause)

        blast_radius: dict[str, Any] = {}
        if registry is not None and service_id in registry.services:
            blast_radius = registry.compute_blast_radius(service_id)

        clean_timeline: list[dict[str, str]] = []
        for entry in timeline or []:
            clean_timeline.append(
                {
                    "timestamp": _clean(str(entry.get("timestamp", "TBD"))),
                    "actor": _clean(str(entry.get("actor", "sre-oncall"))),
                    "event": _clean(str(entry.get("event", ""))),
                }
            )

        clean_actions: list[dict[str, str]] = []
        for item in action_items or []:
            clean_actions.append(
                {
                    "priority": _clean(str(item.get("priority", "P1"))),
                    "owner": _clean(str(item.get("owner", "platform-sre"))),
                    "task": _clean(str(item.get("task", ""))),
                    "due_date": _clean(str(item.get("due_date", "TBD"))),
                }
            )

        lines: list[str] = [
            f"# Blameless SRE Postmortem: {incident_id} — {clean_title}",
            "",
            "| Field | Value |",
            "| :--- | :--- |",
            f"| **Incident ID** | `{incident_id}` |",
            f"| **Primary Service** | `{service_id}` |",
            f"| **Severity** | `{severity}` |",
            f"| **Incident Commander** | `{commander}` |",
            "| **Culture Frame** | Blameless Systemic Review |",
            "",
            "## Executive Summary",
            clean_summary,
            "",
            "## Blameless Root Cause Analysis",
            clean_root_cause,
            "",
            "## Blast Radius & Service Impact",
        ]

        if blast_radius:
            tier0 = ", ".join(f"`{s}`" for s in blast_radius.get("tier0_impacted", [])) or "None"
            lines.append(
                f"- **Root Tier**: `{blast_radius.get('root_tier', 'unknown')}` | "
                f"**Upstream Impacted Services**: {blast_radius.get('total_impacted_services', 0)} | "
                f"**Tier-0 Exposure**: {tier0}"
            )
            for item in blast_radius.get("impacted_upstream", []):
                path_str = " <- ".join(item.get("propagation_path", []))
                lines.append(
                    f"  - `{item['service_id']}` ({item['tier']}, depth {item['depth']}, {item['criticality']}): `{path_str}`"
                )
            active_cves = blast_radius.get("active_cves", [])
            if active_cves:
                cve_str = ", ".join(f"`{c['cve_id']}` (CVSS {c['cvss_score']})" for c in active_cves)
                lines.append(f"- **Active Unpatched CVEs**: {cve_str}")
        else:
            lines.append(f"- **Primary Service**: `{service_id}` (no ontology graph attached)")

        if sbom_scan:
            lines.append(
                f"- **SBOM Gate**: `{sbom_scan.get('gate_decision', 'N/A')}` "
                f"(Max CVSS `{sbom_scan.get('max_cvss', 0.0)}`, "
                f"Vulnerable Packages `{sbom_scan.get('vulnerable_components', 0)}/{sbom_scan.get('total_components', 0)}`)"
            )
            blast_order = sbom_scan.get("blast_radius_order") or []
            if blast_order:
                lines.append(f"- **SBOM Topological Blast Order**: `{' -> '.join(blast_order)}`")

        lines.extend(["", "## Incident Timeline (UTC)"])
        if clean_timeline:
            lines.extend(["| Timestamp | Actor | Event |", "| :--- | :--- | :--- |"])
            for row in clean_timeline:
                lines.append(f"| `{row['timestamp']}` | `{row['actor']}` | {row['event']} |")
        else:
            lines.append("_No timeline events recorded._")

        lines.extend(["", "## Action Items & Preventive Controls"])
        if clean_actions:
            lines.extend(["| Priority | Owner | Action Item | Due Date |", "| :--- | :--- | :--- | :--- |"])
            for item in clean_actions:
                lines.append(
                    f"| `{item['priority']}` | `{item['owner']}` | {item['task']} | `{item['due_date']}` |"
                )
        else:
            lines.append("_No follow-up action items recorded._")

        markdown = "\n".join(lines) + "\n"
        return {
            "incident_id": incident_id,
            "service_id": service_id,
            "severity": severity,
            "commander": commander,
            "redactions_applied": redactions,
            "blast_radius_summary": {
                "total_impacted_services": blast_radius.get("total_impacted_services", 0),
                "tier0_impacted": blast_radius.get("tier0_impacted", []),
            },
            "markdown": markdown,
        }
