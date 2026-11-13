"""Manufacturing LLM Wiki: Markdown Knowledge Graph with [[wiki_links]].

Persists structured Markdown pages under `wiki_dir`:
- `index.md`: Master index of all ingested entities with [[wiki_links]].
- `log.md`: Append-only operational log of ingest, query, and lint events.
- `entities/<id>.md`: Individual entity pages with YAML-style frontmatter,
  body content, and [[wiki_links]] relationships.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ontology import ManufacturingOntologyRegistry

WIKI_LINK_RE = re.compile(r"\[\[([A-Za-z0-9_.\-:]+)\]\]")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManufacturingLLMWiki:
    """Deterministic file-backed Markdown Wiki for manufacturing operations."""

    def __init__(self, wiki_dir: str | Path) -> None:
        self.wiki_dir = Path(wiki_dir)
        self.entities_dir = self.wiki_dir / "entities"
        self.index_path = self.wiki_dir / "index.md"
        self.log_path = self.wiki_dir / "log.md"
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text(
                "# Manufacturing Operations Wiki Index\n\n_No entities ingested yet._\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Manufacturing Operations Wiki Log\n\n",
                encoding="utf-8",
            )

    def _append_log(self, action: str, detail: str) -> None:
        line = f"- [{_utc_now_iso()}] **{action}**: {detail}\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        if not text.startswith("---\n"):
            return {}, text
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return {}, text
        raw_meta = text[4:end_idx]
        body = text[end_idx + 5 :]
        meta: dict[str, Any] = {}
        for line in raw_meta.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith("[") or val.startswith("{"):
                try:
                    meta[key] = json.loads(val)
                    continue
                except json.JSONDecodeError:
                    pass
            if val.lower() in ("true", "false"):
                meta[key] = val.lower() == "true"
            else:
                meta[key] = val
        return meta, body

    def _rebuild_index(self) -> None:
        entries: list[tuple[str, str, str]] = []
        for md_file in sorted(self.entities_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            meta, _ = self._parse_frontmatter(text)
            entity_id = str(meta.get("entity_id", md_file.stem))
            entity_type = str(meta.get("entity_type", "Unknown"))
            title = str(meta.get("title", entity_id))
            entries.append((entity_type, entity_id, title))

        lines = ["# Manufacturing Operations Wiki Index", ""]
        if not entries:
            lines.append("_No entities ingested yet._")
        else:
            current_type = None
            for entity_type, entity_id, title in sorted(entries):
                if entity_type != current_type:
                    current_type = entity_type
                    lines.append(f"## {current_type}")
                lines.append(f"- [[{entity_id}]] — {title}")
            lines.append("")

        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def ingest(
        self,
        entity_id: str,
        entity_type: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Create or update a Markdown entity page and refresh index.md & log.md."""
        self._ensure_structure()
        meta = dict(metadata or {})
        meta["entity_id"] = entity_id
        meta["entity_type"] = entity_type
        meta["title"] = title
        meta["updated_at"] = _utc_now_iso()

        frontmatter_lines = ["---"]
        for k, v in meta.items():
            if isinstance(v, (list, dict)):
                frontmatter_lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            elif isinstance(v, bool):
                frontmatter_lines.append(f"{k}: {'true' if v else 'false'}")
            else:
                frontmatter_lines.append(f"{k}: {v}")
        frontmatter_lines.append("---")

        clean_links = []
        for lnk in links or []:
            token = lnk.strip().removeprefix("[[").removesuffix("]]")
            if token and token not in clean_links:
                clean_links.append(token)

        sections = [
            "\n".join(frontmatter_lines),
            "",
            f"# {title} (`{entity_id}`)",
            "",
            content.strip(),
            "",
        ]
        if clean_links:
            sections.append("## Relations")
            for token in clean_links:
                sections.append(f"- [[{token}]]")
            sections.append("")

        entity_path = self.entities_dir / f"{entity_id}.md"
        entity_path.write_text("\n".join(sections), encoding="utf-8")

        self._rebuild_index()
        self._append_log("INGEST", f"{entity_type} [[{entity_id}]] ({title})")
        return entity_path

    def ingest_from_ontology(self, registry: ManufacturingOntologyRegistry) -> int:
        """Sync Equipment, FaultCodes, and MaintenanceSOPs from Ontology into Wiki."""
        count = 0
        for sop in registry.sops.values():
            steps_md = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sop.steps))
            safety_md = "\n".join(f"- {s}" for s in sop.safety_precautions)
            body = (
                f"Revision: `{sop.revision}` (Latest: `{sop.latest_revision}`)\n\n"
                f"### Procedure Steps\n{steps_md}\n\n"
                f"### Safety Precautions\n{safety_md}"
            )
            self.ingest(
                entity_id=sop.sop_id,
                entity_type="MaintenanceSOP",
                title=sop.title,
                content=body,
                links=list(sop.target_fault_codes),
                metadata={
                    "revision": sop.revision,
                    "latest_revision": sop.latest_revision,
                    "estimated_minutes": sop.estimated_minutes,
                },
            )
            count += 1

        for fc in registry.fault_codes.values():
            links = [fc.recommended_sop_id] if fc.recommended_sop_id else []
            body = (
                f"Severity: **{fc.severity.value}**\n\n"
                f"Requires Shutdown: `{fc.requires_shutdown}`\n\n"
                f"Root Cause: {fc.root_cause}"
            )
            self.ingest(
                entity_id=fc.code,
                entity_type="FaultCode",
                title=fc.title,
                content=body,
                links=links,
                metadata={
                    "severity": fc.severity.value,
                    "equipment_type": fc.equipment_type,
                    "recommended_sop_id": fc.recommended_sop_id or "",
                    "requires_shutdown": fc.requires_shutdown,
                },
            )
            count += 1

        for eq in registry.equipment.values():
            thresh_lines = [
                f"- `{m}`: warn={t.warn}{t.unit}, critical={t.critical}{t.unit}"
                for m, t in sorted(eq.thresholds.items())
            ]
            body = (
                f"Type: `{eq.equipment_type}` | Line: `{eq.line_id}` | Location: {eq.location}\n\n"
                f"### Telemetry Thresholds\n" + "\n".join(thresh_lines)
            )
            self.ingest(
                entity_id=eq.equipment_id,
                entity_type="Equipment",
                title=eq.name,
                content=body,
                links=list(eq.sop_ids),
                metadata={
                    "equipment_type": eq.equipment_type,
                    "line_id": eq.line_id,
                    "status": eq.status.value,
                },
            )
            count += 1

        return count

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Deterministic keyword-based search across persisted entity pages."""
        self._ensure_structure()
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_\-]+", query_text) if len(t) >= 2]
        results: list[dict[str, Any]] = []

        for md_file in sorted(self.entities_dir.glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")
            meta, body = self._parse_frontmatter(raw)
            entity_id = str(meta.get("entity_id", md_file.stem))
            entity_type = str(meta.get("entity_type", "Unknown"))
            title = str(meta.get("title", entity_id))
            haystack = f"{entity_id} {entity_type} {title} {body}".lower()

            if not tokens:
                score = 1
            else:
                score = sum(haystack.count(tok) for tok in tokens)
                if entity_id.lower() in query_text.lower():
                    score += 5

            if score > 0:
                wiki_links = sorted(set(WIKI_LINK_RE.findall(raw)))
                snippet = " ".join(body.strip().splitlines()[:4])[:240]
                results.append(
                    {
                        "entity_id": entity_id,
                        "entity_type": entity_type,
                        "title": title,
                        "score": score,
                        "wiki_links": wiki_links,
                        "snippet": snippet,
                        "path": str(md_file),
                    }
                )

        results.sort(key=lambda r: (-r["score"], r["entity_id"]))
        top_results = results[:top_k]
        self._append_log("QUERY", f"q={query_text!r} hits={len(top_results)}")
        return top_results

    def lint(self, registry: ManufacturingOntologyRegistry | None = None) -> dict[str, Any]:
        """Audit Wiki & optional Ontology for unmapped fault codes, outdated SOPs, and orphan equipment."""
        self._ensure_structure()
        issues: list[dict[str, Any]] = []

        pages: dict[str, dict[str, Any]] = {}
        for md_file in sorted(self.entities_dir.glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")
            meta, body = self._parse_frontmatter(raw)
            eid = str(meta.get("entity_id", md_file.stem))
            pages[eid] = {
                "meta": meta,
                "body": body,
                "raw": raw,
                "links": WIKI_LINK_RE.findall(raw),
            }

        sop_ids = {
            eid for eid, p in pages.items() if p["meta"].get("entity_type") == "MaintenanceSOP"
        }
        if registry:
            sop_ids |= set(registry.sops.keys())

        unmapped_fault_codes: list[str] = []
        outdated_sops: list[str] = []
        orphan_equipment: list[str] = []
        broken_wiki_links: list[dict[str, str]] = []

        for eid, page in sorted(pages.items()):
            meta = page["meta"]
            etype = str(meta.get("entity_type", ""))
            links = page["links"]

            # 1. Unmapped fault codes
            if etype == "FaultCode":
                rec_sop = str(meta.get("recommended_sop_id", "")).strip()
                has_sop_link = any(lnk in sop_ids for lnk in links) or (rec_sop in sop_ids)
                if not has_sop_link:
                    unmapped_fault_codes.append(eid)
                    issues.append(
                        {
                            "category": "unmapped_fault_code",
                            "entity_id": eid,
                            "detail": f"FaultCode {eid} has no mapped MaintenanceSOP",
                        }
                    )

            # 2. Outdated SOP revisions
            elif etype == "MaintenanceSOP":
                rev = str(meta.get("revision", "")).strip()
                latest = str(meta.get("latest_revision", "")).strip()
                if (latest and rev and rev != latest) or meta.get("outdated") is True:
                    outdated_sops.append(eid)
                    issues.append(
                        {
                            "category": "outdated_sop",
                            "entity_id": eid,
                            "detail": f"SOP {eid} is at revision {rev or 'unknown'}, latest is {latest or 'unknown'}",
                        }
                    )

            # 3. Orphan equipment (no links to any SOP/FaultCode or empty relations)
            elif etype == "Equipment":
                if not links:
                    orphan_equipment.append(eid)
                    issues.append(
                        {
                            "category": "orphan_equipment",
                            "entity_id": eid,
                            "detail": f"Equipment {eid} has no [[wiki_links]] to SOPs or FaultCodes",
                        }
                    )

            # 4. Broken wiki links
            for target in links:
                if target not in pages and (registry is None or (
                    target not in registry.equipment
                    and target not in registry.fault_codes
                    and target not in registry.sops
                )):
                    broken_wiki_links.append({"source": eid, "target": target})
                    issues.append(
                        {
                            "category": "broken_wiki_link",
                            "entity_id": eid,
                            "detail": f"Broken link [[{target}]] in {eid}",
                        }
                    )

        # Also check registry-only entities if provided
        if registry:
            for fc_code, fc in sorted(registry.fault_codes.items()):
                if fc_code not in pages:
                    if not fc.recommended_sop_id or fc.recommended_sop_id not in registry.sops:
                        if fc_code not in unmapped_fault_codes:
                            unmapped_fault_codes.append(fc_code)
                            issues.append(
                                {
                                    "category": "unmapped_fault_code",
                                    "entity_id": fc_code,
                                    "detail": f"Registry FaultCode {fc_code} has no valid SOP",
                                }
                            )
            for sop_id, sop in sorted(registry.sops.items()):
                if sop_id not in pages and sop.is_outdated and sop_id not in outdated_sops:
                    outdated_sops.append(sop_id)
                    issues.append(
                        {
                            "category": "outdated_sop",
                            "entity_id": sop_id,
                            "detail": f"Registry SOP {sop_id} revision {sop.revision} != {sop.latest_revision}",
                        }
                    )
            for eq_id, eq in sorted(registry.equipment.items()):
                if eq_id not in pages:
                    has_reg_link = bool(eq.sop_ids) or any(
                        lnk.source_id == eq_id for lnk in registry.links
                    )
                    if not has_reg_link and eq_id not in orphan_equipment:
                        orphan_equipment.append(eq_id)
                        issues.append(
                            {
                                "category": "orphan_equipment",
                                "entity_id": eq_id,
                                "detail": f"Registry Equipment {eq_id} has no SOP or OpsLink",
                            }
                        )

        report = {
            "healthy": len(issues) == 0,
            "unmapped_fault_codes": sorted(unmapped_fault_codes),
            "outdated_sops": sorted(outdated_sops),
            "orphan_equipment": sorted(orphan_equipment),
            "broken_wiki_links": broken_wiki_links,
            "issues": issues,
            "counts": {
                "unmapped_fault_codes": len(unmapped_fault_codes),
                "outdated_sops": len(outdated_sops),
                "orphan_equipment": len(orphan_equipment),
                "broken_wiki_links": len(broken_wiki_links),
                "total_issues": len(issues),
            },
        }
        self._append_log("LINT", f"healthy={report['healthy']} total_issues={len(issues)}")
        return report
