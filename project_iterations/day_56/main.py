"""Day 56 平台启动入口：全栈容器化部署配置校验与打包审计演示 (v0.5.0-day56)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import audit_deployment_bundle


def main() -> None:
    """运行 Day 56 Dockerfile、docker-compose.yml 与 .env.example 全套部署审计."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.5.0-day56 · 容器化部署工程与健康检查审计")
    print("=" * 72)

    report = audit_deployment_bundle(
        dockerfile_path=DAY_DIR / "Dockerfile",
        compose_path=DAY_DIR / "docker-compose.yml",
        env_path=DAY_DIR / ".env.example",
    )

    for name in ("dockerfile", "docker_compose", "env_safety"):
        res = report[name]
        status = "✅ PASS" if res["passed"] else "❌ FAIL"
        print(f"\n[{name}] {status}")
        print(f"    元数据: {res['metadata']}")
        if res["warnings"]:
            print(f"    告警  : {res['warnings']}")
        if res["errors"]:
            print(f"    错误  : {res['errors']}")

    print("\n" + "-" * 72)
    print(f"综合审计结论: {'✅ 准予容器化上线' if report['overall_passed'] else '❌ 存在阻断项'}")


if __name__ == "__main__":
    main()
