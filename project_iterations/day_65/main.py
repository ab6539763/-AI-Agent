"""Day 65 启动脚本：运行 3 位企业评委模拟毕业答辩评估并打印结构化评分卡。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from zhishu_agent import (  # noqa: E402
    DefenseRubric,
    JudgeQuestionBank,
    evaluate_defense,
)


def run_simulated_defense() -> None:
    rubric = DefenseRubric()
    bank = JudgeQuestionBank()

    judge_evaluations = [
        {
            "judge_name": "周明远",
            "judge_role": "外部企业 CTO / 架构评审",
            "scores": {
                "business_value": 91.0,
                "architecture_depth": 94.0,
                "engineering_quality": 90.0,
                "demo_fluency": 88.0,
                "qa_performance": 92.0,
            },
            "comment": "混合 RAG 与 HITL 审批状态机闭环扎实，并发路由与幻觉拒答方案具备直接落地价值。",
        },
        {
            "judge_name": "沈清扬",
            "judge_role": "金融合规与安全总监",
            "scores": {
                "business_value": 89.0,
                "architecture_depth": 91.0,
                "engineering_quality": 92.0,
                "demo_fluency": 86.0,
                "qa_performance": 90.0,
            },
            "comment": "Pre-filtering 文档级 ACL、PII 入库前脱敏与 409 幂等校验守住了风控底线。",
        },
        {
            "judge_name": "张工",
            "judge_role": "星辰数科 Tech Lead（内部导师）",
            "scores": {
                "business_value": 90.0,
                "architecture_depth": 93.0,
                "engineering_quality": 91.0,
                "demo_fluency": 87.0,
                "qa_performance": 89.0,
            },
            "comment": "团队协同交付质量高，建议进一步补齐百并发压测数据以完善容量规划。",
        },
    ]

    result = evaluate_defense(
        scores=judge_evaluations,
        rubric=rubric,
        project_name="星辰数科 · 智枢企业级智能体平台 (ZhiShu-Agent v1.0.0-day65)",
        team_name="林晓 / 张工 / 陈默 / 李婷 / 赵磊",
    )

    print(result.to_markdown())

    print("=== 评委高频追问模拟匹配 ===")
    sample_query = "高并发 500 QPS 下 Token 成本和 P99 延迟怎么控制？"
    matches = bank.match_question(sample_query, top_k=2)
    for q, score in matches:
        print(f"- 命中 [{q.question_id}] ({q.category}, 相关度={score}): {q.question}")

    sample_answer = (
        "我们通过语义缓存(Semantic Cache)拦截高频重复问答，引入大小模型分级路由(Router)控制成本，"
        "同时做上下文压缩裁剪与租户级 Token 桶限流熔断，保障 P99 延迟。"
    )
    diag = bank.score_answer("JQ-02", sample_answer)
    print(
        f"模拟应答诊断 -> 覆盖率: {diag['coverage_ratio'] * 100:.0f}% | "
        f"建议得分: {diag['suggested_score']:.1f}"
    )


if __name__ == "__main__":
    run_simulated_defense()
