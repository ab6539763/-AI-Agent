"""Retail LLM Wiki: persistent compiled Markdown knowledge base with ingest, query, and lint."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ontology import RetailOntologyRegistry

WIKI_LINK_RE = re.compile(r"\[\[([A-Za-z0-9_\-\.]+)\]\]")
DISCOUNT_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:off|discount|折扣|立减)", re.IGNORECASE)


class RetailLLMWiki:
    """Manages compiled Markdown wiki pages (index.md, log.md, entities/*.md)."""

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
                "# Retail & Supply Chain Wiki Index\n\n_No entities ingested yet._\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Retail & Supply Chain Wiki Log\n\n",
                encoding="utf-8",
            )

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def append_log(self, event_type: str, message: str) -> None:
        line = f"- `{self._now_iso()}` **{event_type}**: {message}\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _extract_links(self, text: str, extra_links: list[str] | None = None) -> list[str]:
        found = set(WIKI_LINK_RE.findall(text))
        if extra_links:
            for item in extra_links:
                cleaned = item.strip().strip("[]")
                if cleaned:
                    found.add(cleaned)
        return sorted(found)

    def _rebuild_index(self) -> None:
        pages = sorted(self.entities_dir.glob("*.md"))
        lines = [
            "# Retail & Supply Chain Wiki Index",
            "",
            f"_Updated: {self._now_iso()}_",
            "",
            "| Entity | Type | Links | File |",
            "| :--- | :--- | :--- | :--- |",
        ]
        if not pages:
            lines.append("| _None_ | - | - | - |")
        else:
            for page in pages:
                entity_id = page.stem
                text = page.read_text(encoding="utf-8")
                type_match = re.search(r"^- Type:\s*(.+)$", text, re.MULTILINE)
                etype = type_match.group(1).strip() if type_match else "Entity"
                links = self._extract_links(text)
                link_str = ", ".join(f"[[{lk}]]" for lk in links) if links else "-"
                lines.append(
                    f"| [[{entity_id}]] | {etype} | {link_str} | `entities/{page.name}` |"
                )
        self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        entity_id: str | None = None,
        entity_type: str = "SKU",
        links: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_id = (entity_id or doc_id).strip()
        page_path = self.entities_dir / f"{target_id}.md"
        extracted_links = self._extract_links(content, links)

        existing_facts: list[str] = []
        existing_sources: list[str] = []
        existing_links: set[str] = set(extracted_links)

        if page_path.exists():
            old_text = page_path.read_text(encoding="utf-8")
            existing_links.update(self._extract_links(old_text))
            facts_section = re.search(
                r"## Facts & Rules\n(.*?)(?=\n## |\Z)", old_text, re.DOTALL
            )
            if facts_section:
                for line in facts_section.group(1).strip().splitlines():
                    if line.strip():
                        existing_facts.append(line.strip())
            sources_section = re.search(
                r"## Sources\n(.*?)(?=\n## |\Z)", old_text, re.DOTALL
            )
            if sources_section:
                for line in sources_section.group(1).strip().splitlines():
                    if line.strip():
                        existing_sources.append(line.strip())

        new_fact = f"- [{doc_id}] {title}: {content.strip()}"
        if new_fact not in existing_facts:
            existing_facts.append(new_fact)

        source_entry = f"- `{doc_id}` ({self._now_iso()})"
        if source_entry not in existing_sources:
            existing_sources.append(source_entry)

        # Remove self-link if present
        existing_links.discard(target_id)
        sorted_links = sorted(existing_links)

        meta_lines = [f"- Type: {entity_type}"]
        if metadata:
            for k, v in sorted(metadata.items()):
                meta_lines.append(f"- {k}: {v}")

        link_lines = (
            [f"- [[{lk}]]" for lk in sorted_links] if sorted_links else ["- _None_"]
        )

        page_md = "\n".join(
            [
                f"# {target_id}: {title}",
                "",
                *meta_lines,
                "",
                "## Facts & Rules",
                *existing_facts,
                "",
                "## Wiki Links",
                *link_lines,
                "",
                "## Sources",
                *existing_sources,
                "",
            ]
        )
        page_path.write_text(page_md, encoding="utf-8")
        self._rebuild_index()
        self.append_log(
            "INGEST",
            f"doc={doc_id} -> [[{target_id}]] ({entity_type}), links={sorted_links}",
        )
        return {
            "doc_id": doc_id,
            "entity_id": target_id,
            "entity_type": entity_type,
            "page_path": str(page_path),
            "extracted_links": sorted_links,
            "updated_at": self._now_iso(),
        }

    def query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        tokens = [
            tok.lower()
            for tok in re.findall(r"[A-Za-z0-9_\-]+", question)
            if len(tok) >= 2
        ]
        pages = sorted(self.entities_dir.glob("*.md"))
        scored: list[dict[str, Any]] = []

        for page in pages:
            entity_id = page.stem
            text = page.read_text(encoding="utf-8")
            text_lower = text.lower()
            score = 0.0
            for tok in tokens:
                if tok == entity_id.lower():
                    score += 5.0
                elif tok in text_lower:
                    score += 1.0 + min(text_lower.count(tok), 3) * 0.25

            links = self._extract_links(text)
            for lk in links:
                if lk.lower() in tokens:
                    score += 2.0

            if score > 0:
                snippet_lines = [
                    ln.strip()
                    for ln in text.splitlines()
                    if ln.strip().startswith("- [")
                ]
                snippet = " | ".join(snippet_lines[:3]) if snippet_lines else text[:200]
                scored.append(
                    {
                        "entity_id": entity_id,
                        "score": round(score, 2),
                        "wiki_links": links,
                        "snippet": snippet,
                        "path": str(page),
                    }
                )

        scored.sort(key=lambda x: (-x["score"], x["entity_id"]))
        top_matches = scored[:top_k]

        if not top_matches:
            answer = "No matching wiki entities found for the query."
        else:
            cited = ", ".join(f"[[{m['entity_id']}]]" for m in top_matches)
            answer = f"Matched {len(top_matches)} wiki entities ({cited}): {top_matches[0]['snippet']}"

        return {
            "question": question,
            "matches": top_matches,
            "answer": answer,
        }

    def lint(self, registry: RetailOntologyRegistry | None = None) -> dict[str, Any]:
        pages = sorted(self.entities_dir.glob("*.md"))
        all_page_ids = {p.stem for p in pages}

        outbound_links: dict[str, set[str]] = {}
        inbound_counts: dict[str, int] = {pid: 0 for pid in all_page_ids}
        entity_types: dict[str, str] = {}

        stockout_risks: list[dict[str, Any]] = []
        conflicting_promo_rules: list[dict[str, Any]] = []
        orphan_skus: list[dict[str, Any]] = []
        broken_links: list[dict[str, str]] = []

        for page in pages:
            eid = page.stem
            text = page.read_text(encoding="utf-8")
            type_match = re.search(r"^- Type:\s*(.+)$", text, re.MULTILINE)
            etype = type_match.group(1).strip() if type_match else "Entity"
            entity_types[eid] = etype

            links = set(self._extract_links(text))
            links.discard(eid)
            outbound_links[eid] = links
            for target in links:
                if target in inbound_counts:
                    inbound_counts[target] += 1
                else:
                    in_registry = bool(
                        registry
                        and (
                            target in registry.skus
                            or target in registry.warehouses
                            or target in registry.suppliers
                        )
                    )
                    if not in_registry:
                        broken_links.append({"source": eid, "target": target})

            # 1. Wiki-level stockout keyword check
            text_lower = text.lower()
            if any(
                kw in text_lower
                for kw in ("stockout", "below safety", "critical stock", "缺货", "断货")
            ):
                stockout_risks.append(
                    {
                        "sku_id": eid,
                        "source": "wiki",
                        "detail": "Wiki content flags stockout or safety-stock risk",
                    }
                )

            # 2. Conflicting promo rules check
            discounts = sorted(set(DISCOUNT_PCT_RE.findall(text)))
            has_stackable = bool(
                re.search(r"\bstackable\b|可叠加", text_lower)
                and not re.search(r"\bnon-stackable\b|不可叠加", text_lower)
            )
            has_non_stackable = bool(
                re.search(r"\bnon-stackable\b|互斥|不可叠加", text_lower)
            )
            if len(discounts) > 1 or (has_stackable and has_non_stackable):
                conflicting_promo_rules.append(
                    {
                        "entity_id": eid,
                        "discounts_found": discounts,
                        "stackability_conflict": has_stackable and has_non_stackable,
                        "detail": "Conflicting promo discount percentages or stackability rules detected",
                    }
                )

        # 3. Orphan SKUs in Wiki (no inbound and no outbound links)
        for eid in sorted(all_page_ids):
            is_sku = entity_types.get(eid, "").upper() == "SKU" or eid.startswith("SKU-")
            if is_sku and not outbound_links.get(eid) and inbound_counts.get(eid, 0) == 0:
                orphan_skus.append(
                    {
                        "sku_id": eid,
                        "source": "wiki",
                        "detail": "Orphan SKU page with no inbound or outbound [[wiki_links]]",
                    }
                )

        # 4. Cross-check against Ontology Registry if provided
        if registry is not None:
            for check in registry.check_all_inventory():
                if check.risk_level in {"CRITICAL", "WARNING"}:
                    if not any(
                        r["sku_id"] == check.sku_id and r["source"] == "ontology"
                        for r in stockout_risks
                    ):
                        stockout_risks.append(
                            {
                                "sku_id": check.sku_id,
                                "source": "ontology",
                                "risk_level": check.risk_level,
                                "days_of_supply": check.days_of_supply,
                                "lead_time_days": check.lead_time_days,
                                "detail": check.message,
                            }
                        )

            for sku_id, sku in sorted(registry.skus.items()):
                if sku.gross_margin_pct() < sku.min_margin_pct:
                    conflicting_promo_rules.append(
                        {
                            "entity_id": sku_id,
                            "discounts_found": [str(round(sku.promo_discount_pct * 100, 1))],
                            "stackability_conflict": False,
                            "detail": (
                                f"Active promo discount {sku.promo_discount_pct:.0%} "
                                f"breaches min_margin_pct {sku.min_margin_pct:.0%}"
                            ),
                        }
                    )
                if sku_id not in all_page_ids:
                    orphan_skus.append(
                        {
                            "sku_id": sku_id,
                            "source": "ontology",
                            "detail": "SKU exists in ontology registry without a compiled wiki page",
                        }
                    )

        total_issues = (
            len(stockout_risks)
            + len(conflicting_promo_rules)
            + len(orphan_skus)
            + len(broken_links)
        )
        status = "CLEAN" if total_issues == 0 else "ISSUES_FOUND"
        self.append_log(
            "LINT",
            f"status={status}, total_issues={total_issues}, "
            f"stockout={len(stockout_risks)}, promo_conflicts={len(conflicting_promo_rules)}, "
            f"orphans={len(orphan_skus)}, broken_links={len(broken_links)}",
        )
        return {
            "status": status,
            "total_issues": total_issues,
            "stockout_risks": stockout_risks,
            "conflicting_promo_rules": conflicting_promo_rules,
            "orphan_skus": orphan_skus,
            "broken_links": broken_links,
        }
