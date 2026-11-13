"""Day 33: 高级 RAG Part 2 — BM25 + 向量混合检索、RRF 融合、CrossEncoder 重排与父文档检索."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """兼容 LangChain 的文档数据结构."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_content": self.page_content,
            "metadata": self.metadata,
        }


def _tokenize(text: str) -> list[str]:
    """中英文混合分词器：英文/数字词元 + 中文 Unigram 与 Bigram."""
    normalized = text.strip().lower()
    if not normalized:
        return []

    tokens: list[str] = []
    # 英文单词、错误码、编号等（如 err_502, k8s, redis）
    tokens.extend(re.findall(r"[a-z0-9_]+", normalized))
    # 中文字符 Unigram + Bigram
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    tokens.extend(cjk_chars)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


class LocalEmbedding:
    """基于 Python 标准库的确定性本地向量化器（Feature Hashing + L2 归一化）."""

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("embedding 维度 dim 必须大于 0")
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        """将单条文本编码为定长 L2 归一化向量."""
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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量编码文档列表."""
        return [self.embed_query(t) for t in texts]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量的余弦相似度."""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"向量维度不一致: {len(vec_a)} != {len(vec_b)}")
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class BM25Retriever:
    """纯 Python 标准库实现的 Okapi BM25 稀疏关键词检索器."""

    def __init__(
        self,
        documents: list[Document] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 < 0:
            raise ValueError("BM25 参数 k1 不能为负数")
        if not (0.0 <= b <= 1.0):
            raise ValueError("BM25 参数 b 必须在 [0.0, 1.0] 范围内")

        self.k1 = k1
        self.b = b
        self._documents: list[Document] = []
        self._doc_term_freqs: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl: float = 0.0

        if documents:
            self.add_documents(documents)

    def add_documents(self, documents: list[Document]) -> list[str]:
        """向 BM25 索引中增量添加文档."""
        assigned_ids: list[str] = []
        for doc in documents:
            doc_id = doc.id or f"bm25-{len(self._documents)}"
            stored_doc = Document(
                page_content=doc.page_content,
                metadata=dict(doc.metadata),
                id=doc_id,
            )
            tokens = _tokenize(stored_doc.page_content)
            tf = Counter(tokens)

            self._documents.append(stored_doc)
            self._doc_term_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            for term in tf:
                self._df[term] += 1
            assigned_ids.append(doc_id)

        total_len = sum(self._doc_lengths)
        self._avgdl = total_len / len(self._documents) if self._documents else 0.0
        return assigned_ids

    def _idf(self, term: str) -> float:
        """计算 Robertson-Sparck Jones 非负平滑 IDF."""
        n_docs = len(self._documents)
        df = self._df.get(term, 0)
        if n_docs == 0 or df == 0:
            return 0.0
        return math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def score_document(self, query_tokens: list[str], doc_idx: int) -> float:
        """计算单个文档对查询词元的 BM25 得分."""
        if not query_tokens or not self._documents or self._avgdl == 0.0:
            return 0.0

        tf_map = self._doc_term_freqs[doc_idx]
        dl = self._doc_lengths[doc_idx]
        score = 0.0

        for term in query_tokens:
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            idf = self._idf(term)
            denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / self._avgdl))
            score += idf * (tf * (self.k1 + 1.0)) / denom

        return score

    def retrieve_with_scores(
        self, query: str, top_k: int = 5
    ) -> list[tuple[Document, float]]:
        """检索并返回按 BM25 分数降序排列的 (Document, score) 列表."""
        if top_k <= 0 or not self._documents:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[Document, float]] = []
        for idx, doc in enumerate(self._documents):
            score = self.score_document(query_tokens, idx)
            if score > 0.0:
                scored.append((doc, round(score, 6)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        """检索并返回 Top-K 文档列表."""
        return [doc for doc, _ in self.retrieve_with_scores(query, top_k=top_k)]

    def invoke(self, query: str, top_k: int = 5) -> list[Document]:
        """兼容 LangChain Runnable 接口."""
        return self.retrieve(query, top_k=top_k)


class VectorRetriever:
    """基于 LocalEmbedding 的稠密向量检索器（用于混合检索的语义分支）."""

    def __init__(
        self,
        documents: list[Document] | None = None,
        embedding: LocalEmbedding | None = None,
    ) -> None:
        self.embedding = embedding or LocalEmbedding()
        self._documents: list[Document] = []
        self._vectors: list[list[float]] = []

        if documents:
            self.add_documents(documents)

    def add_documents(self, documents: list[Document]) -> list[str]:
        """向量化并存储文档."""
        assigned_ids: list[str] = []
        vectors = self.embedding.embed_documents([d.page_content for d in documents])
        for doc, vec in zip(documents, vectors):
            doc_id = doc.id or f"vec-{len(self._documents)}"
            self._documents.append(
                Document(
                    page_content=doc.page_content,
                    metadata=dict(doc.metadata),
                    id=doc_id,
                )
            )
            self._vectors.append(vec)
            assigned_ids.append(doc_id)
        return assigned_ids

    def retrieve_with_scores(
        self, query: str, top_k: int = 5
    ) -> list[tuple[Document, float]]:
        """按余弦相似度降序返回 Top-K 文档与分数."""
        if top_k <= 0 or not self._documents:
            return []
        q_vec = self.embedding.embed_query(query)
        scored = [
            (doc, round(_cosine_similarity(q_vec, vec), 6))
            for doc, vec in zip(self._documents, self._vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        """检索并返回 Top-K 文档列表."""
        return [doc for doc, _ in self.retrieve_with_scores(query, top_k=top_k)]


def reciprocal_rank_fusion(
    ranked_lists: list[list[Document] | list[tuple[Document, float]]],
    k: int = 60,
    top_k: int | None = None,
) -> list[tuple[Document, float]]:
    """倒数排名融合算法（Reciprocal Rank Fusion, RRF）.

    公式: RRF(d) = sum_{r in ranked_lists} 1 / (k + rank_r(d))
    支持传入 Document 列表或 (Document, score) 列表，按文档 ID（若无 ID 则按文本内容）去重融合。
    """
    if k <= 0:
        raise ValueError("RRF 平滑常数 k 必须大于 0")

    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            doc = item[0] if isinstance(item, tuple) else item
            key = doc.id if doc.id is not None else doc.page_content
            if key not in doc_map:
                doc_map[key] = doc
                scores[key] = 0.0
            scores[key] += 1.0 / (k + rank)

    fused = [
        (doc_map[key], round(score, 6))
        for key, score in scores.items()
    ]
    fused.sort(key=lambda item: item[1], reverse=True)
    if top_k is not None:
        return fused[:top_k]
    return fused


class CrossEncoderReranker:
    """模拟 Cross-Encoder 精排器：联合建模 Query-Doc 词法覆盖度、语义相似度与短语精确匹配."""

    def __init__(
        self,
        embedding: LocalEmbedding | None = None,
        lexical_weight: float = 0.55,
        semantic_weight: float = 0.45,
        phrase_bonus: float = 0.25,
    ) -> None:
        self.embedding = embedding or LocalEmbedding()
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.phrase_bonus = phrase_bonus

    def score(self, query: str, document: Document) -> float:
        """计算单个 (Query, Document) 对的 Cross-Encoder 精排相关性得分."""
        q_norm = query.strip().lower()
        d_norm = document.page_content.strip().lower()
        if not q_norm or not d_norm:
            return 0.0

        q_tokens = _tokenize(q_norm)
        d_tokens = _tokenize(d_norm)
        if not q_tokens or not d_tokens:
            return 0.0

        q_set = set(q_tokens)
        d_set = set(d_tokens)
        # 词法覆盖率：查询词元在文档中命中的比例 + 词频密度微调
        overlap = len(q_set & d_set) / len(q_set)

        # 语义余弦相似度（裁剪到 [0, 1]）
        q_vec = self.embedding.embed_query(q_norm)
        d_vec = self.embedding.embed_query(d_norm)
        semantic = max(0.0, _cosine_similarity(q_vec, d_vec))

        # 精确短语加分（模拟 Cross-Encoder 注意力对连续匹配的强感知）
        bonus = self.phrase_bonus if q_norm in d_norm else 0.0

        total = (
            self.lexical_weight * overlap
            + self.semantic_weight * semantic
            + bonus
        )
        return round(total, 6)

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int | None = None,
    ) -> list[tuple[Document, float]]:
        """对候选文档列表执行精排，返回按精排分数降序排列的 (Document, score) 列表."""
        if not documents:
            return []
        if top_k is not None and top_k <= 0:
            return []

        scored = [(doc, self.score(query, doc)) for doc in documents]
        scored.sort(key=lambda item: item[1], reverse=True)
        if top_k is not None:
            return scored[:top_k]
        return scored


class ParentDocumentRetriever:
    """父文档检索器（Small-to-Big）：检索细粒度子切片，返回完整父文档上下文."""

    def __init__(
        self,
        chunk_size: int = 120,
        chunk_overlap: int = 20,
        rrf_k: int = 60,
        embedding: LocalEmbedding | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.rrf_k = rrf_k
        self.embedding = embedding or LocalEmbedding()

        self._parents: dict[str, Document] = {}
        self._bm25 = BM25Retriever()
        self._vector = VectorRetriever(embedding=self.embedding)

    def _split_text(self, text: str) -> list[str]:
        """将长文档切分为固定窗口大小的滑动子切片."""
        stripped = text.strip()
        if not stripped:
            return []
        if len(stripped) <= self.chunk_size:
            return [stripped]

        chunks: list[str] = []
        step = self.chunk_size - self.chunk_overlap
        start = 0
        while start < len(stripped):
            end = min(start + self.chunk_size, len(stripped))
            chunks.append(stripped[start:end])
            if end == len(stripped):
                break
            start += step
        return chunks

    def add_documents(self, parent_documents: list[Document]) -> int:
        """写入父文档并自动切分索引子切片，返回生成的子切片总数."""
        child_docs: list[Document] = []
        for idx, parent in enumerate(parent_documents):
            parent_id = parent.id or f"parent-{len(self._parents) + idx}"
            stored_parent = Document(
                page_content=parent.page_content,
                metadata=dict(parent.metadata),
                id=parent_id,
            )
            self._parents[parent_id] = stored_parent

            chunks = self._split_text(stored_parent.page_content)
            for c_idx, chunk_text in enumerate(chunks):
                child_meta = dict(stored_parent.metadata)
                child_meta["parent_id"] = parent_id
                child_meta["chunk_index"] = c_idx
                child_docs.append(
                    Document(
                        page_content=chunk_text,
                        metadata=child_meta,
                        id=f"{parent_id}::chunk-{c_idx}",
                    )
                )

        if child_docs:
            self._bm25.add_documents(child_docs)
            self._vector.add_documents(child_docs)
        return len(child_docs)

    def retrieve_with_matched_children(
        self,
        query: str,
        top_k: int = 3,
        child_k: int = 6,
    ) -> list[tuple[Document, Document, float]]:
        """检索子切片并映射回父文档，返回 (parent_doc, matched_child_doc, rrf_score)."""
        if top_k <= 0 or not self._parents:
            return []

        bm25_hits = self._bm25.retrieve(query, top_k=child_k)
        vec_hits = self._vector.retrieve(query, top_k=child_k)
        fused_children = reciprocal_rank_fusion([bm25_hits, vec_hits], k=self.rrf_k)

        results: list[tuple[Document, Document, float]] = []
        seen_parents: set[str] = set()
        for child_doc, rrf_score in fused_children:
            parent_id = child_doc.metadata.get("parent_id")
            if not parent_id or parent_id in seen_parents:
                continue
            parent_doc = self._parents.get(parent_id)
            if parent_doc is None:
                continue
            seen_parents.add(parent_id)
            results.append((parent_doc, child_doc, rrf_score))
            if len(results) >= top_k:
                break
        return results

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        child_k: int = 6,
    ) -> list[Document]:
        """检索子切片并返回去重后的 Top-K 父文档."""
        return [
            parent
            for parent, _, _ in self.retrieve_with_matched_children(
                query, top_k=top_k, child_k=child_k
            )
        ]
