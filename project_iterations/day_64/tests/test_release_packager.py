"""Day 64 单元测试：覆盖 Dockerfile/Compose 校验、环境变量检查、发布清单生成与 5 步上线演示。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.release_packager import (
    DemoRunner,
    DeploymentConfig,
    check_env_vars,
    generate_release_manifest,
    run_preflight_checks,
    validate_compose,
    validate_dockerfile,
)


def test_validate_dockerfile_pass_and_fail(tmp_path: Path) -> None:
    """验证生产 Dockerfile 通过校验，且单阶段/root 运行的不规范 Dockerfile 被拦截。"""
    prod_res = validate_dockerfile(DAY_DIR / "Dockerfile")
    assert prod_res.passed is True
    assert len(prod_res.errors) == 0

    bad_dockerfile = tmp_path / "Dockerfile"
    bad_dockerfile.write_text("FROM python:3.11\nUSER root\nCMD [\"python\", \"main.py\"]\n", encoding="utf-8")
    bad_res = validate_dockerfile(bad_dockerfile)
    assert bad_res.passed is False
    assert any("多阶段构建" in e for e in bad_res.errors)
    assert any("非 root" in e for e in bad_res.errors)
    assert any("HEALTHCHECK" in e for e in bad_res.errors)


def test_validate_compose_pass_and_fail(tmp_path: Path) -> None:
    """验证生产 docker-compose.yml 通过校验，缺失 healthcheck/restart 时失败。"""
    prod_res = validate_compose(DAY_DIR / "docker-compose.yml")
    assert prod_res.passed is True
    assert len(prod_res.errors) == 0

    bad_compose = tmp_path / "docker-compose.yml"
    bad_compose.write_text("services:\n  app:\n    image: demo:latest\n", encoding="utf-8")
    bad_res = validate_compose(bad_compose)
    assert bad_res.passed is False
    assert any("healthcheck" in e for e in bad_res.errors)
    assert any("restart" in e for e in bad_res.errors)


def test_missing_and_placeholder_env_vars_detection() -> None:
    """验证缺失必填环境变量与生产环境占位符密钥检测。"""
    missing_cfg = DeploymentConfig(env_vars={"APP_ENV": "production", "DATABASE_URL": "sqlite:///prod.db"})
    res_missing = check_env_vars(missing_cfg)
    assert res_missing.passed is False
    assert any("JWT_SECRET" in e for e in res_missing.errors)
    assert any("LLM_API_KEY" in e for e in res_missing.errors)

    placeholder_cfg = DeploymentConfig(
        env_vars={
            "APP_ENV": "production",
            "DATABASE_URL": "sqlite:///prod.db",
            "JWT_SECRET": "change-me-in-production",
            "LLM_API_KEY": "sk-real-key-123",
        }
    )
    res_placeholder = check_env_vars(placeholder_cfg)
    assert res_placeholder.passed is False
    assert any("占位符密钥" in e for e in res_placeholder.errors)


def test_preflight_and_release_manifest_generation(tmp_path: Path) -> None:
    """验证全量预检通过，并正确生成含 SHA-256 校验和的 release_manifest.json。"""
    preflight = run_preflight_checks(DAY_DIR)
    assert preflight["overall_passed"] is True
    assert preflight["version"] == "v1.0.0-day64"

    manifest_path = tmp_path / "release_manifest.json"
    manifest = generate_release_manifest(DAY_DIR, output_path=manifest_path)
    assert manifest["preflight_passed"] is True
    assert manifest["service_name"] == "zhishu-agent"
    assert len(manifest["artifacts"]) >= 5
    for item in manifest["artifacts"]:
        assert len(item["sha256"]) == 64

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == "v1.0.0-day64"


def test_demo_runner_five_steps_and_hitl_idempotency() -> None:
    """验证 5 步演示脚本全流程通过，且重复审批同一单据返回 409 Conflict。"""
    runner = DemoRunner()
    steps = runner.run_all()
    assert len(steps) == 5
    assert all(s["passed"] is True for s in steps)

    # 验证第 4 步返回的审批单不能被二次审批
    approval_id = steps[3]["output"]["approval_id"]
    dup_resp = runner.client.post(
        "/api/v1/hitl/approve",
        json={"approval_id": approval_id, "approved": False, "reviewer": "李婷"},
    )
    assert dup_resp.status_code == 409

    # 验证第 5 步审计日志包含完整事件链
    audit_events = [e["event"] for e in steps[4]["output"]["events"]]
    assert "health_check" in audit_events
    assert "rag_query" in audit_events
    assert "financial_ratio_tool" in audit_events
    assert "hitl_resolved" in audit_events
