"""智枢平台 Day 56 核心模块：容器化部署配置校验与打包器 (v0.5.0-day56).

提供纯 Python 零外部依赖的容器部署工程校验与生成能力：
1. `validate_dockerfile`: 校验多阶段构建、Python 3.11 slim、非 root 用户、HEALTHCHECK、EXPOSE 与密钥安全。
2. `validate_compose_yaml_structure`: 校验 Docker Compose 结构、核心服务编排、持久化卷、健康检查与依赖编排。
3. `check_env_secrets_safety`: 检测 `.env` / 配置中的硬编码真实密钥与高危明文口令泄漏风险。
4. `generate_dockerfile` / `generate_compose_yaml` / `generate_env_example`: 生成生产级部署模板。
5. `audit_deployment_bundle`: 对整套部署文件执行端到端合规性审计。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# 常见真实密钥正则模式
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI API Key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("GitHub PAT", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private Key Block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)

# 需要重点审计的敏感环境变量键名关键词
_SENSITIVE_KEY_KEYWORDS: tuple[str, ...] = (
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "PRIVATE_KEY",
    "ACCESS_KEY",
)

# 允许在模板中使用的安全占位符模式
_SAFE_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\$\{[A-Za-z0-9_]+(?::-[^}]*)?\}$"),  # ${VAR} 或 ${VAR:-default}
    re.compile(r"^<[^>]+>$"),  # <your-key>
    re.compile(r"^(?:your_|change_me|replace_me|placeholder|example|dummy|sample).*", re.I),
    re.compile(r"^redis://:\$\{[A-Za-z0-9_]+\}@.*$"),
)


@dataclass
class ValidationResult:
    """容器配置校验结果数据结构."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典结构."""
        return asdict(self)


def _is_safe_placeholder(value: str) -> bool:
    """判断环境变量值是否为安全的占位符或空值."""
    stripped = value.strip().strip('"').strip("'")
    if stripped == "":
        return True
    return any(pattern.match(stripped) for pattern in _SAFE_PLACEHOLDER_PATTERNS)


def _join_dockerfile_lines(content: str) -> list[str]:
    """合并 Dockerfile 中使用反斜杠续行的指令."""
    logical_lines: list[str] = []
    buffer = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            if buffer:
                logical_lines.append(buffer.strip())
                buffer = ""
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
        else:
            buffer += stripped
            logical_lines.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        logical_lines.append(buffer.strip())
    return logical_lines


def validate_dockerfile(content: str) -> ValidationResult:
    """校验生产级 Dockerfile 是否满足安全与可观测性基线.

    检查项：
    - 非空且包含多阶段构建（至少 2 个 FROM，且存在 AS 别名）
    - 使用 Python 3.11 slim 基础镜像
    - 配置非 root 的 USER（且最终生效用户不能为 root / 0）
    - 配置有效 HEALTHCHECK（不能为 HEALTHCHECK NONE）
    - 配置 EXPOSE 暴露服务端口
    - ENV/ARG 中不存在硬编码真实密钥
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not content or not content.strip():
        return ValidationResult(
            passed=False,
            errors=["Dockerfile 内容为空"],
            warnings=[],
            metadata={"stages": 0},
        )

    lines = _join_dockerfile_lines(content)
    from_clauses: list[str] = []
    user_clauses: list[str] = []
    healthcheck_clauses: list[str] = []
    expose_ports: list[str] = []
    env_arg_lines: list[str] = []

    for line in lines:
        upper = line.upper()
        if upper.startswith("FROM "):
            from_clauses.append(line[5:].strip())
        elif upper.startswith("USER "):
            user_clauses.append(line[5:].strip())
        elif upper.startswith("HEALTHCHECK "):
            healthcheck_clauses.append(line[12:].strip())
        elif upper.startswith("EXPOSE "):
            expose_ports.extend(line[7:].strip().split())
        elif upper.startswith("ENV ") or upper.startswith("ARG "):
            env_arg_lines.append(line)

    # 1. 多阶段构建校验
    has_named_stage = any(re.search(r"\bAS\s+[A-Za-z0-9_-]+", clause, re.I) for clause in from_clauses)
    if len(from_clauses) < 2 or not has_named_stage:
        errors.append("Dockerfile 必须采用多阶段构建（至少两个 FROM 且包含 AS 阶段别名）")

    # 2. Python 3.11 slim 基础镜像校验
    has_py311_slim = any("python:3.11" in clause and "slim" in clause for clause in from_clauses)
    if not has_py311_slim:
        errors.append("Dockerfile 必须基于 python:3.11-slim 精简镜像构建")

    # 3. 非 root 用户校验
    if not user_clauses:
        errors.append("Dockerfile 缺少 USER 指令，禁止以默认 root 用户运行容器")
    else:
        final_user = user_clauses[-1].split(":")[0].strip().lower()
        if final_user in {"root", "0"}:
            errors.append(f"Dockerfile 最终生效用户为 '{user_clauses[-1]}'，必须切换为非 root 用户")

    # 4. HEALTHCHECK 校验
    if not healthcheck_clauses:
        errors.append("Dockerfile 缺少 HEALTHCHECK 健康检查指令")
    elif healthcheck_clauses[-1].upper().startswith("NONE"):
        errors.append("Dockerfile 禁止使用 HEALTHCHECK NONE 禁用健康检查")

    # 5. EXPOSE 端口校验
    if not expose_ports:
        warnings.append("Dockerfile 未显式声明 EXPOSE 端口（建议声明 EXPOSE 8000）")

    # 6. 硬编码密钥检查
    for env_line in env_arg_lines:
        for secret_name, pattern in _SECRET_PATTERNS:
            if pattern.search(env_line):
                errors.append(f"Dockerfile ENV/ARG 疑似包含硬编码 {secret_name}")
        for match in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*([^\s\\]+)", env_line):
            key, val = match.group(1).upper(), match.group(2)
            if any(kw in key for kw in _SENSITIVE_KEY_KEYWORDS) and not _is_safe_placeholder(val):
                errors.append(f"Dockerfile 中敏感变量 {key} 疑似硬编码明文值")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metadata={
            "stages": len(from_clauses),
            "final_user": user_clauses[-1] if user_clauses else None,
            "has_healthcheck": bool(healthcheck_clauses) and not healthcheck_clauses[-1].upper().startswith("NONE"),
            "exposed_ports": expose_ports,
        },
    )


def _strip_yaml_comment(line: str) -> str:
    """移除 YAML 行尾注释（保留引号内 # 号）."""
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:idx].rstrip()
    return line.rstrip()


