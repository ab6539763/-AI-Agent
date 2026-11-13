#!/usr/bin/env python3
"""
智枢企业级智能体平台 — 七大行业生产级项目全量校验脚本
1. 校验每个项目是否具备完整的生产结构（app/ontology.py, llm_wiki.py, fde_pipeline.py, api.py, Dockerfile, docker-compose.yml, .env.example）
2. 校验每个项目是否具备完整的 PMP 0-to-1 五大过程组文档（docs/pmp/01~05）
3. 在独立子进程中运行每个项目的 pytest 测试套件，确保 100% 离线通过
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"

REQUIRED_FILES = [
    "main.py",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    "app/__init__.py",
    "app/ontology.py",
    "app/llm_wiki.py",
    "app/fde_pipeline.py",
    "app/api.py",
    "docs/pmp/01_initiating_charter.md",
    "docs/pmp/02_planning_wbs_and_ontology.md",
    "docs/pmp/03_executing_fde_delivery.md",
    "docs/pmp/04_monitoring_qa_and_eval.md",
    "docs/pmp/05_closing_handover_and_runbook.md",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "frontend/index.html",
    "frontend/src/main.ts",
    "frontend/src/api/client.ts",
    "frontend/src/App.vue",
]


def main() -> int:
    project_dirs = sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir() and p.name.startswith("p0"))
    if len(project_dirs) != 7:
        print(f"[FAIL] Expected 7 industry projects under {PROJECTS_DIR}, found {len(project_dirs)}")
        return 1

    total_passed = 0
    for proj in project_dirs:
        print(f"\n=== Verifying {proj.name} ===")
        missing = [rel for rel in REQUIRED_FILES if not (proj / rel).exists()]
        if missing:
            print(f"[FAIL] {proj.name} missing required files: {missing}")
            return 1
        print(f"[OK] All {len(REQUIRED_FILES)} production & PMP files present.")

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(proj / "tests"), "-v"],
            cwd=str(ROOT),
            text=True,
        )
        if proc.returncode != 0:
            print(f"[FAIL] pytest failed for {proj.name}")
            return proc.returncode
        total_passed += 1

    print(f"\n[SUCCESS] All {total_passed}/7 industry projects passed structure, PMP, and pytest verification!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
