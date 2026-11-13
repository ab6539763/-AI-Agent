"""Day 29: 向量数据库与 Retriever 检索器接口（Chroma 兼容本地向量库）."""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    """兼容 LangChain / Chroma 的文档数据结构."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_content": self.page_content,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        return cls(
            page_content=data["page_content"],
            metadata=dict(data.get("metadata") or {}),
            id=data.get("id"),
        )


class LocalEmbedding:
    """基于 Python 标准库的确定性本地向量化器（Feature Hashing + L2 归一化）.

    特点：
    1. 零外部依赖，完全离线可用，跨进程/跨平台结果 100% 确定。
    2. 同时支持英文词元与中文单字/双字切分（Unigram + Bigram），保证中英文混合检索的语义相关性。
    """

    def __init__(self, dim: int = 128) -> None:
        if dim <= 0:
            raise ValueError("embedding 维度 dim 必须大于 0")
        self.dim = dim

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = text.strip().lower()
        if not normalized:
            return []

        tokens: list[str] = []
        # 英文单词与数字
        tokens.extend(re.findall(r"[a-z0-9_]+", normalized))
        # 中文字符 Unigram + Bigram
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
        tokens.extend(cjk_chars)
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1])
        return tokens

    def embed_query(self, text: str) -> list[float]:
        """将单条查询文本编码为定长 L2 归一化向量."""
        vec = [0.0] * self.dim
        tokens = self._tokenize(text)
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            # Bigram 赋予稍高权重以增强词组匹配区分度
            weight = 1.5 if len(token) >= 2 else 1.0
            vec[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [round(v / norm, 8) for v in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量将文档文本列表编码为向量列表."""
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


def _match_metadata(doc_meta: dict[str, Any], filter_metadata: dict[str, Any] | None) -> bool:
    """校验文档元数据是否满足过滤条件（支持精确匹配与常用 Chroma 比较操作符）."""
    if not filter_metadata:
        return True

    for key, condition in filter_metadata.items():
        if key not in doc_meta:
            return False
        val = doc_meta[key]
        if isinstance(condition, dict):
            for op, target in condition.items():
                if op == "$eq" and val != target:
                    return False
                if op == "$ne" and val == target:
                    return False
                if op == "$gt" and not (val > target):
                    return False
                if op == "$gte" and not (val >= target):
                    return False
                if op == "$lt" and not (val < target):
                    return False
                if op == "$lte" and not (val <= target):
                    return False
                if op == "$in" and val not in target:
                    return False
        else:
            if val != condition:
                return False
    return True


