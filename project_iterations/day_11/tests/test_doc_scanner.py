"""Day 11 单元测试：覆盖 pathlib 扫描、re 关键词统计、datetime 时间戳与 CSV/JSON 报告导出"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

# 确保可以直接导入 project_iterations/day_11 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.doc_scanner import DocScanner, DocumentRecord, ScanReport


def _seed_docs(root: Path) -> None:
    """在 tmp_path 中构造多层级测试文档集合。"""
    sub = root / "nested"
    sub.mkdir(parents=True, exist_ok=True)

    (root / "overview.md").write_text(
        "# ZhiShu RAG Overview\n"
        "RAG combines retrieval and LLM generation. rag is powerful.\n"
        "Agent uses RAG.\n",
        encoding="utf-8",
    )
    (sub / "guide.txt").write_text(
        "Agent workflow guide.\n"
        "Embedding model converts text to vectors.\n",
        encoding="utf-8",
    )
    (sub / "empty.md").write_text("", encoding="utf-8")
    (root / "script.py").write_text("print('RAG Agent')", encoding="utf-8")
    (sub / "data.json").write_text('{"keyword": "RAG"}', encoding="utf-8")


class TestDocScannerDiscovery:
    """测试 pathlib 目录发现与过滤逻辑。"""

    def test_discover_recursive_only_txt_and_md(self, tmp_path: Path) -> None:
        _seed_docs(tmp_path)
        scanner = DocScanner()
        files = scanner.discover_files(tmp_path, recursive=True)
        rel_paths = [f.relative_to(tmp_path).as_posix() for f in files]
        assert rel_paths == ["nested/empty.md", "nested/guide.txt", "overview.md"]

    def test_discover_non_recursive(self, tmp_path: Path) -> None:
        _seed_docs(tmp_path)
        scanner = DocScanner()
        files = scanner.discover_files(tmp_path, recursive=False)
        rel_paths = [f.relative_to(tmp_path).as_posix() for f in files]
        assert rel_paths == ["overview.md"]

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        scanner = DocScanner()
        with pytest.raises(FileNotFoundError, match="不存在"):
            scanner.scan(tmp_path / "does_not_exist", keywords=["RAG"])

    def test_file_instead_of_directory_raises(self, tmp_path: Path) -> None:
        file_path = tmp_path / "single.txt"
        file_path.write_text("hello", encoding="utf-8")
        scanner = DocScanner()
        with pytest.raises(NotADirectoryError, match="不是目录"):
            scanner.scan(file_path, keywords=["hello"])


class TestDocScannerRegexAndStats:
    """测试正则关键词计数、大小写/全词选项及 datetime 元数据。"""

    def test_scan_case_insensitive_counts(self, tmp_path: Path) -> None:
        _seed_docs(tmp_path)
        scanner = DocScanner(case_sensitive=False)
        report = scanner.scan(tmp_path, keywords=["RAG", "Agent", "Embedding"])

        assert isinstance(report, ScanReport)
        assert report.total_files == 3
        assert report.keyword_totals == {"RAG": 4, "Agent": 2, "Embedding": 1}
        assert report.total_hits == 7
        assert report.total_size_bytes > 0

        # 验证 ISO 8601 时间戳可被 datetime.fromisoformat 解析
        parsed_scanned_at = datetime.fromisoformat(report.scanned_at)
        assert parsed_scanned_at.tzinfo is not None

        by_path = {rec.relative_path: rec for rec in report.files}
        assert isinstance(by_path["overview.md"], DocumentRecord)
        assert by_path["overview.md"].keyword_counts == {"RAG": 4, "Agent": 1, "Embedding": 0}
        assert by_path["overview.md"].total_hits == 5
        assert by_path["overview.md"].line_count == 3

        assert by_path["nested/guide.txt"].keyword_counts == {"RAG": 0, "Agent": 1, "Embedding": 1}
        assert by_path["nested/empty.md"].total_hits == 0
        assert by_path["nested/empty.md"].line_count == 0

    def test_scan_case_sensitive_and_whole_word(self, tmp_path: Path) -> None:
        (tmp_path / "sample.txt").write_text(
            "Agent agents agent RAG rag", encoding="utf-8"
        )
        scanner_cs = DocScanner(case_sensitive=True, whole_word=True)
        report_cs = scanner_cs.scan(tmp_path, keywords=["Agent", "RAG"])
        assert report_cs.keyword_totals == {"Agent": 1, "RAG": 1}

        scanner_ci = DocScanner(case_sensitive=False, whole_word=True)
        report_ci = scanner_ci.scan(tmp_path, keywords=["Agent", "RAG"])
        # "agents" 不应被全词匹配为 "Agent"
        assert report_ci.keyword_totals == {"Agent": 2, "RAG": 2}

    def test_chinese_keywords_and_deduplication(self, tmp_path: Path) -> None:
        (tmp_path / "cn.md").write_text("智枢智能体支持企业级智能体检索。", encoding="utf-8")
        scanner = DocScanner()
        report = scanner.scan(tmp_path, keywords=["智能体", "智能体", "检索"])
        assert report.keywords == ["智能体", "检索"]
        assert report.keyword_totals == {"智能体": 2, "检索": 1}

    @pytest.mark.parametrize("bad_keywords", [[], ["  ", ""], [123]])
    def test_invalid_keywords_raises(self, tmp_path: Path, bad_keywords: list) -> None:
        scanner = DocScanner()
        with pytest.raises(ValueError):
            scanner.scan(tmp_path, keywords=bad_keywords)


class TestDocScannerExport:
    """测试 JSON 与 CSV 报告导出。"""

    def test_export_json_and_csv(self, tmp_path: Path) -> None:
        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        _seed_docs(kb_dir)

        scanner = DocScanner()
        report = scanner.scan(kb_dir, keywords=["RAG", "Agent"])

        json_out = tmp_path / "exports" / "nested" / "report.json"
        csv_out = tmp_path / "exports" / "nested" / "report.csv"

        saved_json = scanner.export_json(report, json_out)
        saved_csv = scanner.export_csv(report, csv_out)

        assert saved_json.exists()
        assert saved_csv.exists()

        # 校验 JSON 结构
        data = json.loads(saved_json.read_text(encoding="utf-8"))
        assert data["summary"]["total_files"] == 3
        assert data["summary"]["total_hits"] == 6
        assert data["summary"]["keyword_totals"] == {"RAG": 4, "Agent": 2}
        assert len(data["files"]) == 3

        # 校验 CSV 结构
        with saved_csv.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3
        row_map = {r["relative_path"]: r for r in rows}
        assert row_map["overview.md"]["kw:RAG"] == "4"
        assert row_map["overview.md"]["kw:Agent"] == "1"
        assert row_map["overview.md"]["total_hits"] == "5"
        assert row_map["nested/empty.md"]["total_hits"] == "0"
