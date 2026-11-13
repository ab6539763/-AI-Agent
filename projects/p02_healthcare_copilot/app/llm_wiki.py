"""Offline deterministic Clinical LLM Wiki persisting Markdown pages with [[wiki_links]]."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


WIKI_LINK_RE = re.compile(r"\[\[([a-zA-Z0-9_.-]+)\]\]")
TOKEN_RE = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")


class ClinicalLLMWiki:
    """File-backed clinical knowledge wiki with ingest, query, and lint capabilities."""

    def __init__(self, wiki_dir: Path | str) -> None:
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
                "# Clinical Knowledge Wiki Index\n\n| ID | Title | Type | Condition | Medication | Dose (mg) | Citation |\n| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Clinical Wiki Activity Log\n\n", encoding="utf-8"
            )

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw_id.strip().lower()).strip("_")
        if not cleaned:
            raise ValueError("doc_id must contain at least one alphanumeric character")
        return cleaned

    def _append_log(self, action: str, detail: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"- `{ts}` **{action}**: {detail}\n")

    @staticmethod
    def _parse_entity_file(path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        meta: dict[str, str] = {}
        body = text
        if text.startswith("---\n"):
            parts = text.split("\n---\n", 1)
            if len(parts) == 2:
                fm_block, body = parts[0][4:], parts[1]
                for line in fm_block.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
        links = list(dict.fromkeys(WIKI_LINK_RE.findall(text)))
        dose_val: float | None = None
        if meta.get("dose_mg") and meta["dose_mg"].lower() not in ("none", "null", ""):
            try:
                dose_val = float(meta["dose_mg"])
            except ValueError:
                dose_val = None

        return {
            "doc_id": meta.get("doc_id", path.stem),
            "title": meta.get("title", path.stem),
            "entity_type": meta.get("entity_type", "guideline"),
            "condition": meta.get("condition", ""),
            "medication": meta.get("medication", ""),
            "dose_mg": dose_val,
            "citation": meta.get("citation", ""),
            "updated_at": meta.get("updated_at", ""),
            "wiki_links": links,
            "body": body.strip(),
            "path": str(path),
        }

    def list_entities(self) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for md_file in sorted(self.entities_dir.glob("*.md")):
            entities.append(self._parse_entity_file(md_file))
        return entities

    def _rebuild_index(self) -> None:
        entities = self.list_entities()
        lines = [
            "# Clinical Knowledge Wiki Index",
            "",
            f"Total Entities: {len(entities)}",
            "",
            "| ID | Title | Type | Condition | Medication | Dose (mg) | Citation |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for ent in entities:
            dose_str = f"{ent['dose_mg']}" if ent["dose_mg"] is not None else "-"
            cit = ent["citation"] or "_MISSING_"
            lines.append(
                f"| [[{ent['doc_id']}]] | {ent['title']} | {ent['entity_type']} | "
                f"{ent['condition'] or '-'} | {ent['medication'] or '-'} | {dose_str} | {cit} |"
            )
        lines.append("")
        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        entity_type: str = "guideline",
        condition: str | None = None,
        medication: str | None = None,
        dose_mg: float | None = None,
        citation: str | None = None,
        related_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a clinical knowledge entity as Markdown with [[wiki_links]]."""
        safe_id = self._sanitize_id(doc_id)
        ts = datetime.now(timezone.utc).isoformat()
        related = [self._sanitize_id(r) for r in (related_ids or []) if r.strip()]

        # Ensure condition/medication also appear as wiki_links if provided
        auto_links = list(related)
        if condition:
            cond_id = self._sanitize_id(condition)
            if cond_id not in auto_links and cond_id != safe_id:
                auto_links.append(cond_id)
        if medication:
            med_id = self._sanitize_id(medication)
            if med_id not in auto_links and med_id != safe_id:
                auto_links.append(med_id)

        frontmatter = [
            "---",
            f"doc_id: {safe_id}",
            f"title: {title.strip()}",
            f"entity_type: {entity_type.strip().lower()}",
            f"condition: {(condition or '').strip().lower()}",
            f"medication: {(medication or '').strip().lower()}",
            f"dose_mg: {dose_mg if dose_mg is not None else ''}",
            f"citation: {(citation or '').strip()}",
            f"updated_at: {ts}",
            "---",
            "",
            f"# {title.strip()}",
            "",
            content.strip(),
            "",
        ]
        if auto_links:
            frontmatter.append("## Related Entities")
            frontmatter.append("")
            for link in auto_links:
                frontmatter.append(f"- [[{link}]]")
            frontmatter.append("")

        entity_path = self.entities_dir / f"{safe_id}.md"
        entity_path.write_text("\n".join(frontmatter), encoding="utf-8")
        self._rebuild_index()
        self._append_log("INGEST", f"[[{safe_id}]] ({title.strip()})")

        return self._parse_entity_file(entity_path)

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Deterministic keyword/token overlap search across persisted wiki entities."""
        q_tokens = {t.lower() for t in TOKEN_RE.findall(query_text)}
        if not q_tokens:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for ent in self.list_entities():
            title_tokens = {t.lower() for t in TOKEN_RE.findall(ent["title"])}
            meta_tokens = {
                t.lower()
                for t in TOKEN_RE.findall(
                    f"{ent['doc_id']} {ent['condition']} {ent['medication']} {ent['entity_type']}"
                )
            }
            body_tokens = {t.lower() for t in TOKEN_RE.findall(ent["body"])}

            score = (
                3.0 * len(q_tokens & title_tokens)
                + 2.0 * len(q_tokens & meta_tokens)
                + 1.0 * len(q_tokens & body_tokens)
            )
            if score > 0:
                snippet = ent["body"][:240].replace("\n", " ").strip()
                scored.append(
                    (
                        score,
                        {
                            "doc_id": ent["doc_id"],
                            "title": ent["title"],
                            "entity_type": ent["entity_type"],
                            "score": score,
                            "snippet": snippet,
                            "citation": ent["citation"],
                            "wiki_links": ent["wiki_links"],
                            "path": ent["path"],
                        },
                    )
                )

        scored.sort(key=lambda item: (-item[0], item[1]["doc_id"]))
        return [item[1] for item in scored[:top_k]]

    def lint(self) -> dict[str, Any]:
        """Detect conflicting dosage guidelines, orphan conditions, and missing citations."""
        entities = self.list_entities()
        existing_ids = {ent["doc_id"] for ent in entities}
        issues: list[dict[str, Any]] = []

        # Track incoming links for orphan condition detection
        incoming_links: dict[str, set[str]] = {eid: set() for eid in existing_ids}
        for ent in entities:
            for target in ent["wiki_links"]:
                if target in incoming_links and target != ent["doc_id"]:
                    incoming_links[target].add(ent["doc_id"])

        # 1. Conflicting dosage guidelines: group by (condition, medication)
        dosage_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for ent in entities:
            if ent["entity_type"] == "guideline" and ent["medication"] and ent["dose_mg"] is not None:
                key = (ent["condition"] or "*", ent["medication"])
                dosage_groups.setdefault(key, []).append(ent)

        for (cond, med), group in dosage_groups.items():
            distinct_doses = sorted({g["dose_mg"] for g in group if g["dose_mg"] is not None})
            if len(distinct_doses) > 1:
                issues.append(
                    {
                        "issue_type": "conflicting_dosage_guidelines",
                        "severity": "high",
                        "condition": cond,
                        "medication": med,
                        "doses_mg": distinct_doses,
                        "doc_ids": [g["doc_id"] for g in group],
                        "message": f"Conflicting doses {distinct_doses} mg for {med} ({cond}).",
                    }
                )

        # 2. Orphan conditions (unlinked condition entities or broken [[wiki_links]])
        for ent in entities:
            broken_links = [lnk for lnk in ent["wiki_links"] if lnk not in existing_ids]
            if broken_links:
                issues.append(
                    {
                        "issue_type": "orphan_conditions",
                        "severity": "medium",
                        "doc_id": ent["doc_id"],
                        "broken_links": broken_links,
                        "message": f"Entity '{ent['doc_id']}' references missing wiki_links: {broken_links}.",
                    }
                )
            if ent["entity_type"] == "condition":
                has_incoming = bool(incoming_links.get(ent["doc_id"]))
                has_outgoing = any(lnk in existing_ids for lnk in ent["wiki_links"])
                if not has_incoming and not has_outgoing:
                    issues.append(
                        {
                            "issue_type": "orphan_conditions",
                            "severity": "medium",
                            "doc_id": ent["doc_id"],
                            "broken_links": [],
                            "message": f"Orphan condition '{ent['doc_id']}' has no incoming or outgoing links.",
                        }
                    )

        # 3. Missing citations
        for ent in entities:
            cit = (ent["citation"] or "").strip()
            if ent["entity_type"] in ("guideline", "protocol") and (
                not cit or cit.lower() in ("none", "n/a", "tbd", "unknown")
            ):
                issues.append(
                    {
                        "issue_type": "missing_citations",
                        "severity": "medium",
                        "doc_id": ent["doc_id"],
                        "message": f"Guideline '{ent['doc_id']}' is missing a valid clinical citation.",
                    }
                )

        counts = {
            "conflicting_dosage_guidelines": sum(
                1 for i in issues if i["issue_type"] == "conflicting_dosage_guidelines"
            ),
            "orphan_conditions": sum(
                1 for i in issues if i["issue_type"] == "orphan_conditions"
            ),
            "missing_citations": sum(
                1 for i in issues if i["issue_type"] == "missing_citations"
            ),
        }
        status = "issues_found" if issues else "ok"
        self._append_log("LINT", f"status={status}, total_issues={len(issues)}")
        return {
            "status": status,
            "total_entities": len(entities),
            "total_issues": len(issues),
            "counts": counts,
            "issues": issues,
        }
