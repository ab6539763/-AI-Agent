"""Day 31 核心模块：RAG 切分与检索超参数网格实验台 (v0.3.0-day31).

提供：
1. TuningConfig(chunk_size, chunk_overlap, top_k)：RAG 超参数配置与合法性校验。
2. chunk_text(...)：支持自然边界与重叠窗口的确定性文本切分器。
3. LocalEmbedding：基于 SHA-256 特征哈希与 L2 归一化的确定性中英文向量化器。
4. run_grid_experiment(corpus, eval_qa_pairs, configs)：网格遍历超参组合，计算 Hit Rate@K 与 MRR 并选出最优配置。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import re
from typing import Any, Mapping, Sequence


_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class TuningConfig:
    """RAG 切分与检索超参数配置."""

    chunk_size: int
    chunk_overlap: int
    top_k: int

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size 必须大于 0，当前值: {self.chunk_size}")
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap 不能为负数，当前值: {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) 必须严格小于 chunk_size ({self.chunk_size})"
            )
        if self.top_k <= 0:
            raise ValueError(f"top_k 必须大于 0，当前值: {self.top_k}")

    @property
    def label(self) -> str:
        return f"chunk={self.chunk_size}, overlap={self.chunk_overlap}, top_k={self.top_k}"

    def to_dict(self) -> dict[str, int]:
        return {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class Chunk:
    """切分后的文档切片."""

    chunk_id: str
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalQAPair:
    """RAG 检索评测集单条样本."""

    query: str
    expected_answer: str | None = None
    expected_keywords: tuple[str, ...] = ()
    relevant_doc_ids: tuple[str, ...] = ()

    @classmethod
    def from_obj(cls, item: EvalQAPair | Mapping[str, Any]) -> EvalQAPair:
        if isinstance(item, EvalQAPair):
            return item
        query = str(item.get("query", "")).strip()
        if not query:
            raise ValueError("eval_qa_pairs 中的样本缺少非空 query 字段")
        expected_answer = item.get("expected_answer")
        if expected_answer is not None:
            expected_answer = str(expected_answer)
        raw_kws = item.get("expected_keywords") or ()
        expected_keywords = tuple(str(k) for k in raw_kws)
        raw_ids = item.get("relevant_doc_ids") or ()
        if not raw_ids and item.get("expected_doc_id"):
            raw_ids = (str(item["expected_doc_id"]),)
        relevant_doc_ids = tuple(str(d) for d in raw_ids)
        if not expected_answer and not expected_keywords and not relevant_doc_ids:
            raise ValueError(
                f"评测样本 '{query}' 必须至少指定 expected_answer、expected_keywords 或 relevant_doc_ids 之一"
            )
        return cls(
            query=query,
            expected_answer=expected_answer,
            expected_keywords=expected_keywords,
            relevant_doc_ids=relevant_doc_ids,
        )


@dataclass
class ExperimentResult:
    """单组超参数配置的评测结果."""

    config: TuningConfig
    hit_rate: float
    mrr: float
    num_chunks: int
    total_queries: int
    hits: int
    per_query_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "hit_rate": round(self.hit_rate, 4),
            "mrr": round(self.mrr, 4),
            "num_chunks": self.num_chunks,
            "total_queries": self.total_queries,
            "hits": self.hits,
        }


@dataclass
class GridExperimentReport:
    """网格搜索实验总报告."""

    results: list[ExperimentResult]
    best_result: ExperimentResult

    @property
    def best_config(self) -> TuningConfig:
        return self.best_result.config

    def summary_table(self) -> str:
        header = (
            f"{'Rank':<5} | {'chunk_size':<10} | {'overlap':<8} | {'top_k':<6} | "
            f"{'Chunks':<7} | {'Hit Rate@K':<11} | {'MRR':<8}"
        )
        sep = "-" * len(header)
        lines = [header, sep]
        for idx, res in enumerate(self.results, start=1):
            c = res.config
            lines.append(
                f"{idx:<5} | {c.chunk_size:<10} | {c.chunk_overlap:<8} | {c.top_k:<6} | "
                f"{res.num_chunks:<7} | {res.hit_rate:<11.4f} | {res.mrr:<8.4f}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_config": self.best_config.to_dict(),
            "best_hit_rate": round(self.best_result.hit_rate, 4),
            "best_mrr": round(self.best_result.mrr, 4),
            "results": [r.to_dict() for r in self.results],
        }


class LocalEmbedding:
    """零外部依赖的确定性中英文特征哈希向量化器."""

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("dim 必须大于 0")
        self.dim = dim

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        raw_tokens = _TOKEN_PATTERN.findall(text.lower())
        if not raw_tokens:
            return []
        tokens: list[str] = list(raw_tokens)
        # 为中文与相邻词元补充 Bigram，提升短语匹配精度
        for i in range(len(raw_tokens) - 1):
            if len(raw_tokens[i]) == 1 and len(raw_tokens[i + 1]) == 1:
                tokens.append(raw_tokens[i] + raw_tokens[i + 1])
        return tokens

    def embed_text(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        vec = [0.0] * self.dim
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return [0.0] * self.dim
        return [v / norm for v in vec]


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(vec_a, vec_b))


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """按滑动窗口切分文本，保证每个切片长度 <= chunk_size 且相邻切片保留重叠."""
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")

    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    text_len = len(cleaned)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= text_len:
            break
        start += step

    return chunks


def _normalize_corpus(corpus: Sequence[str | Mapping[str, Any] | Any]) -> list[tuple[str, str, dict[str, Any]]]:
    normalized: list[tuple[str, str, dict[str, Any]]] = []
    for idx, item in enumerate(corpus):
        if isinstance(item, str):
            normalized.append((f"doc-{idx}", item, {}))
        elif isinstance(item, Mapping):
            doc_id = str(item.get("id") or item.get("doc_id") or f"doc-{idx}")
            content = str(item.get("page_content") or item.get("content") or item.get("text") or "")
            metadata = dict(item.get("metadata") or {})
            normalized.append((doc_id, content, metadata))
        elif hasattr(item, "page_content"):
            doc_id = str(getattr(item, "id", None) or f"doc-{idx}")
            content = str(getattr(item, "page_content"))
            metadata = dict(getattr(item, "metadata", {}) or {})
            normalized.append((doc_id, content, metadata))
        else:
            raise TypeError(f"不支持的语料元素类型: {type(item)!r}")
    return normalized


def _is_chunk_relevant(chunk: Chunk, qa: EvalQAPair) -> bool:
    if qa.relevant_doc_ids and chunk.doc_id not in qa.relevant_doc_ids:
        return False

    lowered = chunk.text.lower()
    if qa.expected_answer is not None:
        if qa.expected_answer.lower() not in lowered:
            return False
    if qa.expected_keywords:
        if not all(kw.lower() in lowered for kw in qa.expected_keywords):
            return False
    return True


def run_grid_experiment(
    corpus: Sequence[str | Mapping[str, Any] | Any],
    eval_qa_pairs: Sequence[EvalQAPair | Mapping[str, Any]],
    configs: Sequence[TuningConfig],
    embedding_dim: int = 128,
) -> GridExperimentReport:
    """遍历 TuningConfig 网格，计算 Hit Rate@K 与 MRR 并选出最优超参组合."""
    if not corpus:
        raise ValueError("corpus 不能为空")
    if not eval_qa_pairs:
        raise ValueError("eval_qa_pairs 不能为空")
    if not configs:
        raise ValueError("configs 不能为空")

    norm_corpus = _normalize_corpus(corpus)
    qa_list = [EvalQAPair.from_obj(item) for item in eval_qa_pairs]
    embedder = LocalEmbedding(dim=embedding_dim)
    query_vectors = [embedder.embed_text(qa.query) for qa in qa_list]

    results: list[ExperimentResult] = []

    for cfg in configs:
        chunks: list[Chunk] = []
        for doc_id, content, metadata in norm_corpus:
            pieces = chunk_text(content, cfg.chunk_size, cfg.chunk_overlap)
            for c_idx, piece in enumerate(pieces):
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}#c{c_idx}",
                        doc_id=doc_id,
                        text=piece,
                        metadata=metadata,
                    )
                )

        chunk_vectors = [embedder.embed_text(c.text) for c in chunks]

        hits = 0
        rr_sum = 0.0
        details: list[dict[str, Any]] = []

        for qa, q_vec in zip(qa_list, query_vectors):
            scored = [
                (_cosine_similarity(q_vec, c_vec), chunk)
                for chunk, c_vec in zip(chunks, chunk_vectors)
            ]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            top_k_chunks = [chunk for _, chunk in scored[: cfg.top_k]]

            first_rank: int | None = None
            for rank, chunk in enumerate(top_k_chunks, start=1):
                if _is_chunk_relevant(chunk, qa):
                    first_rank = rank
                    break

            if first_rank is not None:
                hits += 1
                rr = 1.0 / first_rank
            else:
                rr = 0.0
            rr_sum += rr

            details.append(
                {
                    "query": qa.query,
                    "hit": first_rank is not None,
                    "first_relevant_rank": first_rank,
                    "reciprocal_rank": rr,
                }
            )

        total_q = len(qa_list)
        results.append(
            ExperimentResult(
                config=cfg,
                hit_rate=hits / total_q,
                mrr=rr_sum / total_q,
                num_chunks=len(chunks),
                total_queries=total_q,
                hits=hits,
                per_query_details=details,
            )
        )

    # 排序规则：优先 MRR 降序，其次 Hit Rate@K 降序，再次 top_k 升序（更少上下文成本）
    sorted_results = sorted(
        results,
        key=lambda r: (-r.mrr, -r.hit_rate, r.config.top_k, r.config.chunk_size),
    )

    return GridExperimentReport(
        results=sorted_results,
        best_result=sorted_results[0],
    )
