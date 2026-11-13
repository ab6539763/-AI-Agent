"""智枢平台 Day 32 核心模块：高级 RAG 检索增强（Query Rewriting、Multi-Query、HyDE、Context Compression）."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Document:
    """标准文档对象，兼容 LangChain Document 协议。"""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha256(self.page_content.encode("utf-8")).hexdigest()[:12]


def _tokenize(text: str) -> list[str]:
    """中英文混合分词：英文按词切分，中文生成 Unigram + Bigram。"""
    text = text.lower().strip()
    if not text:
        return []
    tokens: list[str] = []
    # 英文/数字词元
    tokens.extend(re.findall(r"[a-z0-9_]+", text))
    # 中文字符序列 -> Unigram + Bigram
    for seq in re.findall(r"[\u4e00-\u9fff]+", text):
        chars = list(seq)
        tokens.extend(chars)
        for i in range(len(chars) - 1):
            tokens.append(chars[i] + chars[i + 1])
    return tokens


class LocalEmbedding:
    """零外部依赖的确定性本地向量化器（Feature Hashing + L2 归一化）。"""

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("向量维度 dim 必须大于 0")
        self.dim = dim

    def embed_query(self, text: str) -> list[float]:
        tokens = _tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        vec = [0.0] * self.dim
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] % 2 == 0) else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return [0.0] * self.dim
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b):
        raise ValueError(f"向量维度不匹配: {len(vec_a)} != {len(vec_b)}")
    return sum(a * b for a, b in zip(vec_a, vec_b))


class LocalVectorStore:
    """轻量级本地向量库，支持按文本或向量检索及元数据预过滤。"""

    def __init__(
        self,
        collection_name: str = "zhishu_kb",
        embedding_function: LocalEmbedding | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_function = embedding_function or LocalEmbedding()
        self._records: dict[str, tuple[Document, list[float]]] = {}

    def add_documents(self, documents: list[Document]) -> list[str]:
        if not documents:
            return []
        vectors = self.embedding_function.embed_documents([d.page_content for d in documents])
        ids: list[str] = []
        for doc, vec in zip(documents, vectors):
            self._records[doc.id] = (doc, vec)
            ids.append(doc.id)
        return ids

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        docs: list[Document] = []
        for i, text in enumerate(texts):
            meta = metadatas[i] if metadatas and i < len(metadatas) else {}
            doc_id = ids[i] if ids and i < len(ids) else ""
            docs.append(Document(page_content=text, metadata=meta, id=doc_id))
        return self.add_documents(docs)

    def count(self) -> int:
        return len(self._records)

    @staticmethod
    def _match_metadata(metadata: dict[str, Any], filter_metadata: dict[str, Any] | None) -> bool:
        if not filter_metadata:
            return True
        for key, expected in filter_metadata.items():
            actual = metadata.get(key)
            if isinstance(expected, dict):
                for op, val in expected.items():
                    if op == "$eq" and actual != val:
                        return False
                    if op == "$ne" and actual == val:
                        return False
                    if op == "$in" and actual not in val:
                        return False
                    if op == "$gte" and (actual is None or actual < val):
                        return False
                    if op == "$lte" and (actual is None or actual > val):
                        return False
            elif actual != expected:
                return False
        return True

    def similarity_search_with_score_by_vector(
        self,
        embedding: list[float],
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        if k <= 0:
            return []
        scored: list[tuple[Document, float]] = []
        for doc, vec in self._records.values():
            if not self._match_metadata(doc.metadata, filter_metadata):
                continue
            score = _cosine_similarity(embedding, vec)
            scored.append((doc, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def similarity_search_by_vector(
        self,
        embedding: list[float],
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        return [
            doc
            for doc, _ in self.similarity_search_with_score_by_vector(
                embedding, k=k, filter_metadata=filter_metadata
            )
        ]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        q_vec = self.embedding_function.embed_query(query)
        return self.similarity_search_with_score_by_vector(q_vec, k=k, filter_metadata=filter_metadata)

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        return [
            doc
            for doc, _ in self.similarity_search_with_score(
                query, k=k, filter_metadata=filter_metadata
            )
        ]

    def as_retriever(self, search_kwargs: dict[str, Any] | None = None) -> VectorStoreRetriever:
        return VectorStoreRetriever(vector_store=self, search_kwargs=search_kwargs or {"k": 3})


class VectorStoreRetriever:
    """标准检索器封装，提供 invoke / get_relevant_documents 接口。"""

    def __init__(self, vector_store: LocalVectorStore, search_kwargs: dict[str, Any] | None = None) -> None:
        self.vector_store = vector_store
        self.search_kwargs = search_kwargs or {"k": 3}

    def get_relevant_documents(self, query: str, **kwargs: Any) -> list[Document]:
        params = {**self.search_kwargs, **kwargs}
        k = int(params.get("k", 3))
        filter_metadata = params.get("filter_metadata")
        return self.vector_store.similarity_search(query, k=k, filter_metadata=filter_metadata)

    def invoke(self, query: str, **kwargs: Any) -> list[Document]:
        return self.get_relevant_documents(query, **kwargs)


# ---------------------------------------------------------------------------
# Day 32 核心高级 RAG 组件：QueryRewriter / MultiQuery / HyDE / ContextCompressor
# ---------------------------------------------------------------------------

_DEFAULT_SYNONYMS: dict[str, str] = {
    "年假": "带薪年假 休假天数",
    "请假": "考勤 休假 审批流程",
    "报销": "差旅 费用报销 发票标准",
    "oom": "oomkilled 内存溢出 内存泄漏",
    "崩溃": "异常 故障 宕机 排查",
    "redis": "redis 缓存 键值遍历",
    "权限": "rbac 角色 隔离 鉴权",
}

_FILLER_PATTERNS = (
    r"^(请问一下|请问|麻烦问下|我想知道|帮我查查|帮我查一下|能告诉我|请问公司|公司里)",
    r"(到底|究竟|大概|一般|呀|啊|呢|吧|吗|？|\?)+$",
)


class QueryRewriter:
    """查询改写器：消除口语冗余、解析多轮指代，并补充检索关键词。"""

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        synonym_map: dict[str, str] | None = None,
    ) -> None:
        self.llm_fn = llm_fn
        self.synonym_map = {**_DEFAULT_SYNONYMS, **(synonym_map or {})}

    def rewrite(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> str:
        """将口语化或多轮指代提问改写为独立、清晰的检索 Query。"""
        cleaned = query.strip()
        if not cleaned:
            return ""

        if self.llm_fn is not None:
            history_text = ""
            if chat_history:
                history_lines = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in chat_history[-4:]]
                history_text = "\n".join(history_lines)
            prompt = (
                f"对话历史:\n{history_text}\n\n原始提问: {cleaned}\n"
                "请改写为独立、精准的企业知识库检索查询语句："
            )
            rewritten = self.llm_fn(prompt).strip()
            return rewritten or cleaned

        # 1. 去除口语化前后缀
        for pattern in _FILLER_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned).strip()

        # 2. 多轮指代消解（如 "它"、"这个"、"该制度"、"那怎么处理"）
        pronouns = ("它", "这个", "那个", "该制度", "该规范", "这方面", "那")
        if chat_history and any(p in cleaned for p in pronouns):
            last_user_topic = ""
            for msg in reversed(chat_history):
                if msg.get("role") == "user" and msg.get("content", "").strip():
                    last_user_topic = msg["content"].strip()
                    break
            if last_user_topic:
                for p in ("它", "这个", "那个", "该制度", "该规范", "这方面"):
                    cleaned = cleaned.replace(p, f" {last_user_topic} ")
                if cleaned.startswith("那"):
                    cleaned = f"{last_user_topic} {cleaned[1:]}"
                cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 3. 领域同义词轻量扩展
        lower_q = cleaned.lower()
        expansions: list[str] = []
        for term, ext in self.synonym_map.items():
            if term in lower_q:
                for token in ext.split():
                    if token.lower() not in lower_q and token not in expansions:
                        expansions.append(token)

        if expansions:
            return f"{cleaned} {' '.join(expansions[:3])}".strip()
        return cleaned

    def invoke(self, input_data: str | dict[str, Any]) -> str:
        if isinstance(input_data, str):
            return self.rewrite(input_data)
        return self.rewrite(
            query=str(input_data.get("query", "")),
            chat_history=input_data.get("chat_history"),
        )


class MultiQueryRetriever:
    """多路查询检索器：生成多视角查询变体 -> 并行召回 -> RRF 融合去重。"""

    def __init__(
        self,
        retriever: Any,
        query_generator: Callable[[str, int], list[str]] | None = None,
        num_queries: int = 3,
        include_original: bool = True,
        rrf_k: int = 60,
    ) -> None:
        if num_queries <= 0:
            raise ValueError("num_queries 必须大于 0")
        self.retriever = retriever
        self.query_generator = query_generator
        self.num_queries = num_queries
        self.include_original = include_original
        self.rrf_k = rrf_k
        self._rewriter = QueryRewriter()

    def generate_queries(self, query: str) -> list[str]:
        """为单条原始提问生成多个不同视角的检索变体。"""
        base = query.strip()
        if not base:
            return []

        if self.query_generator is not None:
            variants = [v.strip() for v in self.query_generator(base, self.num_queries) if v.strip()]
        else:
            rewritten = self._rewriter.rewrite(base)
            # 视角 1：原始/清洗表达；视角 2：同义词扩展表达；视角 3：规范/流程/排查视角
            keyword_tokens = [t for t in _tokenize(base) if len(t) >= 2][:4]
            keyword_view = " ".join(keyword_tokens) + " 规范 制度 手册" if keyword_tokens else f"{base} 规范"
            variants = [
                base,
                rewritten,
                keyword_view.strip(),
                f"{base} 具体要求与步骤",
            ]

        deduped: list[str] = []
        seen: set[str] = set()
        ordered_candidates = ([base] + variants) if self.include_original else variants
        for item in ordered_candidates:
            norm = item.lower().strip()
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(item)
            if len(deduped) >= self.num_queries:
                break
        return deduped

    def _call_retriever(self, query: str, **kwargs: Any) -> list[Document]:
        if hasattr(self.retriever, "invoke"):
            return list(self.retriever.invoke(query, **kwargs))
        if hasattr(self.retriever, "get_relevant_documents"):
            return list(self.retriever.get_relevant_documents(query, **kwargs))
        if hasattr(self.retriever, "similarity_search"):
            return list(self.retriever.similarity_search(query, **kwargs))
        raise TypeError("retriever 必须实现 invoke、get_relevant_documents 或 similarity_search 方法")

    def retrieve_with_details(
        self,
        query: str,
        k: int | None = None,
        **kwargs: Any,
    ) -> tuple[list[Document], list[str]]:
        """执行多路检索与 RRF 去重，同时返回生成的查询变体列表便于可观测追踪。"""
        queries = self.generate_queries(query)
        if not queries:
            return [], []

        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for q in queries:
            docs = self._call_retriever(q, **kwargs)
            for rank, doc in enumerate(docs, start=1):
                doc_key = doc.id or hashlib.sha256(doc.page_content.encode("utf-8")).hexdigest()[:12]
                doc_map[doc_key] = doc
                rrf_scores[doc_key] = rrf_scores.get(doc_key, 0.0) + 1.0 / (self.rrf_k + rank)

        sorted_keys = sorted(rrf_scores.keys(), key=lambda key: rrf_scores[key], reverse=True)
        merged_docs = [doc_map[key] for key in sorted_keys]
        if k is not None:
            merged_docs = merged_docs[: max(0, k)]
        return merged_docs, queries

    def retrieve(self, query: str, k: int | None = None, **kwargs: Any) -> list[Document]:
        docs, _ = self.retrieve_with_details(query, k=k, **kwargs)
        return docs

    def invoke(self, query: str, k: int | None = None, **kwargs: Any) -> list[Document]:
        return self.retrieve(query, k=k, **kwargs)


class HyDERetriever:
    """HyDE（Hypothetical Document Embeddings）检索器：先生成假设答案文档，再用其向量检索真实文档。"""

    def __init__(
        self,
        vector_store: LocalVectorStore,
        llm_fn: Callable[[str], str] | None = None,
        k: int = 3,
    ) -> None:
        self.vector_store = vector_store
        self.llm_fn = llm_fn
        self.k = k

    def generate_hypothetical_document(self, query: str) -> str:
        """根据用户问题生成一段假设性的知识库答案文档。"""
        cleaned = query.strip()
        if not cleaned:
            return ""
        if self.llm_fn is not None:
            prompt = (
                "请根据以下问题，撰写一段专业、信息密度高的知识库参考文档片段（无需编造具体私有编号）：\n"
                f"问题：{cleaned}"
            )
            return self.llm_fn(prompt).strip()

        lower_q = cleaned.lower()
        if any(w in lower_q for w in ("oom", "内存", "溢出", "pod")):
            return (
                f"针对「{cleaned}」的技术排查文档：当容器或服务发生内存溢出（OOMKilled）时，"
                "首先检查内存限制与 JVM 堆参数设置，排查内存泄漏与大对象缓存，并通过监控日志定位异常进程。"
            )
        if any(w in lower_q for w in ("年假", "请假", "休假", "病假")):
            return (
                f"关于「{cleaned}」的企业人事制度说明：员工按司龄享受对应天数的带薪年假，"
                "请假需在考勤系统提前提交审批，病假需附带正规医院诊断证明。"
            )
        if any(w in lower_q for w in ("报销", "差旅", "发票", "住宿")):
            return (
                f"关于「{cleaned}」的财务报销规范：员工出差住宿与交通费用需符合城市等级上限标准，"
                "并在规定时间内上传合规电子发票完成报销审批。"
            )
        return (
            f"关于「{cleaned}」的企业知识库说明文档：本规范详细定义了相关的操作流程、标准要求、"
            "注意事项及常见问题排查步骤。"
        )

    def retrieve_with_hypothesis(
        self,
        query: str,
        k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> tuple[str, list[Document]]:
        """返回 (假设文档文本, 召回的真实文档列表)。"""
        hypo_doc = self.generate_hypothetical_document(query)
        if not hypo_doc:
            return "", []
        hypo_vec = self.vector_store.embedding_function.embed_query(hypo_doc)
        top_k = self.k if k is None else k
        docs = self.vector_store.similarity_search_by_vector(
            hypo_vec,
            k=top_k,
            filter_metadata=filter_metadata,
        )
        return hypo_doc, docs

    def retrieve(
        self,
        query: str,
        k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        _, docs = self.retrieve_with_hypothesis(query, k=k, filter_metadata=filter_metadata)
        return docs

    def invoke(self, query: str, **kwargs: Any) -> list[Document]:
        return self.retrieve(
            query,
            k=kwargs.get("k"),
            filter_metadata=kwargs.get("filter_metadata"),
        )


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点或换行符切分句子，保留原始语义完整性。"""
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


