"""Day 37 企业级知识库检索与问答核心服务（离线确定性实现，免外部 API Key）。"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    """返回标准 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    """中英文混合分词：提取英文/数字词元，并对中文提取单字与双字词元（bigram）。"""
    lowered = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9_]+", lowered)
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    cjk_tokens: list[str] = []
    for run in cjk_runs:
        for ch in run:
            cjk_tokens.append(ch)
        for i in range(len(run) - 1):
            cjk_tokens.append(run[i : i + 2])
    return ascii_tokens + cjk_tokens


@dataclass(frozen=True)
class Citation:
    """检索引用卡片数据模型。"""

    doc_id: str
    filename: str
    chunk_id: str
    score: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KBDocument:
    """已入库知识文档元信息。"""

    doc_id: str
    filename: str
    chunk_count: int
    char_count: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KBQueryResult:
    """知识库问答结果模型。"""

    query: str
    answer: str
    citations: list[Citation]
    used_history_turns: int


@dataclass
class _ChunkRecord:
    """内部文档分块索引记录。"""

    doc_id: str
    filename: str
    chunk_id: str
    text: str
    tokens: list[str]


class KnowledgeBaseService:
    """企业级知识库切分、混合检索与引用生成服务。"""

    def __init__(self, chunk_size: int = 280, chunk_overlap: int = 40) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._documents: dict[str, KBDocument] = {}
        self._chunks: list[_ChunkRecord] = []

    def _split_text(self, content: str) -> list[str]:
        """按段落与句子边界切分文本，并在超长时按固定窗口滑动重叠切分。"""
        cleaned = content.strip()
        if not cleaned:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", cleaned) if p.strip()]
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            if len(para) <= self.chunk_size:
                if not current:
                    current = para
                elif len(current) + 1 + len(para) <= self.chunk_size:
                    current = f"{current}\n{para}"
                else:
                    chunks.append(current)
                    current = para
            else:
                if current:
                    chunks.append(current)
                    current = ""
                step = self.chunk_size - self.chunk_overlap
                for start in range(0, len(para), step):
                    piece = para[start : start + self.chunk_size].strip()
                    if piece:
                        chunks.append(piece)
                    if start + self.chunk_size >= len(para):
                        break

        if current:
            chunks.append(current)
        return chunks

    def ingest_document(
        self,
        filename: str,
        content: str,
        doc_id: str | None = None,
        created_at: str | None = None,
    ) -> KBDocument:
        """切分并索引一份文档，返回文档元信息。"""
        clean_name = filename.strip()
        clean_content = content.strip()
        if not clean_name:
            raise ValueError("filename 不能为空")
        if not clean_content:
            raise ValueError("content 不能为空")

        resolved_id = doc_id or hashlib.sha1(
            f"{clean_name}:{clean_content}".encode("utf-8")
        ).hexdigest()[:12]

        # 若同 doc_id 已存在，先移除旧分块防止重复索引
        self._chunks = [c for c in self._chunks if c.doc_id != resolved_id]

        pieces = self._split_text(clean_content)
        for idx, piece in enumerate(pieces, start=1):
            chunk_id = f"{resolved_id}-chunk-{idx:02d}"
            self._chunks.append(
                _ChunkRecord(
                    doc_id=resolved_id,
                    filename=clean_name,
                    chunk_id=chunk_id,
                    text=piece,
                    tokens=_tokenize(piece),
                )
            )

        doc = KBDocument(
            doc_id=resolved_id,
            filename=clean_name,
            chunk_count=len(pieces),
            char_count=len(clean_content),
            created_at=created_at or _utc_now_iso(),
        )
        self._documents[resolved_id] = doc
        return doc

    def list_documents(self) -> list[dict[str, Any]]:
        """返回已入库文档列表。"""
        return [doc.to_dict() for doc in self._documents.values()]

    def search(self, query: str, top_k: int = 3) -> list[Citation]:
        """基于 BM25 风格词频加权 + 词元覆盖度检索最相关的知识片段。"""
        clean_query = query.strip()
        if not clean_query or not self._chunks or top_k <= 0:
            return []

        query_tokens = _tokenize(clean_query)
        if not query_tokens:
            return []

        unique_q = set(query_tokens)
        total_docs = len(self._chunks)
        avg_len = sum(len(c.tokens) for c in self._chunks) / max(total_docs, 1)

        # 计算各查询词元的逆文档频率 (IDF)
        df_map: dict[str, int] = {}
        for tok in unique_q:
            df_map[tok] = sum(1 for c in self._chunks if tok in c.tokens)

        scored: list[tuple[float, _ChunkRecord]] = []
        k1 = 1.5
        b = 0.75

        for chunk in self._chunks:
            if not chunk.tokens:
                continue
            tf_map: dict[str, int] = {}
            for tok in chunk.tokens:
                tf_map[tok] = tf_map.get(tok, 0) + 1

            bm25_score = 0.0
            matched = 0
            doc_len = len(chunk.tokens)
            for tok in unique_q:
                tf = tf_map.get(tok, 0)
                if tf == 0:
                    continue
                matched += 1
                df = df_map[tok]
                idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
                denom = tf + k1 * (1.0 - b + b * (doc_len / max(avg_len, 1.0)))
                bm25_score += idf * ((tf * (k1 + 1.0)) / max(denom, 1e-9))

            if matched == 0:
                continue

            coverage = matched / len(unique_q)
            exact_bonus = 0.25 if clean_query.lower() in chunk.text.lower() else 0.0
            final_score = round(min(0.99, (bm25_score * 0.25) + (coverage * 0.65) + exact_bonus), 4)
            scored.append((final_score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        citations: list[Citation] = []
        for score, chunk in scored[:top_k]:
            citations.append(
                Citation(
                    doc_id=chunk.doc_id,
                    filename=chunk.filename,
                    chunk_id=chunk.chunk_id,
                    score=score,
                    snippet=chunk.text,
                )
            )
        return citations

    def answer_question(
        self,
        query: str,
        history: list[dict[str, Any]] | None = None,
        top_k: int = 3,
    ) -> KBQueryResult:
        """结合多轮历史与检索上下文生成带引用标注的企业知识库回答。"""
        history_list = history or []
        user_turns = sum(1 for item in history_list if item.get("role") == "user")
        clean_query = query.strip()

        # 若当前问题较简短（如追问），拼接最近一轮用户提问辅助检索
        retrieval_query = clean_query
        if len(clean_query) <= 16 and history_list:
            last_user = next(
                (m["content"] for m in reversed(history_list) if m.get("role") == "user"),
                "",
            )
            if last_user and last_user != clean_query:
                retrieval_query = f"{last_user} {clean_query}"

        citations = self.search(retrieval_query, top_k=top_k)

        if not self._documents:
            answer = (
                f"【智枢知识库 · 第 {user_turns + 1} 轮】\n"
                "当前企业知识库尚未上传任何文档。请先在左侧「知识库文档上传」面板上传制度文档或技术手册后再提问。"
            )
            return KBQueryResult(
                query=clean_query,
                answer=answer,
                citations=[],
                used_history_turns=user_turns,
            )

        if not citations:
            answer = (
                f"【智枢知识库 · 第 {user_turns + 1} 轮】\n"
                f"未在当前已入库的 {len(self._documents)} 份文档中检索到与「{clean_query}」直接相关的条款。"
                "建议更换关键词或补充上传相关业务文档。"
            )
            return KBQueryResult(
                query=clean_query,
                answer=answer,
                citations=[],
                used_history_turns=user_turns,
            )

        lines = [f"【智枢知识库 · 第 {user_turns + 1} 轮解答】"]
        lines.append(f"针对您的问题「{clean_query}」，基于企业知识库检索结果为您整理如下：")
        for idx, cite in enumerate(citations, start=1):
            summary = cite.snippet.replace("\n", " ").strip()
            if len(summary) > 140:
                summary = summary[:137] + "..."
            lines.append(f"[{idx}] 依据《{cite.filename}》（片段 {cite.chunk_id}）：{summary}")

        if user_turns > 0:
            lines.append(f"（已结合前 {user_turns} 轮对话上下文，点击下方引用卡片可查看原文详情。）")
        else:
            lines.append("（点击下方引用卡片可查看对应文档原文与匹配度详情。）")

        return KBQueryResult(
            query=clean_query,
            answer="\n".join(lines),
            citations=citations,
            used_history_turns=user_turns,
        )
