"""LLM Wiki Knowledge Base: persistent Markdown wiki with [[wiki_links]], ingest, query, and lint."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Any, Optional

from .ontology import DevSecOpsOntologyRegistry


WIKI_LINK_RE = re.compile(r"\[\[([A-Za-z0-9_.\-:]+)\]\]")


class DevSecOpsLLMWiki:
    """Maintains a persistent Markdown DevSecOps knowledge graph (index.md, log.md, entities/*.md)."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.entities_dir = self.root_dir / "entities"
        self.index_path = self.root_dir / "index.md"
        self.log_path = self.root_dir / "log.md"
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text("# DevSecOps Knowledge Wiki Index\n\n_No entities ingested yet._\n", encoding="utf-8")
        if not self.log_path.exists():
            self.log_path.write_text("# DevSecOps Wiki Operation Log\n\n", encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def append_log(self, operation: str, detail: str) -> None:
        line = f"- `{self._now_iso()}` **{operation}**: {detail}\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def ingest(
        self,
        entity_type: str,
        entity_id: str,
        title: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        links: Optional[list[str]] = None,
    ) -> Path:
        """Persist an entity Markdown page with [[wiki_links]], rebuild index.md, and append log.md."""
        metadata = metadata or {}
        links = links or []
        safe_id = re.sub(r"[^A-Za-z0-9_.\-]", "_", entity_id)
        entity_path = self.entities_dir / f"{safe_id}.md"

        meta_lines = [f"- **{k}**: {v}" for k, v in sorted(metadata.items())]
        meta_block = "\n".join(meta_lines) if meta_lines else "- *(none)*"
        links_block = " ".join(f"[[{target}]]" for target in links) if links else "*(none)*"

        page = (
            f"# {title}\n\n"
            f"- **Entity ID**: `{entity_id}`\n"
            f"- **Type**: `{entity_type}`\n"
            f"- **Updated**: `{self._now_iso()}`\n\n"
            f"## Metadata\n{meta_block}\n\n"
            f"## Details\n{content.strip()}\n\n"
            f"## Related Links\n{links_block}\n"
        )
        entity_path.write_text(page, encoding="utf-8")
        self._rebuild_index()
        self.append_log("INGEST", f"Ingested `{entity_type}` [[{entity_id}]] ({title})")
        return entity_path

    def _parse_entity_header(self, path: Path) -> dict[str, str]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else path.stem
        entity_id = path.stem
        entity_type = "unknown"
        for line in lines[:12]:
            if line.startswith("- **Entity ID**:"):
                entity_id = line.split("`")[1] if "`" in line else path.stem
            elif line.startswith("- **Type**:"):
                entity_type = line.split("`")[1] if "`" in line else "unknown"
        return {"entity_id": entity_id, "entity_type": entity_type, "title": title, "filename": path.name}

    def _rebuild_index(self) -> None:
        pages = sorted(self.entities_dir.glob("*.md"))
        lines = [
            "# DevSecOps Knowledge Wiki Index",
            "",
            f"Total entities: {len(pages)}",
            "",
            "| Entity | Type | Title | File |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for p in pages:
            info = self._parse_entity_header(p)
            lines.append(
                f"| [[{info['entity_id']}]] | `{info['entity_type']}` | {info['title']} | `entities/{info['filename']}` |"
            )
        lines.append("")
        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def sync_from_ontology(self, registry: DevSecOpsOntologyRegistry) -> int:
        """Materialize all ontology entities into Markdown wiki pages."""
        count = 0
        for svc in registry.services.values():
            links = [
                link.target_service_id
                for link in registry.dependencies
                if link.source_service_id == svc.service_id
            ]
            if svc.runbook_id:
                links.append(svc.runbook_id)
            self.ingest(
                "service",
                svc.service_id,
                svc.name,
                f"Service `{svc.service_id}` owned by `{svc.owner_team}` in `{svc.environment}` ({svc.tier}).",
                metadata={
                    "tier": svc.tier,
                    "owner_team": svc.owner_team,
                    "environment": svc.environment,
                    "runbook_id": svc.runbook_id or "MISSING",
                },
                links=links,
            )
            count += 1

        for rb in registry.runbooks.values():
            steps_md = "\n".join(f"{i}. {step}" for i, step in enumerate(rb.steps, 1))
            self.ingest(
                "runbook",
                rb.runbook_id,
                rb.title,
                f"Operational runbook for [[{rb.service_id}]]:\n\n{steps_md}",
                metadata={"service_id": rb.service_id, "owner": rb.owner},
                links=[rb.service_id],
            )
            count += 1

        for cve in registry.cves.values():
            self.ingest(
                "cve",
                cve.cve_id,
                f"{cve.cve_id} ({cve.severity})",
                f"{cve.description}\n\nRemediation: {cve.remediation}",
                metadata={
                    "service_id": cve.service_id,
                    "cvss_score": cve.cvss_score,
                    "severity": cve.severity,
                    "patched": cve.patched,
                },
                links=[cve.service_id],
            )
            count += 1

        for inc in registry.incidents.values():
            self.ingest(
                "incident",
                inc.incident_id,
                inc.title,
                inc.summary or f"Incident on [[{inc.service_id}]].",
                metadata={
                    "service_id": inc.service_id,
                    "severity": inc.severity,
                    "status": inc.status,
                    "postmortem_updated_at": inc.postmortem_updated_at or "MISSING",
                },
                links=[inc.service_id, *inc.cve_ids],
            )
            count += 1
        return count

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Deterministic keyword-overlap search across entities/*.md."""
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_\-]+", query_text) if len(t) >= 2]
        results: list[dict[str, Any]] = []
        for path in sorted(self.entities_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            score = sum(lowered.count(tok) for tok in tokens) if tokens else 1
            if score > 0:
                info = self._parse_entity_header(path)
                wiki_links = sorted(set(WIKI_LINK_RE.findall(text)))
                snippet = " ".join(line.strip() for line in text.splitlines()[4:10] if line.strip())[:240]
                results.append(
                    {
                        "entity_id": info["entity_id"],
                        "entity_type": info["entity_type"],
                        "title": info["title"],
                        "score": score,
                        "wiki_links": wiki_links,
                        "snippet": snippet,
                        "path": str(path),
                    }
                )
        results.sort(key=lambda r: (-r["score"], r["entity_id"]))
        self.append_log("QUERY", f"Query `{query_text}` returned {min(len(results), top_k)} match(es)")
        return results[:top_k]

    def lint(
        self,
        registry: Optional[DevSecOpsOntologyRegistry] = None,
        reference_date: str = "2026-11-13",
        stale_days: int = 30,
    ) -> dict[str, Any]:
        """Detect services without runbooks, unpatched critical CVEs, stale postmortems, and broken wiki links."""
        services_without_runbooks: list[str] = []
        unpatched_critical_cves: list[dict[str, Any]] = []
        stale_postmortems: list[dict[str, Any]] = []

        if registry is not None:
            for svc in registry.services.values():
                has_runbook = bool(svc.runbook_id and svc.runbook_id in registry.runbooks)
                if not has_runbook:
                    services_without_runbooks.append(svc.service_id)

            for cve in registry.cves.values():
                if not cve.patched and (cve.cvss_score >= 9.0 or cve.severity == "CRITICAL"):
                    unpatched_critical_cves.append(
                        {
                            "cve_id": cve.cve_id,
                            "service_id": cve.service_id,
                            "cvss_score": cve.cvss_score,
                        }
                    )

            ref = date.fromisoformat(reference_date)
            for inc in registry.incidents.values():
                if not inc.postmortem_updated_at:
                    stale_postmortems.append(
                        {
                            "incident_id": inc.incident_id,
                            "service_id": inc.service_id,
                            "reason": "missing_postmortem",
                        }
                    )
                else:
                    pm_date = date.fromisoformat(inc.postmortem_updated_at)
                    age_days = (ref - pm_date).days
                    if age_days > stale_days:
                        stale_postmortems.append(
                            {
                                "incident_id": inc.incident_id,
                                "service_id": inc.service_id,
                                "age_days": age_days,
                                "reason": f"stale_by_{age_days}_days",
                            }
                        )

        # Check broken [[wiki_links]] across entities/*.md
        existing_ids = {self._parse_entity_header(p)["entity_id"] for p in self.entities_dir.glob("*.md")}
        broken_wiki_links: list[dict[str, str]] = []
        for path in sorted(self.entities_dir.glob("*.md")):
            src_id = self._parse_entity_header(path)["entity_id"]
            text = path.read_text(encoding="utf-8")
            for target in sorted(set(WIKI_LINK_RE.findall(text))):
                if target not in existing_ids:
                    broken_wiki_links.append({"source": src_id, "missing_target": target})

        total_issues = (
            len(services_without_runbooks)
            + len(unpatched_critical_cves)
            + len(stale_postmortems)
            + len(broken_wiki_links)
        )
        report = {
            "reference_date": reference_date,
            "stale_days": stale_days,
            "healthy": total_issues == 0,
            "total_issues": total_issues,
            "services_without_runbooks": sorted(services_without_runbooks),
            "unpatched_critical_cves": unpatched_critical_cves,
            "stale_postmortems": stale_postmortems,
            "broken_wiki_links": broken_wiki_links,
        }
        self.append_log("LINT", f"Completed wiki lint: {total_issues} issue(s) found")
        return report
