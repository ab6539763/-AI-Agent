"""Day 63 入口脚本：智枢企业级智能体平台 Ragas 评估与性能/成本压测优化报告 (v1.0.0-day63)。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.capstone_eval import (
    OptimizationAdvisor,
    build_sample_capstone_cases,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行智枢平台 Capstone Ragas 评估与性能/成本优化压测"
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="输出格式：json、markdown 或 both（默认）",
    )
    parser.add_argument(
        "--rerank-top-k",
        type=int,
        default=2,
        help="Rerank 精排保留的上下文数量（默认 2）",
    )
    args = parser.parse_args()

    cases = build_sample_capstone_cases()
    advisor = OptimizationAdvisor()
    comparison = advisor.compare(cases, rerank_top_k=args.rerank_top_k)

    if args.format in ("markdown", "both"):
        print(comparison.baseline.to_markdown())
        print("\n" + "=" * 72 + "\n")
        print(comparison.to_markdown())

    if args.format in ("json", "both"):
        summary_payload = {
            "version": "v1.0.0-day63",
            "baseline_ragas": comparison.baseline.overall_ragas_score,
            "optimized_ragas": comparison.optimized.overall_ragas_score,
            "baseline_p95_ms": comparison.baseline.benchmark.p95_ms,
            "optimized_p95_ms": comparison.optimized.benchmark.p95_ms,
            "latency_p95_reduction_pct": comparison.latency_p95_reduction_pct,
            "baseline_cost_per_1k_cny": comparison.baseline.benchmark.cost_per_1k_req_cny,
            "optimized_cost_per_1k_cny": comparison.optimized.benchmark.cost_per_1k_req_cny,
            "cost_reduction_pct": comparison.cost_reduction_pct,
            "monthly_savings_cny_at_100k_req": comparison.monthly_savings_cny_at_100k_req,
        }
        print("\n[JSON Summary]")
        print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
