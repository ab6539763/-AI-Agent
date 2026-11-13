"""Day 31 平台启动入口：Week 5 RAG 切分与检索超参数网格调优实验台 (v0.3.0-day31)."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import EvalQAPair, TuningConfig, run_grid_experiment


def main() -> None:
    """运行企业知识库 RAG 超参数网格实验并输出 Hit Rate@K 与 MRR 排行榜."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.3.0-day31 · Week 5 RAG 调优实验台")
    print("=" * 72)

    corpus = [
        {
            "id": "hr-policy",
            "content": (
                "星辰数科员工休假制度：入职满1年的正式员工每年享有5天带薪年假，"
                "入职满10年享有10天带薪年假。请假超过3天需由部门总监审批。"
            ),
        },
        {
            "id": "fin-reimburse",
            "content": (
                "差旅报销规范：一线城市酒店住宿标准上限为每晚600元，二线城市为每晚450元。"
                "员工出差需在返程后7个工作日内通过智枢财务系统提交电子发票。"
            ),
        },
        {
            "id": "it-redis",
            "content": (
                "生产环境 Redis 运维红线：严禁在生产主库执行 KEYS * 或 FLUSHALL 命令，"
                "批量遍历键空间必须使用 SCAN 命令并控制 COUNT 参数。"
            ),
        },
        {
            "id": "rag-arch",
            "content": (
                "智枢 RAG 检索架构：采用递归切分与向量检索结合，支持按 department 元数据预过滤，"
                "默认推荐使用 chunk_size=80、chunk_overlap=20 与 top_k=2。"
            ),
        },
    ]

    eval_qa_pairs = [
        EvalQAPair(
            query="入职满1年有几天带薪年假？",
            expected_keywords=("5天带薪年假",),
            relevant_doc_ids=("hr-policy",),
        ),
        EvalQAPair(
            query="一线城市出差住宿每晚报销上限是多少？",
            expected_keywords=("600元",),
            relevant_doc_ids=("fin-reimburse",),
        ),
        EvalQAPair(
            query="生产环境 Redis 禁止执行什么命令？",
            expected_keywords=("KEYS *", "SCAN"),
            relevant_doc_ids=("it-redis",),
        ),
        EvalQAPair(
            query="智枢 RAG 默认推荐什么切分和检索参数？",
            expected_keywords=("chunk_size=80", "top_k=2"),
            relevant_doc_ids=("rag-arch",),
        ),
    ]

    configs = [
        TuningConfig(chunk_size=30, chunk_overlap=0, top_k=1),
        TuningConfig(chunk_size=50, chunk_overlap=10, top_k=2),
        TuningConfig(chunk_size=80, chunk_overlap=20, top_k=2),
        TuningConfig(chunk_size=120, chunk_overlap=20, top_k=3),
    ]

    report = run_grid_experiment(corpus=corpus, eval_qa_pairs=eval_qa_pairs, configs=configs)
    print("\n📊 网格实验结果排行榜（按 MRR 与 Hit Rate@K 排序）：\n")
    print(report.summary_table())

    best = report.best_result
    print(
        f"\n🏆 最优配置: {best.config.label} | "
        f"Hit Rate@K={best.hit_rate:.2%}, MRR={best.mrr:.4f}"
    )


if __name__ == "__main__":
    main()
