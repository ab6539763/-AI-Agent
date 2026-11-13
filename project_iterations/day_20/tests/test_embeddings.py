"""Day 20 单元测试：多模态消息构造、确定性 Embedding、余弦相似度与语义 FAQ 检索"""
import math
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.embeddings import (
    FAQItem,
    LocalEmbeddingModel,
    SemanticFAQMatcher,
    build_multimodal_message,
    cosine_similarity,
    create_default_faq_matcher,
)


def test_build_multimodal_message_structure():
    msg = build_multimodal_message(
        text="请分析这张架构图",
        image_url="https://example.com/arch.png",
    )
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 2
    assert msg["content"][0] == {"type": "text", "text": "请分析这张架构图"}
    assert msg["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/arch.png", "detail": "auto"},
    }


def test_build_multimodal_message_validation():
    with pytest.raises(ValueError):
        build_multimodal_message("", "https://example.com/a.png")
    with pytest.raises(ValueError):
        build_multimodal_message("看图", "   ")
    with pytest.raises(ValueError):
        build_multimodal_message("看图", "https://example.com/a.png", detail="ultra")


def test_cosine_similarity_exact_values():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == pytest.approx(0.0)


def test_cosine_similarity_dimension_mismatch():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        cosine_similarity([], [])


def test_local_embedding_determinism_and_unit_norm():
    model = LocalEmbeddingModel(dimensions=64)
    v1 = model.embed("报销发票流程")
    v2 = model.embed("报销发票流程")
    assert len(v1) == 64
    assert v1 == v2
    norm = math.sqrt(sum(x * x for x in v1))
    assert norm == pytest.approx(1.0, rel=1e-6)


def test_local_embedding_empty_text_returns_zero_vector():
    model = LocalEmbeddingModel(dimensions=32)
    vec = model.embed("   ")
    assert vec == [0.0] * 32


def test_semantic_similarity_ordering():
    model = LocalEmbeddingModel(dimensions=128)
    base = model.embed("差旅发票怎么提交报销")
    similar = model.embed("出差发票如何报销")
    unrelated = model.embed("Python 异步协程原理")
    assert cosine_similarity(base, similar) > cosine_similarity(base, unrelated)


def test_semantic_faq_matcher_top_k_retrieval():
    matcher = create_default_faq_matcher()
    assert len(matcher) == 5

    res_invoice = matcher.search("出差回来发票怎么报销？", top_k=2)
    assert len(res_invoice) == 2
    assert "报销" in res_invoice[0].question
    assert res_invoice[0].score >= res_invoice[1].score

    res_vpn = matcher.search("VPN 密码忘了怎么重置", top_k=1)
    assert len(res_vpn) == 1
    assert "VPN" in res_vpn[0].question

    res_leave = matcher.search("年假有几天怎么请假", top_k=1)
    assert len(res_leave) == 1
    assert "年假" in res_leave[0].question


def test_semantic_faq_matcher_custom_items_and_min_score():
    matcher = SemanticFAQMatcher()
    matcher.add_faqs([
        FAQItem(question="如何申请 GPU 算力资源", answer="在算力平台提交工单", category="研发"),
        ("食堂几点开饭", "午餐 11:30 开始", "后勤"),
    ])
    assert len(matcher) == 2
    high_threshold = matcher.search("完全不相关的随机词xyz", top_k=2, min_score=0.99)
    assert high_threshold == []

    with pytest.raises(ValueError):
        matcher.search("GPU", top_k=0)
