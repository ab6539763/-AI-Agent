"""Day 70 结业日启动入口：70天智枢平台演进全景、前沿趋势追踪与结业证书演示 (v1.0.0-day70)。"""

from __future__ import annotations

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.graduation_summary import (
    ZHISHU_STAGE_MILESTONES,
    TrendTracker,
    generate_career_roadmap,
    generate_graduation_certificate,
    render_evolution_summary,
    validate_curriculum_span,
)


def main() -> None:
    """打印 70 天演进全景、前沿趋势、结业证书与 30/60/90 天成长路线图预览。"""
    span = validate_curriculum_span(ZHISHU_STAGE_MILESTONES)
    print("=" * 72)
    print(f"🎓 智枢企业级智能体平台 {span['versions'][-1]}-day70 · 70天结业全景报告")
    print("=" * 72)

    print("\n[1/4] 70 天六阶段演进全景：")
    print(render_evolution_summary(ZHISHU_STAGE_MILESTONES))

    tracker = TrendTracker()
    print("\n[2/4] 2025-2026 前沿 AI Agent 趋势追踪：")
    for trend in tracker.list_trends():
        print(f"  - [{trend.maturity.upper():12s}] {trend.name} ({trend.category})")

    print("\n[3/4] 结业电子证书示例：")
    cert = generate_graduation_certificate(
        learner_name="陈默",
        completion_date="2026-11-13",
        track="Agent Engineer",
        completed_days=70,
    )
    print(cert)

    print("\n[4/4] 结业后 30/60/90 天职业发展路线图（前 12 行预览）：")
    roadmap = generate_career_roadmap(target_role="Agent Engineer", learner_name="陈默")
    for line in roadmap.splitlines()[:12]:
        print(f"  {line}")


if __name__ == "__main__":
    main()
