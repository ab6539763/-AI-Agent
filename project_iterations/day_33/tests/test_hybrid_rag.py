"""Day 33 单元测试：BM25Retriever、RRF、CrossEncoderReranker 与 ParentDocumentRetriever."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    BM25Retriever,
    CrossEncoderReranker,
    Document,
    ParentDocumentRetriever,
    VectorRetriever,
    reciprocal_rank_fusion,
)


def test_bm25_retriever_exact_keyword_and_idf() -> None:
    """测试 BM25 对精确错误码/稀有关键词的精准召回与打分排序."""
    docs = [
        Document(id="d1", page_content="系统日常巡检日志正常，无异常告警。"),
        Document(id="d2", page_content="网关出现 ERR_NGX_502 错误时，请检查上游服务与 keepalive 超时。"),
        Document(id="d3", page_content="网关日常流量监控面板配置说明。"),
    ]
    bm25 = BM25Retriever(docs)
    results = bm25.retrieve_with_scores("ERR_NGX_502 网关", top_k=2)

    assert len(results) == 2
    assert results[0][0].id == "d2"
    assert results[0][1] > results[1][1] > 0.0
    assert bm25.retrieve("不存在的词xyz", top_k=2) == []


def test_reciprocal_rank_fusion_consensus_and_dedup() -> None:
    """测试 RRF 对多路召回结果的去重与共识加权."""
    doc_a = Document(id="a", page_content="Doc A")
    doc_b = Document(id="b", page_content="Doc B")
    doc_c = Document(id="c", page_content="Doc C")

    # doc_b 在两路均排名第 2；doc_a 仅在第一路排第 1，doc_c 仅在第二路排第 1
    list_bm25 = [doc_a, doc_b]
    list_vec = [doc_c, doc_b]

    fused = reciprocal_rank_fusion([list_bm25, list_vec], k=60)
    fused_ids = [doc.id for doc, _ in fused]

    # doc_b 出现两次: 2 * 1/(60+2) = 2/62 ≈ 0.032258 > 1/61 ≈ 0.016393
    assert fused_ids[0] == "b"
    assert len(fused) == 3
    assert abs(fused[0][1] - (2.0 / 62.0)) < 1e-5


def test_cross_encoder_reranker_promotes_relevant_doc() -> None:
    """测试 CrossEncoderReranker 联合词法+语义+短语匹配将最相关文档排在首位."""
    reranker = CrossEncoderReranker()
    candidates = [
        Document(id="noise", page_content="今天食堂午餐提供红烧肉和青菜。"),
        Document(id="partial", page_content="智枢平台支持向量检索与文档切分。"),
        Document(id="exact", page_content="智枢平台使用 RRF 倒数排名融合算法合并 BM25 与向量检索结果。"),
    ]

    reranked = reranker.rerank("RRF 倒数排名融合", candidates, top_k=2)
    assert len(reranked) == 2
    assert reranked[0][0].id == "exact"
    assert reranked[0][1] > reranked[1][1]


def test_parent_document_retriever_small_to_big() -> None:
    """测试 ParentDocumentRetriever 检索小切片但返回去重后的完整父文档."""
    parent_1 = Document(
        id="p1",
        page_content=(
            "第一部分：公司考勤制度总则，所有员工需按时打卡。"
            "第二部分：如遇 K8s Pod OOMKilled（错误码 137），请立即扩容内存限制并排查内存泄漏。"
            "第三部分：每周五下午为技术分享时间。"
        ),
        metadata={"dept": "it"},
    )
    parent_2 = Document(
        id="p2",
        page_content="财务报销规定：差旅住宿需提供增值税电子普通发票，并在月底前提交审批。",
        metadata={"dept": "finance"},
    )

    retriever = ParentDocumentRetriever(chunk_size=40, chunk_overlap=10)
    num_chunks = retriever.add_documents([parent_1, parent_2])
    assert num_chunks >= 4

    details = retriever.retrieve_with_matched_children("OOMKilled 错误码 137", top_k=2)
    assert len(details) >= 1
    top_parent, matched_child, rrf_score = details[0]

    assert top_parent.id == "p1"
    assert top_parent.page_content == parent_1.page_content
    assert len(matched_child.page_content) <= 40
    assert matched_child.metadata["parent_id"] == "p1"
    assert rrf_score > 0.0

    # 确保去重：即便多个子切片命中 p1，返回列表中 p1 只出现一次
    parents = retriever.retrieve("OOMKilled 内存", top_k=5)
    parent_ids = [p.id for p in parents]
    assert len(parent_ids) == len(set(parent_ids))


def test_end_to_end_hybrid_pipeline() -> None:
    """测试 BM25 + Vector -> RRF -> CrossEncoderReranker 端到端链路."""
    docs = [
        Document(id="1", page_content="Redis 集群禁止使用 KEYS *，应改用 SCAN 游标遍历。"),
        Document(id="2", page_content="Redis 缓存雪崩可通过随机过期时间与互斥锁预防。"),
        Document(id="3", page_content="PostgreSQL 慢查询优化需要检查 B-Tree 索引命中率。"),
    ]
    bm25 = BM25Retriever(docs)
    vec = VectorRetriever(docs)
    reranker = CrossEncoderReranker()

    query = "Redis KEYS * 替换方案 SCAN"
    fused = reciprocal_rank_fusion(
        [bm25.retrieve(query, top_k=3), vec.retrieve(query, top_k=3)],
        k=60,
    )
    final_top = reranker.rerank(query, [d for d, _ in fused], top_k=1)

    assert len(final_top) == 1
    assert final_top[0][0].id == "1"
