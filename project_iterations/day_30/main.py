"""Day 30 平台启动入口：端到端企业级 RAG 问答系统演示 (v0.3.0-day30)."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import Document, RAGPipeline


def main() -> None:
    """演示完整 RAG 链路：文档切片入库 -> Top-K 检索 -> 引用生成 -> 低分拒答兜底."""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day30 · 端到端 RAG 问答系统（核心日）")
    print("=" * 68)

    pipeline = RAGPipeline(min_score_threshold=0.15, default_k=2)
    docs = [
        Document(
            id="hr-policy-01",
            page_content=(
                "星辰数科年假制度：员工入职满1年享受5天带薪年假，满10年享受10天带薪年假。"
                "年假需提前3个工作日在 OA 系统提交审批。"
            ),
            metadata={"source": "《星辰数科员工手册 2025》", "department": "hr"},
        ),
        Document(
            id="fin-policy-01",
            page_content=(
                "差旅报销规范：一线城市酒店住宿报销上限为每晚600元，二线城市为每晚450元，"
                "需在出差结束后15天内上传电子发票。"
            ),
            metadata={"source": "《财务差旅报销制度》", "department": "finance"},
        ),
        Document(
            id="it-runbook-01",
            page_content=(
                "Redis 生产运维规范：严禁在生产环境执行 KEYS * 命令以免阻塞主线程，"
                "请统一使用 SCAN 游标分批遍历键空间。"
            ),
            metadata={"source": "《SRE Redis 运维手册》", "department": "it"},
        ),
    ]

    chunk_ids = pipeline.ingest_documents(docs, chunk_size=120, chunk_overlap=20)
    print(f"已完成文档切分与向量入库，总切片数: {len(chunk_ids)}")

    # 1. 正常命中场景（grounded=True）
    q1 = "员工带薪年假有多少天？"
    res1 = pipeline.answer_with_citations(q1)
    print(f"\n[场景 1 · 知识库命中] Q: {q1}")
    print(f"grounded={res1.grounded} | max_score={res1.max_score:.4f}")
    print(res1.answer)
    print("引用溯源:")
    for cite in res1.citations:
        print(f"  [{cite.index}] {cite.source} ({cite.doc_id}, score={cite.score:.4f})")

    # 2. 低相似度兜底拒答场景（grounded=False）
    q2 = "火星殖民地基地的班车几点发车？"
    res2 = pipeline.answer_with_citations(q2)
    print(f"\n[场景 2 · 超出知识库边界] Q: {q2}")
    print(f"grounded={res2.grounded} | max_score={res2.max_score:.4f}")
    print(res2.answer)


if __name__ == "__main__":
    main()
