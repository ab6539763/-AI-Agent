"""Day 38 平台启动入口：智枢 Project 2 工程代码审查与静态质量审计演示 (v0.3.0-day38)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import audit_project_dir


def _resolve_target_dir() -> Path:
    """优先审计 project_iterations/day_37；若不存在则回退至 day_34 或当前目录."""
    iterations_root = DAY_DIR.parent
    for candidate in ("day_37", "day_34", "day_38"):
        target = iterations_root / candidate
        if target.is_dir():
            return target
    return DAY_DIR


def main() -> None:
    """执行智枢迭代目录的 AST 静态质量审计并打印报告."""
    print("=" * 64)
    print("🔍 智枢企业级智能体平台 v0.3.0-day38 · AST 工程代码审计")
    print("=" * 64)

    target_dir = _resolve_target_dir()
    report = audit_project_dir(target_dir)
    print(report.format_summary())


if __name__ == "__main__":
    main()
