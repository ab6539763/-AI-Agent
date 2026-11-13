"""Day 34 单元测试：Ragas 四大 RAG 评估指标与 RAGEvaluator 评测流水线."""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    EvalReport,
    EvalSample,
    RAGEvaluator,
    compute_answer_relevancy,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
)


def test_faithfulness_and_hallucination_detection() -> None:
    """验证 Faithfulness 能准确识别无支撑陈述与数值幻觉."""
    contexts = ["星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。"]

    faithful_answer = "入职满1年员工每年享有5天带薪年假。"
    assert compute_faithfulness(faithful_answer, contexts) == 1.0

    # 半幻觉：1条有支撑 + 1条无支撑
    partial_hallucination = "入职满1年员工每年享有5天带薪年假。公司还为每位员工提供免费班车。"
    assert compute_faithfulness(partial_hallucination, contexts) == 0.5

    # 数值幻觉：上下文为 5天，回答篡改为 15天
    numeric_hallucination = "入职满1年员工每年享有15天带薪年假。"
    assert compute_faithfulness(numeric_hallucination, contexts) == 0.0

    assert compute_faithfulness("", contexts) == 0.0
    assert compute_faithfulness(faithful_answer, []) == 0.0


def test_answer_relevancy_ranking() -> None:
    """验证 Answer Relevancy 对切题回答给出高分，对答非所问给出低分."""
    question = "生产环境 Redis 集群禁止执行什么命令？"
    relevant = "生产环境 Redis 集群禁止执行 KEYS * 命令，建议使用 SCAN 分批遍历。"
    off_topic = "今天北京天气晴朗，食堂午餐提供红烧肉。"

    rel_score = compute_answer_relevancy(question, relevant)
    off_score = compute_answer_relevancy(question, off_topic)

    assert rel_score > 0.55
    assert off_score < 0.25
    assert rel_score > off_score
    assert compute_answer_relevancy(question, "") == 0.0


def test_context_precision_rank_sensitivity() -> None:
    """验证 Context Precision@K 对相关文档排序位置敏感."""
    question = "差旅酒店住宿报销上限是多少？"
    ground_truth = "一线城市酒店住宿报销上限每晚600元，需提供电子发票。"
    rel_ctx = "差旅报销标准：一线城市酒店住宿报销上限每晚600元，需提供电子发票。"
    noise_1 = "公司食堂每周三免费提供水果。"
    noise_2 = "办公用品领用请前往行政前台登记。"

    top_ranked = compute_context_precision(question, [rel_ctx, noise_1, noise_2], ground_truth)
    bottom_ranked = compute_context_precision(question, [noise_1, noise_2, rel_ctx], ground_truth)
    all_noise = compute_context_precision(question, [noise_1, noise_2], ground_truth)

    assert top_ranked == 1.0
    assert abs(bottom_ranked - 0.3333) < 1e-3
    assert top_ranked > bottom_ranked
    assert all_noise == 0.0


def test_context_recall_coverage() -> None:
    """验证 Context Recall 能正确衡量 Ground Truth 事实覆盖率."""
    ground_truth = "入职满1年享有5天带薪年假。申请年假需提前3个工作日在OA系统审批。"

    full_contexts = [
        "入职满1年员工每年享有5天带薪年假。",
        "员工申请年假需提前3个工作日在OA系统提交审批。",
    ]
    partial_contexts = ["入职满1年员工每年享有5天带薪年假。"]
    irrelevant_contexts = ["公司每周五下午举办技术分享会。"]

    assert compute_context_recall(ground_truth, full_contexts) == 1.0
    assert compute_context_recall(ground_truth, partial_contexts) == 0.5
    assert compute_context_recall(ground_truth, irrelevant_contexts) == 0.0


def test_rag_evaluator_dataset_report_and_diagnostics() -> None:
    """验证 RAGEvaluator.evaluate_dataset 生成聚合报告与逐样本诊断."""
    samples = [
        EvalSample(
            sample_id="s1",
            question="年假有几天？",
            answer="入职满1年员工每年享有5天带薪年假。",
            contexts=["星辰数科年假制度：入职满1年员工每年享有5天带薪年假。"],
            ground_truth="入职满1年员工每年享有5天带薪年假。",
        ),
        EvalSample(
            sample_id="s2",
            question="Redis 禁止什么命令？",
            answer="禁止执行 KEYS * 命令。另外必须每周五重启服务器。",
            contexts=["生产环境 Redis 集群禁止执行 KEYS * 命令，请使用 SCAN。"],
            ground_truth="禁止执行 KEYS * 命令，应使用 SCAN 分批遍历。",
        ),
    ]

    evaluator = RAGEvaluator()
    report = evaluator.evaluate_dataset(samples)

    assert isinstance(report, EvalReport)
    assert report.total_samples == 2
    assert len(report.sample_results) == 2
    assert report.sample_results[0].diagnostics == ["healthy"]
    assert "hallucination_risk" in report.sample_results[1].diagnostics
    assert len(report.sample_results[1].unsupported_claims) == 1

    report_dict = report.to_dict()
    assert report_dict["total_samples"] == 2
    assert "mean_faithfulness" in report_dict
    assert "智枢 RAG 评测报告" in report.format_summary()

    empty_report = evaluator.evaluate_dataset([])
    assert empty_report.total_samples == 0
    assert empty_report.overall_score == 0.0
