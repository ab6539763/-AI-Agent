"""Day 35 单元测试：LlamaIndex 核心抽象与 LangChain 对比工具."""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    Document,
    Node,
    QueryResponse,
    SimpleDirectoryReader,
    VectorStoreIndex,
    compare_frameworks,
    format_framework_comparison,
)


def test_simple_directory_reader_with_tmp_path(tmp_path: Path) -> None:
    """验证 SimpleDirectoryReader 能正确读取目录文档、过滤扩展名与空文件."""
    (tmp_path / "policy.md").write_text("入职满1年享有5天带薪年假。", encoding="utf-8")
    (tmp_path / "empty.txt").write_text("   \n  ", encoding="utf-8")
    (tmp_path / "ignore.bin").write_text("binary-ignored", encoding="utf-8")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "ops.txt").write_text("生产环境禁止执行 KEYS *。", encoding="utf-8")

    # 非递归模式仅读取根目录有效文件
    docs = SimpleDirectoryReader(tmp_path).load_data()
    assert len(docs) == 1
    assert docs[0].metadata["file_name"] == "policy.md"
    assert docs[0].doc_id.startswith("doc-")

    # 递归模式读取包含子目录的文档
    recursive_docs = SimpleDirectoryReader(tmp_path, recursive=True).load_data()
    assert len(recursive_docs) == 2
    names = {d.metadata["file_name"] for d in recursive_docs}
    assert names == {"policy.md", "ops.txt"}

    with pytest.raises(FileNotFoundError):
        SimpleDirectoryReader(tmp_path / "non_existent").load_data()


def test_vector_store_index_nodes_and_retrieval(tmp_path: Path) -> None:
    """验证 VectorStoreIndex.from_documents 构建 Node 关系链并准确检索 Top-K."""
    long_text = (
        "第一段：星辰数科年假制度规定入职满1年员工每年享有5天带薪年假。"
        "第二段：员工申请年假需提前3个工作日在 OA 系统提交审批。"
        "第三段：差旅报销标准规定一线城市酒店住宿上限每晚600元。"
    )
    (tmp_path / "handbook.md").write_text(long_text, encoding="utf-8")
    (tmp_path / "redis.txt").write_text("生产环境 Redis 集群严禁执行 KEYS * 命令，请使用 SCAN。", encoding="utf-8")

    docs = SimpleDirectoryReader(tmp_path).load_data()
    index = VectorStoreIndex.from_documents(docs, chunk_size=55, chunk_overlap=10)

    assert len(index.nodes) >= 3
    # 验证同一文档切片具备 PREVIOUS / NEXT 关系链
    handbook_nodes = [n for n in index.nodes if n.metadata.get("file_name") == "handbook.md"]
    assert len(handbook_nodes) >= 2
    assert "SOURCE" in handbook_nodes[0].relationships
    assert handbook_nodes[0].relationships.get("NEXT") == handbook_nodes[1].node_id
    assert handbook_nodes[1].relationships.get("PREVIOUS") == handbook_nodes[0].node_id

    # 验证检索排序相关性
    results = index.retrieve("Redis 集群禁止执行什么命令？", similarity_top_k=2)
    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert "Redis" in results[0].node.text


def test_query_engine_modes_and_validation() -> None:
    """验证 QueryEngine 无状态单轮问答与三种 response_mode."""
    docs = [
        Document(
            text="一线城市酒店住宿报销上限每晚600元，需提供电子发票。",
            metadata={"file_name": "travel.md"},
        ),
        Document(
            text="生产环境 Redis 禁止执行 KEYS * 命令，应使用 SCAN 分批遍历。",
            metadata={"file_name": "redis.md"},
        ),
    ]
    index = VectorStoreIndex.from_documents(docs)

    for mode in ("compact", "refine", "tree_summarize"):
        qe = index.as_query_engine(similarity_top_k=2, response_mode=mode)
        res = qe.query("一线城市酒店报销上限是多少？")
        assert isinstance(res, QueryResponse)
        assert "600" in res.response
        assert res.metadata["response_mode"] == mode
        assert "travel.md" in res.format_sources()

    empty_res = index.as_query_engine().query("   ")
    assert "有效" in empty_res.response

    with pytest.raises(ValueError):
        index.as_query_engine(response_mode="invalid_mode")


def test_chat_engine_multi_turn_and_reset(tmp_path: Path) -> None:
    """验证 ChatEngine 多轮追问改写与历史重置功能."""
    (tmp_path / "leave.md").write_text(
        "星辰数科年假制度：入职满1年员工每年享有5天带薪年假。申请年假需提前3个工作日在 OA 系统审批。",
        encoding="utf-8",
    )
    docs = SimpleDirectoryReader(tmp_path).load_data()
    index = VectorStoreIndex.from_documents(docs, chunk_size=120, chunk_overlap=20)
    chat_engine = index.as_chat_engine(similarity_top_k=2)

    turn1 = chat_engine.chat("入职满1年员工每年有多少天带薪年假？")
    assert "5天" in turn1.response
    assert len(chat_engine.chat_history) == 2

    # 指代性短追问应触发历史上下文改写
    turn2 = chat_engine.chat("申请它需要提前几天？")
    assert "年假" in turn2.metadata["condensed_query"]
    assert "3个工作日" in turn2.response
    assert turn2.metadata["history_turns"] == 2

    chat_engine.reset()
    assert chat_engine.chat_history == []


def test_compare_frameworks_and_formatter() -> None:
    """验证 compare_frameworks() 对比维度完整性与场景选型推荐."""
    base = compare_frameworks()
    assert base["frameworks"] == ["LangChain", "LlamaIndex"]
    assert len(base["dimensions"]) >= 5

    rag_rec = compare_frameworks(use_case="enterprise_rag")
    assert rag_rec["recommendation"]["recommended"] == "LlamaIndex"

    hybrid_rec = compare_frameworks(use_case="hybrid")
    assert "LangChain" in hybrid_rec["recommendation"]["recommended"]
    assert "LlamaIndex" in hybrid_rec["recommendation"]["recommended"]

    formatted = format_framework_comparison(use_case="multi_agent_workflow")
    assert "LangChain + LangGraph" in formatted

    with pytest.raises(ValueError):
        compare_frameworks(use_case="unknown_case")
