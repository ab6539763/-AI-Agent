"""Day 28 核心模块：企业级文档加载器（Loader）与智能文本切分器（TextSplitter）。

实现 RAG（检索增强生成）Pipeline 第一步：
1. 统一文档数据结构 `Document(page_content, metadata)`
2. 多格式文档加载器：`TextLoader`、`MarkdownLoader`、`CSVLoader`
3. 多策略文本切分器：`CharacterTextSplitter`、`RecursiveCharacterTextSplitter`、`MarkdownHeaderTextSplitter`
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    """标准文档对象，承载文本正文与结构化元数据。"""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.page_content, str):
            raise TypeError("page_content 必须为字符串类型")
        self.metadata = dict(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典格式。"""
        return {
            "page_content": self.page_content,
            "metadata": dict(self.metadata),
        }


class TextLoader:
    """纯文本文件加载器（支持 .txt / .log 等纯文本）。"""

    def __init__(self, file_path: str | Path, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding

    def load(self) -> list[Document]:
        """读取纯文本文件并返回单元素 Document 列表。"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        content = self.file_path.read_text(encoding=self.encoding)
        metadata = {
            "source": str(self.file_path),
            "file_name": self.file_path.name,
            "file_type": self.file_path.suffix.lower() or ".txt",
            "loader": "TextLoader",
        }
        return [Document(page_content=content, metadata=metadata)]


class MarkdownLoader:
    """Markdown 文档加载器（自动提取一级标题作为 title 元数据）。"""

    def __init__(self, file_path: str | Path, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding

    def load(self) -> list[Document]:
        """读取 Markdown 文件并提取基础元数据。"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        content = self.file_path.read_text(encoding=self.encoding)
        title = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break
        metadata: dict[str, Any] = {
            "source": str(self.file_path),
            "file_name": self.file_path.name,
            "file_type": ".md",
            "loader": "MarkdownLoader",
        }
        if title:
            metadata["title"] = title
        return [Document(page_content=content, metadata=metadata)]


class CSVLoader:
    """CSV 结构化表格加载器（每行记录转为一条独立的 Document）。"""

    def __init__(
        self,
        file_path: str | Path,
        encoding: str = "utf-8",
        source_column: str | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding
        self.source_column = source_column

    def load(self) -> list[Document]:
        """逐行解析 CSV，将每行键值对格式化为文本并记录行号元数据。"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        documents: list[Document] = []
        with self.file_path.open("r", encoding=self.encoding, newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames is None:
                return documents
            for row_idx, row in enumerate(reader):
                lines = [
                    f"{key}: {value if value is not None else ''}"
                    for key, value in row.items()
                ]
                content = "\n".join(lines)
                source = str(self.file_path)
                if self.source_column and self.source_column in row:
                    source = str(row[self.source_column])
                metadata = {
                    "source": source,
                    "file_name": self.file_path.name,
                    "file_type": ".csv",
                    "row": row_idx,
                    "loader": "CSVLoader",
                }
                documents.append(Document(page_content=content, metadata=metadata))
        return documents


def _validate_chunk_params(chunk_size: int, chunk_overlap: int) -> None:
    """校验切分窗口大小与重叠长度参数。"""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须大于 0，当前值: {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap 不能为负数，当前值: {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) 必须严格小于 chunk_size ({chunk_size})"
        )


def _merge_splits(
    splits: list[str],
    separator: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """将细粒度文本片段按 chunk_size 与 chunk_overlap 滑动窗口合并为最终 Chunk。"""
    docs: list[str] = []
    current_doc: list[str] = []
    total_len = 0
    sep_len = len(separator)

    for piece in splits:
        piece_len = len(piece)
        added_len = piece_len + (sep_len if current_doc else 0)

        if total_len + added_len > chunk_size and current_doc:
            joined = separator.join(current_doc).strip()
            if joined:
                docs.append(joined)

            # 滑动窗口回退：保留尾部片段以满足 chunk_overlap
            while current_doc and (
                total_len > chunk_overlap
                or (total_len + piece_len + sep_len > chunk_size and total_len > 0)
            ):
                removed = current_doc.pop(0)
                total_len -= len(removed) + (sep_len if current_doc else 0)

        current_doc.append(piece)
        total_len += piece_len + (sep_len if len(current_doc) > 1 else 0)

    if current_doc:
        joined = separator.join(current_doc).strip()
        if joined:
            docs.append(joined)

    return docs


class CharacterTextSplitter:
    """按单一分隔符进行定长切分的文本切分器。"""

    def __init__(
        self,
        separator: str = "\n\n",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        _validate_chunk_params(chunk_size, chunk_overlap)
        self.separator = separator
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        """将纯文本按指定分隔符切分为不超过 chunk_size 的片段（超长单片按步长截断）。"""
        if not text or not text.strip():
            return []

        if self.separator:
            raw_splits = [s for s in text.split(self.separator) if s.strip()]
        else:
            raw_splits = list(text)

        merged = _merge_splits(
            raw_splits,
            self.separator if self.separator else "",
            self.chunk_size,
            self.chunk_overlap,
        )

        # 若单个片段本身超过 chunk_size，按滑动窗口硬切兜底
        final_chunks: list[str] = []
        step = self.chunk_size - self.chunk_overlap
        for chunk in merged:
            if len(chunk) <= self.chunk_size:
                final_chunks.append(chunk)
            else:
                for start in range(0, len(chunk), step):
                    sub = chunk[start : start + self.chunk_size].strip()
                    if sub:
                        final_chunks.append(sub)
                    if start + self.chunk_size >= len(chunk):
                        break
        return final_chunks

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """切分 Document 列表并完整保留原始元数据，同时注入 chunk_index。"""
        result: list[Document] = []
        for doc in documents:
            chunks = self.split_text(doc.page_content)
            for idx, chunk in enumerate(chunks):
                new_meta = dict(doc.metadata)
                new_meta["chunk_index"] = idx
                new_meta["chunk_total"] = len(chunks)
                result.append(Document(page_content=chunk, metadata=new_meta))
        return result


class RecursiveCharacterTextSplitter:
    """递归字符文本切分器：按多级分隔符优先保持段落、换行、句子与词语完整性。"""

    DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", " ", ""]

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ) -> None:
        _validate_chunk_params(chunk_size, chunk_overlap)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = (
            list(separators)
            if separators is not None
            else list(self.DEFAULT_SEPARATORS)
        )

    def _split_text_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            stripped = text.strip()
            return [stripped] if stripped else []

        # 选择当前文本中命中的最高优先级分隔符
        separator = separators[-1] if separators else ""
        remaining_separators: list[str] = []
        for idx, sep in enumerate(separators):
            if sep == "":
                separator = ""
                remaining_separators = []
                break
            if sep in text:
                separator = sep
                remaining_separators = separators[idx + 1 :]
                break

        if separator:
            splits = [s for s in text.split(separator) if s]
        else:
            splits = list(text)

        good_splits: list[str] = []
        final_chunks: list[str] = []

        for piece in splits:
            if len(piece) <= self.chunk_size:
                good_splits.append(piece)
            else:
                if good_splits:
                    final_chunks.extend(
                        _merge_splits(
                            good_splits,
                            separator,
                            self.chunk_size,
                            self.chunk_overlap,
                        )
                    )
                    good_splits = []

                if not remaining_separators:
                    # 终极兜底：按步长切片
                    step = self.chunk_size - self.chunk_overlap
                    for start in range(0, len(piece), step):
                        sub = piece[start : start + self.chunk_size].strip()
                        if sub:
                            final_chunks.append(sub)
                        if start + self.chunk_size >= len(piece):
                            break
                else:
                    final_chunks.extend(
                        self._split_text_recursive(piece, remaining_separators)
                    )

        if good_splits:
            final_chunks.extend(
                _merge_splits(
                    good_splits,
                    separator,
                    self.chunk_size,
                    self.chunk_overlap,
                )
            )

        return final_chunks

    def split_text(self, text: str) -> list[str]:
        """递归切分纯文本，返回语义尽量完整的 Chunk 列表。"""
        if not text or not text.strip():
            return []
        return self._split_text_recursive(text, self.separators)

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """切分 Document 列表，保留原文档元数据并附加 chunk_index / chunk_total。"""
        result: list[Document] = []
        for doc in documents:
            chunks = self.split_text(doc.page_content)
            for idx, chunk in enumerate(chunks):
                new_meta = dict(doc.metadata)
                new_meta["chunk_index"] = idx
                new_meta["chunk_total"] = len(chunks)
                result.append(Document(page_content=chunk, metadata=new_meta))
        return result


class MarkdownHeaderTextSplitter:
    """Markdown 标题层级切分器：按标题切分并将各级标题自动注入 Chunk 元数据。"""

    DEFAULT_HEADERS: list[tuple[str, str]] = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]

    def __init__(
        self,
        headers_to_split_on: list[tuple[str, str]] | None = None,
        strip_headers: bool = True,
    ) -> None:
        raw_headers = (
            headers_to_split_on
            if headers_to_split_on is not None
            else self.DEFAULT_HEADERS
        )
        # 按标题井号长度降序匹配，避免 "##" 被 "#" 误匹配
        self.headers_to_split_on = sorted(
            raw_headers, key=lambda item: len(item[0]), reverse=True
        )
        self.strip_headers = strip_headers

    def split_text(self, text: str) -> list[Document]:
        """按 Markdown 标题层级切分文本，正确跳过围栏代码块中的 `#` 注释。"""
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        chunks: list[Document] = []
        current_lines: list[str] = []
        current_headers: dict[str, str] = {}
        in_code_block = False
        code_fence_pattern = re.compile(r"^\s*(```|~~~)")

        def _flush() -> None:
            body = "\n".join(current_lines).strip()
            if body:
                chunks.append(
                    Document(page_content=body, metadata=dict(current_headers))
                )

        for line in lines:
            if code_fence_pattern.match(line):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue

            matched_header: tuple[str, str, str] | None = None
            if not in_code_block:
                stripped = line.lstrip()
                for prefix, meta_key in self.headers_to_split_on:
                    if stripped.startswith(prefix + " "):
                        title_text = stripped[len(prefix) + 1 :].strip()
                        matched_header = (prefix, meta_key, title_text)
                        break

            if matched_header is not None:
                _flush()
                current_lines = [] if self.strip_headers else [line]
                prefix, meta_key, title_text = matched_header
                current_level = len(prefix)

                # 更新当前层级标题，并清除所有更低层级的旧标题
                updated_headers: dict[str, str] = {}
                for h_prefix, h_key in sorted(
                    self.headers_to_split_on, key=lambda item: len(item[0])
                ):
                    if len(h_prefix) < current_level and h_key in current_headers:
                        updated_headers[h_key] = current_headers[h_key]
                updated_headers[meta_key] = title_text
                current_headers = updated_headers
            else:
                current_lines.append(line)

        _flush()
        return chunks

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """对 Document 列表按 Markdown 标题切分，并合并保留原文档元数据。"""
        result: list[Document] = []
        for doc in documents:
            header_docs = self.split_text(doc.page_content)
            for idx, h_doc in enumerate(header_docs):
                merged_meta = dict(doc.metadata)
                merged_meta.update(h_doc.metadata)
                merged_meta["chunk_index"] = idx
                merged_meta["chunk_total"] = len(header_docs)
                result.append(
                    Document(page_content=h_doc.page_content, metadata=merged_meta)
                )
        return result