class ContextCompressor:
    """上下文压缩器：从召回切片中只抽取与 Query 高度相关的句子，剔除冗余噪音。"""

    def __init__(
        self,
        min_score: float = 0.15,
        max_sentences_per_doc: int = 3,
        embedding_function: LocalEmbedding | None = None,
        llm_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        self.min_score = min_score
        self.max_sentences_per_doc = max_sentences_per_doc
        self.embedding_function = embedding_function or LocalEmbedding()
        self.llm_fn = llm_fn

    def _score_sentence(self, query: str, sentence: str, q_vec: list[float], q_tokens: set[str]) -> float:
        s_vec = self.embedding_function.embed_query(sentence)
        vec_sim = max(0.0, _cosine_similarity(q_vec, s_vec))
        s_tokens = set(_tokenize(sentence))
        if not q_tokens or not s_tokens:
            return vec_sim
        overlap = len(q_tokens & s_tokens) / max(1, len(q_tokens))
        return 0.6 * vec_sim + 0.4 * overlap

    def compress_document(
        self,
        query: str,
        doc: Document,
        drop_empty: bool = True,
    ) -> Document | None:
        """压缩单篇文档，仅保留与 query 相关的关键句。"""
        if not doc.page_content.strip():
            return None if drop_empty else doc

        if self.llm_fn is not None:
            compressed_text = self.llm_fn(query, doc.page_content).strip()
            if not compressed_text:
                return None if drop_empty else None
            return Document(
                id=doc.id,
                page_content=compressed_text,
                metadata={
                    **doc.metadata,
                    "compressed": True,
                    "original_chars": len(doc.page_content),
                    "compressed_chars": len(compressed_text),
                },
            )

        sentences = _split_sentences(doc.page_content)
        if not sentences:
            return None if drop_empty else doc

        q_vec = self.embedding_function.embed_query(query)
        q_tokens = set(_tokenize(query))

        scored_indexed: list[tuple[int, str, float]] = []
        for idx, sent in enumerate(sentences):
            score = self._score_sentence(query, sent, q_vec, q_tokens)
            if score >= self.min_score:
                scored_indexed.append((idx, sent, score))

        if not scored_indexed:
            if drop_empty:
                return None
            # 若不丢弃空结果，至少保留得分最高的一句
            best_idx, best_sent, _ = max(
                ((i, s, self._score_sentence(query, s, q_vec, q_tokens)) for i, s in enumerate(sentences)),
                key=lambda x: x[2],
            )
            scored_indexed = [(best_idx, best_sent, 0.0)]

        # 先按相关性挑出 Top-N，再按原文顺序拼接以保持语序连贯
        top_selected = sorted(scored_indexed, key=lambda x: x[2], reverse=True)[: self.max_sentences_per_doc]
        top_selected.sort(key=lambda x: x[0])
        compressed_text = " ".join(item[1] for item in top_selected)

        orig_len = len(doc.page_content)
        comp_len = len(compressed_text)
        ratio = round(comp_len / orig_len, 4) if orig_len > 0 else 1.0

        return Document(
            id=doc.id,
            page_content=compressed_text,
            metadata={
                **doc.metadata,
                "compressed": True,
                "original_chars": orig_len,
                "compressed_chars": comp_len,
                "compression_ratio": ratio,
            },
        )

    def compress_documents(
        self,
        query: str,
        documents: list[Document],
        drop_empty: bool = True,
    ) -> list[Document]:
        """批量压缩召回文档列表。"""
        compressed: list[Document] = []
        for doc in documents:
            res = self.compress_document(query, doc, drop_empty=drop_empty)
            if res is not None:
                compressed.append(res)
        return compressed

    def invoke(self, input_data: dict[str, Any]) -> list[Document]:
        return self.compress_documents(
            query=str(input_data.get("query", "")),
            documents=list(input_data.get("documents", [])),
            drop_empty=bool(input_data.get("drop_empty", True)),
        )
