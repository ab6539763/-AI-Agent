"""智枢平台 Day 11 核心模块：文档扫描与关键词统计引擎（RAG 预处理基石）"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS: tuple[str, ...] = (".txt", ".md")


@dataclass
class DocumentRecord:
    """单个文档的扫描与关键词命中统计结果。"""

    file_name: str
    relative_path: str
    extension: str
    size_bytes: int
    line_count: int
    char_count: int
    modified_at: str
    keyword_counts: dict[str, int] = field(default_factory=dict)
    total_hits: int = 0

    def to_dict(self) -> dict[str, object]:
        """转换为可序列化的字典结构。"""
        return asdict(self)


@dataclass
class ScanReport:
    """目录级文档扫描汇总报告。"""

    root_dir: str
    scanned_at: str
    keywords: list[str]
    total_files: int
    total_size_bytes: int
    total_hits: int
    keyword_totals: dict[str, int]
    files: list[DocumentRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换为完整嵌套字典，便于 JSON 导出。"""
        return {
            "root_dir": self.root_dir,
            "scanned_at": self.scanned_at,
            "keywords": self.keywords,
            "summary": {
                "total_files": self.total_files,
                "total_size_bytes": self.total_size_bytes,
                "total_hits": self.total_hits,
                "keyword_totals": self.keyword_totals,
            },
            "files": [record.to_dict() for record in self.files],
        }


class DocScanner:
    """企业知识库文档扫描器：基于标准库实现文件遍历、正则词频统计与报告导出。"""

    def __init__(
        self,
        extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
        case_sensitive: bool = False,
        whole_word: bool = False,
    ) -> None:
        normalized_exts = tuple(
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in extensions
        )
        if not normalized_exts:
            raise ValueError("extensions 不能为空，至少需要指定一种文件后缀")
        self.extensions = normalized_exts
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word

    @staticmethod
    def _validate_directory(directory: str | Path) -> Path:
        root = Path(directory)
        if not root.exists():
            raise FileNotFoundError(f"目标目录不存在: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"目标路径不是目录: {root}")
        return root

    @staticmethod
    def _validate_keywords(keywords: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for kw in keywords:
            if not isinstance(kw, str) or not kw.strip():
                raise ValueError("关键词必须为非空字符串")
            item = kw.strip()
            if item not in seen:
                seen.add(item)
                cleaned.append(item)
        if not cleaned:
            raise ValueError("keywords 不能为空，请至少提供一个待检索关键词")
        return cleaned

    def _compile_patterns(self, keywords: list[str]) -> dict[str, re.Pattern[str]]:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        patterns: dict[str, re.Pattern[str]] = {}
        for kw in keywords:
            escaped = re.escape(kw)
            # 仅在全词匹配且关键词首尾为字母/数字/下划线时添加 \b 边界
            if self.whole_word and re.match(r"^\w.*\w$|^\w$", kw):
                pattern_str = rf"\b{escaped}\b"
            else:
                pattern_str = escaped
            patterns[kw] = re.compile(pattern_str, flags)
        return patterns

    def discover_files(self, directory: str | Path, recursive: bool = True) -> list[Path]:
        """扫描目录中符合后缀要求的文本文件，并按相对路径排序。"""
        root = self._validate_directory(directory)
        iterator = root.rglob("*") if recursive else root.iterdir()
        files = [
            p
            for p in iterator
            if p.is_file() and p.suffix.lower() in self.extensions
        ]
        return sorted(files, key=lambda p: p.relative_to(root).as_posix())

    def scan(
        self,
        directory: str | Path,
        keywords: Iterable[str],
        recursive: bool = True,
    ) -> ScanReport:
        """执行目录扫描与正则关键词频次统计，返回结构化 ScanReport。"""
        root = self._validate_directory(directory)
        kw_list = self._validate_keywords(keywords)
        patterns = self._compile_patterns(kw_list)
        target_files = self.discover_files(root, recursive=recursive)

        records: list[DocumentRecord] = []
        keyword_totals: dict[str, int] = {kw: 0 for kw in kw_list}
        total_size_bytes = 0
        total_hits = 0

        for file_path in target_files:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            stat = file_path.stat()
            modified_at = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()

            counts: dict[str, int] = {}
            file_hits = 0
            for kw, pattern in patterns.items():
                hit_count = len(pattern.findall(content))
                counts[kw] = hit_count
                keyword_totals[kw] += hit_count
                file_hits += hit_count

            record = DocumentRecord(
                file_name=file_path.name,
                relative_path=file_path.relative_to(root).as_posix(),
                extension=file_path.suffix.lower(),
                size_bytes=stat.st_size,
                line_count=len(content.splitlines()),
                char_count=len(content),
                modified_at=modified_at,
                keyword_counts=counts,
                total_hits=file_hits,
            )
            records.append(record)
            total_size_bytes += stat.st_size
            total_hits += file_hits

        return ScanReport(
            root_dir=str(root.resolve()),
            scanned_at=datetime.now(timezone.utc).isoformat(),
            keywords=kw_list,
            total_files=len(records),
            total_size_bytes=total_size_bytes,
            total_hits=total_hits,
            keyword_totals=keyword_totals,
            files=records,
        )

    @staticmethod
    def export_json(report: ScanReport, output_path: str | Path) -> Path:
        """将扫描报告导出为格式化的 UTF-8 JSON 文件。"""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        out.write_text(payload, encoding="utf-8")
        return out

    @staticmethod
    def export_csv(report: ScanReport, output_path: str | Path) -> Path:
        """将扫描报告逐文件导出为结构化 CSV 表格。"""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        kw_headers = [f"kw:{kw}" for kw in report.keywords]
        fieldnames = [
            "file_name",
            "relative_path",
            "extension",
            "size_bytes",
            "line_count",
            "char_count",
            "modified_at",
            "total_hits",
            *kw_headers,
        ]

        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in report.files:
                row: dict[str, object] = {
                    "file_name": record.file_name,
                    "relative_path": record.relative_path,
                    "extension": record.extension,
                    "size_bytes": record.size_bytes,
                    "line_count": record.line_count,
                    "char_count": record.char_count,
                    "modified_at": record.modified_at,
                    "total_hits": record.total_hits,
                }
                for kw in report.keywords:
                    row[f"kw:{kw}"] = record.keyword_counts.get(kw, 0)
                writer.writerow(row)

        return out
