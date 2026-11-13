"""Day 32 平台启动入口：高级 RAG Part 1（Query Rewriting、Multi-Query、HyDE、Context Compression）演示 (v0.3.0-day32)."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
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


def main() -> None:
    """演示查询改写、多路查询去重、HyDE 假设文档检索与上下文压缩全流程。"""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.3.0-day32 · 高级 RAG Part 1：查询变换与压缩")
    print("=" * 72)

    docs = [
        Document(
            id="hr-001",
            page_content=(
                "星辰数科考勤与假期制度总则：所有正式员工均享有法定节假日。"
                "入职满1年的员工每年享有5天带薪年假，满10年享有10天。"
                "年假需提前3个工作日通过 OA 系统提交审批。公司食堂每周五提供下午茶。"
            ),
            metadata={"department": "hr", "year": 2025},
        ),
        Document(
            id="fin-001",
            page_content=(
                "员工差旅费用报销规范：出差前需在系统填写出差申请单。"
                "一线城市住宿标准为每晚600元以内，二线城市为每晚450元以内，需提供合规电子发票。"
                "高铁二等座按实际票面金额报销。"
            ),
            metadata={"department": "finance", "year": 2025},
        ),
        Document(
            id="it-001",
            page_content=(
                "Kubernetes 容器内存溢出（OOMKilled）排查手册：当 Pod 频繁重启且退出码为 137 时，"
                "首先检查容器 limits.memory 配置与 JVM -Xmx 堆参数是否匹配。"
                "其次通过 heap dump 与监控面板排查内存泄漏和大对象缓存问题。"
                "日常巡检请在每周一上午 10 点前完成记录。"
            ),
            metadata={"department": "it", "year": 2026},
        ),
    ]

    store = LocalVectorStore(collection_name="zhishu_adv_rag")
    store.add_documents(docs)
    base_retriever = store.as_retriever(search_kwargs={"k": 2})

    # 1. Query Rewriting（多轮指代消解 + 口语清洗）
    rewriter = QueryRewriter()
    history = [{"role": "user", "content": "年假制度"}]
    raw_query = "请问一下它一般有几天呀？"
    rewritten_query = rewriter.rewrite(raw_query, chat_history=history)
    print(f"\n[1. QueryRewriter] 原始提问: {raw_query}")
    print(f"                   改写结果: {rewritten_query}")

    # 2. Multi-Query Retrieval（多路查询生成 + RRF 融合去重）
    multi_retriever = MultiQueryRetriever(retriever=base_retriever, num_queries=3)
    mq_docs, variants = multi_retriever.retrieve_with_details("年假几天", k=2)
    print(f"\n[2. MultiQueryRetriever] 生成变体 ({len(variants)} 条): {variants}")
    print(f"                         去重召回 ID: {[d.id for d in mq_docs]}")

    # 3. HyDE（假设文档向量检索）
    hyde = HyDERetriever(vector_store=store, k=2)
    hypo_doc, hyde_docs = hyde.retrieve_with_hypothesis("Pod 老是 OOM 怎么办")
    print(f"\n[3. HyDERetriever] 假设文档: {hypo_doc}")
    print(f"                   召回 Top-1: {hyde_docs[0].id} -> {hyde_docs[0].page_content[:48]}...")

    # 4. Context Compression（句子级上下文压缩）
    compressor = ContextCompressor(min_score=0.18, max_sentences_per_doc=2)
    compressed_docs = compressor.compress_documents("年假有几天", mq_docs)
    print("\n[4. ContextCompressor] 上下文压缩对比:")
    for doc in compressed_docs:
        print(
            f"  - {doc.id}: {doc.metadata['original_chars']} 字符 -> "
            f"{doc.metadata['compressed_chars']} 字符 "
            f"(压缩率 {doc.metadata['compression_ratio']:.0%})"
        )
        print(f"    提炼内容: {doc.page_content}")


if __name__ == "__main__":
    main()
