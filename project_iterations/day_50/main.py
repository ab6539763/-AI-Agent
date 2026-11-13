"""Day 50 平台启动入口：Stage 4 多智能体回归评测与 Project 3 验收基准演示 (v0.4.0-day50)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import BenchmarkRunner, build_default_benchmark_suite


def main() -> None:
    """运行 Stage 4 全量多智能体基准评测并输出验收报告."""
    print("=" * 72)
    print("🏁 智枢企业级智能体平台 v0.4.0-day50 · Stage 4 多智能体基准评测套件")
    print("=" * 72)

    runner = BenchmarkRunner()
    suite = build_default_benchmark_suite()
    report = runner.run_suite(suite)

    print(report.to_markdown())
    print("\n[单用例明细]")
    for item in report.case_results:
        status = "PASS" if (item.task_success and item.guardrail_passed) else "FAIL"
        print(
            f"  [{status}] {item.case_id} ({item.scenario}) | "
            f"latency={item.latency_ms:.3f}ms | tokens={item.total_tokens} | "
            f"cost=${item.token_cost_usd:.6f} | blocked={item.blocked}"
        )


if __name__ == "__main__":
    main()
