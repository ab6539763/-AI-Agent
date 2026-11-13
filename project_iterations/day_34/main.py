"""Day 34 平台启动入口：RAG 自动化评估体系（Ragas 四大核心指标）演示 (v0.3.0-day34)."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import EvalSample, RAGEvaluator


def main() -> None:
    """演示企业知识库问答集在 Ragas 四大指标下的自动化评测与诊断."""
    print("=" * 64)
    print("🚀 智枢企业级智能体平台 v0.3.0-day34 · RAG 评估体系 (Ragas)")
    print("=" * 64)

    samples = [
        EvalSample(
            sample_id="qa-001",
            question="星辰数科入职满1年员工每年有多少天带薪年假？",
            answer="星辰数科入职满1年员工每年享有5天带薪年假，满10年享有10天。",
            contexts=[
                "星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。",
                "员工申请年假需提前3个工作日在 OA 系统提交审批。",
            ],
            ground_truth="入职满1年员工每年享有5天带薪年假，满10年享有10天。",
        ),
        EvalSample(
            sample_id="qa-002",
            question="生产环境 Redis 集群禁止执行什么命令？",
            answer="生产环境 Redis 集群禁止执行 KEYS * 命令。此外每天凌晨会自动重启集群。",
            contexts=[
                "生产环境 Redis 集群禁止执行 KEYS * 命令，请使用 SCAN 分批遍历。",
            ],
            ground_truth="生产环境 Redis 集群禁止执行 KEYS * 命令，应使用 SCAN 分批遍历。",
        ),
        EvalSample(
            sample_id="qa-003",
            question="一线城市差旅酒店住宿报销上限是多少？",
            answer="一线城市酒店住宿报销上限为每晚600元，需提供电子发票。",
            contexts=[
                "公司食堂每周三免费提供水果。",
                "办公用品领用请前往行政前台登记。",
                "差旅报销标准：一线城市酒店住宿报销上限每晚600元，需提供电子发票。",
            ],
            ground_truth="一线城市酒店住宿报销上限每晚600元，需提供电子发票。",
        ),
    ]

    evaluator = RAGEvaluator()
    report = evaluator.evaluate_dataset(samples)
    print(report.format_summary())
    print("\n--- 逐样本诊断明细 ---")
    for res in report.sample_results:
        print(
            f"[{res.sample_id}] F={res.faithfulness:.2f} | AR={res.answer_relevancy:.2f} | "
            f"CP={res.context_precision:.2f} | CR={res.context_recall:.2f} | "
            f"诊断={res.diagnostics}"
        )
        if res.unsupported_claims:
            print(f"   ⚠️ 疑似幻觉陈述: {res.unsupported_claims}")
        if res.missing_gt_claims:
            print(f"   ⚠️ 缺失标准事实: {res.missing_gt_claims}")


if __name__ == "__main__":
    main()
