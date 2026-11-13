"""Day 64: Capstone Deployment, Release Readiness Checker & 5-Step Live Demo Runner.

为「星辰数科 · 智枢企业级智能体平台 (ZhiShu-Agent)」提供生产级发布前检查、
容器配置校验（Dockerfile / docker-compose.yml）、发布清单生成以及
基于 FastAPI TestClient 的 5 步全流程演示脚本执行器。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class DeploymentConfig(BaseModel):
    """生产部署配置模型。"""

    service_name: str = Field(default="zhishu-agent", min_length=1)
    version: str = Field(default="v1.0.0-day64", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=4, ge=1, le=64)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_env_vars: list[str] = Field(
        default_factory=lambda: [
            "APP_ENV",
            "DATABASE_URL",
            "JWT_SECRET",
            "LLM_API_KEY",
        ]
    )
    health_endpoint: str = Field(default="/api/v1/health", pattern=r"^/.*")


class ValidationResult(BaseModel):
    """单项校验结果。"""

    target: str
    passed: bool
    passed_checks: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_dockerfile(dockerfile_path: Path | str) -> ValidationResult:
    """校验 Dockerfile 是否符合生产多阶段构建与安全基线。"""
    path = Path(dockerfile_path)
    if not path.exists():
        return ValidationResult(
            target=str(path),
            passed=False,
            errors=[f"Dockerfile 不存在: {path}"],
        )

    content = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

    passed_checks: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    from_lines = [line for line in lines if line.upper().startswith("FROM ")]
    has_copy_from = any("--from=" in line.lower() for line in lines)
    if len(from_lines) >= 2 and has_copy_from:
        passed_checks.append("多阶段构建 (Multi-stage build)")
    else:
        errors.append("缺少多阶段构建（需要至少两个 FROM 阶段及 COPY --from=）")

    user_lines = [line for line in lines if line.upper().startswith("USER ")]
    if user_lines and not user_lines[-1].upper().endswith("ROOT"):
        passed_checks.append(f"非 root 运行用户 ({user_lines[-1]})")
    else:
        errors.append("缺少非 root USER 指令，存在容器提权风险")

    if any(line.upper().startswith("EXPOSE ") for line in lines):
        passed_checks.append("端口声明 (EXPOSE)")
    else:
        errors.append("缺少 EXPOSE 端口声明")

    if any(line.upper().startswith("HEALTHCHECK ") for line in lines):
        passed_checks.append("容器健康检查 (HEALTHCHECK)")
    else:
        errors.append("缺少 HEALTHCHECK 健康检查指令")

    if any(line.upper().startswith(("CMD ", "ENTRYPOINT ")) for line in lines):
        passed_checks.append("启动入口 (CMD/ENTRYPOINT)")
    else:
        errors.append("缺少 CMD 或 ENTRYPOINT 启动指令")

    if "PYTHONDONTWRITEBYTECODE=1" not in content:
        warnings.append("建议设置 PYTHONDONTWRITEBYTECODE=1 减少镜像体积")

    return ValidationResult(
        target=str(path),
        passed=len(errors) == 0,
        passed_checks=passed_checks,
        errors=errors,
        warnings=warnings,
    )


def validate_compose(compose_path: Path | str) -> ValidationResult:
    """校验 docker-compose.yml 是否包含服务编排、健康检查与重启策略。"""
    path = Path(compose_path)
    if not path.exists():
        return ValidationResult(
            target=str(path),
            passed=False,
            errors=[f"docker-compose.yml 不存在: {path}"],
        )

    content = path.read_text(encoding="utf-8")
    passed_checks: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    required_keys = {
        r"^\s*services\s*:": "services 服务定义",
        r"^\s*ports\s*:": "ports 端口映射",
        r"^\s*healthcheck\s*:": "healthcheck 健康检查",
        r"^\s*restart\s*:": "restart 重启策略",
    }
    for pattern, label in required_keys.items():
        if re.search(pattern, content, flags=re.MULTILINE):
            passed_checks.append(label)
        else:
            errors.append(f"docker-compose.yml 缺少 {label}")

    if re.search(r"^\s*(environment|env_file)\s*:", content, flags=re.MULTILINE):
        passed_checks.append("环境变量配置 (environment/env_file)")
    else:
        errors.append("docker-compose.yml 缺少 environment 或 env_file 配置")

    if re.search(r"^\s*volumes\s*:", content, flags=re.MULTILINE):
        passed_checks.append("数据卷挂载 (volumes)")
    else:
        warnings.append("建议配置 volumes 持久化 SQLite/日志数据")

    return ValidationResult(
        target=str(path),
        passed=len(errors) == 0,
        passed_checks=passed_checks,
        errors=errors,
        warnings=warnings,
    )


def check_env_vars(config: DeploymentConfig) -> ValidationResult:
    """校验必填环境变量是否齐全且非默认占位符。"""
    passed_checks: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    placeholder_values = {"change-me-in-production", "your-api-key-here", "changeme", "todo"}

    for key in config.required_env_vars:
        val = config.env_vars.get(key, "").strip()
        if not val:
            errors.append(f"缺少必填环境变量: {key}")
        elif val.lower() in placeholder_values and config.env_vars.get("APP_ENV") == "production":
            errors.append(f"生产环境禁止使用占位符密钥: {key}")
        else:
            passed_checks.append(f"环境变量已就绪: {key}")

    return ValidationResult(
        target="env_vars",
        passed=len(errors) == 0,
        passed_checks=passed_checks,
        errors=errors,
        warnings=warnings,
    )


def parse_env_file(env_path: Path | str) -> dict[str, str]:
    """解析 .env 或 .env.example 文件为键值字典。"""
    path = Path(env_path)
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def run_preflight_checks(
    base_dir: Path | str,
    config: DeploymentConfig | None = None,
) -> dict[str, Any]:
    """执行发布前全量预检（Dockerfile + Compose + 环境变量）。"""
    root = Path(base_dir)
    if config is None:
        env_vars = parse_env_file(root / ".env") or parse_env_file(root / ".env.example")
        config = DeploymentConfig(env_vars=env_vars)

    docker_res = validate_dockerfile(root / "Dockerfile")
    compose_res = validate_compose(root / "docker-compose.yml")
    env_res = check_env_vars(config)

    env_example_exists = (root / ".env.example").exists()
    overall_passed = docker_res.passed and compose_res.passed and env_res.passed and env_example_exists

    return {
        "service_name": config.service_name,
        "version": config.version,
        "overall_passed": overall_passed,
        "env_example_exists": env_example_exists,
        "dockerfile": docker_res.model_dump(),
        "compose": compose_res.model_dump(),
        "env_check": env_res.model_dump(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate_release_manifest(
    base_dir: Path | str,
    config: DeploymentConfig | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """生成带 SHA-256 校验码的生产发布清单 (release_manifest.json)。"""
    root = Path(base_dir)
    cfg = config or DeploymentConfig(
        env_vars=parse_env_file(root / ".env") or parse_env_file(root / ".env.example")
    )
    preflight = run_preflight_checks(root, cfg)

    candidate_files = [
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
        "main.py",
        "zhishu_agent/__init__.py",
        "zhishu_agent/release_packager.py",
    ]
    artifacts: list[dict[str, Any]] = []
    for rel in candidate_files:
        fp = root / rel
        if fp.exists():
            artifacts.append(
                {
                    "path": rel,
                    "size_bytes": fp.stat().st_size,
                    "sha256": _sha256_file(fp),
                }
            )

    manifest = {
        "service_name": cfg.service_name,
        "version": cfg.version,
        "port": cfg.port,
        "workers": cfg.workers,
        "health_endpoint": cfg.health_endpoint,
        "preflight_passed": preflight["overall_passed"],
        "artifacts": artifacts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return manifest


# ---------------------------------------------------------------------------
# 5-Step Live Demo FastAPI Application & DemoRunner
# ---------------------------------------------------------------------------


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=2, ge=1, le=5)


class FinancialRatioRequest(BaseModel):
    company: str = "星辰数科"
    net_income: float
    revenue: float
    shareholders_equity: float
    total_assets: float
    total_liabilities: float


class HITLSubmitRequest(BaseModel):
    action: str
    amount_cny: float
    requester: str = "陈默"


class HITLApproveRequest(BaseModel):
    approval_id: str
    approved: bool
    reviewer: str = "张工"
    comment: str = "合规复核通过"


def create_demo_app() -> FastAPI:
    """构建用于 Day 64 5 步上线演示的轻量级 FastAPI 服务。"""
    app = FastAPI(title="智枢企业级智能体平台", version="v1.0.0-day64")

    knowledge_base = [
        {
            "doc_id": "fin-2025-q4",
            "title": "星辰数科 2025 年第四季度财报摘要",
            "content": "2025 年第四季度营业收入 12.8 亿元，同比增长 24.5%；净利润 2.1 亿元，研发费用率 18.2%。",
        },
        {
            "doc_id": "risk-policy-2025",
            "title": "星辰数科企业内控与资金审批红线制度",
            "content": "单笔超过 50 万元的对外资金划拨或关联交易披露必须触发 HITL 人工审批，由财务总监或 Tech Lead 复核。",
        },
    ]
    approvals: dict[str, dict[str, Any]] = {}
    audit_logs: list[dict[str, Any]] = []

    def record_audit(event: str, detail: dict[str, Any]) -> None:
        audit_logs.append(
            {
                "event_id": f"evt-{len(audit_logs) + 1:03d}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "detail": detail,
            }
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        res = {"status": "ok", "service": "zhishu-agent", "version": "v1.0.0-day64"}
        record_audit("health_check", res)
        return res

    @app.post("/api/v1/rag/query")
    def rag_query(req: RAGQueryRequest) -> dict[str, Any]:
        citations = knowledge_base[: req.top_k]
        answer = (
            f"根据检索到的 {len(citations)} 份企业文档："
            "星辰数科 2025 Q4 营收 12.8 亿元（同比 +24.5%），净利润 2.1 亿元；"
            "且单笔超 50 万元资金划拨需强制经过 HITL 审批。"
        )
        record_audit("rag_query", {"query": req.query, "citation_ids": [c["doc_id"] for c in citations]})
        return {"query": req.query, "answer": answer, "citations": citations}

    @app.post("/api/v1/tools/financial-ratio")
    def calc_financial_ratio(req: FinancialRatioRequest) -> dict[str, Any]:
        if req.revenue <= 0 or req.shareholders_equity <= 0 or req.total_assets <= 0:
            raise HTTPException(status_code=400, detail="营收、净资产与总资产必须为正数")
        ratios = {
            "company": req.company,
            "net_profit_margin_pct": round((req.net_income / req.revenue) * 100, 2),
            "roe_pct": round((req.net_income / req.shareholders_equity) * 100, 2),
            "debt_to_asset_pct": round((req.total_liabilities / req.total_assets) * 100, 2),
        }
        record_audit("financial_ratio_tool", ratios)
        return ratios

    @app.post("/api/v1/hitl/submit")
    def hitl_submit(req: HITLSubmitRequest) -> dict[str, Any]:
        approval_id = f"hitl-{uuid.uuid4().hex[:8]}"
        ticket = {
            "approval_id": approval_id,
            "action": req.action,
            "amount_cny": req.amount_cny,
            "requester": req.requester,
            "status": "pending",
        }
        approvals[approval_id] = ticket
        record_audit("hitl_submitted", ticket)
        return ticket

    @app.post("/api/v1/hitl/approve")
    def hitl_approve(req: HITLApproveRequest) -> dict[str, Any]:
        ticket = approvals.get(req.approval_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="审批单不存在")
        if ticket["status"] != "pending":
            raise HTTPException(status_code=409, detail="审批单已处理，禁止重复审批")
        ticket["status"] = "approved" if req.approved else "rejected"
        ticket["reviewer"] = req.reviewer
        ticket["comment"] = req.comment
        record_audit("hitl_resolved", dict(ticket))
        return ticket

    @app.get("/api/v1/audit/export")
    def export_audit() -> dict[str, Any]:
        return {
            "service": "zhishu-agent",
            "version": "v1.0.0-day64",
            "total_events": len(audit_logs),
            "events": audit_logs,
        }

    return app


class DemoRunner:
    """5 步毕业答辩现场演示执行器（基于 FastAPI TestClient）。"""

    def __init__(self, app: FastAPI | None = None) -> None:
        self.app = app or create_demo_app()
        self.client = TestClient(self.app)

    def run_all(self) -> list[dict[str, Any]]:
        """依次执行 5 步端到端演示并返回每步执行报告。"""
        steps: list[dict[str, Any]] = []

        # Step 1: Health Check
        t0 = time.perf_counter()
        r1 = self.client.get("/api/v1/health")
        r1.raise_for_status()
        steps.append(
            {
                "step": 1,
                "name": "服务健康检查 (Health Check)",
                "passed": r1.json().get("status") == "ok",
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "output": r1.json(),
            }
        )

        # Step 2: Hybrid RAG Query
        t0 = time.perf_counter()
        r2 = self.client.post(
            "/api/v1/rag/query",
            json={"query": "星辰数科 2025 Q4 营收与内控审批红线是什么？", "top_k": 2},
        )
        r2.raise_for_status()
        d2 = r2.json()
        steps.append(
            {
                "step": 2,
                "name": "混合 RAG 财报与制度检索",
                "passed": len(d2.get("citations", [])) == 2,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "output": d2,
            }
        )

        # Step 3: Financial Ratio Tool
        t0 = time.perf_counter()
        r3 = self.client.post(
            "/api/v1/tools/financial-ratio",
            json={
                "company": "星辰数科",
                "net_income": 2.1,
                "revenue": 12.8,
                "shareholders_equity": 10.5,
                "total_assets": 20.0,
                "total_liabilities": 7.6,
            },
        )
        r3.raise_for_status()
        d3 = r3.json()
        steps.append(
            {
                "step": 3,
                "name": "财务比率分析工具调用 (ROE / 净利率 / 资产负债率)",
                "passed": d3.get("roe_pct") == 20.0,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "output": d3,
            }
        )

        # Step 4: HITL Approval
        t0 = time.perf_counter()
        sub = self.client.post(
            "/api/v1/hitl/submit",
            json={"action": "研发GPU集群扩容资金划拨", "amount_cny": 850000.0, "requester": "陈默"},
        )
        sub.raise_for_status()
        approval_id = sub.json()["approval_id"]
        app_resp = self.client.post(
            "/api/v1/hitl/approve",
            json={"approval_id": approval_id, "approved": True, "reviewer": "张工", "comment": "预算合规，批准执行"},
        )
        app_resp.raise_for_status()
        d4 = app_resp.json()
        steps.append(
            {
                "step": 4,
                "name": "HITL 高风险人工审批闭环",
                "passed": d4.get("status") == "approved",
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "output": d4,
            }
        )

        # Step 5: Audit Log Export
        t0 = time.perf_counter()
        r5 = self.client.get("/api/v1/audit/export")
        r5.raise_for_status()
        d5 = r5.json()
        steps.append(
            {
                "step": 5,
                "name": "全链路合规审计日志导出",
                "passed": d5.get("total_events", 0) >= 5,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "output": d5,
            }
        )

        return steps
