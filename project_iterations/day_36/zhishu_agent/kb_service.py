"""Day 36: 里程碑项目 2 Part 1 — 企业知识库问答系统后端 (EnterpriseKBService).

核心能力：
1. 多格式文档解析与切分（支持 .txt / .md / .csv）
2. BM25 稀疏检索 + 本地向量密集检索 + RRF 倒数排名融合 + CrossEncoder 风格重排序
3. 基于检索上下文的严谨引用溯源回答生成（Grounded Answer + Inline Citations `[1][2]`）
4. SQLite 多轮会话历史持久化（Session & Message 管理）
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    """中英文混合分词器：英文/数字词元 + 中文 Unigram 与 Bigram."""
    normalized = text.strip().lower()
    if not normalized:
        return []
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9_]+", normalized))
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    tokens.extend(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点或换行切分句子（避免误切文件名中的点号）."""
    raw = re.split(r"(?:[。！？\n]+|(?<!\w)[.!?]+(?!\w))\s*", text.strip())
    return [s.strip() for s in raw if s and s.strip()]


@dataclass
class ChunkDocument:
    """切分后的知识库文档片段."""

    chunk_id: str
    doc_id: str
    source: str
    file_type: str
    chunk_index: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source": self.source,
            "file_type": self.file_type,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class IngestResult:
    """文档入库结果."""

    doc_id: str
    source: str
    file_type: str
    num_chunks: int
    chunk_ids: list[str]


@dataclass
class RetrievedChunk:
    """混合检索与重排后的候选片段及各阶段得分."""

    chunk: ChunkDocument
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class Citation:
    """回答引用溯源条目."""

    index: int
    chunk_id: str
    source: str
    chunk_index: int
    snippet: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "chunk_id": self.chunk_id,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }


@dataclass
class QAResponse:
    """企业知识库问答响应."""

    session_id: str
    question: str
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    grounded: bool

    def format_with_sources(self) -> str:
        """格式化输出回答与引用来源清单."""
        if not self.citations:
            return self.answer
        lines = [self.answer, "", "参考来源："]
        for c in self.citations:
            lines.append(f"[{c.index}] {c.source} (chunk #{c.chunk_index}, score={c.score:.4f}): {c.snippet}")
        return "\n".join(lines)


@dataclass
class SessionMessage:
    """SQLite 会话消息记录."""

    id: int
    session_id: str
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: str


