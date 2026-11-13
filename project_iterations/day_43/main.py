"""Day 43 平台启动入口：Supervisor 多智能体协作系统演示 (v0.4.0-day43)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    AnalystAgent,
    ResearcherAgent,
    SupervisorOrchestrator,
    WriterAgent,
)


def main() -> None:
    """运行 Day 43 Supervisor 多智能体研究团队端到端演示."""
    print("=" * 68)
    print("🤖 智枢企业级智能体平台 v0.4.0-day43 · Supervisor 多智能体协作系统")
    print("=" * 68)

    orchestrator = SupervisorOrchestrator(
        workers=[ResearcherAgent(), AnalystAgent(), WriterAgent()],
        max_rounds=6,
    )

    topic = "企业级多智能体系统的 Supervisor 编排与防死循环治理"
    print(f"\n[阶段 1] 启动研究任务：{topic!r} (max_rounds={orchestrator.max_rounds})")
    result = orchestrator.run(topic)

    print(f"[阶段 2] 编排完成：status={result.status} | rounds_used={result.rounds_used}")
    print("\n[阶段 3] 智能体交接轨迹 (agent_handoffs):")
    for rec in result.agent_handoffs:
        print(f"  Round {rec.round_num}: {rec.from_agent} -> {rec.to_agent} | {rec.summary}")

    print("\n[阶段 4] 最终研究报告预览:")
    print("-" * 68)
    print(result.final_report)
    print("-" * 68)


if __name__ == "__main__":
    main()
