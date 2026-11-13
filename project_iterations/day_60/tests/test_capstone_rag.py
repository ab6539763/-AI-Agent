"""Day 60 (v1.0.0-day60) 毕业设计核心混合 RAG + 可溯源引用主链路单元测试."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (  # noqa: E402
    BM25Index,
    CapstoneRAGEngine,
    CrossReranker,
    DeterministicEmbedder,
    KnowledgeChunk,
    VectorIndex,
    reciprocal_rank_fusion,
    tokenize_mixed,
)


def _sample_chunks() -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            chunk_id="c-1",
            doc_id="d-fin",
            title="差旅报销制度",
            section="报销时效",
            source="finance.md",
            content="员工出差结束后需在 15 个工作日内提交差旅报销单，单笔超过 5000 元需总监审批。",
        ),
        KnowledgeChunk(
            chunk_id="c-2",
            doc_id="d-sre",
            title="生产故障排查手册",
            section="ERR_502 处理",
            source="sre_runbook.md",
            content="网关出现 ERR_502 时，请先检查 vLLM GPU 显存水位及 Nginx proxy_read_timeout 是否大于 120s。",
        ),
        KnowledgeChunk(
            chunk_id="c-3",
            doc_id="d-sec",
            title="数据安全合规规范",
            section="PII 脱敏",
            source="security.md",
            content="用户身份证号、银行卡号和手机号在进入大模型前必须脱敏，审计日志不得保留明文 PII。",
        ),
        KnowledgeChunk(
            chunk_id="c-4",
            doc_id="d-hr",
            title="年假与考勤制度",
            section="年假天数",
            source="hr_handbook.md",
            content="入职满 1 年不满 10 年的员工每年享有 5 天带薪年假，年假可拆分为半天申请。",
        ),
    ]


def test_tokenize_and_embedder_normalization() -> None:
    tokens = tokenize_mixed("ERR_502 网关超时排查")
    assert "err_502" in tokens
    assert "网关" in tokens

    embedder = DeterministicEmbedder(dim=128)
    v1 = embedder.embed_query("差旅报销单提交时效")
    v2 = embedder.embed_query("差旅报销单提交时间")
    v3 = embedder.embed_query("量子计算超导比特")
    assert len(v1) == 128
    assert embedder.cosine_similarity(v1, v2) > embedder.cosine_similarity(v1, v3)


def test_bm25_and_rrf_fusion() -> None:
    chunks = _sample_chunks()
    bm25 = BM25Index()
    bm25.add_chunks(chunks)
    bm25_hits = bm25.search("ERR_502 显存", top_k=3)
    assert bm25_hits
    assert bm25_hits[0][0].chunk_id == "c-2"

    vec_idx = VectorIndex()
    vec_idx.add_chunks(chunks)
    vec_hits = vec_idx.search("ERR_502 网关超时", top_k=3)
    assert vec_hits

    fused = reciprocal_rank_fusion(bm25_hits, vec_hits, k=60, top_k=3)
    assert fused[0].chunk.chunk_id == "c-2"
    assert fused[0].bm25_rank == 1
    assert fused[0].rrf_score > 0.0

    with pytest.raises(ValueError):
        reciprocal_rank_fusion(bm25_hits, vec_hits, k=0)


def test_reranker_scores_relevant_chunk_highest() -> None:
    chunks = _sample_chunks()
    bm25 = BM25Index()
    bm25.add_chunks(chunks)
    vec_idx = VectorIndex()
    vec_idx.add_chunks(chunks)

    query = "入职满3年有多少天带薪年假？"
    fused = reciprocal_rank_fusion(
        bm25.search(query, top_k=4),
        vec_idx.search(query, top_k=4),
        top_k=4,
    )
    reranked = CrossReranker().rerank(query, fused, top_k=3)
    assert reranked[0].chunk.chunk_id == "c-4"
    assert 0.0 < reranked[0].rerank_score <= 1.0


def test_capstone_rag_engine_grounded_answer_with_citations() -> None:
    engine = CapstoneRAGEngine(min_confidence=0.20, max_citations=2)
    count = engine.index_documents(_sample_chunks())
    assert count == 4
    assert engine.stats()["indexed_chunks"] == 4

    resp = engine.query("差旅报销单需要在多少个工作日内提交？")
    assert resp.refused is False
    assert resp.refusal_reason is None
    assert resp.confidence >= 0.20
    assert len(resp.citations) >= 1
    assert resp.citations[0].chunk_id == "c-1"
    assert resp.citations[0].source == "finance.md"
    assert "[1]" in resp.answer

    # 校验正文中出现的每个 [i] 引用编号均在 citations 列表中真实存在
    inline_ids = {int(m) for m in re.findall(r"\[(\d+)\]", resp.answer)}
    citation_ids = {c.citation_id for c in resp.citations}
    assert inline_ids.issubset(citation_ids)

    payload = resp.to_dict()
    assert payload["refused"] is False
    assert payload["citations"][0]["chunk_id"] == "c-1"


def test_capstone_rag_engine_low_confidence_refusal() -> None:
    engine = CapstoneRAGEngine(min_confidence=0.25)
    engine.index_documents(_sample_chunks())

    out_of_domain = engine.query("明天沪深300股票指数会涨吗？")
    assert out_of_domain.refused is True
    assert out_of_domain.citations == []
    assert out_of_domain.refusal_reason is not None
    assert "拒答" in out_of_domain.answer

    empty_resp = engine.query("   ")
    assert empty_resp.refused is True
    assert empty_resp.citations == []
