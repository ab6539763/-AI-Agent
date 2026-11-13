"""Day 56 单元测试：Dockerfile、Docker Compose 与环境变量安全校验器."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    audit_deployment_bundle,
    check_env_secrets_safety,
    generate_compose_yaml,
    generate_dockerfile,
    generate_env_example,
    validate_compose_yaml_structure,
    validate_dockerfile,
)


def test_day56_production_bundle_passes_audit() -> None:
    """Day 56 实际交付的 Dockerfile、docker-compose.yml 与 .env.example 必须全部通过审计."""
    report = audit_deployment_bundle(
        dockerfile_path=DAY_DIR / "Dockerfile",
        compose_path=DAY_DIR / "docker-compose.yml",
        env_path=DAY_DIR / ".env.example",
    )
    assert report["overall_passed"] is True
    assert report["dockerfile"]["passed"] is True
    assert report["dockerfile"]["metadata"]["stages"] >= 2
    assert report["dockerfile"]["metadata"]["final_user"] == "zhishu"
    assert report["dockerfile"]["metadata"]["has_healthcheck"] is True
    assert report["docker_compose"]["passed"] is True
    assert set(report["docker_compose"]["metadata"]["services"]) >= {
        "zhishu-api",
        "qdrant",
        "redis",
    }
    assert report["env_safety"]["passed"] is True


def test_validate_dockerfile_rejects_root_and_single_stage() -> None:
    """缺少多阶段、非 3.11-slim、使用 root 用户及缺少 HEALTHCHECK 均应报错."""
    bad_df = """
    FROM python:3.10
    WORKDIR /app
    COPY . .
    USER root
    CMD ["python", "app.py"]
    """
    res = validate_dockerfile(bad_df)
    assert res.passed is False
    joined = "\n".join(res.errors)
    assert "多阶段" in joined
    assert "3.11" in joined
    assert "root" in joined
    assert "HEALTHCHECK" in joined


def test_validate_dockerfile_rejects_healthcheck_none_and_hardcoded_secret() -> None:
    """HEALTHCHECK NONE 与 ENV 硬编码密钥必须被拦截."""
    bad_df = """
    FROM python:3.11-slim AS builder
    WORKDIR /build
    FROM python:3.11-slim AS runtime
    ENV OPENAI_API_KEY=sk-proj-1234567890abcdef1234567890
    RUN useradd --system zhishu
    USER zhishu
    HEALTHCHECK NONE
    CMD ["uvicorn", "app:app"]
    """
    res = validate_dockerfile(bad_df)
    assert res.passed is False
    joined = "\n".join(res.errors)
    assert "HEALTHCHECK NONE" in joined
    assert "OPENAI_API_KEY" in joined or "OpenAI API Key" in joined


def test_validate_compose_rejects_missing_service_healthcheck_and_tabs() -> None:
    """缺失服务、缺失 healthcheck、缺失 depends_on 或包含 Tab 缩进均应报错."""
    bad_compose = (
        "services:\n"
        "  zhishu-api:\n"
        "\timage: zhishu:latest\n"
        "  qdrant:\n"
        "    image: qdrant/qdrant:v1.11.3\n"
    )
    res = validate_compose_yaml_structure(bad_compose)
    assert res.passed is False
    joined = "\n".join(res.errors)
    assert "Tab" in joined
    assert "redis" in joined
    assert "volumes" in joined


def test_validate_compose_rejects_hardcoded_env_secret() -> None:
    """docker-compose.yml environment 中硬编码真实密钥应报错."""
    compose = generate_compose_yaml().replace(
        "OPENAI_API_KEY: ${OPENAI_API_KEY}",
        "OPENAI_API_KEY: sk-live-abcdef1234567890abcdef",
    )
    res = validate_compose_yaml_structure(compose)
    assert res.passed is False
    assert any("OpenAI API Key" in err or "OPENAI_API_KEY" in err for err in res.errors)


def test_check_env_secrets_safety_detects_real_leaks_and_allows_placeholders() -> None:
    """占位符应放行，真实格式密钥或明文口令必须拦截."""
    safe_res = check_env_secrets_safety(generate_env_example())
    assert safe_res.passed is True

    leaked_env = (
        "OPENAI_API_KEY=sk-test1234567890abcdef123456\n"
        "GITHUB_TOKEN=ghp_1234567890abcdefghij1234567890\n"
        "REDIS_PASSWORD=MyRealProdPassword123\n"
    )
    bad_res = check_env_secrets_safety(leaked_env)
    assert bad_res.passed is False
    assert len(bad_res.errors) >= 3


def test_generators_produce_compliant_configs() -> None:
    """代码生成器产出的模板应 100% 通过对应校验器."""
    assert validate_dockerfile(generate_dockerfile()).passed is True
    assert validate_compose_yaml_structure(generate_compose_yaml()).passed is True
    assert check_env_secrets_safety(generate_env_example()).passed is True
