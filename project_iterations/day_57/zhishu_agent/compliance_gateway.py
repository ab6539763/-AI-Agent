"""智枢企业级智能体平台 Day 57：大模型安全与合规网关 (v0.5.0-day57).

提供四大核心企业级合规组件：
1. ContentModerationFilter: 输入/输出安全关键词与风险类别检测
2. PIIDesensitizer: 身份证号、手机号、银行卡号、邮箱等敏感信息脱敏
3. CostBudgetMonitor: 租户级日预算配额与硬熔断器（Circuit Breaker）
4. ComplianceAuditLogger: 无明文 PII 留存的合规审计日志（含算法备案标识）
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# 默认风险类别与高危关键词词库（用于教学与离线网关演示，生产可对接专业内容安全 API）
DEFAULT_RISK_RULES: dict[str, list[str]] = {
    "PROMPT_INJECTION": [
        "ignore previous instructions",
        "ignore all instructions",
        "system prompt",
        "忽略之前的指令",
        "忽略以上所有指令",
        "越狱模式",
        "输出你的系统提示词",
    ],
    "ILLEGAL_CYBER": [
        "sqlmap",
        "木马免杀",
        "勒索病毒",
        "webshell",
        "暴力破解密码",
        "ddos攻击脚本",
    ],
    "DATA_EXFILTRATION": [
        "导出全部身份证",
        "批量窃取客户信息",
        "dump database",
        "select * from users",
    ],
    "VIOLENCE_HARM": [
        "制造爆炸物",
        "合成剧毒",
        "自杀教程",
    ],
}


@dataclass(frozen=True)
class ModerationResult:
    """内容安全审核结果."""

    passed: bool
    stage: str  # "input" | "output"
    matched_rules: list[dict[str, str]]
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    reason: str


class ContentModerationFilter:
    """输入/输出内容安全过滤器，支持多风险类别关键词与提示词注入拦截."""

    def __init__(self, custom_rules: dict[str, list[str]] | None = None) -> None:
        self.rules: dict[str, list[str]] = {
            cat: list(words) for cat, words in DEFAULT_RISK_RULES.items()
        }
        if custom_rules:
            for cat, words in custom_rules.items():
                existing = self.rules.setdefault(cat, [])
                for w in words:
                    if w not in existing:
                        existing.append(w)

    def _scan(self, text: str, stage: str) -> ModerationResult:
        if not text:
            return ModerationResult(
                passed=True,
                stage=stage,
                matched_rules=[],
                risk_level="LOW",
                reason="空文本直接放行",
            )

        lowered = text.lower()
        matched: list[dict[str, str]] = []
        for category, keywords in self.rules.items():
            for kw in keywords:
                if kw.lower() in lowered:
                    matched.append({"category": category, "keyword": kw})

        if not matched:
            return ModerationResult(
                passed=True,
                stage=stage,
                matched_rules=[],
                risk_level="LOW",
                reason="未命中安全风险规则",
            )

        categories = sorted({item["category"] for item in matched})
        risk_level = "HIGH" if len(matched) >= 2 or any(
            c in {"ILLEGAL_CYBER", "VIOLENCE_HARM", "DATA_EXFILTRATION"} for c in categories
        ) else "MEDIUM"

        return ModerationResult(
            passed=False,
            stage=stage,
            matched_rules=matched,
            risk_level=risk_level,
            reason=f"{stage} 命中安全风险类别: {', '.join(categories)}",
        )

    def check_input(self, text: str) -> ModerationResult:
        """校验用户输入提示词安全性."""
        return self._scan(text, stage="input")

    def check_output(self, text: str) -> ModerationResult:
        """校验模型输出内容安全性."""
        return self._scan(text, stage="output")


@dataclass(frozen=True)
class PIIMaskingResult:
    """PII 脱敏结果."""

    masked_text: str
    redacted_counts: dict[str, int]
    total_redacted: int


class PIIDesensitizer:
    """企业级 PII 敏感信息脱敏器（身份证、银行卡、手机号、邮箱）."""

    # 注意匹配顺序：18位身份证 -> 16-19位银行卡 -> 11位手机号 -> 邮箱
    _ID_CARD_RE = re.compile(
        r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
    )
    _BANK_CARD_RE = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")
    _PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
    _EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")

    @staticmethod
    def _mask_id_card(match: re.Match[str]) -> str:
        val = match.group(1)
        return f"{val[:6]}********{val[-4:]}"

    @staticmethod
    def _mask_bank_card(match: re.Match[str]) -> str:
        val = match.group(1)
        return f"{val[:4]}{'*' * (len(val) - 8)}{val[-4:]}"

    @staticmethod
    def _mask_phone(match: re.Match[str]) -> str:
        val = match.group(1)
        return f"{val[:3]}****{val[-4:]}"

    @staticmethod
    def _mask_email(match: re.Match[str]) -> str:
        val = match.group(1)
        local, domain = val.split("@", 1)
        prefix = local[0] if len(local) <= 2 else local[:2]
        return f"{prefix}***@{domain}"

    def desensitize(self, text: str) -> PIIMaskingResult:
        """对文本执行全量 PII 脱敏并统计各类别脱敏次数."""
        if not text:
            return PIIMaskingResult(
                masked_text=text,
                redacted_counts={"id_card": 0, "bank_card": 0, "phone": 0, "email": 0},
                total_redacted=0,
            )

        counts: dict[str, int] = {}
        current = text

        current, counts["id_card"] = self._ID_CARD_RE.subn(self._mask_id_card, current)
        current, counts["bank_card"] = self._BANK_CARD_RE.subn(self._mask_bank_card, current)
        current, counts["phone"] = self._PHONE_RE.subn(self._mask_phone, current)
        current, counts["email"] = self._EMAIL_RE.subn(self._mask_email, current)

        total = sum(counts.values())
        return PIIMaskingResult(
            masked_text=current,
            redacted_counts=counts,
            total_redacted=total,
        )

    def mask_text(self, text: str) -> str:
        """便捷方法：仅返回脱敏后的文本."""
        return self.desensitize(text).masked_text


@dataclass(frozen=True)
class BudgetCheckResult:
    """租户成本配额检查结果."""

    allowed: bool
    tenant_id: str
    used_cost_cny: float
    daily_limit_cny: float
    remaining_cny: float
    circuit_open: bool
    reason: str


class CostBudgetMonitor:
    """租户日预算配额监控与硬熔断器（Circuit Breaker）."""

    def __init__(
        self,
        default_daily_limit_cny: float = 100.0,
        input_price_per_1k_cny: float = 0.002,
        output_price_per_1k_cny: float = 0.006,
    ) -> None:
        if default_daily_limit_cny <= 0:
            raise ValueError("default_daily_limit_cny 必须大于 0")
        self.default_daily_limit_cny = float(default_daily_limit_cny)
        self.input_price_per_1k_cny = float(input_price_per_1k_cny)
        self.output_price_per_1k_cny = float(output_price_per_1k_cny)
        self._tenant_limits: dict[str, float] = {}
        self._daily_usage: dict[tuple[str, str], float] = {}
        self._circuit_breakers: set[tuple[str, str]] = set()

    @staticmethod
    def _today(date_str: str | None = None) -> str:
        if date_str:
            return date_str
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def set_tenant_quota(self, tenant_id: str, daily_limit_cny: float) -> None:
        """为指定租户配置自定义每日预算上限（元）."""
        if daily_limit_cny <= 0:
            raise ValueError("daily_limit_cny 必须大于 0")
        self._tenant_limits[tenant_id] = float(daily_limit_cny)

    def get_tenant_quota(self, tenant_id: str) -> float:
        return self._tenant_limits.get(tenant_id, self.default_daily_limit_cny)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """按千 Token 单价估算调用成本（人民币元）."""
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("Token 数量不能为负数")
        cost = (
            (prompt_tokens / 1000.0) * self.input_price_per_1k_cny
            + (completion_tokens / 1000.0) * self.output_price_per_1k_cny
        )
        return round(cost, 6)

    def is_circuit_open(self, tenant_id: str, date_str: str | None = None) -> bool:
        key = (tenant_id, self._today(date_str))
        return key in self._circuit_breakers

    def check_budget(
        self,
        tenant_id: str,
        estimated_cost_cny: float = 0.0,
        date_str: str | None = None,
    ) -> BudgetCheckResult:
        """检查租户当日预算是否充足，若已触发熔断则直接拒绝."""
        day = self._today(date_str)
        key = (tenant_id, day)
        limit = self.get_tenant_quota(tenant_id)
        used = round(self._daily_usage.get(key, 0.0), 6)
        remaining = round(max(0.0, limit - used), 6)

        if key in self._circuit_breakers or used >= limit:
            self._circuit_breakers.add(key)
            return BudgetCheckResult(
                allowed=False,
                tenant_id=tenant_id,
                used_cost_cny=used,
                daily_limit_cny=limit,
                remaining_cny=0.0,
                circuit_open=True,
                reason=f"租户 {tenant_id} 当日预算已耗尽，硬熔断器处于断开状态",
            )

        if used + estimated_cost_cny > limit:
            return BudgetCheckResult(
                allowed=False,
                tenant_id=tenant_id,
                used_cost_cny=used,
                daily_limit_cny=limit,
                remaining_cny=remaining,
                circuit_open=False,
                reason=f"预估成本 {estimated_cost_cny:.4f} 元将超出当日剩余配额 {remaining:.4f} 元",
            )

        return BudgetCheckResult(
            allowed=True,
            tenant_id=tenant_id,
            used_cost_cny=used,
            daily_limit_cny=limit,
            remaining_cny=remaining,
            circuit_open=False,
            reason="预算充足，允许放行",
        )

    def record_usage(
        self,
        tenant_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        date_str: str | None = None,
    ) -> BudgetCheckResult:
        """记录实际 Token 消耗；若累计成本达到或超过日配额则触发硬熔断."""
        day = self._today(date_str)
        key = (tenant_id, day)
        cost = self.estimate_cost(prompt_tokens, completion_tokens)
        new_used = round(self._daily_usage.get(key, 0.0) + cost, 6)
        self._daily_usage[key] = new_used

        limit = self.get_tenant_quota(tenant_id)
        if new_used >= limit:
            self._circuit_breakers.add(key)
            return BudgetCheckResult(
                allowed=False,
                tenant_id=tenant_id,
                used_cost_cny=new_used,
                daily_limit_cny=limit,
                remaining_cny=0.0,
                circuit_open=True,
                reason=f"累计消费 {new_used:.4f} 元达到日限额 {limit:.4f} 元，已触发硬熔断",
            )

        remaining = round(limit - new_used, 6)
        return BudgetCheckResult(
            allowed=True,
            tenant_id=tenant_id,
            used_cost_cny=new_used,
            daily_limit_cny=limit,
            remaining_cny=remaining,
            circuit_open=False,
            reason="计费成功",
        )

    def reset_tenant(self, tenant_id: str, date_str: str | None = None) -> None:
        """人工重置租户当日配额与熔断器状态."""
        key = (tenant_id, self._today(date_str))
        self._daily_usage.pop(key, None)
        self._circuit_breakers.discard(key)


@dataclass(frozen=True)
class AuditRecord:
    """无明文 PII 的合规审计日志条目."""

    trace_id: str
    timestamp: str
    tenant_id: str
    action: str  # "ALLOW" | "BLOCK_INPUT" | "BLOCK_OUTPUT" | "BLOCK_QUOTA"
    input_sha256: str
    masked_input_preview: str
    masked_output_preview: str
    pii_redacted_counts: dict[str, int]
    risk_categories: list[str]
    cost_cny: float
    filing_record_id: str


class ComplianceAuditLogger:
    """合规审计日志记录器：强制脱敏后再落盘，严禁记录明文 PII."""

    def __init__(
        self,
        desensitizer: PIIDesensitizer | None = None,
        log_path: Path | str | None = None,
        preview_limit: int = 200,
    ) -> None:
        self._desensitizer = desensitizer or PIIDesensitizer()
        self._log_path = Path(log_path) if log_path else None
        self._preview_limit = preview_limit
        self._records: list[AuditRecord] = []

    def log_event(
        self,
        tenant_id: str,
        action: str,
        raw_input: str,
        raw_output: str = "",
        risk_categories: list[str] | None = None,
        cost_cny: float = 0.0,
        filing_record_id: str = "BeiAn-ZhiShu-2026-001",
    ) -> AuditRecord:
        """对输入输出执行二次强制脱敏并生成不可篡改 SHA-256 摘要后记录审计日志."""
        in_res = self._desensitizer.desensitize(raw_input)
        out_res = self._desensitizer.desensitize(raw_output)

        merged_counts = {
            k: in_res.redacted_counts.get(k, 0) + out_res.redacted_counts.get(k, 0)
            for k in ("id_card", "bank_card", "phone", "email")
        }

        input_hash = hashlib.sha256(raw_input.encode("utf-8")).hexdigest()
        record = AuditRecord(
            trace_id=f"tr-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            tenant_id=tenant_id,
            action=action,
            input_sha256=input_hash,
            masked_input_preview=in_res.masked_text[: self._preview_limit],
            masked_output_preview=out_res.masked_text[: self._preview_limit],
            pii_redacted_counts=merged_counts,
            risk_categories=list(risk_categories or []),
            cost_cny=round(cost_cny, 6),
            filing_record_id=filing_record_id,
        )
        self._records.append(record)

        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

        return record

    def get_records(self, tenant_id: str | None = None) -> list[AuditRecord]:
        if tenant_id is None:
            return list(self._records)
        return [r for r in self._records if r.tenant_id == tenant_id]

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in self._records)


class ComplianceGateway:
    """智枢统一大模型安全与合规网关."""

    def __init__(
        self,
        moderation: ContentModerationFilter | None = None,
        desensitizer: PIIDesensitizer | None = None,
        budget_monitor: CostBudgetMonitor | None = None,
        audit_logger: ComplianceAuditLogger | None = None,
        filing_record_id: str = "BeiAn-ZhiShu-2026-001",
    ) -> None:
        self.moderation = moderation or ContentModerationFilter()
        self.desensitizer = desensitizer or PIIDesensitizer()
        self.budget_monitor = budget_monitor or CostBudgetMonitor()
        self.audit_logger = audit_logger or ComplianceAuditLogger(desensitizer=self.desensitizer)
        self.filing_record_id = filing_record_id

    def process_request(
        self,
        tenant_id: str,
        user_prompt: str,
        llm_fn: Callable[[str], tuple[str, int, int]] | None = None,
    ) -> dict[str, Any]:
        """执行完整网关流水线：配额校验 -> 输入审核 -> 输入脱敏 -> 模型推理 -> 输出审核 -> 输出脱敏 -> 审计日志."""
        budget_check = self.budget_monitor.check_budget(tenant_id)
        if not budget_check.allowed:
            audit = self.audit_logger.log_event(
                tenant_id=tenant_id,
                action="BLOCK_QUOTA",
                raw_input=user_prompt,
                risk_categories=["QUOTA_EXCEEDED"],
                filing_record_id=self.filing_record_id,
            )
            return {
                "allowed": False,
                "action": "BLOCK_QUOTA",
                "response": budget_check.reason,
                "audit_trace_id": audit.trace_id,
                "cost_cny": 0.0,
            }

        in_mod = self.moderation.check_input(user_prompt)
        if not in_mod.passed:
            cats = sorted({m["category"] for m in in_mod.matched_rules})
            audit = self.audit_logger.log_event(
                tenant_id=tenant_id,
                action="BLOCK_INPUT",
                raw_input=user_prompt,
                risk_categories=cats,
                filing_record_id=self.filing_record_id,
            )
            return {
                "allowed": False,
                "action": "BLOCK_INPUT",
                "response": f"请求已被内容安全网关拦截：{in_mod.reason}",
                "audit_trace_id": audit.trace_id,
                "cost_cny": 0.0,
            }

        masked_in = self.desensitizer.desensitize(user_prompt)
        if llm_fn is None:
            raw_output = f"[智枢合规助手] 已安全接收脱敏请求：{masked_in.masked_text}"
            prompt_tokens, completion_tokens = 120, 80
        else:
            raw_output, prompt_tokens, completion_tokens = llm_fn(masked_in.masked_text)

        call_cost = self.budget_monitor.estimate_cost(prompt_tokens, completion_tokens)
        self.budget_monitor.record_usage(tenant_id, prompt_tokens, completion_tokens)

        out_mod = self.moderation.check_output(raw_output)
        if not out_mod.passed:
            cats = sorted({m["category"] for m in out_mod.matched_rules})
            audit = self.audit_logger.log_event(
                tenant_id=tenant_id,
                action="BLOCK_OUTPUT",
                raw_input=user_prompt,
                raw_output=raw_output,
                risk_categories=cats,
                cost_cny=call_cost,
                filing_record_id=self.filing_record_id,
            )
            return {
                "allowed": False,
                "action": "BLOCK_OUTPUT",
                "response": f"模型输出已被内容安全网关拦截：{out_mod.reason}",
                "audit_trace_id": audit.trace_id,
                "cost_cny": call_cost,
            }

        masked_out = self.desensitizer.desensitize(raw_output)
        audit = self.audit_logger.log_event(
            tenant_id=tenant_id,
            action="ALLOW",
            raw_input=user_prompt,
            raw_output=masked_out.masked_text,
            cost_cny=call_cost,
            filing_record_id=self.filing_record_id,
        )
        return {
            "allowed": True,
            "action": "ALLOW",
            "response": masked_out.masked_text,
            "masked_prompt": masked_in.masked_text,
            "pii_redacted": masked_in.total_redacted + masked_out.total_redacted,
            "audit_trace_id": audit.trace_id,
            "cost_cny": call_cost,
        }