class LocalVectorStore:
    """Chroma 兼容的本地向量存储与持久化引擎."""

    def __init__(
        self,
        collection_name: str = "zhishu_knowledge",
        embedding_function: LocalEmbedding | None = None,
        persist_directory: str | Path | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_function = embedding_function or LocalEmbedding()
        self.persist_directory = Path(persist_directory) if persist_directory else None
        # 按 id 存储文档记录，保持插入顺序同时支持幂等更新
        self._records: dict[str, dict[str, Any]] = {}

    def count(self) -> int:
        """返回当前集合中的文档数量."""
        return len(self._records)

    def add_documents(
        self,
        documents: list[Document],
        ids: list[str] | None = None,
    ) -> list[str]:
        """向向量库写入或更新 Document 列表，返回文档 ID 列表."""
        if not documents:
            return []
        if ids is not None and len(ids) != len(documents):
            raise ValueError("ids 长度必须与 documents 长度一致")

        texts = [doc.page_content for doc in documents]
        embeddings = self.embedding_function.embed_documents(texts)

        assigned_ids: list[str] = []
        for idx, (doc, emb) in enumerate(zip(documents, embeddings)):
            doc_id = (
                ids[idx]
                if ids is not None
                else (doc.id if doc.id else str(uuid.uuid4()))
            )
            stored_doc = Document(
                page_content=doc.page_content,
                metadata=dict(doc.metadata),
                id=doc_id,
            )
            self._records[doc_id] = {
                "document": stored_doc,
                "embedding": emb,
            }
            assigned_ids.append(doc_id)

        return assigned_ids

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """便捷写入纯文本列表与对应元数据."""
        if metadatas is not None and len(metadatas) != len(texts):
            raise ValueError("metadatas 长度必须与 texts 长度一致")
        docs = [
            Document(
                page_content=text,
                metadata=dict(metadatas[i]) if metadatas is not None else {},
                id=ids[i] if ids is not None else None,
            )
            for i, text in enumerate(texts)
        ]
        return self.add_documents(docs, ids=ids)

    def delete(self, ids: list[str]) -> int:
        """按 ID 删除文档，返回实际删除的数量."""
        removed = 0
        for doc_id in ids:
            if doc_id in self._records:
                del self._records[doc_id]
                removed += 1
        return removed

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        """执行带元数据过滤的余弦相似度检索，返回 (Document, score) 列表（按相似度降序）."""
        if k <= 0:
            raise ValueError("检索数量 k 必须大于 0")
        if not self._records:
            return []

        query_vec = self.embedding_function.embed_query(query)
        scored: list[tuple[Document, float]] = []

        for record in self._records.values():
            doc: Document = record["document"]
            if not _match_metadata(doc.metadata, filter_metadata):
                continue
            score = round(_cosine_similarity(query_vec, record["embedding"]), 6)
            scored.append((doc, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        """执行相似度检索，仅返回 Top-K Document 列表."""
        return [
            doc
            for doc, _score in self.similarity_search_with_score(
                query=query,
                k=k,
                filter_metadata=filter_metadata,
            )
        ]

    def _resolve_save_path(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.persist_directory
        if target is None:
            raise ValueError("未指定持久化路径，请传入 path 或在初始化时设置 persist_directory")
        if target.suffix != ".json":
            return target / f"{self.collection_name}.json"
        return target

    def save(self, path: str | Path | None = None) -> Path:
        """将集合元信息、文档、元数据与向量持久化为 JSON 文件."""
        save_path = self._resolve_save_path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "collection_name": self.collection_name,
            "dim": self.embedding_function.dim,
            "records": [
                {
                    "id": doc_id,
                    "page_content": rec["document"].page_content,
                    "metadata": rec["document"].metadata,
                    "embedding": rec["embedding"],
                }
                for doc_id, rec in self._records.items()
            ],
        }
        save_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return save_path

    @classmethod
    def load(
        cls,
        path: str | Path,
        embedding_function: LocalEmbedding | None = None,
        collection_name: str = "zhishu_knowledge",
    ) -> "LocalVectorStore":
        """从 JSON 文件或目录加载持久化向量库."""
        target = Path(path)
        if target.is_dir():
            target = target / f"{collection_name}.json"
        if not target.exists():
            raise FileNotFoundError(f"向量库持久化文件不存在: {target}")

        payload = json.loads(target.read_text(encoding="utf-8"))
        dim = int(payload.get("dim", 128))
        emb_fn = embedding_function or LocalEmbedding(dim=dim)
        if emb_fn.dim != dim:
            raise ValueError(f"Embedding 维度不匹配: 期望 {dim}，实际 {emb_fn.dim}")

        store = cls(
            collection_name=payload.get("collection_name", collection_name),
            embedding_function=emb_fn,
            persist_directory=target.parent,
        )
        for rec in payload.get("records", []):
            doc_id = rec["id"]
            doc = Document(
                page_content=rec["page_content"],
                metadata=dict(rec.get("metadata") or {}),
                id=doc_id,
            )
            store._records[doc_id] = {
                "document": doc,
                "embedding": list(rec["embedding"]),
            }
        return store

    def as_retriever(
        self,
        search_kwargs: dict[str, Any] | None = None,
    ) -> "VectorStoreRetriever":
        """将当前向量库封装为标准 Retriever 接口."""
        return VectorStoreRetriever(
            vector_store=self,
            search_kwargs=dict(search_kwargs or {"k": 3}),
        )


class VectorStoreRetriever:
    """兼容 LangChain Runnable/Retriever 接口的统一检索器."""

    def __init__(
        self,
        vector_store: LocalVectorStore,
        search_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.search_kwargs = dict(search_kwargs or {"k": 3})

    def invoke(self, query: str, **kwargs: Any) -> list[Document]:
        """执行检索，支持通过 kwargs 临时覆盖 search_kwargs."""
        merged = {**self.search_kwargs, **kwargs}
        k = int(merged.get("k", 3))
        filter_metadata = merged.get("filter_metadata")
        return self.vector_store.similarity_search(
            query=query,
            k=k,
            filter_metadata=filter_metadata,
        )

    def get_relevant_documents(self, query: str, **kwargs: Any) -> list[Document]:
        """兼容经典 LangChain get_relevant_documents 调用方式."""
        return self.invoke(query, **kwargs)
