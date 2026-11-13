"""Day 59 单元测试：CapstoneKBInitializer 知识库构建、元数据切分与双路持久化."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent
ITER_ROOT = Path(__file__).resolve().parents[1]
if str(ITER_ROOT) not in sys.path:
    sys.path.insert(0, str(ITER_ROOT))

from zhishu_agent import CapstoneKBInitializer


def test_ingest_markdown_with_frontmatter_and_sections(tmp_path: Path) -> None:
    md_file = tmp_path / "fy2025_report.md"
    md_file.write_text(
        "---\n"
        "title: FY2025 财务年报\n"
        "department: finance\n"
        "fiscal_year: FY2025\n"
        "doc_type: financial_report\n"
        "---\n\n"
        "# 核心营收表现\n\n"
        "2025 财年总营收 4.82 亿元。\n\n"
        "## 成本优化\n\n"
        "算力成本下降 31.5%。\n",
        encoding="utf-8",
    )

    init = CapstoneKBInitializer(chunk_size=200, chunk_overlap=30)
    chunks = init.ingest_file(md_file)

    assert len(chunks) == 2
    assert chunks[0].department == "finance"
    assert chunks[0].fiscal_year == "FY2025"
    assert chunks[0].doc_type == "financial_report"
    assert chunks[0].section_heading == "核心营收表现"
    assert chunks[1].section_heading == "成本优化"
    assert chunks[0].metadata["title"] == "FY2025 财务年报"


def test_ingest_csv_ledger_and_metadata_inference(tmp_path: Path) -> None:
    csv_file = tmp_path / "fy2026_finance_budget.csv"
    rows = ["department,fiscal_year,budget_cny,actual_cny"]
    for i in range(1, 13):
        rows.append(f"finance,FY2026,{100000 * i},{95000 * i}")
    csv_file.write_text("\n".join(rows), encoding="utf-8")

    init = CapstoneKBInitializer(chunk_size=600, chunk_overlap=50, rows_per_csv_chunk=5)
    chunks = init.ingest_file(csv_file)

    # 12 行数据，每批 5 行 -> 3 批
    assert len(chunks) == 3
    assert all(c.department == "finance" for c in chunks)
    assert all(c.fiscal_year == "FY2026" for c in chunks)
    assert all(c.doc_type == "financial_ledger" for c in chunks)
    assert "第 1 条" in chunks[0].content
    assert "第 12 条" in chunks[2].content


def test_build_and_persist_json_and_sqlite(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    CapstoneKBInitializer.create_sample_corpus(corpus_dir)
    # 添加一个不支持的扩展名文件，验证跳过计数
    (corpus_dir / "ignored.tmp").write_text("ignore me", encoding="utf-8")

    json_path = tmp_path / "out" / "kb_index.json"
    sqlite_path = tmp_path / "out" / "kb_index.sqlite"

    init = CapstoneKBInitializer(chunk_size=260, chunk_overlap=40)
    chunks, stats = init.build_and_persist(
        input_dir=corpus_dir,
        json_path=json_path,
        sqlite_path=sqlite_path,
    )

    assert stats.total_files == 4
    assert stats.processed_files == 3
    assert stats.skipped_files == 1
    assert stats.total_chunks == len(chunks)
    assert stats.total_chunks >= 4

    # 校验 JSON 持久化
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["version"] == "v1.0.0-day59"
    assert payload["total_chunks"] == len(chunks)
    assert len(payload["chunks"]) == len(chunks)

    # 校验 SQLite 持久化与元数据检索
    assert sqlite_path.exists()
    conn = sqlite3.connect(str(sqlite_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
        assert count == len(chunks)
    finally:
        conn.close()

    compliance_hits = init.query_sqlite(
        db_path=sqlite_path,
        department="compliance",
        fiscal_year="FY2026",
        keyword="脱敏",
    )
    assert len(compliance_hits) >= 1
    assert any("PII" in h["content"] for h in compliance_hits)


def test_idempotent_sqlite_upsert_and_error_handling(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    CapstoneKBInitializer.create_sample_corpus(corpus_dir)
    sqlite_path = tmp_path / "kb.sqlite"

    init = CapstoneKBInitializer(chunk_size=300, chunk_overlap=40)
    chunks, _ = init.build_and_persist(corpus_dir, sqlite_path=sqlite_path)
    # 重复写入应保持幂等，不产生重复主键冲突或重复行
    init.save_sqlite_index(chunks, sqlite_path)

    all_rows = init.query_sqlite(sqlite_path, limit=100)
    assert len(all_rows) == len(chunks)

    bad_file = tmp_path / "unsupported.txt"
    bad_file.write_text("plain text", encoding="utf-8")
    with pytest.raises(ValueError, match="不支持的文件格式"):
        init.ingest_file(bad_file)

    with pytest.raises(FileNotFoundError):
        init.ingest_file(tmp_path / "missing.md")
