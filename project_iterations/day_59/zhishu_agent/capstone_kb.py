"""智枢企业级智能体平台 Day 59：Capstone Day 1 知识库初始化与持久化模块 (v1.0.0-day59)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".md", ".csv"}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_YEAR_RE = re.compile(r"(?:FY)?(20\d{2})", re.IGNORECASE)


@dataclass
class DocumentMetadata:
    """企业文档结构化元数据."""

    source_file: str
    department: str
    fiscal_year: str
    doc_type: str
    title: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class KBChunk:
    """切分后的知识库文本块."""

    chunk_id: str
    content: str
    chunk_index: int
    char_count: int
    content_hash: str
    department: str
    fiscal_year: str
    doc_type: str
    source_file: str
    section_heading: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionStats:
    """知识库构建与持久化统计信息."""

    total_files: int
    processed_files: int
    skipped_files: int
    total_chunks: int
    departments: dict[str, int]
    fiscal_years: dict[str, int]
    doc_types: dict[str, int]
    json_index_path: str | None = None
    sqlite_db_path: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapstoneKBInitializer:
    """Capstone 财务与合规知识库初始化器.

    负责加载企业结构化财务报告（`.md`/`.csv`）与合规制度文档（`.md`），
    提取 `department`、`fiscal_year`、`doc_type` 元数据并完成语义切分，
    最终将索引持久化至 JSON 与 SQLite。
    """

    def __init__(
        self,
        chunk_size: int = 400,
        chunk_overlap: int = 60,
        rows_per_csv_chunk: int = 10,
        encoding: str = "utf-8",
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须为正整数")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")
        if rows_per_csv_chunk <= 0:
            raise ValueError("rows_per_csv_chunk 必须为正整数")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.rows_per_csv_chunk = rows_per_csv_chunk
        self.encoding = encoding

    @staticmethod
    def _parse_frontmatter(raw_text: str) -> tuple[dict[str, str], str]:
        """解析 Markdown 顶部的 YAML-like Frontmatter."""
        match = _FRONTMATTER_RE.match(raw_text)
        if not match:
            return {}, raw_text

        fm_block = match.group(1)
        body = raw_text[match.end() :]
        parsed: dict[str, str] = {}
        for line in fm_block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, val = line.split(":", 1)
            parsed[key.strip().lower()] = val.strip().strip("\"'")
        return parsed, body

    @staticmethod
    def _infer_department(name_lower: str, text_lower: str) -> str:
        rules = (
            ("compliance", ("compliance", "合规", "policy", "制度")),
            ("audit", ("audit", "审计", "风控")),
            ("legal", ("legal", "法务", "合同")),
            ("finance", ("finance", "financial", "财务", "财报", "budget", "ledger", "预算")),
        )
        for dept, keywords in rules:
            if any(k in name_lower for k in keywords):
                return dept
        for dept, keywords in rules:
            if any(k in text_lower for k in keywords):
                return dept
        return "general"

    @staticmethod
    def _infer_fiscal_year(name: str, text: str) -> str:
        for candidate in (name, text[:500]):
            match = _YEAR_RE.search(candidate)
            if match:
                return f"FY{match.group(1)}"
        return "FY2026"

    @staticmethod
    def _infer_doc_type(ext: str, name_lower: str, department: str) -> str:
        if ext == ".csv":
            if "compliance" in name_lower or "audit" in name_lower:
                return "compliance_ledger"
            return "financial_ledger"
        if "policy" in name_lower or "制度" in name_lower or department == "compliance":
            return "compliance_policy"
        if "audit" in name_lower or "审计" in name_lower:
            return "audit_guideline"
        return "financial_report"

    def extract_metadata(
        self,
        file_path: Path,
        raw_text: str | None = None,
    ) -> DocumentMetadata:
        """提取文档的 department / fiscal_year / doc_type 元数据."""
        text = raw_text if raw_text is not None else file_path.read_text(encoding=self.encoding)
        fm, body = self._parse_frontmatter(text)
        name_lower = file_path.name.lower()
        body_lower = body[:600].lower()

        department = fm.get("department") or self._infer_department(name_lower, body_lower)
        fiscal_year = fm.get("fiscal_year") or self._infer_fiscal_year(file_path.name, body)
        if re.fullmatch(r"20\d{2}", fiscal_year):
            fiscal_year = f"FY{fiscal_year}"
        doc_type = fm.get("doc_type") or self._infer_doc_type(
            file_path.suffix.lower(), name_lower, department
        )
        title = fm.get("title") or file_path.stem

        extra = {
            k: v
            for k, v in fm.items()
            if k not in {"department", "fiscal_year", "doc_type", "title"}
        }
        return DocumentMetadata(
            source_file=file_path.name,
            department=department,
            fiscal_year=fiscal_year,
            doc_type=doc_type,
            title=title,
            extra=extra,
        )

    def _split_long_text(self, text: str) -> list[str]:
        """按段落与滑动窗口切分超长文本，保证 chunk_size 与 chunk_overlap 约束."""
        cleaned = text.strip()
        if not cleaned:
            return []
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        length = len(cleaned)
        step = self.chunk_size - self.chunk_overlap

        while start < length:
            end = min(start + self.chunk_size, length)
            if end < length:
                # 尽量在换行或句号处断开
                split_pos = max(
                    cleaned.rfind("\n", start, end),
                    cleaned.rfind("。", start, end),
                    cleaned.rfind(". ", start, end),
                )
                if split_pos > start + self.chunk_size // 3:
                    end = split_pos + 1
            segment = cleaned[start:end].strip()
            if segment:
                chunks.append(segment)
            if end >= length:
                break
            start = max(end - self.chunk_overlap, start + step) if end - start >= self.chunk_size else end - self.chunk_overlap
            if start < 0:
                start = 0
        return chunks

    def parse_markdown(self, raw_text: str) -> list[tuple[str, str]]:
        """解析 Markdown 文档，按标题分节并切分为 (section_heading, chunk_text)."""
        _, body = self._parse_frontmatter(raw_text)
        sections: list[tuple[str, list[str]]] = []
        current_heading = "Overview"
        current_lines: list[str] = []

        for line in body.splitlines():
            heading_match = _HEADING_RE.match(line.strip())
            if heading_match:
                if current_lines and "\n".join(current_lines).strip():
                    sections.append((current_heading, current_lines))
                current_heading = heading_match.group(2).strip()
                current_lines = [line.strip()]
            else:
                current_lines.append(line)

        if current_lines and "\n".join(current_lines).strip():
            sections.append((current_heading, current_lines))

        result: list[tuple[str, str]] = []
        for heading, lines in sections:
            section_text = "\n".join(lines).strip()
            for piece in self._split_long_text(section_text):
                result.append((heading, piece))
        return result

    def parse_csv(self, file_path: Path) -> list[tuple[str, str]]:
        """解析结构化 CSV 财务/合规台账，按批次聚合为文本块."""
        with file_path.open("r", encoding=self.encoding, newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return []
            rows = [
                {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                for row in reader
                if any(str(v or "").strip() for v in row.values())
            ]

        if not rows:
            return []

        chunks: list[tuple[str, str]] = []
        for batch_idx in range(0, len(rows), self.rows_per_csv_chunk):
            batch = rows[batch_idx : batch_idx + self.rows_per_csv_chunk]
            start_row = batch_idx + 1
            end_row = batch_idx + len(batch)
            heading = f"CSV Rows {start_row}-{end_row}"
            lines = [f"数据表: {file_path.name} (行 {start_row} 至 {end_row})"]
            for offset, row in enumerate(batch, start=start_row):
                kv_pairs = " | ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))
                lines.append(f"- 第 {offset} 条: {kv_pairs}")
            block_text = "\n".join(lines)
            for piece in self._split_long_text(block_text):
                chunks.append((heading, piece))
        return chunks

    def ingest_file(self, file_path: Path | str) -> list[KBChunk]:
        """加载并切分单个 `.md` 或 `.csv` 文档."""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"文档不存在: {path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式 '{ext}'，仅支持 {sorted(SUPPORTED_EXTENSIONS)}")

        raw_text = path.read_text(encoding=self.encoding)
        doc_meta = self.extract_metadata(path, raw_text=raw_text)

        if ext == ".md":
            raw_chunks = self.parse_markdown(raw_text)
        else:
            raw_chunks = self.parse_csv(path)

        kb_chunks: list[KBChunk] = []
        for idx, (heading, content) in enumerate(raw_chunks):
            content_hash = hashlib.sha256(content.encode(self.encoding)).hexdigest()[:16]
            chunk_id = hashlib.sha256(
                f"{doc_meta.source_file}:{idx}:{content_hash}".encode(self.encoding)
            ).hexdigest()[:20]

            merged_meta = {
                "title": doc_meta.title,
                "department": doc_meta.department,
                "fiscal_year": doc_meta.fiscal_year,
                "doc_type": doc_meta.doc_type,
                "source_file": doc_meta.source_file,
                "section_heading": heading,
                **doc_meta.extra,
            }
            kb_chunks.append(
                KBChunk(
                    chunk_id=chunk_id,
                    content=content,
                    chunk_index=idx,
                    char_count=len(content),
                    content_hash=content_hash,
                    department=doc_meta.department,
                    fiscal_year=doc_meta.fiscal_year,
                    doc_type=doc_meta.doc_type,
                    source_file=doc_meta.source_file,
                    section_heading=heading,
                    metadata=merged_meta,
                )
            )
        return kb_chunks

    def ingest_directory(
        self,
        input_dir: Path | str,
        recursive: bool = True,
    ) -> tuple[list[KBChunk], IngestionStats]:
        """扫描目录内全部 `.md`/`.csv` 企业文档并生成切片与统计."""
        root = Path(input_dir)
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"知识库目录不存在: {root}")

        candidates = sorted(root.rglob("*") if recursive else root.glob("*"))
        files = [p for p in candidates if p.is_file()]

        all_chunks: list[KBChunk] = []
        processed = 0
        skipped = 0
        dept_counter: Counter[str] = Counter()
        fy_counter: Counter[str] = Counter()
        type_counter: Counter[str] = Counter()

        for file_path in files:
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                skipped += 1
                continue
            chunks = self.ingest_file(file_path)
            processed += 1
            all_chunks.extend(chunks)
            for c in chunks:
                dept_counter[c.department] += 1
                fy_counter[c.fiscal_year] += 1
                type_counter[c.doc_type] += 1

        stats = IngestionStats(
            total_files=len(files),
            processed_files=processed,
            skipped_files=skipped,
            total_chunks=len(all_chunks),
            departments=dict(dept_counter),
            fiscal_years=dict(fy_counter),
            doc_types=dict(type_counter),
        )
        return all_chunks, stats

    def save_json_index(
        self,
        chunks: list[KBChunk],
        output_path: Path | str,
        stats: IngestionStats | None = None,
    ) -> Path:
        """将切分后的知识库索引持久化为 JSON 文件."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "v1.0.0-day59",
            "total_chunks": len(chunks),
            "stats": stats.to_dict() if stats is not None else None,
            "chunks": [c.to_dict() for c in chunks],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding=self.encoding)
        return out

    def save_sqlite_index(
        self,
        chunks: list[KBChunk],
        db_path: Path | str,
    ) -> Path:
        """将切分后的知识库索引持久化至 SQLite 数据库（支持幂等更新与元数据索引）."""
        out = Path(db_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(str(out))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_file TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    department TEXT NOT NULL,
                    fiscal_year TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    section_heading TEXT NOT NULL,
                    content TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kb_meta
                ON kb_chunks (department, fiscal_year, doc_type)
                """
            )

            rows = [
                (
                    c.chunk_id,
                    c.source_file,
                    c.chunk_index,
                    c.department,
                    c.fiscal_year,
                    c.doc_type,
                    c.section_heading,
                    c.content,
                    c.char_count,
                    c.content_hash,
                    json.dumps(c.metadata, ensure_ascii=False),
                    now_iso,
                )
                for c in chunks
            ]
            conn.executemany(
                """
                INSERT OR REPLACE INTO kb_chunks (
                    chunk_id, source_file, chunk_index, department,
                    fiscal_year, doc_type, section_heading, content,
                    char_count, content_hash, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return out

    def build_and_persist(
        self,
        input_dir: Path | str,
        json_path: Path | str | None = None,
        sqlite_path: Path | str | None = None,
        recursive: bool = True,
    ) -> tuple[list[KBChunk], IngestionStats]:
        """一键完成目录扫描、切分、元数据提取与 JSON/SQLite 双路持久化."""
        chunks, stats = self.ingest_directory(input_dir, recursive=recursive)
        if json_path is not None:
            saved_json = self.save_json_index(chunks, json_path, stats=stats)
            stats.json_index_path = str(saved_json)
        if sqlite_path is not None:
            saved_db = self.save_sqlite_index(chunks, sqlite_path)
            stats.sqlite_db_path = str(saved_db)
        return chunks, stats

    @staticmethod
    def query_sqlite(
        db_path: Path | str,
        department: str | None = None,
        fiscal_year: str | None = None,
        doc_type: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """按结构化元数据与关键词检索已持久化的 SQLite 知识库索引."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if department:
                clauses.append("department = ?")
                params.append(department)
            if fiscal_year:
                clauses.append("fiscal_year = ?")
                params.append(fiscal_year)
            if doc_type:
                clauses.append("doc_type = ?")
                params.append(doc_type)
            if keyword:
                clauses.append("content LIKE ?")
                params.append(f"%{keyword}%")

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"""
                SELECT chunk_id, source_file, chunk_index, department,
                       fiscal_year, doc_type, section_heading, content,
                       char_count, content_hash
                FROM kb_chunks
                {where_sql}
                ORDER BY source_file ASC, chunk_index ASC
                LIMIT ?
            """
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def create_sample_corpus(target_dir: Path | str) -> list[Path]:
        """生成用于演练与测试的企业财务报告与合规政策样例语料."""
        root = Path(target_dir)
        root.mkdir(parents=True, exist_ok=True)

        files_content = {
            "fy2025_q4_financial_report.md": (
                "---\n"
                "title: 智枢科技 FY2025 第四季度财务报告\n"
                "department: finance\n"
                "fiscal_year: FY2025\n"
                "doc_type: financial_report\n"
                "---\n\n"
                "# 智枢科技 FY2025 Q4 财务摘要\n\n"
                "2025 财年第四季度，公司实现营业收入 4.82 亿元人民币，同比增长 26.4%。"
                "其中企业级智能体平台订阅收入达到 2.95 亿元，毛利率提升至 71.8%。\n\n"
                "## 研发与算力成本结构\n\n"
                "本季度大模型私有化推理集群 GPU 算力支出为 4,120 万元，通过 vLLM 量化与多租户成本熔断网关，"
                "单位推理成本较 Q3 下降 31.5%。\n"
            ),
            "compliance_expense_policy_2026.md": (
                "---\n"
                "title: 2026 年度企业费用报销与数据合规管理制度\n"
                "department: compliance\n"
                "fiscal_year: FY2026\n"
                "doc_type: compliance_policy\n"
                "---\n\n"
                "# 第一章 报销审批与发票合规红线\n\n"
                "单笔差旅或云算力采购报销超过 50,000 元人民币，须经部门负责人、财务总监与合规官三级联签。"
                "严禁拆分报销规避审批阈值。\n\n"
                "## 第二章 敏感信息与审计留存规范\n\n"
                "所有进入智能体问答系统的财务凭证必须经过 PII 自动脱敏（身份证、银行卡、手机号、邮箱），"
                "审计日志仅保留 SHA-256 摘要与脱敏文本。\n"
            ),
            "fy2025_dept_budget_ledger.csv": (
                "department,fiscal_year,quarter,budget_cny,actual_cny,variance_pct,status\n"
                "finance,FY2025,Q4,12000000,11450000,-4.58,within_budget\n"
                "compliance,FY2025,Q4,6500000,6180000,-4.92,within_budget\n"
                "rd_ai_platform,FY2025,Q4,45000000,41200000,-8.44,within_budget\n"
                "audit,FY2025,Q4,4800000,4750000,-1.04,within_budget\n"
            ),
        }

        created: list[Path] = []
        for filename, content in files_content.items():
            p = root / filename
            p.write_text(content, encoding="utf-8")
            created.append(p)
        return created
