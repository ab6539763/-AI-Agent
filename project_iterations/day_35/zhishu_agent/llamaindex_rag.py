"""智枢平台 Day 35：LlamaIndex 核心抽象与 LangChain 框架对比 (v0.3.0-day35).

提供零外部依赖、确定性可复现的 LlamaIndex 风格核心组件：
1. SimpleDirectoryReader：从本地目录加载文档并封装为 Document。
2. Node / NodeWithScore：文档切片后的原子数据单元，支持元数据与节点关系链。
3. VectorStoreIndex：通过 from_documents() 构建向量索引，支持 Top-K 相似度检索。
4. QueryEngine：无状态单轮 RAG 问答引擎（支持 compact / refine / tree_summarize）。
5. ChatEngine：有状态多轮对话引擎（支持上下文改写与历史记忆）。
6. compare_frameworks()：LangChain 与 LlamaIndex 多维度对比与选型建议工具。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re
from typing import Any


_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "也", "都", "就", "而", "但",
    "吗", "呢", "啊", "吧", "呀", "么", "什么", "多少", "如何", "怎么", "为什么",
    "请问", "一下", "可以", "能否", "有", "没有", "这", "那", "这个", "那个",
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "and", "or", "by", "from",
    "what", "how", "why", "when", "where", "which", "who", "do", "does", "did",
}


def _tokenize(text: str, include_bigrams: bool = True) -> list[str]:
    """中英文混合分词：英文单词 + 中文单字/双字切分，过滤常见虚词."""
    if not text:
        return []
    lowered = text.lower()
    tokens: list[str] = []

    for word in re.findall(r"[a-z0-9_]+", lowered):
        if word not in _STOPWORDS:
            tokens.append(word)

    for zh_seq in re.findall(r"[\u4e00-\u9fff]+", lowered):
        chars = [c for c in zh_seq if c not in _STOPWORDS]
        tokens.extend(chars)
        if include_bigrams and len(zh_seq) >= 2:
            for i in range(len(zh_seq) - 1):
                bg = zh_seq[i : i + 2]
                if bg not in _STOPWORDS:
                    tokens.append(bg)

    return tokens


def _embed_text(text: str, dim: int = 256) -> list[float]:
    """基于 SHA-256 特征哈希的确定性 L2 归一化向量编码."""
    vec = [0.0] * dim
    tokens = _tokenize(text, include_bigrams=True)
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个归一化向量的余弦相似度，截断到 [0.0, 1.0]."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(0.0, min(1.0, dot))


def _short_hash(text: str) -> str:
    """生成确定性的 12 位短 ID."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class Document:
    """LlamaIndex 核心文档对象，封装原始文本与元数据."""

    text: str
    doc_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.doc_id:
            source = str(self.metadata.get("file_path", ""))
            self.doc_id = f"doc-{_short_hash(source + '::' + self.text[:128])}"


@dataclass
class Node:
    """LlamaIndex 原子切片节点（TextNode），携带向量与节点关系链."""

    text: str
    node_id: str = ""
    doc_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{_short_hash(self.doc_id + '::' + self.text[:128])}"


@dataclass
class NodeWithScore:
    """带检索相关性分数的节点."""

    node: Node
    score: float


@dataclass
class QueryResponse:
    """QueryEngine / ChatEngine 的标准响应对象."""

    response: str
    source_nodes: list[NodeWithScore] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def format_sources(self) -> str:
        """格式化溯源节点摘要."""
        if not self.source_nodes:
            return "无检索溯源节点"
        lines = []
        for idx, nws in enumerate(self.source_nodes, start=1):
            fname = nws.node.metadata.get("file_name", nws.node.doc_id)
            preview = nws.node.text.replace("\n", " ")[:60]
            lines.append(f"[{idx}] ({fname}, score={nws.score:.4f}) {preview}...")
        return "\n".join(lines)


@dataclass
class ChatTurn:
    """多轮对话单条历史记录."""

    role: str
    content: str


