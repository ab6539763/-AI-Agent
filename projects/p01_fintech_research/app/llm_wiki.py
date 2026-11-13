"""FinTech LLM Wiki Engine: Persistent Markdown Knowledge Base with [[wiki_links]], ingest, query, and lint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional


_WIKI_LINK_RE = re.compile(r"\[\[([A-Za-z0-9_\-:.]+)\]\]")
_OBSERVATION_RE = re.compile(
    r"^- `(?P<period>[^`]+)` \| `(?P<metric>[^`]+)` = `(?P<value>[^`]+)` \(doc: `(?P<doc_id>[^`]+)`\)$"
)


class FinTechLLMWiki:
    """Persistent Markdown Wiki for FinTech investment research & compliance."""

    def __init__(self, wiki_dir: Path | str) -> None:
        self.wiki_dir = Path(wiki_dir)
        self.entities_dir = self.wiki_dir / "entities"
        self.index_path = self.wiki_dir / "index.md"
        self.log_path = self.wiki_dir / "log.md"
        self._init_storage()

    def _init_storage(self) -> None:
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text(
                "# FinTech Research Wiki Index\n\n"
                "| Entity ID | Name | Type | Updated At | Last Doc |\n"
                "| --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text("# FinTech Wiki Operation Log\n\n", encoding="utf-8")

    @staticmethod
    def _now_iso(timestamp: Optional[str] = None) -> str:
        if timestamp:
            return timestamp
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _parse_iso(ts: str) -> Optional[datetime]:
        ts = ts.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    def _entity_path(self, entity_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_\-:.]", "_", entity_id)
        return self.entities_dir / f"{safe_id}.md"

    def _parse_entity_page(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {
            "id": path.stem,
            "name": path.stem,
            "type": "Issuer",
            "period": "unknown",
            "updated_at": "",
            "last_doc": "",
            "metrics": {},
            "observations": [],
            "links": [],
            "notes": [],
            "raw": text,
        }
        in_frontmatter = False
        section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter and ":" in stripped:
                k, v = stripped.split(":", 1)
                meta[k.strip()] = v.strip()
                continue
            if stripped.startswith("## "):
                section = stripped[3:].strip().lower()
                continue
            if section == "observations":
                m = _OBSERVATION_RE.match(stripped)
                if m:
                    obs = {
                        "period": m.group("period"),
                        "metric": m.group("metric"),
                        "value": float(m.group("value")),
                        "doc_id": m.group("doc_id"),
                    }
                    meta["observations"].append(obs)
                    meta["metrics"][obs["metric"]] = obs["value"]
            elif section == "notes" and stripped.startswith("- "):
                meta["notes"].append(stripped[2:])

        meta["links"] = sorted(set(_WIKI_LINK_RE.findall(text)))
        return meta

    def _render_entity_page(self, data: dict[str, Any]) -> str:
        lines = [
            "---",
            f"id: {data['id']}",
            f"name: {data['name']}",
            f"type: {data['type']}",
            f"period: {data['period']}",
            f"updated_at: {data['updated_at']}",
            f"last_doc: {data['last_doc']}",
            "---",
            "",
            f"# {data['name']} (`{data['id']}`)",
            "",
            "## Metrics",
            "",
            "| Metric | Latest Value |",
            "| --- | --- |",
        ]
        for k, v in sorted(data["metrics"].items()):
            lines.append(f"| {k} | {v} |")
        if not data["metrics"]:
            lines.append("| (none) | - |")

        lines.extend(["", "## Observations", ""])
        for obs in data["observations"]:
            lines.append(
                f"- `{obs['period']}` | `{obs['metric']}` = `{obs['value']}` (doc: `{obs['doc_id']}`)"
            )
        if not data["observations"]:
            lines.append("- (no observations)")

        lines.extend(["", "## Wiki Links", ""])
        links = sorted(set(data.get("links", [])))
        if links:
            for lk in links:
                lines.append(f"- [[{lk}]]")
        else:
            lines.append("- (none)")

        lines.extend(["", "## Notes", ""])
        for note in data.get("notes", []):
            lines.append(f"- {note}")
        if not data.get("notes"):
            lines.append("- (none)")

        lines.append("")
        return "\n".join(lines)

    def _rebuild_index(self) -> None:
        rows = [
            "# FinTech Research Wiki Index",
            "",
            "| Entity ID | Name | Type | Updated At | Last Doc |",
            "| --- | --- | --- | --- | --- |",
        ]
        for path in sorted(self.entities_dir.glob("*.md")):
            meta = self._parse_entity_page(path)
            rows.append(
                f"| [[{meta['id']}]] | {meta['name']} | {meta['type']} | "
                f"{meta['updated_at']} | {meta['last_doc']} |"
            )
        rows.append("")
        self.index_path.write_text("\n".join(rows), encoding="utf-8")

    def _append_log(self, action: str, detail: str, timestamp: Optional[str] = None) -> None:
        ts = self._now_iso(timestamp)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"- [{ts}] **{action}**: {detail}\n")

    def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        entities: Optional[list[dict[str, Any]]] = None,
        timestamp: Optional[str] = None,
    ) -> dict[str, Any]:
        ts = self._now_iso(timestamp)
        entities = entities or []
        content_links = _WIKI_LINK_RE.findall(content)
        pages_updated: list[str] = []
        links_created: list[str] = []

        if not entities and content_links:
            # Create stub/note entries for referenced wiki links if no explicit entity dicts provided
            entities = [{"id": lk, "name": lk, "type": "Issuer", "links": []} for lk in content_links]

        for ent in entities:
            eid = str(ent["id"])
            epath = self._entity_path(eid)
            if epath.exists():
                page = self._parse_entity_page(epath)
            else:
                page = {
                    "id": eid,
                    "name": ent.get("name", eid),
                    "type": ent.get("type", "Issuer"),
                    "period": ent.get("period", "2025-Q4"),
                    "updated_at": ts,
                    "last_doc": doc_id,
                    "metrics": {},
                    "observations": [],
                    "links": [],
                    "notes": [],
                }

            page["name"] = ent.get("name", page["name"])
            page["type"] = ent.get("type", page["type"])
            period = str(ent.get("period", page.get("period", "2025-Q4")))
            page["period"] = period
            page["updated_at"] = ts
            page["last_doc"] = doc_id

            for m_name, m_val in ent.get("metrics", {}).items():
                f_val = float(m_val)
                page["metrics"][m_name] = f_val
                page["observations"].append(
                    {
                        "period": period,
                        "metric": m_name,
                        "value": f_val,
                        "doc_id": doc_id,
                    }
                )

            new_links = set(page.get("links", []))
            for lk in ent.get("links", []):
                if lk != eid:
                    new_links.add(str(lk))
                    links_created.append(f"{eid}->[[{lk}]]")
            for lk in content_links:
                if lk != eid:
                    new_links.add(lk)
            page["links"] = sorted(new_links)

            note_summary = f"[{doc_id}] {title}: {content.strip()[:240]}"
            if note_summary not in page["notes"]:
                page["notes"].append(note_summary)

            epath.write_text(self._render_entity_page(page), encoding="utf-8")
            pages_updated.append(eid)

        self._rebuild_index()
        self._append_log(
            "INGEST",
            f"doc_id=`{doc_id}` title=\"{title}\" pages={json.dumps(pages_updated)}",
            timestamp=ts,
        )
        return {
            "doc_id": doc_id,
            "title": title,
            "pages_updated": pages_updated,
            "links_created": sorted(set(links_created)),
            "updated_at": ts,
        }

    def query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", question) if len(t) >= 2]
        scored: list[tuple[int, dict[str, Any], Path]] = []

        for path in sorted(self.entities_dir.glob("*.md")):
            meta = self._parse_entity_page(path)
            haystack = meta["raw"].lower()
            score = 0
            for tok in tokens:
                if tok in meta["id"].lower() or tok in meta["name"].lower():
                    score += 5
                elif tok in haystack:
                    score += 2
            if score > 0 or not tokens:
                scored.append((score, meta, path))

        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        top_hits = scored[:top_k]

        if not top_hits:
            return {
                "question": question,
                "answer": "No matching entities or financial metrics found in the FinTech Wiki.",
                "citations": [],
                "matched_links": [],
                "confidence": 0.0,
            }

        summary_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        matched_links: set[str] = set()

        for score, meta, path in top_hits:
            metrics_str = ", ".join(f"{k}={v}" for k, v in sorted(meta["metrics"].items())) or "no metrics"
            summary_parts.append(
                f"{meta['name']} ([[{meta['id']}]], {meta['type']}, period={meta['period']}): {metrics_str}."
            )
            citations.append(
                {
                    "entity_id": meta["id"],
                    "name": meta["name"],
                    "score": score,
                    "path": str(path),
                    "metrics": meta["metrics"],
                }
            )
            for lk in meta["links"]:
                matched_links.add(f"[[{lk}]]")

        confidence = min(0.95, 0.4 + 0.1 * len(top_hits))
        return {
            "question": question,
            "answer": " ".join(summary_parts),
            "citations": citations,
            "matched_links": sorted(matched_links),
            "confidence": round(confidence, 2),
        }

    def lint(self, stale_days: int = 90, reference_date: Optional[str] = None) -> dict[str, Any]:
        ref_dt = self._parse_iso(reference_date) if reference_date else datetime.now(timezone.utc)
        if ref_dt is None:
            ref_dt = datetime.now(timezone.utc)

        pages: dict[str, dict[str, Any]] = {}
        for path in sorted(self.entities_dir.glob("*.md")):
            meta = self._parse_entity_page(path)
            pages[meta["id"]] = meta

        incoming_counts: dict[str, int] = {eid: 0 for eid in pages}
        broken_links: list[dict[str, str]] = []

        for eid, meta in pages.items():
            for target in meta["links"]:
                if target in pages:
                    incoming_counts[target] += 1
                else:
                    broken_links.append({"source": eid, "target": target})

        orphan_pages = sorted(eid for eid, cnt in incoming_counts.items() if cnt == 0)

        conflicting_metrics: list[dict[str, Any]] = []
        for eid, meta in pages.items():
            by_key: dict[tuple[str, str], list[tuple[float, str]]] = {}
            for obs in meta["observations"]:
                key = (obs["period"], obs["metric"])
                by_key.setdefault(key, []).append((obs["value"], obs["doc_id"]))
            for (period, metric_name), vals in sorted(by_key.items()):
                distinct_vals = sorted({v for v, _ in vals})
                if len(distinct_vals) > 1:
                    conflicting_metrics.append(
                        {
                            "entity_id": eid,
                            "period": period,
                            "metric": metric_name,
                            "values": distinct_vals,
                            "docs": [d for _, d in vals],
                        }
                    )

        stale_entries: list[dict[str, str]] = []
        cutoff = ref_dt - timedelta(days=stale_days)
        for eid, meta in pages.items():
            upd = self._parse_iso(meta.get("updated_at", ""))
            if upd is not None and upd < cutoff:
                stale_entries.append({"entity_id": eid, "updated_at": meta["updated_at"]})

        has_issues = bool(orphan_pages or broken_links or conflicting_metrics or stale_entries)
        status = "issues_found" if has_issues else "healthy"

        self._append_log(
            "LINT",
            f"status={status} orphans={len(orphan_pages)} broken={len(broken_links)} "
            f"conflicts={len(conflicting_metrics)} stale={len(stale_entries)}",
        )
        return {
            "status": status,
            "total_pages": len(pages),
            "orphan_pages": orphan_pages,
            "broken_links": broken_links,
            "conflicting_metrics": conflicting_metrics,
            "stale_entries": stale_entries,
        }
