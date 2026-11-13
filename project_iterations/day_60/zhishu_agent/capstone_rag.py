"""Day 60 (v1.0.0-day60): 毕业设计核心混合检索 + 重排 + 行内引用与低置信度拒答主链路."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class KnowledgeChunk:
    """企业知识库切片数据结构."""

    chunk_id: str
    doc_id: str
    title: str
    content: str
    source: str
    section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "section": self.section,
            "metadata": self.metadata,
        }


@dataclass
class RetrievedChunk:
    """多路召回与重排后的候选切片及各阶段得分."""

    chunk: KnowledgeChunk
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    bm25_rank: int | None = None
    vector_rank: int | None = None


@dataclass
class Citation:
    """可溯源引用条目，与回答中的 [1], [2] 一一对应."""

    citation_id: int
    chunk_id: str
    doc_id: str
    title: str
    source: str
    section: str
    snippet: str
    relevance_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "source": self.source,
            "section": self.section,
            "snippet": self.snippet,
            "relevance_score": round(self.relevance_score, 4),
        }


@dataclass
class RAGResponse:
    """Capstone RAG 端到端问答输出结构."""

    query: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None
    confidence: float = 0.0
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "confidence": round(self.confidence, 4),
            "trace": self.trace,
        }


_ZH_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "和",
        "是",
        "在",
        "有",
        "与",
        "及",
        "或",
        "吗",
        "呢",
        "啊",
        "吧",
        "请",
        "问",
        "请问",
        "如何",
        "怎么",
        "什么",
        "哪些",
        "为什么",
        "可以",
        "是否",
        "一个",
        "我们",
        "公司",
    }
)


def tokenize_mixed(text: str, remove_stopwords: bool = False) -> list[str]:
    """中英文混合分词：保留英文/数字/下划线词元，以及中文 Unigram + Bigram."""
    normalized = text.strip().lower()
    if not normalized:
        return []

    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9_]+", normalized))

    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    if remove_stopwords:
        filtered_cjk = [ch for ch in cjk_chars if ch not in _ZH_STOPWORDS]
    else:
        filtered_cjk = cjk_chars

    tokens.extend(filtered_cjk)
    for i in range(len(cjk_chars) - 1):
        bigram = cjk_chars[i] + cjk_chars[i + 1]
        if remove_stopwords and bigram in _ZH_STOPWORDS:
            continue
        tokens.append(bigram)
    return tokens


class DeterministicEmbedder:
    """基于 Feature Hashing + L2 归一化的确定性本地向量化器（无需外部模型下载）."""

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("向量维度 dim 必须大于 0")
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = tokenize_mixed(text)
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            weight = 1.6 if len(token) >= 2 else 1.0
            vec[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [round(v / norm, 8) for v in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if len(vec_a) != len(vec_b):
            raise ValueError(f"向量维度不一致: {len(vec_a)} != {len(vec_b)}")
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


class BM25Index:
    """Okapi BM25 稀疏关键词检索器."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 < 0:
            raise ValueError("BM25 参数 k1 不能为负数")
        if not (0.0 <= b <= 1.0):
            raise ValueError("BM25 参数 b 必须在 [0.0, 1.0] 范围内")
        self.k1 = k1
        self.b = b
        self._chunks: list[KnowledgeChunk] = []
        self._doc_tfs: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl: float = 0.0

    def add_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        for chunk in chunks:
            full_text = f"{chunk.title} {chunk.section} {chunk.content}"
            tokens = tokenize_mixed(full_text)
            tf = Counter(tokens)
            self._chunks.append(chunk)
            self._doc_tfs.append(tf)
            self._doc_lengths.append(len(tokens))
            for term in tf:
                self._df[term] += 1

        total_docs = len(self._chunks)
        self._avgdl = sum(self._doc_lengths) / total_docs if total_docs > 0 else 0.0
        return len(chunks)

    def search(self, query: str, top_k: int = 8) -> list[tuple[KnowledgeChunk, float]]:
        if not self._chunks or top_k <= 0:
            return []
        query_tokens = tokenize_mixed(query, remove_stopwords=True)
        if not query_tokens:
            query_tokens = tokenize_mixed(query)
        if not query_tokens:
            return []

        n_docs = len(self._chunks)
        scored: list[tuple[KnowledgeChunk, float]] = []
        avgdl = self._avgdl if self._avgdl > 0 else 1.0

        for idx, chunk in enumerate(self._chunks):
            tf_map = self._doc_tfs[idx]
            dl = self._doc_lengths[idx]
            score = 0.0
            for term in query_tokens:
                tf = tf_map.get(term, 0)
                if tf == 0:
                    continue
                df = self._df.get(term, 0)
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / avgdl))
                score += idf * ((tf * (self.k1 + 1.0)) / denom)
            if score > 0.0:
                scored.append((chunk, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


class VectorIndex:
    """稠密向量语义检索器（内存余弦相似度索引）."""

    def __init__(self, embedder: DeterministicEmbedder | None = None) -> None:
        self.embedder = embedder or DeterministicEmbedder()
        self._chunks: list[KnowledgeChunk] = []
        self._vectors: list[list[float]] = []

    def add_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        texts = [f"{c.title} {c.section} {c.content}" for c in chunks]
        vectors = self.embedder.embed_documents(texts)
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)
        return len(chunks)

    def search(self, query: str, top_k: int = 8) -> list[tuple[KnowledgeChunk, float]]:
        if not self._chunks or top_k <= 0:
            return []
        q_vec = self.embedder.embed_query(query)
        scored: list[tuple[KnowledgeChunk, float]] = []
        for chunk, vec in zip(self._chunks, self._vectors):
            sim = self.embedder.cosine_similarity(q_vec, vec)
            if sim > 0.0:
                scored.append((chunk, sim))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


def reciprocal_rank_fusion(
    bm25_results: list[tuple[KnowledgeChunk, float]],
    vector_results: list[tuple[KnowledgeChunk, float]],
    k: int = 60,
    bm25_weight: float = 1.0,
    vector_weight: float = 1.0,
    top_k: int = 6,
) -> list[RetrievedChunk]:
    """倒数排序融合（Reciprocal Rank Fusion）：将 BM25 与向量两路排名融合为统一候选集."""
    if k <= 0:
        raise ValueError("RRF 平滑常数 k 必须大于 0")

    merged: dict[str, RetrievedChunk] = {}

    for rank, (chunk, score) in enumerate(bm25_results, start=1):
        entry = merged.setdefault(chunk.chunk_id, RetrievedChunk(chunk=chunk))
        entry.bm25_score = score
        entry.bm25_rank = rank
        entry.rrf_score += bm25_weight / (k + rank)

    for rank, (chunk, score) in enumerate(vector_results, start=1):
        entry = merged.setdefault(chunk.chunk_id, RetrievedChunk(chunk=chunk))
        entry.vector_score = score
        entry.vector_rank = rank
        entry.rrf_score += vector_weight / (k + rank)

    ranked = sorted(merged.values(), key=lambda item: item.rrf_score, reverse=True)
    return ranked[:top_k]


class CrossReranker:
    """精排器：结合查询词元覆盖率、标题命中、双字词匹配与 RRF 先验计算 [0, 1] 置信度."""

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 4,
    ) -> list[RetrievedChunk]:
        if not candidates or top_k <= 0:
            return []

        q_tokens = tokenize_mixed(query, remove_stopwords=True)
        if not q_tokens:
            q_tokens = tokenize_mixed(query)
        q_unique = set(q_tokens)
        q_bigrams = {t for t in q_unique if len(t) >= 2}
        max_rrf = max((c.rrf_score for c in candidates), default=1.0) or 1.0

        for item in candidates:
            title_tokens = set(tokenize_mixed(f"{item.chunk.title} {item.chunk.section}"))
            body_tokens = set(tokenize_mixed(item.chunk.content))
            all_doc_tokens = title_tokens | body_tokens

            if not q_unique:
                item.rerank_score = 0.0
                continue

            # 1. 查询词元覆盖率（核心语义对齐）
            overlap = q_unique & all_doc_tokens
            coverage = len(overlap) / len(q_unique)

            # 2. 多字词 / 英文专业术语精确命中率
            if q_bigrams:
                bigram_hits = len(q_bigrams & all_doc_tokens) / len(q_bigrams)
            else:
                bigram_hits = coverage

            # 3. 标题/章节命中加分
            title_hits = len(q_unique & title_tokens) / len(q_unique)

            # 4. 归一化 RRF 先验
            rrf_norm = item.rrf_score / max_rrf

            # 若没有任何多字词或关键单字命中，抑制虚高得分
            if len(overlap) == 0:
                score = 0.0
            else:
                score = (
                    0.42 * bigram_hits
                    + 0.28 * coverage
                    + 0.15 * title_hits
                    + 0.15 * rrf_norm
                )
            item.rerank_score = round(min(1.0, max(0.0, score)), 4)

        reranked = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)
        return reranked[:top_k]


