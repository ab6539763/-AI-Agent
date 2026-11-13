"""Day 32 自动化单元测试：覆盖 QueryRewriter、MultiQueryRetriever、HyDERetriever 与 ContextCompressor。"""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    ContextCompressor,
    Document,
    HyDERetriever,
    LocalVectorStore,
    MultiQueryRetriever,
    QueryRewriter,
)


@pytest.fixture()
def kb_store() -> LocalVectorStore:
    store = LocalVectorStore(collection_name="test_adv_rag")
    store.add_documents(
        [
            Document(
                id="hr-leave",
                page_content=(
                    "星辰数科考勤总则：全体员工遵守弹性打卡制度。"
                    "入职满1年的员工每年享有5天带薪年假，满10年享有10天带薪年假。"
                    "公司食堂每周三免费供应水果。"
                ),
                metadata={"department": "hr", "year": 2025},
            ),
            Document(
                id="fin-travel",
                page_content=(
                    "差旅费用报销标准：出差前须提交审批单。"
                    "一线城市酒店住宿报销上限为每晚600元，需上传合规电子发票。"
                ),
                metadata={"department": "finance", "year": 2025},
            ),
            Document(
                id="it-oom",
                page_content=(
                    "Kubernetes Pod 内存溢出（OOMKilled）排查指南：退出码 137 表示触发内核 OOM。"
                    "请检查容器内存限制与 JVM -Xmx 参数配置，并分析 heap dump 排查内存泄漏。"
                ),
                metadata={"department": "it", "year": 2026},
            ),
        ]
    )
    return store


def test_query_rewriter_history_and_custom_llm() -> None:
    """验证 QueryRewriter 的口语清洗、多轮指代消解及自定义 LLM 回调。"""
    rewriter = QueryRewriter()

    assert rewriter.rewrite("   ") == ""

    history = [{"role": "user", "content": "年假制度"}]
    rewritten = rewriter.rewrite("请问一下它一般有几天呀？", chat_history=history)
    assert "年假制度" in rewritten
    assert "请问一下" not in rewritten
    assert "它" not in rewritten

    # Runnable invoke 接口兼容
    assert rewriter.invoke({"query": "报销怎么算？"}) != ""

    # 自定义 llm_fn 优先路径
    custom_rewriter = QueryRewriter(llm_fn=lambda prompt: "带薪年假天数标准")
    assert custom_rewriter.rewrite("年假几天") == "带薪年假天数标准"


def test_multi_query_retriever_dedup_and_rrf(kb_store: LocalVectorStore) -> None:
    """验证 MultiQueryRetriever 生成多视角变体、去重及 RRF 融合排序。"""
    base_retriever = kb_store.as_retriever(search_kwargs={"k": 2})
    mq = MultiQueryRetriever(retriever=base_retriever, num_queries=3)

    docs, variants = mq.retrieve_with_details("年假几天", k=2)
    assert len(variants) == 3
    assert len(set(v.lower() for v in variants)) == 3
    assert len(docs) == 2
    # 验证无重复 ID
    doc_ids = [d.id for d in docs]
    assert len(doc_ids) == len(set(doc_ids))
    assert doc_ids[0] == "hr-leave"

    # 自定义 query_generator
    custom_mq = MultiQueryRetriever(
        retriever=base_retriever,
        query_generator=lambda q, n: ["差旅住宿标准", "电子发票报销上限"],
        num_queries=2,
        include_original=False,
    )
    custom_docs = custom_mq.invoke("出差住酒店", k=1)
    assert len(custom_docs) == 1
    assert custom_docs[0].id == "fin-travel"


def test_hyde_retriever_hypothesis_and_filter(kb_store: LocalVectorStore) -> None:
    """验证 HyDERetriever 生成假设文档、向量检索与元数据过滤。"""
    hyde = HyDERetriever(vector_store=kb_store, k=2)
    hypo, docs = hyde.retrieve_with_hypothesis("Pod 老是 OOM 怎么办")

    assert len(hypo) > 10
    assert "OOMKilled" in hypo or "内存" in hypo
    assert len(docs) >= 1
    assert docs[0].id == "it-oom"

    # 带元数据过滤的检索
    hr_only = hyde.invoke("休假天数", k=2, filter_metadata={"department": "hr"})
    assert len(hr_only) == 1
    assert hr_only[0].id == "hr-leave"

    # 空查询边界
    assert hyde.retrieve("   ") == []


def test_context_compressor_extracts_relevant_sentences(kb_store: LocalVectorStore) -> None:
    """验证 ContextCompressor 只保留与 Query 相关的句子并记录压缩统计。"""
    raw_docs = kb_store.similarity_search("带薪年假有几天", k=2)
    compressor = ContextCompressor(min_score=0.20, max_sentences_per_doc=1)

    compressed = compressor.compress_documents("带薪年假有几天", raw_docs, drop_empty=True)
    assert len(compressed) >= 1
    top_compressed = compressed[0]
    assert top_compressed.id == "hr-leave"
    assert "5天带薪年假" in top_compressed.page_content
    assert "食堂" not in top_compressed.page_content
    assert top_compressed.metadata["compressed"] is True
    assert top_compressed.metadata["compressed_chars"] < top_compressed.metadata["original_chars"]

    # drop_empty=False 时即使低于阈值也保留最相关的一句
    strict_compressor = ContextCompressor(min_score=0.99, max_sentences_per_doc=1)
    assert strict_compressor.compress_documents("无关查询", raw_docs, drop_empty=True) == []
    kept = strict_compressor.compress_documents("无关查询", raw_docs, drop_empty=False)
    assert len(kept) == len(raw_docs)