def validate_compose_yaml_structure(
    content: str,
    required_services: tuple[str, ...] = ("zhishu-api", "qdrant", "redis"),
) -> ValidationResult:
    """纯 Python 校验 Docker Compose YAML 结构与生产编排规范.

    检查项：
    - 语法基础：禁止 Tab 缩进、必须包含 `services:` 与 `volumes:` 顶级段落
    - 核心服务：`zhishu-api`、`qdrant`、`redis` 均已定义
    - 每个服务必须配置 `image` 或 `build`，且核心服务具备 `healthcheck` 与 `volumes`
    - `zhishu-api` 必须配置 `depends_on` 依赖编排与 `ports`
    - 不得在 `environment` 中硬编码真实密钥
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not content or not content.strip():
        return ValidationResult(
            passed=False,
            errors=["docker-compose.yml 内容为空"],
            warnings=[],
            metadata={"services": []},
        )

    top_sections: set[str] = set()
    services: dict[str, dict[str, Any]] = {}
    top_volumes: set[str] = set()

    current_top: str | None = None
    current_service: str | None = None
    current_service_key: str | None = None
    service_indent: int | None = None

    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip("\t "))]:
            errors.append(f"第 {line_no} 行使用了 Tab 缩进，YAML 必须使用空格缩进")
            continue

        cleaned = _strip_yaml_comment(raw_line)
        if not cleaned.strip():
            continue

        indent = len(cleaned) - len(cleaned.lstrip(" "))
        stripped = cleaned.strip()

        if indent == 0:
            if ":" not in stripped:
                errors.append(f"第 {line_no} 行顶级键格式错误: {stripped}")
                continue
            key = stripped.split(":", 1)[0].strip()
            top_sections.add(key)
            current_top = key
            current_service = None
            current_service_key = None
            service_indent = None
            continue

        if current_top == "services":
            # 第一个子级缩进即为服务名层级（通常 2 空格）
            if service_indent is None or indent <= service_indent:
                if ":" in stripped and not stripped.startswith("- "):
                    service_indent = indent
                    svc_name = stripped.split(":", 1)[0].strip()
                    current_service = svc_name
                    current_service_key = None
                    services.setdefault(
                        svc_name,
                        {
                            "has_image_or_build": False,
                            "has_healthcheck": False,
                            "has_volumes": False,
                            "has_ports": False,
                            "has_depends_on": False,
                            "env_lines": [],
                        },
                    )
                continue

            if current_service is not None:
                # 服务属性层级（通常 4 空格）
                if indent == service_indent + 2 and ":" in stripped and not stripped.startswith("- "):
                    prop = stripped.split(":", 1)[0].strip()
                    current_service_key = prop
                    svc_info = services[current_service]
                    if prop in {"image", "build"}:
                        svc_info["has_image_or_build"] = True
                    elif prop == "healthcheck":
                        svc_info["has_healthcheck"] = True
                    elif prop == "volumes":
                        svc_info["has_volumes"] = True
                    elif prop == "ports":
                        svc_info["has_ports"] = True
                    elif prop == "depends_on":
                        svc_info["has_depends_on"] = True
                elif current_service_key == "environment":
                    services[current_service]["env_lines"].append(stripped)

        elif current_top == "volumes":
            if indent == 2 and ":" in stripped and not stripped.startswith("- "):
                vol_name = stripped.split(":", 1)[0].strip()
                top_volumes.add(vol_name)

    if "services" not in top_sections:
        errors.append("docker-compose.yml 缺少顶级 'services:' 定义")
    if "volumes" not in top_sections:
        errors.append("docker-compose.yml 缺少顶级 'volumes:' 持久化卷定义")

    for req in required_services:
        if req not in services:
            errors.append(f"docker-compose.yml 缺少必需服务 '{req}'")
            continue

        info = services[req]
        if not info["has_image_or_build"]:
            errors.append(f"服务 '{req}' 必须配置 'image' 或 'build'")
        if not info["has_healthcheck"]:
            errors.append(f"服务 '{req}' 缺少 'healthcheck' 健康检查配置")
        if not info["has_volumes"]:
            errors.append(f"服务 '{req}' 缺少 'volumes' 持久化挂载配置")
        if req == "zhishu-api":
            if not info["has_depends_on"]:
                errors.append("服务 'zhishu-api' 缺少 'depends_on' 依赖编排（应等待 qdrant 与 redis 健康）")
            if not info["has_ports"]:
                warnings.append("服务 'zhishu-api' 未声明 'ports' 端口映射")

        # 检查 environment 中硬编码密钥
        for env_entry in info["env_lines"]:
            for secret_name, pattern in _SECRET_PATTERNS:
                if pattern.search(env_entry):
                    errors.append(f"服务 '{req}' 的 environment 疑似硬编码 {secret_name}")
            kv_match = re.match(r"^-?\s*([A-Za-z0-9_]+)\s*[:=]\s*(.+)$", env_entry)
            if kv_match:
                key, val = kv_match.group(1).upper(), kv_match.group(2).strip()
                if any(kw in key for kw in _SENSITIVE_KEY_KEYWORDS) and not _is_safe_placeholder(val):
                    errors.append(f"服务 '{req}' 的环境变量 {key} 疑似硬编码明文密钥")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metadata={
            "top_sections": sorted(top_sections),
            "services": sorted(services.keys()),
            "volumes": sorted(top_volumes),
        },
    )


def check_env_secrets_safety(content: str, *, allow_placeholders: bool = True) -> ValidationResult:
    """扫描 .env / 配置文本，检测硬编码密钥与敏感信息泄漏风险.

    Args:
        content: `.env.example` 或配置文件文本。
        allow_placeholders: 若为 True（默认，适用于检查 `.env.example`），允许 `${VAR}`、
            `your_..._here`、`change_me...` 等安全占位符；若检测到真实格式密钥或普通明文密码则报错。
    """
    errors: list[str] = []
    warnings: list[str] = []
    inspected_keys: list[str] = []

    if not content or not content.strip():
        return ValidationResult(
            passed=False,
            errors=["环境变量配置内容为空"],
            warnings=[],
            metadata={"inspected_keys": []},
        )

    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 先做全局高危正则扫描
        for secret_name, pattern in _SECRET_PATTERNS:
            if pattern.search(stripped):
                errors.append(f"第 {line_no} 行检测到真实 {secret_name} 泄漏风险")

        if "=" not in stripped:
            continue

        key, val = stripped.split("=", 1)
        key = key.strip()
        val = val.strip()
        inspected_keys.append(key)

        upper_key = key.upper()
        if any(kw in upper_key for kw in _SENSITIVE_KEY_KEYWORDS):
            is_placeholder = _is_safe_placeholder(val)
            if not allow_placeholders and val.strip('"\'') != "":
                errors.append(f"第 {line_no} 行敏感键 {key} 不应包含非空值")
            elif allow_placeholders and not is_placeholder:
                errors.append(
                    f"第 {line_no} 行敏感键 {key} 疑似硬编码真实值（请替换为 your_..._here 或 ${{VAR}} 占位符）"
                )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metadata={"inspected_keys": inspected_keys, "key_count": len(inspected_keys)},
    )


def generate_dockerfile(
    app_module: str = "zhishu_agent.api:app",
    port: int = 8000,
    user_name: str = "zhishu",
) -> str:
    """生成符合 Day 56 生产基线的多阶段 Dockerfile."""
    return (
        "# syntax=docker/dockerfile:1\n"
        "FROM python:3.11-slim AS builder\n"
        "WORKDIR /build\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1\n"
        "RUN python -m venv /opt/venv\n"
        'ENV PATH="/opt/venv/bin:$PATH"\n'
        "RUN pip install fastapi uvicorn[standard] pydantic qdrant-client redis\n\n"
        "FROM python:3.11-slim AS runtime\n"
        'ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"\n'
        f"RUN groupadd --system --gid 10001 {user_name} && \\\n"
        f"    useradd --system --uid 10001 --gid {user_name} --create-home {user_name}\n"
        "WORKDIR /app\n"
        "COPY --from=builder /opt/venv /opt/venv\n"
        f"COPY --chown={user_name}:{user_name} . /app\n"
        f"USER {user_name}\n"
        f"EXPOSE {port}\n"
        "HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\\n"
        f"    CMD python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}/health', timeout=3)\" || exit 1\n"
        f'CMD ["uvicorn", "{app_module}", "--host", "0.0.0.0", "--port", "{port}"]\n'
    )


def generate_compose_yaml(
    api_port: int = 8000,
    qdrant_version: str = "v1.11.3",
    redis_version: str = "7.2-alpine",
) -> str:
    """生成包含 zhishu-api、qdrant 与 redis 的标准 docker-compose.yml."""
    return (
        "services:\n"
        "  zhishu-api:\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: Dockerfile\n"
        "    ports:\n"
        f'      - "${{API_PORT:-{api_port}}}:{api_port}"\n'
        "    env_file:\n"
        "      - .env\n"
        "    environment:\n"
        "      OPENAI_API_KEY: ${OPENAI_API_KEY}\n"
        "      QDRANT_URL: ${QDRANT_URL:-http://qdrant:6333}\n"
        "      REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}\n"
        "    volumes:\n"
        "      - zhishu_data:/app/data\n"
        "    depends_on:\n"
        "      qdrant:\n"
        "        condition: service_healthy\n"
        "      redis:\n"
        "        condition: service_healthy\n"
        "    healthcheck:\n"
        f'      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen(\'http://127.0.0.1:{api_port}/health\', timeout=3)"]\n'
        "      interval: 30s\n"
        "      timeout: 5s\n"
        "      retries: 3\n\n"
        "  qdrant:\n"
        f"    image: qdrant/qdrant:{qdrant_version}\n"
        "    ports:\n"
        '      - "6333:6333"\n'
        "    volumes:\n"
        "      - qdrant_storage:/qdrant/storage\n"
        "    healthcheck:\n"
        '      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:6333/healthz || exit 1"]\n'
        "      interval: 15s\n"
        "      timeout: 5s\n"
        "      retries: 5\n\n"
        "  redis:\n"
        f"    image: redis:{redis_version}\n"
        '    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD}"]\n'
        "    ports:\n"
        '      - "6379:6379"\n'
        "    volumes:\n"
        "      - redis_data:/data\n"
        "    healthcheck:\n"
        '      test: ["CMD-SHELL", "redis-cli -a ${REDIS_PASSWORD} ping | grep -q PONG"]\n'
        "      interval: 10s\n"
        "      timeout: 3s\n"
        "      retries: 5\n\n"
        "volumes:\n"
        "  zhishu_data:\n"
        "  qdrant_storage:\n"
        "  redis_data:\n"
    )


def generate_env_example() -> str:
    """生成无真实密钥泄漏风险的 .env.example 模板."""
    return (
        "APP_ENV=production\n"
        "LOG_LEVEL=INFO\n"
        "API_PORT=8000\n"
        "OPENAI_API_KEY=your_openai_api_key_here\n"
        "QDRANT_URL=http://qdrant:6333\n"
        "REDIS_PASSWORD=change_me_redis_password\n"
        "REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0\n"
        "SQLITE_DB_PATH=/app/data/zhishu.db\n"
        "JWT_SECRET_KEY=change_me_jwt_secret_key\n"
    )


def audit_deployment_bundle(
    dockerfile_path: Path,
    compose_path: Path,
    env_path: Path,
) -> dict[str, Any]:
    """对本地 Dockerfile、docker-compose.yml 与 .env.example 执行全套容器化上线审计."""
    df_res = validate_dockerfile(dockerfile_path.read_text(encoding="utf-8"))
    dc_res = validate_compose_yaml_structure(compose_path.read_text(encoding="utf-8"))
    env_res = check_env_secrets_safety(env_path.read_text(encoding="utf-8"))

    all_passed = df_res.passed and dc_res.passed and env_res.passed
    return {
        "overall_passed": all_passed,
        "dockerfile": df_res.to_dict(),
        "docker_compose": dc_res.to_dict(),
        "env_safety": env_res.to_dict(),
    }
