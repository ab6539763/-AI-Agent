"""LLM Wiki Knowledge Base for Legal Compliance & Contract Review."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ontology import (
    Clause,
    Contract,
    LegalOntologyRegistry,
    Regulation,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LegalLLMWiki:
    """Markdown-backed Legal Wiki with [[wiki_links]], ingest(), query(), and lint()."""

    def __init__(
        self,
        root_dir: str | Path,
        registry: LegalOntologyRegistry | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.entities_dir = self.root_dir / "entities"
        self.index_path = self.root_dir / "index.md"
        self.log_path = self.root_dir / "log.md"
        self.registry = registry or LegalOntologyRegistry()

        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("# Legal Wiki Audit & Event Log\n\n", encoding="utf-8")

        # Materialize seeded regulations into entities/ if not yet present
        for reg in self.registry.regulations.values():
            reg_file = self.entities_dir / f"{reg.id}.md"
            if not reg_file.exists():
                self._write_regulation_page(reg)
        self._rebuild_index()

    def append_log(self, action: str, target_id: str, detail: str) -> None:
        line = f"- `{_utc_now()}` **{action}** `[[{target_id}]]`: {detail}\n"
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def _write_regulation_page(self, reg: Regulation) -> Path:
        links = []
        if reg.superseded_by:
            links.append(f"- Superseded By: [[{reg.superseded_by}]]")
        links_block = "\n".join(links) if links else "- None"
        content = (
            f"# Regulation: {reg.code} — {reg.title}\n\n"
            f"- **ID**: `{reg.id}`\n"
            f"- **Type**: `regulation`\n"
            f"- **Jurisdiction**: `{reg.jurisdiction}`\n"
            f"- **Status**: `{reg.status}`\n"
            f"- **Keywords**: {', '.join(reg.keywords)}\n\n"
            f"## Summary\n{reg.summary}\n\n"
            f"## Wiki Links\n{links_block}\n"
        )
        path = self.entities_dir / f"{reg.id}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _write_contract_page(self, contract: Contract) -> Path:
        clause_links = "\n".join(f"- [[{cid}]]" for cid in contract.clauses) or "- None"
        cap_str = f"${contract.liability_cap_usd:,.2f}" if contract.liability_cap_usd is not None else "Unspecified"
        content = (
            f"# Contract: {contract.title}\n\n"
            f"- **ID**: `{contract.id}`\n"
            f"- **Type**: `contract`\n"
            f"- **Counterparty**: {contract.counterparty}\n"
            f"- **Jurisdiction**: `{contract.jurisdiction}`\n"
            f"- **Effective Date**: {contract.effective_date}\n"
            f"- **Liability Cap**: {cap_str}\n"
            f"- **Status**: `{contract.status}`\n\n"
            f"## Clauses\n{clause_links}\n"
        )
        path = self.entities_dir / f"{contract.id}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _write_clause_page(self, clause: Clause) -> Path:
        reg_links = "\n".join(f"- [[{rid}]]" for rid in clause.matched_regulations) or "- None"
        redline = clause.redline_suggestion or "No redline required."
        content = (
            f"# Clause: {clause.title}\n\n"
            f"- **ID**: `{clause.id}`\n"
            f"- **Type**: `clause`\n"
            f"- **Contract**: [[{clause.contract_id}]]\n"
            f"- **Clause Type**: `{clause.clause_type}`\n"
            f"- **Risk Level**: `{clause.risk_level}` ({clause.risk_score:.2f})\n\n"
            f"## Clause Text\n{clause.text}\n\n"
            f"## Redline Suggestion\n{redline}\n\n"
            f"## Governed By Regulations\n{reg_links}\n"
        )
        path = self.entities_dir / f"{clause.id}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _rebuild_index(self) -> None:
        lines = [
            "# Legal Compliance & Contract Wiki Index\n",
            f"_Last updated: {_utc_now()}_\n",
            "## Contracts\n",
        ]
        if self.registry.contracts:
            for c in sorted(self.registry.contracts.values(), key=lambda x: x.id):
                lines.append(f"- [[{c.id}]] — {c.title} ({c.counterparty}, `{c.status}`)")
        else:
            lines.append("- _No contracts ingested yet._")

        lines.append("\n## Clauses\n")
        if self.registry.clauses:
            for cl in sorted(self.registry.clauses.values(), key=lambda x: x.id):
                lines.append(f"- [[{cl.id}]] — {cl.title} (`{cl.clause_type}`, risk=`{cl.risk_level}`)")
        else:
            lines.append("- _No clauses registered yet._")

        lines.append("\n## Regulations\n")
        for reg in sorted(self.registry.regulations.values(), key=lambda x: x.id):
            lines.append(f"- [[{reg.id}]] — {reg.code}: {reg.title} (`{reg.status}`)")

        self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def sync_contract(self, contract: Contract) -> None:
        self._write_contract_page(contract)
        for cid in contract.clauses:
            if cid in self.registry.clauses:
                self._write_clause_page(self.registry.clauses[cid])
        self._rebuild_index()

    def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        doc_type: str = "contract",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest a contract, clause, or regulation into the ontology and Markdown wiki."""
        meta = metadata or {}
        created_entities: list[str] = []

        if doc_type == "regulation":
            reg = Regulation(
                id=doc_id,
                code=meta.get("code", doc_id.upper()),
                title=title,
                jurisdiction=meta.get("jurisdiction", "GLOBAL"),
                status=meta.get("status", "active"),
                superseded_by=meta.get("superseded_by"),
                summary=content,
                keywords=meta.get("keywords", [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", title)]),
            )
            self.registry.register_regulation(reg)
            self._write_regulation_page(reg)
            created_entities.append(reg.id)
        elif doc_type == "clause":
            contract_id = meta.get("contract_id", "unassigned_contract")
            clause = Clause(
                id=doc_id,
                contract_id=contract_id,
                title=title,
                clause_type=meta.get("clause_type", "general"),
                text=content,
                matched_regulations=list(meta.get("matched_regulations", [])),
            )
            self.registry.register_clause(
                clause,
                auto_classify=meta.get("auto_classify", True),
                auto_map=meta.get("auto_map", True),
            )
            self._write_clause_page(clause)
            created_entities.append(clause.id)
        else:
            contract = Contract(
                id=doc_id,
                title=title,
                counterparty=meta.get("counterparty", "Counterparty Inc."),
                jurisdiction=meta.get("jurisdiction", "US-NY"),
                effective_date=meta.get("effective_date", "2026-01-01"),
                liability_cap_usd=meta.get("liability_cap_usd"),
                status=meta.get("status", "ingested"),
                metadata=meta,
            )
            self.registry.register_contract(contract)

            # Split into clauses by blank lines or numbered sections
            sections = [s.strip() for s in re.split(r"\n\s*\n+", content.strip()) if s.strip()]
            if not sections:
                sections = [content.strip()]
            for idx, sec in enumerate(sections, start=1):
                cid = f"{doc_id}_cl_{idx}"
                first_line = sec.splitlines()[0][:60]
                clause = Clause(
                    id=cid,
                    contract_id=doc_id,
                    title=first_line,
                    text=sec,
                )
                self.registry.register_clause(clause, auto_classify=True, auto_map=True)
                self._write_clause_page(clause)
                created_entities.append(cid)

            self._write_contract_page(contract)
            created_entities.insert(0, doc_id)

        self._rebuild_index()
        self.append_log("INGEST", doc_id, f"type={doc_type}, entities={len(created_entities)}")
        return {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "entities": created_entities,
            "index_path": str(self.index_path),
        }

    def query(self, q: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Deterministic TF-like keyword search across entity Markdown pages."""
        tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9_-]{2,}", q)]
        if not tokens:
            return []

        results: list[dict[str, Any]] = []
        for md_file in sorted(self.entities_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            lower = text.lower()
            hits = sum(lower.count(tok) for tok in tokens)
            if hits == 0:
                continue
            unique_hits = sum(1 for tok in set(tokens) if tok in lower)
            score = round((unique_hits / len(set(tokens))) + 0.1 * math.log1p(hits), 4)
            first_line = text.splitlines()[0].lstrip("# ").strip() if text else md_file.stem
            wiki_links = re.findall(r"\[\[([^\]]+)\]\]", text)
            snippet = " ".join(text.splitlines()[:6])[:240]
            results.append(
                {
                    "entity_id": md_file.stem,
                    "title": first_line,
                    "score": score,
                    "wiki_links": wiki_links,
                    "snippet": snippet,
                    "path": str(md_file),
                }
            )

        results.sort(key=lambda r: (-r["score"], r["entity_id"]))
        self.append_log("QUERY", "wiki", f"q={q!r}, hits={len(results[:top_k])}")
        return results[:top_k]

    def lint(self) -> dict[str, Any]:
        """Detect superseded regulations, unlinked clauses, and conflicting liability caps."""
        superseded_regulations: list[dict[str, Any]] = []
        unlinked_clauses: list[dict[str, Any]] = []
        conflicting_liability_caps: list[dict[str, Any]] = []

        # 1. Check clauses referencing superseded regulations
        for clause in self.registry.clauses.values():
            for reg_id in clause.matched_regulations:
                reg = self.registry.regulations.get(reg_id)
                if reg and reg.status == "superseded":
                    superseded_regulations.append(
                        {
                            "clause_id": clause.id,
                            "contract_id": clause.contract_id,
                            "regulation_id": reg.id,
                            "regulation_code": reg.code,
                            "superseded_by": reg.superseded_by,
                        }
                    )

            # 2. Check unlinked clauses (no matched regulations or missing [[wiki_links]] on disk)
            entity_file = self.entities_dir / f"{clause.id}.md"
            has_reg_links = len(clause.matched_regulations) > 0
            if not has_reg_links:
                unlinked_clauses.append(
                    {
                        "clause_id": clause.id,
                        "contract_id": clause.contract_id,
                        "reason": "no_matched_regulations",
                        "entity_exists": entity_file.exists(),
                    }
                )

        # 3. Check conflicting liability caps per contract
        for contract in self.registry.contracts.values():
            caps: list[tuple[str, float]] = []
            for cid in contract.clauses:
                cl = self.registry.clauses.get(cid)
                if cl and cl.extracted_cap_usd is not None:
                    caps.append((cl.id, cl.extracted_cap_usd))

            distinct_caps = {cap for _, cap in caps}
            conflict_detected = False
            reason = ""
            if len(distinct_caps) > 1:
                conflict_detected = True
                reason = "multiple_distinct_clause_caps"
            elif contract.liability_cap_usd is not None and caps:
                for _, cap in caps:
                    if cap != contract.liability_cap_usd:
                        conflict_detected = True
                        reason = "contract_cap_mismatch_with_clause"
                        break

            if conflict_detected:
                conflicting_liability_caps.append(
                    {
                        "contract_id": contract.id,
                        "contract_cap_usd": contract.liability_cap_usd,
                        "clause_caps": [
                            {"clause_id": cid, "cap_usd": "unlimited" if math.isinf(cap) else cap}
                            for cid, cap in caps
                        ],
                        "reason": reason,
                    }
                )

        total_issues = (
            len(superseded_regulations)
            + len(unlinked_clauses)
            + len(conflicting_liability_caps)
        )
        self.append_log("LINT", "wiki", f"total_issues={total_issues}")
        return {
            "total_issues": total_issues,
            "superseded_regulations": superseded_regulations,
            "unlinked_clauses": unlinked_clauses,
            "conflicting_liability_caps": conflicting_liability_caps,
        }
