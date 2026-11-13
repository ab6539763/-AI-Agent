"""Day 33 平台启动入口：高级 RAG Part 2 — BM25 + 向量混合检索、RRF、重排与父文档检索 (v0.3.0-day33)."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
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


def main() -> None:
    """演示混合检索 + RRF 融合 + CrossEncoder 精排 + ParentDocumentRetriever 全链路."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.3.0-day33 · 高级 RAG 混合检索与父文档检索")
    print("=" * 72)

    docs = [
        Document(
            id="runbook-502",
            page_content=(
                "【生产排障】错误码 ERR_NGX_502 处理手册：当网关出现 502 Bad Gateway 时，"
                "首先检查上游 Pod 是否发生 OOMKilled，并核对 upstream keepalive_timeout 配置。"
            ),
            metadata={"department": "ops", "doc_type": "runbook"},
        ),
        Document(
            id="arch-rag",
            page_content=(
                "【架构规范】智枢平台 RAG 检索链路采用 BM25 稀疏检索与向量稠密检索双路召回，"
                "通过 RRF（倒数排名融合）合并候选集，再经 Cross-Encoder 精排返回 Top-K。"
            ),
            metadata={"department": "ai", "doc_type": "architecture"},
        ),
        Document(
            id="hr-leave",
            page_content=(
                "【人事制度】星辰数科年假规定：入职满 1 年享受 5 天带薪年假，"
                "需提前 3 个工作日在 OA 系统提交休假审批。"
            ),
            metadata={"department": "hr", "doc_type": "policy"},
        ),
        Document(
            id="fin-reimburse",
            page_content=(
                "【财务规范】差旅报销标准：一线城市住宿每晚不超过 600 元，需附电子发票。"
            ),
            metadata={"department": "finance", "doc_type": "policy"},
        ),
    ]

    bm25 = BM25Retriever(docs)
    vector = VectorRetriever(docs)
    reranker = CrossEncoderReranker()

    query = "ERR_NGX_502 网关报错怎么排查"
    bm25_hits = bm25.retrieve(query, top_k=3)
    vec_hits = vector.retrieve(query, top_k=3)
    rrf_hits = reciprocal_rank_fusion([bm25_hits, vec_hits], k=60)
    reranked = reranker.rerank(query, [doc for doc, _ in rrf_hits], top_k=2)

    print(f"\n[1] 混合检索 + RRF + 重排 Query: {query}")
    print("  BM25 Top-3:", [d.id for d in bm25_hits])
    print("  Vector Top-3:", [d.id for d in vec_hits])
    print("  RRF 融合:", [(d.id, round(s, 4)) for d, s in rrf_hits])
    print("  CrossEncoder 精排 Top-2:", [(d.id, round(s, 4)) for d, s in reranked])

    parent_docs = [
        Document(
            id="handbook-k8s",
            page_content=(
                "第一章 集群概述：智枢生产集群部署于多可用区。"
                "第二章 内存故障排查：当容器内存超过 limits 时会触发 OOMKilled（退出码 137），"
                "此时应使用 kubectl describe pod 查看 Last State 并调大 memory limit。"
                "第三章 网络策略：默认启用 Calico NetworkPolicy 隔离命名空间。"
            ),
            metadata={"source": "k8s_handbook.md"},
        ),
        Document(
            id="handbook-git",
            page_content=(
                "第一章 分支模型：主干分支为 main，功能开发统一从 main 拉取 feature 分支。"
                "第二章 提交规范：提交信息需遵循 Conventional Commits，例如 feat(day-33): 新增混合检索。"
            ),
            metadata={"source": "git_handbook.md"},
        ),
    ]

    parent_retriever = ParentDocumentRetriever(chunk_size=75, chunk_overlap=15)
    chunk_count = parent_retriever.add_documents(parent_docs)
    parent_hits = parent_retriever.retrieve_with_matched_children("OOMKilled 退出码 137", top_k=1)

    print(f"\n[2] ParentDocumentRetriever（已切分 {chunk_count} 个子切片）")
    for parent_doc, child_doc, score in parent_hits:
        print(f"  命中子切片 ({child_doc.id}, rrf={score:.4f}): {child_doc.page_content}")
        print(f"  返回完整父文档 ({parent_doc.id}, 长度={len(parent_doc.page_content)}): {parent_doc.page_content}")


if __name__ == "__main__":
    main()