class LocalEmbedding:
    """基于 Feature Hashing + L2 归一化的确定性本地向量化器."""

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("embedding 维度 dim 必须大于 0")
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            weight = 1.5 if len(token) >= 2 else 1.0
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [round(v / norm, 8) for v in vec]
        return vec


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class BM25Index:
    """纯 Python 实现的 Okapi BM25 稀疏检索索引."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: list[ChunkDocument] = []
        self._term_freqs: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl: float = 0.0

    def add_chunks(self, chunks: list[ChunkDocument]) -> None:
        for chunk in chunks:
            tokens = _tokenize(chunk.content)
            tf = Counter(tokens)
            self._chunks.append(chunk)
            self._term_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            for term in tf:
                self._df[term] += 1
        total_len = sum(self._doc_lengths)
        self._avgdl = total_len / len(self._chunks) if self._chunks else 0.0

    def remove_by_doc_id(self, doc_id: str) -> None:
        remaining = [c for c in self._chunks if c.doc_id != doc_id]
        self._chunks = []
        self._term_freqs = []
        self._doc_lengths = []
        self._df = Counter()
        self._avgdl = 0.0
        if remaining:
            self.add_chunks(remaining)

    def search(self, query: str, top_k: int = 5) -> list[tuple[ChunkDocument, float]]:
        if not self._chunks or top_k <= 0:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        n_docs = len(self._chunks)
        scores: list[tuple[int, float]] = []
        for idx in range(n_docs):
            tf = self._term_freqs[idx]
            dl = self._doc_lengths[idx]
            score = 0.0
            for term in q_tokens:
                if term not in tf:
                    continue
                df = self._df[term]
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                freq = tf[term]
                denom = freq + self.k1 * (1.0 - self.b + self.b * (dl / max(self._avgdl, 1e-9)))
                score += idf * (freq * (self.k1 + 1.0)) / max(denom, 1e-9)
            if score > 0.0:
                scores.append((idx, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        return [(self._chunks[idx], round(score, 6)) for idx, score in scores[:top_k]]


class SQLiteSessionStore:
    """基于 SQLite 的企业知识库多轮会话持久化存储."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )

    def create_session(self, session_id: str | None = None, title: str = "") -> str:
        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (sid, title, now, now),
            )
        return sid

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[Citation] | None = None,
    ) -> int:
        self.create_session(session_id=session_id)
        now = _now_iso()
        citations_payload = [c.to_dict() for c in (citations or [])]
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO messages (session_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, json.dumps(citations_payload, ensure_ascii=False), now),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            return int(cursor.lastrowid)

    def get_history(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        query = """
            SELECT id, session_id, role, content, citations_json, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """
        params: list[Any] = [session_id]
        if limit is not None and limit > 0:
            query = f"""
                SELECT * FROM (
                    SELECT id, session_id, role, content, citations_json, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
            """
            params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            SessionMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                citations=json.loads(row["citations_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT s.session_id, s.title, s.created_at, s.updated_at, COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def clear_session(self, session_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def close(self) -> None:
        self._conn.close()


class EnterpriseKBService:
    """企业级知识库问答系统后端服务（Milestone Project 2 Part 1）.

    支持多格式文档上传解析（.txt/.md/.csv）、文本切分、BM25+向量混合检索、
    RRF 融合与重排序、带引用的严谨回答生成，以及 SQLite 会话持久化。
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        embedding_dim: int = 128,
        min_relevance_score: float = 0.06,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_relevance_score = min_relevance_score

        self.embedder = LocalEmbedding(dim=embedding_dim)
        self.bm25_index = BM25Index()
        self.session_store = SQLiteSessionStore(db_path=db_path)

        self._chunks: dict[str, ChunkDocument] = {}
        self._vectors: dict[str, list[float]] = {}
        self._documents: dict[str, dict[str, Any]] = {}

    def _split_text_with_overlap(self, text: str) -> list[str]:
        cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
        if not cleaned:
            return []
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        step = self.chunk_size - self.chunk_overlap
        while start < len(cleaned):
            end = min(start + self.chunk_size, len(cleaned))
            piece = cleaned[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(cleaned):
                break
            start += step
        return chunks

    def _parse_and_chunk(self, content: str, file_type: str, source: str) -> list[tuple[str, dict[str, Any]]]:
        """按文件格式解析文本并生成带元数据的切片列表."""
        ext = file_type.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {file_type}，仅支持 {sorted(SUPPORTED_EXTENSIONS)}")

        if ext == ".txt":
            return [(piece, {"format": "txt"}) for piece in self._split_text_with_overlap(content)]

        if ext == ".md":
            sections: list[tuple[str, str]] = []
            current_heading = ""
            buffer: list[str] = []
            for line in content.splitlines():
                if re.match(r"^#{1,6}\s+", line):
                    if buffer:
                        sections.append((current_heading, "\n".join(buffer).strip()))
                        buffer = []
                    current_heading = line.strip()
                else:
                    buffer.append(line)
            if buffer or current_heading:
                sections.append((current_heading, "\n".join(buffer).strip()))

            results: list[tuple[str, dict[str, Any]]] = []
            for heading, body in sections:
                full_sec = f"{heading}\n{body}".strip() if heading and body else (heading or body)
                if not full_sec:
                    continue
                for piece in self._split_text_with_overlap(full_sec):
                    if heading and not piece.startswith(heading):
                        piece_with_ctx = f"{heading}\n{piece}"
                    else:
                        piece_with_ctx = piece
                    results.append((piece_with_ctx, {"format": "md", "heading": heading}))
            return results

        # .csv 格式：逐行转换为结构化文本片段
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if not lines:
            return []
        reader = csv.DictReader(lines)
        results = []
        if reader.fieldnames:
            for row_idx, row in enumerate(reader, start=1):
                pairs = [f"{k.strip()}: {(v or '').strip()}" for k, v in row.items() if k and (v or "").strip()]
                if pairs:
                    row_text = f"[{source} 第{row_idx}行] " + " | ".join(pairs)
                    results.append((row_text, {"format": "csv", "row_index": row_idx}))
        return results

    def ingest_file(self, file_path: str | Path, doc_id: str | None = None) -> IngestResult:
        """上传并解析本地文件（支持 .txt / .md / .csv）入库."""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 {sorted(SUPPORTED_EXTENSIONS)}")

        raw_text = path.read_text(encoding="utf-8")
        return self.ingest_text(
            content=raw_text,
            source=path.name,
            file_type=ext,
            doc_id=doc_id,
        )

    def ingest_text(
        self,
        content: str,
        source: str,
        file_type: str = ".txt",
        doc_id: str | None = None,
    ) -> IngestResult:
        """直接将文本内容按指定格式解析切分并入库."""
        ext = file_type.lower() if file_type.startswith(".") else f".{file_type.lower()}"
        assigned_doc_id = doc_id or f"doc-{uuid.uuid4().hex[:10]}"

        parsed_pieces = self._parse_and_chunk(content=content, file_type=ext, source=source)
        chunk_docs: list[ChunkDocument] = []
        for idx, (piece_text, meta) in enumerate(parsed_pieces):
            chunk_id = f"{assigned_doc_id}-c{idx:03d}"
            chunk = ChunkDocument(
                chunk_id=chunk_id,
                doc_id=assigned_doc_id,
                source=source,
                file_type=ext,
                chunk_index=idx,
                content=piece_text,
                metadata=meta,
            )
            chunk_docs.append(chunk)
            self._chunks[chunk_id] = chunk
            self._vectors[chunk_id] = self.embedder.embed_text(piece_text)

        self.bm25_index.add_chunks(chunk_docs)
        self._documents[assigned_doc_id] = {
            "doc_id": assigned_doc_id,
            "source": source,
            "file_type": ext,
            "num_chunks": len(chunk_docs),
            "ingested_at": _now_iso(),
        }
        return IngestResult(
            doc_id=assigned_doc_id,
            source=source,
            file_type=ext,
            num_chunks=len(chunk_docs),
            chunk_ids=[c.chunk_id for c in chunk_docs],
        )

    def list_documents(self) -> list[dict[str, Any]]:
        return list(self._documents.values())

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self._documents:
            return False
        to_remove = [cid for cid, ch in self._chunks.items() if ch.doc_id == doc_id]
        for cid in to_remove:
            self._chunks.pop(cid, None)
            self._vectors.pop(cid, None)
        self.bm25_index.remove_by_doc_id(doc_id)
        self._documents.pop(doc_id, None)
        return True

    def _compute_rerank_score(
        self,
        query: str,
        chunk: ChunkDocument,
        bm25_score: float,
        vector_score: float,
        rrf_score: float,
    ) -> float:
        """CrossEncoder 风格精排打分：融合词元精确覆盖、双字重叠、向量相似度与 RRF."""
        q_tokens = _tokenize(query)
        c_tokens = set(_tokenize(chunk.content))
        if not q_tokens:
            return 0.0

        exact_overlap = sum(1 for t in q_tokens if t in c_tokens) / len(q_tokens)
        q_bigrams = [t for t in q_tokens if len(t) >= 2]
        bigram_overlap = (
            sum(1 for t in q_bigrams if t in c_tokens) / len(q_bigrams)
            if q_bigrams
            else exact_overlap
        )
        bm25_norm = bm25_score / (bm25_score + 2.0) if bm25_score > 0 else 0.0
        rrf_norm = min(rrf_score * 30.0, 1.0)
        score = (
            0.40 * bigram_overlap
            + 0.20 * exact_overlap
            + 0.20 * max(vector_score, 0.0)
            + 0.10 * bm25_norm
            + 0.10 * rrf_norm
        )
        if q_bigrams and bigram_overlap == 0.0 and vector_score < 0.25:
            score *= 0.3
        return round(score, 6)

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        rrf_k: int = 60,
        use_rerank: bool = True,
    ) -> list[RetrievedChunk]:
        """执行 BM25 + Vector 混合检索、RRF 融合与可选 Rerank 重排序."""
        if not self._chunks or not query.strip() or top_k <= 0:
            return []

        candidate_k = max(top_k * 3, 10)
        bm25_hits = self.bm25_index.search(query, top_k=candidate_k)
        bm25_rank_map = {chunk.chunk_id: (rank, score) for rank, (chunk, score) in enumerate(bm25_hits, start=1)}

        q_vec = self.embedder.embed_text(query)
        vec_scored: list[tuple[ChunkDocument, float]] = []
        for cid, chunk in self._chunks.items():
            sim = _cosine_similarity(q_vec, self._vectors[cid])
            if sim > 0.0:
                vec_scored.append((chunk, sim))
        vec_scored.sort(key=lambda item: item[1], reverse=True)
        vec_hits = vec_scored[:candidate_k]
        vec_rank_map = {chunk.chunk_id: (rank, score) for rank, (chunk, score) in enumerate(vec_hits, start=1)}

        all_ids = set(bm25_rank_map.keys()) | set(vec_rank_map.keys())
        candidates: list[RetrievedChunk] = []
        for cid in all_ids:
            chunk = self._chunks[cid]
            b_rank, b_score = bm25_rank_map.get(cid, (None, 0.0))
            v_rank, v_score = vec_rank_map.get(cid, (None, 0.0))

            rrf = 0.0
            if b_rank is not None:
                rrf += 1.0 / (rrf_k + b_rank)
            if v_rank is not None:
                rrf += 1.0 / (rrf_k + v_rank)

            rerank = (
                self._compute_rerank_score(query, chunk, b_score, v_score, rrf)
                if use_rerank
                else round(rrf, 6)
            )
            candidates.append(
                RetrievedChunk(
                    chunk=chunk,
                    bm25_score=round(b_score, 6),
                    vector_score=round(v_score, 6),
                    rrf_score=round(rrf, 6),
                    rerank_score=rerank,
                )
            )

        candidates.sort(key=lambda item: item.rerank_score, reverse=True)
        return candidates[:top_k]

    def _extract_best_sentence(self, query: str, text: str) -> str:
        sentences = _split_sentences(text)
        if not sentences:
            return text.strip()
        q_tokens = set(_tokenize(query))
        best_sent = sentences[0]
        best_hits = -1
        for sent in sentences:
            s_tokens = set(_tokenize(sent))
            hits = len(q_tokens & s_tokens)
            if hits > best_hits:
                best_hits = hits
                best_sent = sent
        return best_sent

    def ask(
        self,
        question: str,
        session_id: str | None = None,
        top_k: int = 3,
        use_rerank: bool = True,
    ) -> QAResponse:
        """执行混合检索 + 重排 + 引用溯源回答生成，并持久化到 SQLite 会话历史."""
        if not question.strip():
            raise ValueError("question 不能为空")

        sid = self.session_store.create_session(session_id=session_id, title=question[:40])
        self.session_store.add_message(session_id=sid, role="user", content=question)

        retrieved = self.retrieve(query=question, top_k=top_k, use_rerank=use_rerank)
        relevant = [item for item in retrieved if item.rerank_score >= self.min_relevance_score]

        if not relevant:
            refusal = "抱歉，当前企业知识库中未检索到与您问题直接相关的依据，无法给出确切回答。"
            self.session_store.add_message(session_id=sid, role="assistant", content=refusal, citations=[])
            return QAResponse(
                session_id=sid,
                question=question,
                answer=refusal,
                citations=[],
                retrieved_chunks=retrieved,
                grounded=False,
            )

        citations: list[Citation] = []
        answer_parts: list[str] = []
        for idx, item in enumerate(relevant, start=1):
            best_sent = self._extract_best_sentence(question, item.chunk.content)
            snippet = best_sent if len(best_sent) <= 120 else best_sent[:117] + "..."
            citations.append(
                Citation(
                    index=idx,
                    chunk_id=item.chunk.chunk_id,
                    source=item.chunk.source,
                    chunk_index=item.chunk.chunk_index,
                    snippet=snippet,
                    score=item.rerank_score,
                )
            )
            answer_parts.append(f"{best_sent} [{idx}]")

        answer = "根据企业知识库检索结果：" + " ".join(answer_parts)
        self.session_store.add_message(
            session_id=sid,
            role="assistant",
            content=answer,
            citations=citations,
        )
        return QAResponse(
            session_id=sid,
            question=question,
            answer=answer,
            citations=citations,
            retrieved_chunks=retrieved,
            grounded=True,
        )

    def get_session_history(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        return self.session_store.get_history(session_id=session_id, limit=limit)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.session_store.list_sessions()

    def clear_session(self, session_id: str) -> None:
        self.session_store.clear_session(session_id=session_id)

    def close(self) -> None:
        self.session_store.close()
