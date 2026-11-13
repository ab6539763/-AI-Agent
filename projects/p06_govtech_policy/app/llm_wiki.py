"""GovTech LLM Wiki: Persistent Markdown knowledge base with [[wiki_links]],
chronological log, deterministic retrieval, and automated policy linting.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> set[str]:
    """Deterministic tokenizer supporting both ASCII words and CJK bigrams/unigrams."""
    lowered = text.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9_\-\.]+", lowered))
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    cjk_tokens = set(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        cjk_tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    return ascii_tokens | cjk_tokens


class WikiEntityMeta(BaseModel):
    doc_id: str
    title: str
    department: str = "市政务服务和数据管理局"
    entity_type: str = "policy"  # policy | program | rule | department
    program_id: str | None = None
    effective_date: str = "2026-01-01"
    expiry_date: str | None = None
    subsidy_threshold: float | None = None
    rule_ids: list[str] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    clauses: dict[str, str] = Field(default_factory=dict)


class WikiQueryHit(BaseModel):
    doc_id: str
    title: str
    department: str
    score: float
    snippet: str
    wiki_links: list[str] = Field(default_factory=list)
    clauses: dict[str, str] = Field(default_factory=dict)
    path: str


class LintIssue(BaseModel):
    issue_type: str  # expired_policy | conflicting_threshold | orphan_rule | broken_link
    severity: str  # error | warning
    entity_id: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class LintReport(BaseModel):
    checked_at: str = Field(default_factory=_utc_now_iso)
    reference_date: str
    total_entities: int
    healthy: bool
    expired_policies: list[LintIssue] = Field(default_factory=list)
    conflicting_thresholds: list[LintIssue] = Field(default_factory=list)
    orphan_rules: list[LintIssue] = Field(default_factory=list)
    issues: list[LintIssue] = Field(default_factory=list)


class GovTechLLMWiki:
    """Markdown-backed GovTech knowledge wiki with index.md, log.md, and entities/<id>.md."""

    def __init__(self, wiki_dir: Path | str) -> None:
        self.wiki_dir = Path(wiki_dir)
        self.entities_dir = self.wiki_dir / "entities"
        self.index_path = self.wiki_dir / "index.md"
        self.log_path = self.wiki_dir / "log.md"
        self._meta_cache: dict[str, WikiEntityMeta] = {}
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.entities_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text(
                "# GovTech 政务与企业政策知识库索引\n\n"
                "| 实体编号 | 标题 | 责任部门 | 类型 | 有效期至 | 关联链接 |\n"
                "|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# GovTech Wiki 操作日志 (Append-Only)\n\n",
                encoding="utf-8",
            )

    def _append_log(self, action: str, detail: str) -> None:
        line = f"- `{_utc_now_iso()}` **{action}**: {detail}\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _render_entity_markdown(
        self, meta: WikiEntityMeta, content: str
    ) -> str:
        links = [f"[[{rid}]]" for rid in meta.related_ids]
        if meta.program_id and f"[[{meta.program_id}]]" not in links:
            links.append(f"[[{meta.program_id}]]")
        for r_id in meta.rule_ids:
            if f"[[{r_id}]]" not in links:
                links.append(f"[[{r_id}]]")

        lines = [
            f"# {meta.title}",
            "",
            "## 元数据 (Metadata)",
            f"- **doc_id**: `{meta.doc_id}`",
            f"- **entity_type**: `{meta.entity_type}`",
            f"- **department**: {meta.department}",
            f"- **program_id**: `{meta.program_id or 'N/A'}`",
            f"- **effective_date**: `{meta.effective_date}`",
            f"- **expiry_date**: `{meta.expiry_date or 'OPEN'}`",
            f"- **subsidy_threshold**: `{meta.subsidy_threshold if meta.subsidy_threshold is not None else 'N/A'}`",
            f"- **rule_ids**: {', '.join(meta.rule_ids) if meta.rule_ids else 'None'}",
            f"- **wiki_links**: {' '.join(links) if links else 'None'}",
            "",
            "## 正文内容 (Policy Content)",
            content.strip(),
            "",
        ]
        if meta.clauses:
            lines.append("## 条款引用 (Clauses)")
            for ref, clause_text in meta.clauses.items():
                lines.append(f"- **{meta.doc_id} {ref}**: {clause_text}")
            lines.append("")

        if links:
            lines.append("## 关联实体 (Wiki Links)")
            for lnk in links:
                lines.append(f"- {lnk}")
            lines.append("")

        return "\n".join(lines)

    def _rebuild_index(self) -> None:
        rows = [
            "# GovTech 政务与企业政策知识库索引",
            "",
            "| 实体编号 | 标题 | 责任部门 | 类型 | 有效期至 | 关联链接 |",
            "|---|---|---|---|---|---|",
        ]
        for doc_id in sorted(self._meta_cache):
            m = self._meta_cache[doc_id]
            expiry = m.expiry_date or "长期有效"
            links = " ".join(f"[[{r}]]" for r in m.related_ids) or "-"
            rows.append(
                f"| [[entities/{m.doc_id}]] | {m.title} | {m.department} | {m.entity_type} | {expiry} | {links} |"
            )
        rows.append("")
        self.index_path.write_text("\n".join(rows), encoding="utf-8")

    def ingest(
        self,
        doc_id: str,
        title: str,
        content: str,
        department: str = "市政务服务和数据管理局",
        entity_type: str = "policy",
        program_id: str | None = None,
        effective_date: str = "2026-01-01",
        expiry_date: str | None = None,
        subsidy_threshold: float | None = None,
        rule_ids: list[str] | None = None,
        related_ids: list[str] | None = None,
        clauses: dict[str, str] | None = None,
    ) -> Path:
        """Ingest or update a policy/entity Markdown page in entities/<doc_id>.md."""
        meta = WikiEntityMeta(
            doc_id=doc_id,
            title=title,
            department=department,
            entity_type=entity_type,
            program_id=program_id,
            effective_date=effective_date,
            expiry_date=expiry_date,
            subsidy_threshold=subsidy_threshold,
            rule_ids=rule_ids or [],
            related_ids=related_ids or [],
            clauses=clauses or {},
        )
        self._meta_cache[doc_id] = meta
        entity_path = self.entities_dir / f"{doc_id}.md"
        entity_path.write_text(
            self._render_entity_markdown(meta, content),
            encoding="utf-8",
        )
        self._rebuild_index()
        self._append_log("INGEST", f"`{doc_id}` ({title}) -> `{entity_path.name}`")
        return entity_path

    def list_entities(self) -> list[str]:
        return sorted(p.stem for p in self.entities_dir.glob("*.md"))

    def read_entity(self, doc_id: str) -> str:
        path = self.entities_dir / f"{doc_id}.md"
        if not path.exists():
            raise FileNotFoundError(f"Wiki entity not found: {doc_id}")
        return path.read_text(encoding="utf-8")

    def query(self, query_text: str, top_k: int = 5) -> list[WikiQueryHit]:
        """Deterministic token-overlap search across ingested Markdown entities."""
        q_tokens = _tokenize(query_text)
        if not q_tokens:
            return []

        hits: list[WikiQueryHit] = []
        for md_path in sorted(self.entities_dir.glob("*.md")):
            doc_id = md_path.stem
            text = md_path.read_text(encoding="utf-8")
            doc_tokens = _tokenize(text)
            overlap = q_tokens & doc_tokens
            if not overlap:
                continue

            # Weight exact doc_id or title matches higher
            meta = self._meta_cache.get(doc_id)
            title = meta.title if meta else doc_id
            department = meta.department if meta else "市政务服务和数据管理局"
            clauses = meta.clauses if meta else {}
            score = len(overlap) / max(len(q_tokens), 1)
            if doc_id.lower() in query_text.lower():
                score += 1.0
            if meta and any(tok in _tokenize(meta.title) for tok in q_tokens):
                score += 0.3

            wiki_links = re.findall(r"\[\[([^\]]+)\]\]", text)
            # Extract concise snippet from正文内容
            body_lines = [
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and not ln.startswith("#") and not ln.startswith("- **")
            ]
            snippet = " ".join(body_lines)[:220]

            hits.append(
                WikiQueryHit(
                    doc_id=doc_id,
                    title=title,
                    department=department,
                    score=round(score, 4),
                    snippet=snippet,
                    wiki_links=wiki_links,
                    clauses=clauses,
                    path=str(md_path),
                )
            )

        hits.sort(key=lambda h: (-h.score, h.doc_id))
        result = hits[:top_k]
        self._append_log("QUERY", f"q={query_text!r} hits={len(result)}")
        return result

    def lint(
        self,
        reference_date: str | None = None,
        known_program_ids: set[str] | None = None,
        known_rule_ids: set[str] | None = None,
    ) -> LintReport:
        """Audit wiki pages for expired policies, conflicting subsidy thresholds, and orphan rules."""
        ref_date = reference_date or date.today().isoformat()
        expired_issues: list[LintIssue] = []
        conflict_issues: list[LintIssue] = []
        orphan_issues: list[LintIssue] = []

        existing_entities = set(self.list_entities())
        program_thresholds: dict[str, list[tuple[str, float]]] = {}

        for doc_id in sorted(existing_entities):
            meta = self._meta_cache.get(doc_id)
            if meta is None:
                continue

            # 1. Expired policies
            if meta.expiry_date and meta.expiry_date < ref_date:
                expired_issues.append(
                    LintIssue(
                        issue_type="expired_policy",
                        severity="warning",
                        entity_id=doc_id,
                        message=f"政策/实体 `{doc_id}` 已于 {meta.expiry_date} 过期（基准日 {ref_date}）。",
                        details={"expiry_date": meta.expiry_date, "reference_date": ref_date},
                    )
                )

            # Collect thresholds by program_id for active policies
            is_expired = bool(meta.expiry_date and meta.expiry_date < ref_date)
            if meta.program_id and meta.subsidy_threshold is not None and not is_expired:
                program_thresholds.setdefault(meta.program_id, []).append(
                    (doc_id, meta.subsidy_threshold)
                )

            # 3a. Orphan rules: rules referenced by an entity with no known rule or missing program
            if known_program_ids is not None and meta.program_id and meta.program_id not in known_program_ids:
                orphan_issues.append(
                    LintIssue(
                        issue_type="orphan_rule",
                        severity="error",
                        entity_id=doc_id,
                        message=f"实体 `{doc_id}` 关联了未知补贴项目 `{meta.program_id}`。",
                        details={"program_id": meta.program_id},
                    )
                )

            if meta.entity_type == "rule" and not meta.program_id:
                orphan_issues.append(
                    LintIssue(
                        issue_type="orphan_rule",
                        severity="error",
                        entity_id=doc_id,
                        message=f"孤立规则 `{doc_id}` 未绑定任何补贴项目 (program_id)。",
                        details={"rule_id": doc_id},
                    )
                )

            if known_rule_ids is not None:
                for rid in meta.rule_ids:
                    if rid not in known_rule_ids and rid not in existing_entities:
                        orphan_issues.append(
                            LintIssue(
                                issue_type="orphan_rule",
                                severity="error",
                                entity_id=doc_id,
                                message=f"实体 `{doc_id}` 引用了不存在的规则 `{rid}`。",
                                details={"missing_rule_id": rid},
                            )
                        )

            # Broken [[wiki_links]] check for related_ids
            for rel_id in meta.related_ids:
                in_known_programs = known_program_ids is not None and rel_id in known_program_ids
                in_known_rules = known_rule_ids is not None and rel_id in known_rule_ids
                if rel_id not in existing_entities and not in_known_programs and not in_known_rules:
                    orphan_issues.append(
                        LintIssue(
                            issue_type="broken_link",
                            severity="warning",
                            entity_id=doc_id,
                            message=f"实体 `{doc_id}` 包含悬空链接 `[[{rel_id}]]`。",
                            details={"broken_link": rel_id},
                        )
                    )

        # 2. Conflicting subsidy thresholds
        for prog_id, entries in sorted(program_thresholds.items()):
            distinct_thresholds = sorted({val for _, val in entries})
            if len(distinct_thresholds) > 1:
                conflict_issues.append(
                    LintIssue(
                        issue_type="conflicting_threshold",
                        severity="error",
                        entity_id=prog_id,
                        message=(
                            f"项目 `{prog_id}` 存在冲突的补贴上限阈值: "
                            f"{', '.join(f'{d}:{v}' for d, v in entries)}"
                        ),
                        details={
                            "program_id": prog_id,
                            "entries": [{"doc_id": d, "threshold": v} for d, v in entries],
                        },
                    )
                )

        all_issues = expired_issues + conflict_issues + orphan_issues
        report = LintReport(
            reference_date=ref_date,
            total_entities=len(existing_entities),
            healthy=len(all_issues) == 0,
            expired_policies=expired_issues,
            conflicting_thresholds=conflict_issues,
            orphan_rules=orphan_issues,
            issues=all_issues,
        )
        self._append_log(
            "LINT",
            f"entities={report.total_entities} healthy={report.healthy} issues={len(all_issues)}",
        )
        return report
