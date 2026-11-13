"""智枢企业级智能体平台 Day 59 主程序入口 (v1.0.0-day59)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from zhishu_agent import CapstoneKBInitializer


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        corpus_dir = base / "corpus"
        json_index = base / "artifacts" / "kb_index.json"
        sqlite_db = base / "artifacts" / "kb_index.sqlite"

        CapstoneKBInitializer.create_sample_corpus(corpus_dir)

        initializer = CapstoneKBInitializer(chunk_size=300, chunk_overlap=40)
        chunks, stats = initializer.build_and_persist(
            input_dir=corpus_dir,
            json_path=json_index,
            sqlite_path=sqlite_db,
        )

        print("=== 1. 知识库构建统计 ===")
        print(f"处理文件数: {stats.processed_files}/{stats.total_files}")
        print(f"生成切片数: {stats.total_chunks}")
        print(f"部门分布: {stats.departments}")
        print(f"财年分布: {stats.fiscal_years}")
        print(f"文档类型: {stats.doc_types}")

        print("\n=== 2. SQLite 元数据检索示例（compliance / FY2026）===")
        hits = initializer.query_sqlite(
            db_path=sqlite_db,
            department="compliance",
            fiscal_year="FY2026",
        )
        for item in hits:
            print(f"- [{item['chunk_id']}] {item['section_heading']} ({item['char_count']} chars)")


if __name__ == "__main__":
    run_demo()
