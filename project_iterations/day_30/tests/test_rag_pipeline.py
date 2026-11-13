"""Day 30 自动化单元测试：覆盖端到端 RAG 流水线、文本切分、引用溯源、LLM 注入与低分拒答兜底."""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    FALLBACK_ANSWER,
    Document,
    LocalVectorStore,
    RAGAnswer,
    RAGPipeline,
    answer_with_citations,
    build_rag_prompt,
    ingest_documents,
    retrieve,
    split_text,
)


@pytest.fixture()
def populated_pipeline() -> RAGPipeline:
    pipeline = RAGPipeline(min_score_threshold=0.15, default_k=2)
    docs = [
        Document(
            id="hr-001",
            page_content="星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天带薪年假。",
            metadata={"source": "员工手册-年假篇", "department": "hr"},
        ),
        Document(
            id="fin-001",
            page_content="差旅报销规范：一线城市住宿报销标准为每晚600元以内，需提供电子发票。",
            metadata={"source": "财务报销制度", "department": "finance"},
        ),
        Document(
            id="it-001",
            page_content="生产环境 Redis 集群禁止执行 KEYS * 命令，统一使用 SCAN 分批遍历。",
            metadata={"source": "SRE 运维手册", "department": "it"},
        ),
    ]
    pipeline.ingest_documents(docs)
    return pipeline


def test_split_text_and_ingest_long_document() -> None:
    """验证长文档按 chunk_size / chunk_overlap 切分并保留元数据."""
    long_text = "第一段：星辰数科智枢平台采用模块化设计。" * 8
    chunks = split_text(long_text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 1
    assert all(len(c) <= 50 for c in chunks)

    store = LocalVectorStore()
    ids = ingest_documents(
        store,
        [Document(id="arch-1", page_content=long_text, metadata={"source": "架构白皮书"})],
        chunk_size=50,
        chunk_overlap=10,
    )
    assert len(ids) == len(chunks)
    assert ids[0] == "arch-1#chunk-0"
    assert store.count() == len(chunks)


def test_retrieve_and_build_rag_prompt(populated_pipeline: RAGPipeline) -> None:
    """验证 retrieve Top-K 召回与 build_rag_prompt 引用编号及防幻觉指令."""
    retrieved = populated_pipeline.retrieve("带薪年假有多少天？", k=2)
    assert len(retrieved) == 2
    top_doc, top_score = retrieved[0]
    assert top_doc.id == "hr-001"
    assert top_score >= 0.15

    prompt = populated_pipeline.build_rag_prompt("带薪年假有多少天？", retrieved)
    assert "【参考上下文】" in prompt
    assert "[1]" in prompt
    assert "员工手册-年假篇" in prompt
    assert FALLBACK_ANSWER in prompt


def test_answer_with_citations_grounded(populated_pipeline: RAGPipeline) -> None:
    """验证命中知识库时返回 grounded=True 且包含结构化 Citation."""
    result = populated_pipeline.answer_with_citations("员工年假有几天？")
    assert isinstance(result, RAGAnswer)
    assert result.grounded is True
    assert result.max_score >= 0.15
    assert len(result.citations) == 2
    assert result.citations[0].index == 1
    assert result.citations[0].doc_id == "hr-001"
    assert result.citations[0].source == "员工手册-年假篇"
    assert "[1]" in result.answer


def test_low_score_fallback_when_out_of_domain(populated_pipeline: RAGPipeline) -> None:
    """验证当最高相似度低于 min_score_threshold 时触发安全拒答兜底."""
    result = populated_pipeline.answer_with_citations(
        "火星移民基地班车时刻表是什么？",
        min_score_threshold=0.20,
    )
    assert result.grounded is False
    assert result.citations == []
    assert FALLBACK_ANSWER in result.answer


def test_empty_store_and_custom_llm_fn() -> None:
    """验证空库安全兜底以及自定义 llm_fn 注入调用."""
    empty_store = LocalVectorStore()
    empty_res = answer_with_citations(empty_store, "任意问题")
    assert empty_res.grounded is False
    assert empty_res.citations == []
    assert FALLBACK_ANSWER in empty_res.answer

    # 测试函数式 API + 自定义 llm_fn
    store = LocalVectorStore()
    ingest_documents(
        store,
        [Document(id="sec-1", page_content="生产数据库密码每90天轮换一次。", metadata={"source": "安全基线"})],
    )
    captured_prompts: list[str] = []

    def mock_llm(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "生产数据库密码需每90天轮换一次 [1]。"

    res = answer_with_citations(
        store=store,
        query="数据库密码多久轮换？",
        k=1,
        min_score_threshold=0.10,
        llm_fn=mock_llm,
    )
    assert res.grounded is True
    assert res.answer == "生产数据库密码需每90天轮换一次 [1]。"
    assert len(captured_prompts) == 1
    assert "[1]" in captured_prompts[0]
    assert len(retrieve(store, "数据库密码", k=1)) == 1
    assert "数据库密码多久轮换？" in build_rag_prompt("数据库密码多久轮换？", retrieve(store, "数据库密码", k=1))