class GroundedAnswerGenerator:
    """基于检索证据的受控生成与行内引用生成器（含低置信度拒答机制）."""

    DEFAULT_REFUSAL_MESSAGE = (
        "抱歉，当前企业知识库中未检索到足够高置信度的依据来回答该问题。"
        "为防止模型产生幻觉，系统已触发低置信度拒答策略，建议补充更精确的业务关键词或转人工处理。"
    )

    def __init__(self, min_confidence: float = 0.22, max_citations: int = 3) -> None:
        if not (0.0 <= min_confidence <= 1.0):
            raise ValueError("min_confidence 必须在 [0.0, 1.0] 范围内")
        self.min_confidence = min_confidence
        self.max_citations = max_citations

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[。！？.!?\n])\s*", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _extract_best_snippet(self, query: str, content: str) -> str:
        sentences = self._split_sentences(content)
        if not sentences:
            return content.strip()[:160]
        q_tokens = set(tokenize_mixed(query, remove_stopwords=True))
        if not q_tokens:
            return sentences[0][:160]

        best_sent = sentences[0]
        best_hits = -1
        for sent in sentences:
            s_tokens = set(tokenize_mixed(sent))
            hits = len(q_tokens & s_tokens)
            if hits > best_hits:
                best_hits = hits
                best_sent = sent
        return best_sent[:180]

    def generate(
        self,
        query: str,
        reranked_chunks: list[RetrievedChunk],
        min_confidence: float | None = None,
    ) -> RAGResponse:
        threshold = self.min_confidence if min_confidence is None else min_confidence

        if not reranked_chunks:
            return RAGResponse(
                query=query,
                answer=self.DEFAULT_REFUSAL_MESSAGE,
                citations=[],
                refused=True,
                refusal_reason="知识库未召回任何候选切片",
                confidence=0.0,
                retrieved_chunks=[],
            )

        top_score = reranked_chunks[0].rerank_score
        if top_score < threshold:
            return RAGResponse(
                query=query,
                answer=self.DEFAULT_REFUSAL_MESSAGE,
                citations=[],
                refused=True,
                refusal_reason=(
                    f"最高重排置信度 {top_score:.4f} 低于阈值 {threshold:.4f}，触发防幻觉拒答"
                ),
                confidence=top_score,
                retrieved_chunks=reranked_chunks,
            )

        # 筛选达到次级门槛的证据用于引用合成
        secondary_floor = max(threshold * 0.75, 0.12)
        selected = [
            item for item in reranked_chunks if item.rerank_score >= secondary_floor
        ][: self.max_citations]
        if not selected:
            selected = [reranked_chunks[0]]

        citations: list[Citation] = []
        claim_lines: list[str] = []
        for idx, item in enumerate(selected, start=1):
            snippet = self._extract_best_snippet(query, item.chunk.content)
            citation = Citation(
                citation_id=idx,
                chunk_id=item.chunk.chunk_id,
                doc_id=item.chunk.doc_id,
                title=item.chunk.title,
                source=item.chunk.source,
                section=item.chunk.section,
                snippet=snippet,
                relevance_score=item.rerank_score,
            )
            citations.append(citation)
            claim_lines.append(f"{snippet} [{idx}]")

        answer_body = " ".join(claim_lines)
        refs_footer = "；".join(
            f"[{c.citation_id}] {c.title}（{c.source}）" for c in citations
        )
        full_answer = f"{answer_body}\n\n参考来源：{refs_footer}"

        return RAGResponse(
            query=query,
            answer=full_answer,
            citations=citations,
            refused=False,
            refusal_reason=None,
            confidence=top_score,
            retrieved_chunks=reranked_chunks,
        )


