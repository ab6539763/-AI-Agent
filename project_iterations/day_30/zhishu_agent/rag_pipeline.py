"""Day 30: 端到端 RAG 问答系统核心流水线 (v0.3.0-day30).

完整链路: Load -> Split -> Embed -> Store -> Retrieve -> Prompt -> Generate + Citations
支持低相似度兜底拒答（"我不知道/知识库中未找到相关信息"）与严格引用溯源。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from zhishu_agent.vector_store import Document, LocalVectorStore

FALLBACK_ANSWER = "我不知道/知识库中未找到相关信息"


@dataclass
class Citation:
    """单条引用来源信息."""

    index: int
    doc_id: str
    source: str
    score: float
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "doc_id": self.doc_id,
            "source": self.source,
            "score": self.score,
            "snippet": self.snippet,
            "metadata": self.metadata,
        }


@dataclass
class RAGAnswer:
    """结构化 RAG 问答输出."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    query: str = ""
    max_score: float = 0.0
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "grounded": self.grounded,
            "max_score": self.max_score,
            "citations": [c.to_dict() for c in self.citations],
        }


def split_text(
    text: str,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
) -> list[str]:
    """按字符窗口与重叠度切分长文本，尽量在句号/换行边界处断开."""
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
    start = 0
    text_len = len(cleaned)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            # 优先在标点或换行处截断，避免生硬切断词语
            for sep in ("\n", "。", "！", "？", ".", "!", "?", "；", ";"):
                pos = cleaned.rfind(sep, start + chunk_size // 2, end)
                if pos != -1:
                    end = pos + 1
                    break

        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= text_len:
            break
        start = max(end - chunk_overlap, start + 1)

    return chunks


def _normalize_document(item: Document | str | dict[str, Any]) -> Document:
    """将 str / dict / Document 统一转换为 Document 对象."""
    if isinstance(item, Document):
        return Document(
            page_content=item.page_content,
            metadata=dict(item.metadata),
            id=item.id,
        )
    if isinstance(item, str):
        return Document(page_content=item, metadata={})
    if isinstance(item, dict):
        return Document.from_dict(item)
    raise TypeError(f"不支持的文档输入类型: {type(item).__name__}")


def ingest_documents(
    store: LocalVectorStore,
    documents: Sequence[Document | str | dict[str, Any]],
    chunk_size: int = 300,
    chunk_overlap: int = 50,
) -> list[str]:
    """文档入库流水线：标准化 -> 文本切分 (Split) -> 向量化 (Embed) -> 写入向量库 (Store)."""
    if not documents:
        return []

    chunk_docs: list[Document] = []
    for raw_item in documents:
        doc = _normalize_document(raw_item)
        pieces = split_text(doc.page_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not pieces:
            continue

        base_id = doc.id or str(uuid.uuid4())
        if len(pieces) == 1:
            meta = dict(doc.metadata)
            meta.setdefault("source", meta.get("title", base_id))
            meta.setdefault("chunk_index", 0)
            chunk_docs.append(Document(page_content=pieces[0], metadata=meta, id=base_id))
        else:
            for idx, piece in enumerate(pieces):
                meta = dict(doc.metadata)
                meta.setdefault("source", meta.get("title", base_id))
                meta["parent_id"] = base_id
                meta["chunk_index"] = idx
                chunk_docs.append(
                    Document(
                        page_content=piece,
                        metadata=meta,
                        id=f"{base_id}#chunk-{idx}",
                    )
                )

    return store.add_documents(chunk_docs)


def retrieve(
    store: LocalVectorStore,
    query: str,
    k: int = 3,
    filter_metadata: dict[str, Any] | None = None,
) -> list[tuple[Document, float]]:
    """从向量库检索 Top-K 相关文档切片及其余弦相似度分数."""
    if not query.strip():
        return []
    return store.similarity_search_with_score(
        query=query,
        k=k,
        filter_metadata=filter_metadata,
    )


def build_rag_prompt(
    query: str,
    retrieved_docs: Sequence[tuple[Document, float] | Document],
) -> str:
    """构造带引用编号 [1], [2]... 与防幻觉约束的 RAG Prompt."""
    context_blocks: list[str] = []
    for idx, item in enumerate(retrieved_docs, start=1):
        if isinstance(item, tuple):
            doc, score = item
            score_tag = f", 相似度: {score:.4f}"
        else:
            doc = item
            score_tag = ""

        source = doc.metadata.get("source") or doc.id or f"doc-{idx}"
        context_blocks.append(
            f"[{idx}] (来源: {source}, ID: {doc.id or source}{score_tag})\n{doc.page_content}"
        )

    context_text = "\n\n".join(context_blocks) if context_blocks else "（无可用参考上下文）"
    return (
        "你是星辰数科《智枢》企业级知识问答助手。请严格遵循以下规则回答用户问题：\n"
        "1. 只能基于下方【参考上下文】中的事实进行回答，严禁编造或引入上下文之外的信息。\n"
        "2. 在回答的关键结论后使用 [1]、[2] 等编号标注对应的参考来源。\n"
        f"3. 如果参考上下文不足以回答该问题，请直接回复：“{FALLBACK_ANSWER}”。\n\n"
        f"【参考上下文】\n{context_text}\n\n"
        f"【用户问题】\n{query}\n\n"
        "【回答】"
    )


def _default_grounded_synthesis(
    query: str,
    retrieved: list[tuple[Document, float]],
) -> str:
    """离线确定性答案合成器（无外部 LLM 时使用，严格基于召回片段生成带引用回答）."""
    lines = ["根据企业知识库检索结果，为您整理如下："]
    for idx, (doc, _score) in enumerate(retrieved, start=1):
        lines.append(f"- {doc.page_content} [{idx}]")
    return "\n".join(lines)


def answer_with_citations(
    store: LocalVectorStore,
    query: str,
    k: int = 3,
    filter_metadata: dict[str, Any] | None = None,
    min_score_threshold: float = 0.15,
    llm_fn: Callable[[str], str] | None = None,
) -> RAGAnswer:
    """执行端到端 RAG 检索与带引用生成，低相似度时触发拒答兜底."""
    retrieved = retrieve(
        store=store,
        query=query,
        k=k,
        filter_metadata=filter_metadata,
    )

    if not retrieved:
        return RAGAnswer(
            answer=f"{FALLBACK_ANSWER}（知识库未检索到任何匹配片段）。",
            citations=[],
            grounded=False,
            query=query,
            max_score=0.0,
            prompt="",
        )

    max_score = max(score for _doc, score in retrieved)
    if max_score < min_score_threshold:
        return RAGAnswer(
            answer=(
                f"{FALLBACK_ANSWER}。"
                f"当前最高相似度为 {max_score:.4f}，低于阈值 {min_score_threshold:.4f}，已触发安全拒答。"
            ),
            citations=[],
            grounded=False,
            query=query,
            max_score=max_score,
            prompt="",
        )

    prompt = build_rag_prompt(query=query, retrieved_docs=retrieved)
    citations = [
        Citation(
            index=idx,
            doc_id=doc.id or f"doc-{idx}",
            source=str(doc.metadata.get("source") or doc.id or f"doc-{idx}"),
            score=score,
            snippet=doc.page_content,
            metadata=dict(doc.metadata),
        )
        for idx, (doc, score) in enumerate(retrieved, start=1)
    ]

    if llm_fn is not None:
        answer_text = llm_fn(prompt).strip()
    else:
        answer_text = _default_grounded_synthesis(query=query, retrieved=retrieved)

    return RAGAnswer(
        answer=answer_text,
        citations=citations,
        grounded=True,
        query=query,
        max_score=max_score,
        prompt=prompt,
    )


class RAGPipeline:
    """面向对象封装的端到端 RAG 流水线."""

    def __init__(
        self,
        vector_store: LocalVectorStore | None = None,
        min_score_threshold: float = 0.15,
        default_k: int = 3,
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        llm_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.vector_store = vector_store or LocalVectorStore(collection_name="zhishu_rag_kb")
        self.min_score_threshold = min_score_threshold
        self.default_k = default_k
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.llm_fn = llm_fn

    def ingest_documents(
        self,
        documents: Sequence[Document | str | dict[str, Any]],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[str]:
        return ingest_documents(
            store=self.vector_store,
            documents=documents,
            chunk_size=chunk_size if chunk_size is not None else self.chunk_size,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else self.chunk_overlap,
        )

    def retrieve(
        self,
        query: str,
        k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        return retrieve(
            store=self.vector_store,
            query=query,
            k=k if k is not None else self.default_k,
            filter_metadata=filter_metadata,
        )

    def build_rag_prompt(
        self,
        query: str,
        retrieved_docs: Sequence[tuple[Document, float] | Document],
    ) -> str:
        return build_rag_prompt(query=query, retrieved_docs=retrieved_docs)

    def answer_with_citations(
        self,
        query: str,
        k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
        min_score_threshold: float | None = None,
    ) -> RAGAnswer:
        return answer_with_citations(
            store=self.vector_store,
            query=query,
            k=k if k is not None else self.default_k,
            filter_metadata=filter_metadata,
            min_score_threshold=(
                min_score_threshold
                if min_score_threshold is not None
                else self.min_score_threshold
            ),
            llm_fn=self.llm_fn,
        )
