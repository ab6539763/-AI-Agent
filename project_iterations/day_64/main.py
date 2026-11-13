"""Day 64 平台发布预检与 5 步上线演示 CLI 入口 (v1.0.0-day64)。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.release_packager import (
    DemoRunner,
    generate_release_manifest,
    run_preflight_checks,
)


def main() -> int:
    """执行发布前全量预检、生成发布清单并运行 5 步端到端演示脚本。"""
    print("=" * 72)
    print("🚀 星辰数科 · 智枢企业级智能体平台 v1.0.0-day64 发布预检与上线演示")
    print("=" * 72)

    preflight = run_preflight_checks(DAY_DIR)
    print(f"[1/3] 发布前预检 (Preflight): {'PASS ✅' if preflight['overall_passed'] else 'FAIL ❌'}")
    print(f"      - Dockerfile 校验: {'通过' if preflight['dockerfile']['passed'] else '失败'}")
    print(f"      - Compose 校验:    {'通过' if preflight['compose']['passed'] else '失败'}")
    print(f"      - 环境变量校验:    {'通过' if preflight['env_check']['passed'] else '失败'}")

    manifest = generate_release_manifest(DAY_DIR)
    print(f"[2/3] 发布清单 (Release Manifest): 共登记 {len(manifest['artifacts'])} 个核心交付物")

    runner = DemoRunner()
    steps = runner.run_all()
    print("[3/3] 5 步全流程上线演示 (5-Step Live Demo):")
    for step in steps:
        status_icon = "✅" if step["passed"] else "❌"
        print(f"      Step {step['step']}: {step['name']} -> {status_icon} ({step['duration_ms']} ms)")

    all_ok = preflight["overall_passed"] and all(s["passed"] for s in steps)
    print("-" * 72)
    print(f"总结: {'v1.0.0-day64 达到生产上线就绪标准 (Ready for Release) 🎉' if all_ok else '存在未通过项，请检查日志'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