class CapstoneRAGEngine:
    """毕业设计核心混合检索 + 重排 + 可溯源引用 RAG 引擎."""

    def __init__(
        self,
        embedding_dim: int = 256,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
        min_confidence: float = 0.22,
        max_citations: int = 3,
    ) -> None:
        self.embedder = DeterministicEmbedder(dim=embedding_dim)
        self.bm25_index = BM25Index()
        self.vector_index = VectorIndex(embedder=self.embedder)
        self.reranker = CrossReranker()
        self.generator = GroundedAnswerGenerator(
            min_confidence=min_confidence,
            max_citations=max_citations,
        )
        self.rrf_k = rrf_k
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self._chunk_count = 0

    def index_documents(self, chunks: list[KnowledgeChunk]) -> int:
        """将知识切片同步写入 BM25 稀疏索引与向量稠密索引."""
        if not chunks:
            return 0
        self.bm25_index.add_chunks(chunks)
        self.vector_index.add_chunks(chunks)
        self._chunk_count += len(chunks)
        return len(chunks)

    def retrieve(
        self,
        query: str,
        bm25_top_k: int = 8,
        vector_top_k: int = 8,
        rrf_top_k: int = 6,
        rerank_top_k: int = 4,
    ) -> tuple[list[RetrievedChunk], dict[str, Any]]:
        """执行 BM25 + Vector 双路召回 -> RRF 融合 -> CrossReranker 精排."""
        bm25_hits = self.bm25_index.search(query, top_k=bm25_top_k)
        vector_hits = self.vector_index.search(query, top_k=vector_top_k)
        rrf_candidates = reciprocal_rank_fusion(
            bm25_results=bm25_hits,
            vector_results=vector_hits,
            k=self.rrf_k,
            bm25_weight=self.bm25_weight,
            vector_weight=self.vector_weight,
            top_k=rrf_top_k,
        )
        reranked = self.reranker.rerank(query, rrf_candidates, top_k=rerank_top_k)
        trace = {
            "bm25_hits": len(bm25_hits),
            "vector_hits": len(vector_hits),
            "rrf_candidates": len(rrf_candidates),
            "reranked_count": len(reranked),
            "top_rerank_score": reranked[0].rerank_score if reranked else 0.0,
        }
        return reranked, trace

    def query(
        self,
        question: str,
        top_k: int = 4,
        min_confidence: float | None = None,
    ) -> RAGResponse:
        """端到端混合 RAG 问答入口：检索、重排、生成带 [1][2] 引用的答案或拒答."""
        cleaned = question.strip()
        if not cleaned:
            return RAGResponse(
                query=question,
                answer=self.generator.DEFAULT_REFUSAL_MESSAGE,
                citations=[],
                refused=True,
                refusal_reason="查询问题为空",
                confidence=0.0,
                trace={"bm25_hits": 0, "vector_hits": 0, "rrf_candidates": 0},
            )

        reranked, trace = self.retrieve(cleaned, rerank_top_k=top_k)
        response = self.generator.generate(
            query=cleaned,
            reranked_chunks=reranked,
            min_confidence=min_confidence,
        )
        response.trace = trace
        return response

    def stats(self) -> dict[str, Any]:
        return {
            "indexed_chunks": self._chunk_count,
            "embedding_dim": self.embedder.dim,
            "rrf_k": self.rrf_k,
            "min_confidence": self.generator.min_confidence,
            "max_citations": self.generator.max_citations,
        }
