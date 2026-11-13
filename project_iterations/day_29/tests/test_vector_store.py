"""Day 29 自动化单元测试：覆盖 LocalEmbedding、LocalVectorStore、元数据过滤、持久化与 Retriever。"""
import math
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import Document, LocalEmbedding, LocalVectorStore, VectorStoreRetriever


@pytest.fixture()
def sample_documents() -> list[Document]:
    return [
        Document(
            id="doc-hr-1",
            page_content="年假与请假制度：员工入职满1年享受5天带薪年假，病假需提交医院证明。",
            metadata={"department": "hr", "year": 2025, "security": "internal"},
        ),
        Document(
            id="doc-fin-1",
            page_content="差旅报销标准：一线城市酒店住宿报销上限每晚600元，高铁二等座实报实销。",
            metadata={"department": "finance", "year": 2025, "security": "internal"},
        ),
        Document(
            id="doc-it-1",
            page_content="Redis 运维规范：生产环境严禁使用 KEYS * 阻塞主线程，统一使用 SCAN 遍历。",
            metadata={"department": "it", "year": 2024, "security": "confidential"},
        ),
        Document(
            id="doc-it-2",
            page_content="RAG 向量检索架构：通过 Cosine Similarity 召回 Top-K 文档片段并支持元数据过滤。",
            metadata={"department": "it", "year": 2026, "security": "internal"},
        ),
    ]


def test_local_embedding_determinism_and_normalization() -> None:
    """验证 LocalEmbedding 确定性、L2 归一化以及语义/词法重合度排序。"""
    emb = LocalEmbedding(dim=64)
    vec1 = emb.embed_query("年假几天")
    vec2 = emb.embed_query("年假几天")

    assert len(vec1) == 64
    assert vec1 == vec2

    norm = math.sqrt(sum(v * v for v in vec1))
    assert norm == pytest.approx(1.0, rel=1e-4)

    # 空文本返回零向量
    assert emb.embed_query("   ") == [0.0] * 64


def test_add_documents_and_similarity_search(sample_documents: list[Document]) -> None:
    """验证文档入库、ID 返回、similarity_search 与 similarity_search_with_score。"""
    store = LocalVectorStore(collection_name="test_kb")
    ids = store.add_documents(sample_documents)
    assert ids == ["doc-hr-1", "doc-fin-1", "doc-it-1", "doc-it-2"]
    assert store.count() == 4

    results = store.similarity_search_with_score("员工带薪年假有多少天？", k=2)
    assert len(results) == 2
    top_doc, top_score = results[0]
    second_doc, second_score = results[1]
    assert top_doc.id == "doc-hr-1"
    assert top_score >= second_score

    plain_docs = store.similarity_search("Redis KEYS SCAN", k=1)
    assert len(plain_docs) == 1
    assert plain_docs[0].id == "doc-it-1"


def test_metadata_filtering_and_k_selection(sample_documents: list[Document]) -> None:
    """验证元数据过滤（精确匹配与比较操作符）以及 k 值截断边界。"""
    store = LocalVectorStore()
    store.add_documents(sample_documents)

    # 精确匹配 department="it"
    it_docs = store.similarity_search(
        "规范",
        k=5,
        filter_metadata={"department": "it"},
    )
    assert len(it_docs) == 2
    assert all(d.metadata["department"] == "it" for d in it_docs)

    # 多条件 + 操作符过滤
    recent_it = store.similarity_search(
        "向量检索",
        k=3,
        filter_metadata={"department": "it", "year": {"$gte": 2025}},
    )
    assert [d.id for d in recent_it] == ["doc-it-2"]

    # 无匹配时返回空列表
    assert store.similarity_search("年假", k=3, filter_metadata={"department": "legal"}) == []

    # k <= 0 应抛出 ValueError
    with pytest.raises(ValueError):
        store.similarity_search("年假", k=0)


def test_json_persistence_save_and_load(
    tmp_path: Path,
    sample_documents: list[Document],
) -> None:
    """验证 save/load JSON 持久化后文档、元数据与检索结果完全一致。"""
    store = LocalVectorStore(collection_name="hr_kb", persist_directory=tmp_path)
    store.add_documents(sample_documents)
    saved_file = store.save()

    assert saved_file.exists()
    assert saved_file == tmp_path / "hr_kb.json"

    loaded_store = LocalVectorStore.load(saved_file)
    assert loaded_store.collection_name == "hr_kb"
    assert loaded_store.count() == 4

    orig_res = store.similarity_search_with_score("差旅住宿报销标准", k=2)
    load_res = loaded_store.similarity_search_with_score("差旅住宿报销标准", k=2)
    assert [(d.id, s) for d, s in orig_res] == [(d.id, s) for d, s in load_res]
    assert load_res[0][0].id == "doc-fin-1"


def test_as_retriever_interface(sample_documents: list[Document]) -> None:
    """验证 as_retriever 封装及 invoke / get_relevant_documents 调用。"""
    store = LocalVectorStore()
    store.add_documents(sample_documents)

    retriever = store.as_retriever(search_kwargs={"k": 3})
    assert isinstance(retriever, VectorStoreRetriever)

    docs = retriever.invoke("企业 RAG 检索")
    assert len(docs) == 3
    assert docs[0].id == "doc-it-2"

    # 支持在调用时覆盖 k 与 filter_metadata
    filtered = retriever.get_relevant_documents(
        "报销",
        k=1,
        filter_metadata={"department": "finance"},
    )
    assert len(filtered) == 1
    assert filtered[0].id == "doc-fin-1"
