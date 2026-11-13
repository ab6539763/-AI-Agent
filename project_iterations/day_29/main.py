"""Day 29 平台启动入口：Chroma 兼容本地向量库与 Retriever 检索器演示 (v0.3.0-day29)."""
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import Document, LocalVectorStore


def main() -> None:
    """演示企业知识库入库、元数据过滤、JSON 持久化与 Retriever 统一检索."""
    print("=" * 64)
    print("🚀 智枢企业级智能体平台 v0.3.0-day29 · 本地向量数据库与 Retriever")
    print("=" * 64)

    docs = [
        Document(
            id="hr-001",
            page_content="星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。",
            metadata={"department": "hr", "year": 2025, "doc_type": "policy"},
        ),
        Document(
            id="hr-002",
            page_content="员工差旅报销规范：一线城市住宿标准为每晚600元以内，需提供电子发票。",
            metadata={"department": "finance", "year": 2025, "doc_type": "policy"},
        ),
        Document(
            id="it-001",
            page_content="生产环境 Redis 集群禁止执行 KEYS * 命令，请使用 SCAN 分批遍历。",
            metadata={"department": "it", "year": 2025, "doc_type": "runbook"},
        ),
        Document(
            id="it-002",
            page_content="智枢平台 RAG 检索默认召回 Top-3 文档片段，并支持按部门元数据过滤。",
            metadata={"department": "it", "year": 2026, "doc_type": "architecture"},
        ),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalVectorStore(collection_name="zhishu_kb", persist_directory=tmp_dir)
        store.add_documents(docs)
        saved_path = store.save()
        print(f"已入库 {store.count()} 条文档，并持久化至: {saved_path}")

        reloaded = LocalVectorStore.load(saved_path)
        retriever = reloaded.as_retriever(search_kwargs={"k": 2})

        query = "年假有几天？"
        results = retriever.invoke(query)
        print(f"\n[全库检索] Query: {query}")
        for idx, doc in enumerate(results, start=1):
            print(f"  Top-{idx} ({doc.id}, {doc.metadata}): {doc.page_content}")

        it_results = reloaded.similarity_search_with_score(
            "Redis 命令规范",
            k=2,
            filter_metadata={"department": "it"},
        )
        print("\n[元数据过滤 department=it] Query: Redis 命令规范")
        for doc, score in it_results:
            print(f"  score={score:.4f} | {doc.id}: {doc.page_content}")


if __name__ == "__main__":
    main()