class SimpleDirectoryReader:
    """从指定目录读取文本文件并构建 Document 列表."""

    DEFAULT_EXTS = (".txt", ".md", ".csv", ".json", ".log")

    def __init__(
        self,
        input_dir: str | Path,
        required_exts: list[str] | None = None,
        recursive: bool = False,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.required_exts = (
            tuple(ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in required_exts)
            if required_exts is not None
            else self.DEFAULT_EXTS
        )
        self.recursive = recursive

    def load_data(self) -> list[Document]:
        """扫描目录并加载所有符合扩展名要求的非空文档."""
        if not self.input_dir.exists() or not self.input_dir.is_dir():
            raise FileNotFoundError(f"目录不存在或不是有效目录: {self.input_dir}")

        iterator = self.input_dir.rglob("*") if self.recursive else self.input_dir.iterdir()
        files = sorted(
            p for p in iterator if p.is_file() and p.suffix.lower() in self.required_exts
        )

        documents: list[Document] = []
        for file_path in files:
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            metadata = {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_ext": file_path.suffix.lower(),
            }
            doc_id = f"doc-{_short_hash(str(file_path))}"
            documents.append(Document(text=content, doc_id=doc_id, metadata=metadata))
        return documents


def _split_text_into_chunks(text: str, chunk_size: int = 200, chunk_overlap: int = 40) -> list[str]:
    """按段落/句子边界切分文本为定长窗口，保留重叠上下文."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    step = max(1, chunk_size - max(0, min(chunk_overlap, chunk_size - 1)))
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            # 尽量在句末标点或换行处截断，避免生硬切断词语
            window = cleaned[start:end]
            for sep in ("\n", "。", "！", "？", ".", "!", "?", "；", ";"):
                pos = window.rfind(sep)
                if pos >= chunk_size // 2:
                    end = start + pos + 1
                    break
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


class QueryEngine:
    """LlamaIndex 风格无状态单轮问答引擎."""

    SUPPORTED_MODES = ("compact", "refine", "tree_summarize")

    def __init__(
        self,
        index: VectorStoreIndex,
        similarity_top_k: int = 3,
        response_mode: str = "compact",
        min_score: float = 0.05,
    ) -> None:
        if response_mode not in self.SUPPORTED_MODES:
            raise ValueError(f"不支持的 response_mode: {response_mode}，可选: {self.SUPPORTED_MODES}")
        self.index = index
        self.similarity_top_k = similarity_top_k
        self.response_mode = response_mode
        self.min_score = min_score

    def _synthesize_answer(self, query: str, nodes: list[NodeWithScore]) -> str:
        """根据检索到的节点确定性合成回答."""
        relevant = [nws for nws in nodes if nws.score >= self.min_score]
        if not relevant:
            return "未在当前知识库索引中检索到足够相关的参考信息，请尝试调整提问关键词或补充文档。"

        top_score = relevant[0].score
        relevant = [nws for nws in relevant if nws.score >= max(self.min_score, top_score * 0.35)]

        query_tokens = set(_tokenize(query, include_bigrams=True))
        selected_sentences: list[str] = []
        seen: set[str] = set()

        for nws in relevant:
            parts = re.split(r"[。！？\n.!?]+", nws.node.text)
            scored_parts: list[tuple[int, str]] = []
            for part in parts:
                s = part.strip()
                if len(s) < 2:
                    continue
                s_tokens = set(_tokenize(s, include_bigrams=True))
                overlap = len(query_tokens & s_tokens)
                scored_parts.append((overlap, s))
            scored_parts.sort(key=lambda item: item[0], reverse=True)
            for _, sentence in scored_parts[:2]:
                if sentence not in seen:
                    seen.add(sentence)
                    selected_sentences.append(sentence)

        if not selected_sentences:
            selected_sentences = [relevant[0].node.text.strip()]

        if self.response_mode == "compact":
            body = "。".join(selected_sentences[:3])
            if not body.endswith(("。", "！", "？", ".", "!", "?")):
                body += "。"
            return f"根据知识库检索结果：{body}"

        if self.response_mode == "refine":
            first_src = relevant[0].node.metadata.get("file_name", relevant[0].node.doc_id)
            refined = "；".join(selected_sentences[:4])
            return f"[Refine 综合答案 | 主来源: {first_src}] {refined}。"

        # tree_summarize
        sources = sorted({nws.node.metadata.get("file_name", nws.node.doc_id) for nws in relevant})
        summary = "；".join(selected_sentences[:4])
        return f"[TreeSummarize 汇总 | 涉及文档: {', '.join(sources)}] {summary}。"

    def query(self, query_str: str) -> QueryResponse:
        """执行单轮检索 + 响应合成."""
        if not query_str or not query_str.strip():
            return QueryResponse(
                response="请输入有效的查询问题。",
                source_nodes=[],
                metadata={"response_mode": self.response_mode},
            )
        retrieved = self.index.retrieve(query_str, similarity_top_k=self.similarity_top_k)
        answer = self._synthesize_answer(query_str, retrieved)
        return QueryResponse(
            response=answer,
            source_nodes=retrieved,
            metadata={
                "response_mode": self.response_mode,
                "top_k": self.similarity_top_k,
            },
        )


class ChatEngine:
    """LlamaIndex 风格有状态多轮对话引擎，支持上下文改写与历史记忆."""

    def __init__(
        self,
        index: VectorStoreIndex,
        similarity_top_k: int = 3,
        chat_mode: str = "condense_question",
        max_history: int = 10,
    ) -> None:
        self.index = index
        self.similarity_top_k = similarity_top_k
        self.chat_mode = chat_mode
        self.max_history = max_history
        self._query_engine = QueryEngine(index=index, similarity_top_k=similarity_top_k)
        self.chat_history: list[ChatTurn] = []

    def _condense_with_history(self, message: str) -> str:
        """结合最近一轮用户提问，改写指代不清的追问（如“它呢？”、“报销上限是多少？”）."""
        if not self.chat_history:
            return message
        last_user_msgs = [t.content for t in self.chat_history if t.role == "user"]
        if not last_user_msgs:
            return message
        prev_query = last_user_msgs[-1]
        # 若当前追问较短或包含指代词，拼接上一轮核心上下文辅助检索
        pronouns = ("它", "这个", "那个", "那", "这", "还有", "另外", "上面", "刚才", "it", "that", "this")
        if len(message.strip()) <= 16 or any(p in message.lower() for p in pronouns):
            return f"{prev_query} {message}"
        return message

    def chat(self, message: str) -> QueryResponse:
        """执行多轮对话：改写检索 -> 合成回答 -> 写入对话历史."""
        effective_query = self._condense_with_history(message)
        result = self._query_engine.query(effective_query)

        self.chat_history.append(ChatTurn(role="user", content=message))
        self.chat_history.append(ChatTurn(role="assistant", content=result.response))
        if len(self.chat_history) > self.max_history * 2:
            self.chat_history = self.chat_history[-(self.max_history * 2) :]

        result.metadata["chat_mode"] = self.chat_mode
        result.metadata["condensed_query"] = effective_query
        result.metadata["history_turns"] = len(self.chat_history) // 2
        return result

    def reset(self) -> None:
        """清空多轮对话历史."""
        self.chat_history.clear()


class VectorStoreIndex:
    """LlamaIndex 核心向量索引抽象，负责文档切片、向量化与相似度检索."""

    def __init__(self, nodes: list[Node] | None = None, embed_dim: int = 256) -> None:
        self.embed_dim = embed_dim
        self.nodes: list[Node] = []
        if nodes:
            self.insert_nodes(nodes)

    @classmethod
    def from_documents(
        cls,
        documents: list[Document],
        chunk_size: int = 200,
        chunk_overlap: int = 40,
        embed_dim: int = 256,
    ) -> VectorStoreIndex:
        """从 Document 列表一键构建 VectorStoreIndex."""
        all_nodes: list[Node] = []
        for doc in documents:
            chunks = _split_text_into_chunks(doc.text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            doc_nodes: list[Node] = []
            for idx, chunk in enumerate(chunks):
                node_meta = dict(doc.metadata)
                node_meta["chunk_index"] = idx
                node_id = f"{doc.doc_id}-node-{idx}"
                node = Node(
                    text=chunk,
                    node_id=node_id,
                    doc_id=doc.doc_id,
                    metadata=node_meta,
                    embedding=_embed_text(chunk, dim=embed_dim),
                    relationships={"SOURCE": doc.doc_id},
                )
                doc_nodes.append(node)

            for idx, node in enumerate(doc_nodes):
                if idx > 0:
                    node.relationships["PREVIOUS"] = doc_nodes[idx - 1].node_id
                if idx < len(doc_nodes) - 1:
                    node.relationships["NEXT"] = doc_nodes[idx + 1].node_id
            all_nodes.extend(doc_nodes)

        return cls(nodes=all_nodes, embed_dim=embed_dim)

    def insert_nodes(self, nodes: list[Node]) -> None:
        """向索引中增量插入 Node（自动补全缺失的向量）."""
        for node in nodes:
            if not node.embedding:
                node.embedding = _embed_text(node.text, dim=self.embed_dim)
            self.nodes.append(node)

    def retrieve(self, query: str, similarity_top_k: int = 3) -> list[NodeWithScore]:
        """基于余弦相似度检索最相关的 Top-K Node."""
        if not self.nodes or not query.strip() or similarity_top_k <= 0:
            return []
        q_vec = _embed_text(query, dim=self.embed_dim)
        scored = [
            NodeWithScore(node=node, score=round(_cosine_similarity(q_vec, node.embedding), 6))
            for node in self.nodes
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:similarity_top_k]

    def as_query_engine(
        self,
        similarity_top_k: int = 3,
        response_mode: str = "compact",
    ) -> QueryEngine:
        """将索引转换为无状态 QueryEngine."""
        return QueryEngine(
            index=self,
            similarity_top_k=similarity_top_k,
            response_mode=response_mode,
        )

    def as_chat_engine(
        self,
        similarity_top_k: int = 3,
        chat_mode: str = "condense_question",
        max_history: int = 10,
    ) -> ChatEngine:
        """将索引转换为有状态 ChatEngine."""
        return ChatEngine(
            index=self,
            similarity_top_k=similarity_top_k,
            chat_mode=chat_mode,
            max_history=max_history,
        )


def compare_frameworks(use_case: str | None = None) -> dict[str, Any]:
    """对比 LangChain 与 LlamaIndex 的核心架构差异，并按业务场景给出选型建议.

    Args:
        use_case: 可选场景标识，支持 ``"enterprise_rag"``、``"multi_agent_workflow"``、
            ``"hybrid"``，传入后将返回针对该场景的推荐框架与理由。
    """
    dimensions = [
        {
            "dimension": "核心定位",
            "langchain": "通用 LLM 应用与复杂 Agent 编排框架（Chains / LCEL / LangGraph）",
            "llamaindex": "以数据为中心的 RAG 与知识索引框架（Data Framework for LLM）",
        },
        {
            "dimension": "核心抽象",
            "langchain": "Runnable、PromptTemplate、Chain、Tool、AgentExecutor、StateGraph",
            "llamaindex": "Document、Node、VectorStoreIndex、Retriever、QueryEngine、ChatEngine",
        },
        {
            "dimension": "数据接入与索引",
            "langchain": "DocumentLoader + TextSplitter + VectorStore，需手动串联切分与入库流水线",
            "llamaindex": "SimpleDirectoryReader + NodeParser + VectorStoreIndex.from_documents() 一键索引",
        },
        {
            "dimension": "检索与响应合成",
            "langchain": "Retriever 输出 Document 列表，需自行拼接 Prompt 与上下文压缩逻辑",
            "llamaindex": "内置 QueryEngine（compact/refine/tree_summarize）与 ChatEngine 多轮改写",
        },
        {
            "dimension": "Agent 与复杂工作流",
            "langchain": "生态最成熟，LangGraph 原生支持循环图、人工介入（HITL）与状态持久化",
            "llamaindex": "支持 FunctionAgent 与 Workflows，但在复杂多智能体编排上不如 LangGraph 灵活",
        },
    ]

    recommendations = {
        "enterprise_rag": {
            "recommended": "LlamaIndex",
            "reason": "企业私有知识库问答、多文档结构化索引与高阶检索（层次索引/响应合成）场景下，LlamaIndex 开箱即用程度更高、代码量更少。",
        },
        "multi_agent_workflow": {
            "recommended": "LangChain + LangGraph",
            "reason": "涉及多工具调用、条件分支、循环反思与人工审批（HITL）的复杂智能体工作流，LangChain/LangGraph 编排能力最强。",
        },
        "hybrid": {
            "recommended": "LlamaIndex (检索索引层) + LangChain/LangGraph (Agent 编排层)",
            "reason": "生产级企业智能体最佳实践：用 LlamaIndex 管理高质量文档索引与 QueryEngine，将其封装为 Tool 交给 LangChain/LangGraph 智能体调度。",
        },
    }

    result: dict[str, Any] = {
        "frameworks": ["LangChain", "LlamaIndex"],
        "dimensions": dimensions,
        "best_practice": "二者并非非此即彼：知识检索底座优先 LlamaIndex，复杂多步 Agent 编排优先 LangChain/LangGraph。",
    }
    if use_case is not None:
        if use_case not in recommendations:
            raise ValueError(
                f"未知场景 '{use_case}'，可选值: {list(recommendations.keys())}"
            )
        result["use_case"] = use_case
        result["recommendation"] = recommendations[use_case]
    return result


def format_framework_comparison(use_case: str | None = None) -> str:
    """将 LangChain vs LlamaIndex 对比结果格式化为可读文本."""
    data = compare_frameworks(use_case=use_case)
    lines = [
        "=== LangChain vs LlamaIndex 框架对比矩阵 ===",
    ]
    for item in data["dimensions"]:
        lines.append(
            f"- [{item['dimension']}]\n"
            f"  * LangChain : {item['langchain']}\n"
            f"  * LlamaIndex: {item['llamaindex']}"
        )
    lines.append(f"架构师总结: {data['best_practice']}")
    if "recommendation" in data:
        rec = data["recommendation"]
        lines.append(
            f"场景推荐 ({data['use_case']}): {rec['recommended']} — {rec['reason']}"
        )
    return "\n".join(lines)
