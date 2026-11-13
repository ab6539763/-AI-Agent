"""Day 46：Agent 稳定性、LangSmith 风格嵌套链路追踪（Tracing）、安全护栏（Guardrails）与熔断降级（CircuitBreaker）.

核心能力：
1. LangSmith 风格嵌套追踪：`TraceSpan`、`TraceStore`、`Tracer`（基于 contextvars 自动关联 `run_id` / `parent_run_id`，记录延迟、Token 用量、费用与异常栈）。
2. 安全护栏引擎：`GuardrailsEngine`（手机号/身份证号/邮箱 PII 脱敏、Prompt Injection 注入拦截、JSON Schema 输出校验）。
3. 稳定性与预算防护：`CircuitBreaker`（CLOSED / OPEN / HALF_OPEN 状态机熔断器）与 `LatencyBudget`（延迟预算守卫）。
4. 端到端管道：`GuardedAgentRunner` 串联 Input Guardrail -> Traced Agent -> Output Guardrail -> TraceStore。
"""

from __future__ import annotations

import contextvars
import functools
import json
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator


# ---------------------------------------------------------------------------
# 1. LangSmith-style Tracing & Cost Observability
# ---------------------------------------------------------------------------

_ACTIVE_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "zhishu_active_trace_id", default=None
)
_ACTIVE_SPAN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "zhishu_active_span_id", default=None
)


@dataclass
class TokenUsage:
    """Token 消耗与费用统计."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.prompt_tokens or self.completion_tokens):
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    @classmethod
    def from_counts(
        cls,
        prompt_tokens: int,
        completion_tokens: int,
        input_price_per_1k: float = 0.0015,
        output_price_per_1k: float = 0.0020,
    ) -> "TokenUsage":
        """根据 Token 数量与单价自动计算费用（USD）."""
        total = prompt_tokens + completion_tokens
        cost = (prompt_tokens / 1000.0) * input_price_per_1k + (
            completion_tokens / 1000.0
        ) * output_price_per_1k
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=round(cost, 6),
        )


@dataclass
class TraceSpan:
    """单个链路追踪节点（对应 LangSmith Run / Span）."""

    run_id: str
    trace_id: str
    name: str
    span_type: str = "chain"
    parent_run_id: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    error: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    latency_ms: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        """记录节点输出."""
        self.outputs = dict(outputs)

    def record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        input_price_per_1k: float = 0.0015,
        output_price_per_1k: float = 0.0020,
    ) -> None:
        """记录 Token 用量并计算费用."""
        self.usage = TokenUsage.from_counts(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 导出的字典."""
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "name": self.name,
            "span_type": self.span_type,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "status": self.status,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_ms": self.latency_ms,
            "usage": asdict(self.usage),
            "metadata": self.metadata,
        }


class TraceStore:
    """链路追踪存储中心：支持按 trace_id 查询、树形重建、聚合指标与 JSONL 导出."""

    def __init__(self) -> None:
        self._spans: dict[str, TraceSpan] = {}
        self._by_trace: dict[str, list[str]] = {}

    def add_span(self, span: TraceSpan) -> None:
        """写入或更新一个 TraceSpan."""
        self._spans[span.run_id] = span
        trace_runs = self._by_trace.setdefault(span.trace_id, [])
        if span.run_id not in trace_runs:
            trace_runs.append(span.run_id)

    def get_span(self, run_id: str) -> TraceSpan | None:
        """按 run_id 查询单个 Span."""
        return self._spans.get(run_id)

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        """按 trace_id 获取完整执行链路的所有 Span（按创建顺序）."""
        run_ids = self._by_trace.get(trace_id, [])
        return [self._spans[rid] for rid in run_ids if rid in self._spans]

    def list_trace_ids(self) -> list[str]:
        """列出所有已记录的 trace_id."""
        return list(self._by_trace.keys())

    def get_trace_tree(self, trace_id: str) -> list[dict[str, Any]]:
        """将扁平的 Span 列表重建为嵌套树结构."""
        spans = self.get_trace(trace_id)
        nodes: dict[str, dict[str, Any]] = {}
        for s in spans:
            node = s.to_dict()
            node["children"] = []
            nodes[s.run_id] = node

        roots: list[dict[str, Any]] = []
        for s in spans:
            node = nodes[s.run_id]
            if s.parent_run_id and s.parent_run_id in nodes:
                nodes[s.parent_run_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def summary(self, trace_id: str) -> dict[str, Any]:
        """聚合一条 Trace 的总耗时、总 Token、总费用与错误数."""
        spans = self.get_trace(trace_id)
        if not spans:
            return {
                "trace_id": trace_id,
                "span_count": 0,
                "total_latency_ms": 0.0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "error_count": 0,
            }
        root_spans = [s for s in spans if s.parent_run_id is None]
        total_latency = (
            sum(s.latency_ms for s in root_spans)
            if root_spans
            else sum(s.latency_ms for s in spans)
        )
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_latency_ms": round(total_latency, 3),
            "prompt_tokens": sum(s.usage.prompt_tokens for s in spans),
            "completion_tokens": sum(s.usage.completion_tokens for s in spans),
            "total_tokens": sum(s.usage.total_tokens for s in spans),
            "total_cost_usd": round(sum(s.usage.cost_usd for s in spans), 6),
            "error_count": sum(1 for s in spans if s.status == "error"),
        }

    def export_jsonl(self, path: str | Path) -> Path:
        """将所有 Span 导出为 JSONL 文件."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for span in self._spans.values():
                f.write(json.dumps(span.to_dict(), ensure_ascii=False) + "\n")
        return out_path


class Tracer:
    """基于 contextvars 的嵌套链路追踪器（LangSmith 风格）."""

    def __init__(self, store: TraceStore | None = None) -> None:
        self.store = store or TraceStore()

    @contextmanager
    def start_span(
        self,
        name: str,
        span_type: str = "chain",
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Iterator[TraceSpan]:
        """开启一个追踪 Span，自动继承当前上下文的 trace_id 与 parent_run_id."""
        parent_run_id = _ACTIVE_SPAN_ID.get()
        current_trace_id = trace_id or _ACTIVE_TRACE_ID.get() or f"trace-{uuid.uuid4().hex[:12]}"
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        span = TraceSpan(
            run_id=run_id,
            trace_id=current_trace_id,
            parent_run_id=parent_run_id,
            name=name,
            span_type=span_type,
            inputs=dict(inputs or {}),
            metadata=dict(metadata or {}),
            start_time=time.time(),
        )
        self.store.add_span(span)

        trace_token = _ACTIVE_TRACE_ID.set(current_trace_id)
        span_token = _ACTIVE_SPAN_ID.set(run_id)
        perf_start = time.perf_counter()
        try:
            yield span
            span.status = "success"
        except Exception as exc:
            span.status = "error"
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span.end_time = time.time()
            span.latency_ms = round((time.perf_counter() - perf_start) * 1000.0, 3)
            _ACTIVE_SPAN_ID.reset(span_token)
            _ACTIVE_TRACE_ID.reset(trace_token)

    def trace(
        self, name: str | None = None, span_type: str = "chain"
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """函数装饰器：自动为被调用函数创建嵌套 TraceSpan."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            span_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                inputs = {"args_count": len(args), "kwargs": kwargs}
                with self.start_span(span_name, span_type=span_type, inputs=inputs) as span:
                    result = fn(*args, **kwargs)
                    span.set_outputs({"result": result})
                    return result

            return wrapper

        return decorator


# ---------------------------------------------------------------------------
# 2. Guardrails Engine (PII Redaction, Prompt Injection, JSON Schema)
# ---------------------------------------------------------------------------


class GuardrailViolation(Exception):
    """护栏拦截异常."""

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"[{rule}] {detail}")


@dataclass
class GuardrailResult:
    """护栏校验结果."""

    passed: bool
    sanitized_text: str = ""
    redactions: list[dict[str, str]] = field(default_factory=list)
    blocked_reason: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    parsed_json: dict[str, Any] | list[Any] | None = None


class GuardrailsEngine:
    """企业级输入/输出安全护栏引擎."""

    # 中国大陆 11 位手机号、18 位身份证号、电子邮箱
    PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
    ID_CARD_PATTERN = re.compile(
        r"(?<!\d)([1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"
    )
    EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

    DEFAULT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
        re.compile(r"(reveal|show|print|leak)\s+(your\s+)?(system\s+prompt|instructions)", re.IGNORECASE),
        re.compile(r"bypass\s+(all\s+)?(guardrails|safety|filters|rules)", re.IGNORECASE),
        re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
        re.compile(r"忽略(之前|以上|所有|全部)(的)?(指令|提示词|规则|限制)"),
        re.compile(r"(泄露|输出|打印)(你的)?系统提示词"),
        re.compile(r"(进入|开启)越狱模式"),
    )

    def __init__(
        self,
        extra_injection_patterns: list[str] | None = None,
    ) -> None:
        self._injection_patterns: list[re.Pattern[str]] = list(self.DEFAULT_INJECTION_PATTERNS)
        if extra_injection_patterns:
            for pat in extra_injection_patterns:
                self._injection_patterns.append(re.compile(pat, re.IGNORECASE))

    def redact_pii(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """对文本中的手机号、身份证号、邮箱进行脱敏替换，并返回脱敏明细."""
        redactions: list[dict[str, str]] = []
        sanitized = text

        def _replace(pattern: re.Pattern[str], pii_type: str, replacement: str, source: str) -> str:
            def _sub(match: re.Match[str]) -> str:
                redactions.append({"type": pii_type, "original": match.group(1), "replacement": replacement})
                return replacement

            return pattern.sub(_sub, source)

        # 注意顺序：先匹配 18 位身份证号，再匹配 11 位手机号，避免长数字子串误匹配
        sanitized = _replace(self.ID_CARD_PATTERN, "id_card", "[REDACTED_ID_CARD]", sanitized)
        sanitized = _replace(self.PHONE_PATTERN, "phone", "[REDACTED_PHONE]", sanitized)
        sanitized = _replace(self.EMAIL_PATTERN, "email", "[REDACTED_EMAIL]", sanitized)
        return sanitized, redactions

    def check_prompt_injection(self, text: str) -> tuple[bool, str | None]:
        """检测提示词注入攻击；返回 (is_safe, blocked_reason)."""
        for pat in self._injection_patterns:
            match = pat.search(text)
            if match:
                return False, f"检测到潜在提示词注入攻击模式: {match.group(0)!r}"
        return True, None

    def validate_input(self, text: str, raise_on_block: bool = False) -> GuardrailResult:
        """执行输入护栏：先检测 Prompt Injection，再对 PII 进行脱敏."""
        is_safe, reason = self.check_prompt_injection(text)
        if not is_safe:
            if raise_on_block:
                raise GuardrailViolation("prompt_injection", reason or "Prompt injection detected")
            return GuardrailResult(
                passed=False,
                sanitized_text="",
                blocked_reason=reason,
            )

        sanitized, redactions = self.redact_pii(text)
        return GuardrailResult(
            passed=True,
            sanitized_text=sanitized,
            redactions=redactions,
        )

    def _redact_json_value(self, value: Any, redactions: list[dict[str, str]]) -> Any:
        """递归对 JSON 输出中的字符串字段执行 PII 脱敏."""
        if isinstance(value, str):
            cleaned, items = self.redact_pii(value)
            redactions.extend(items)
            return cleaned
        if isinstance(value, list):
            return [self._redact_json_value(item, redactions) for item in value]
        if isinstance(value, dict):
            return {k: self._redact_json_value(v, redactions) for k, v in value.items()}
        return value

    def validate_json_output(
        self,
        raw_output: str | dict[str, Any],
        schema: dict[str, Any] | None = None,
        redact_output_pii: bool = True,
    ) -> GuardrailResult:
        """校验模型输出是否符合 JSON 格式及 Schema 约束，并可选对输出字段执行 PII 脱敏."""
        parsed: Any
        if isinstance(raw_output, str):
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                return GuardrailResult(
                    passed=False,
                    sanitized_text=raw_output,
                    blocked_reason=f"输出非合法 JSON: {exc.msg}",
                    validation_errors=[f"JSONDecodeError: {exc.msg}"],
                )
        else:
            parsed = raw_output

        errors: list[str] = []
        if schema:
            self._validate_schema_node(parsed, schema, path="$", errors=errors)

        redactions: list[dict[str, str]] = []
        if redact_output_pii:
            parsed = self._redact_json_value(parsed, redactions)

        serialized = json.dumps(parsed, ensure_ascii=False)
        if errors:
            return GuardrailResult(
                passed=False,
                sanitized_text=serialized,
                redactions=redactions,
                blocked_reason="; ".join(errors),
                validation_errors=errors,
                parsed_json=parsed,
            )

        return GuardrailResult(
            passed=True,
            sanitized_text=serialized,
            redactions=redactions,
            parsed_json=parsed,
        )

    def _validate_schema_node(
        self,
        data: Any,
        schema: dict[str, Any],
        path: str,
        errors: list[str],
    ) -> None:
        """轻量级 JSON Schema 校验器（支持 type/required/properties/enum/minLength/minimum/maximum）."""
        expected_type = schema.get("type")
        type_map: dict[str, tuple[type, ...]] = {
            "object": (dict,),
            "array": (list,),
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "boolean": (bool,),
        }
        if expected_type and expected_type in type_map:
            # Python 中 bool 是 int 的子类，需单独排除
            if expected_type in ("integer", "number") and isinstance(data, bool):
                errors.append(f"{path}: 期望类型 {expected_type}，实际为 bool")
                return
            if not isinstance(data, type_map[expected_type]):
                errors.append(f"{path}: 期望类型 {expected_type}，实际为 {type(data).__name__}")
                return

        if "enum" in schema and data not in schema["enum"]:
            errors.append(f"{path}: 值 {data!r} 不在允许枚举 {schema['enum']} 中")

        if isinstance(data, str) and "minLength" in schema:
            if len(data) < schema["minLength"]:
                errors.append(f"{path}: 字符串长度 {len(data)} 小于 minLength={schema['minLength']}")

        if isinstance(data, (int, float)) and not isinstance(data, bool):
            if "minimum" in schema and data < schema["minimum"]:
                errors.append(f"{path}: 数值 {data} 小于 minimum={schema['minimum']}")
            if "maximum" in schema and data > schema["maximum"]:
                errors.append(f"{path}: 数值 {data} 大于 maximum={schema['maximum']}")

        if isinstance(data, dict):
            for req_key in schema.get("required", []):
                if req_key not in data:
                    errors.append(f"{path}: 缺少必填字段 '{req_key}'")
            properties = schema.get("properties", {})
            for prop_key, prop_schema in properties.items():
                if prop_key in data:
                    self._validate_schema_node(
                        data[prop_key], prop_schema, path=f"{path}.{prop_key}", errors=errors
                    )


# ---------------------------------------------------------------------------
# 3. Stability: CircuitBreaker & Latency Budget Guard
# ---------------------------------------------------------------------------


class CircuitBreakerState(str, Enum):
    """熔断器三态枚举."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(RuntimeError):
    """熔断器处于 OPEN 状态时拒绝请求抛出的异常."""


class LatencyBudgetExceededError(TimeoutError):
    """单次调用超出延迟预算时抛出的异常."""


class CircuitBreaker:
    """滑动计数熔断器：连续失败达到阈值后自动跳闸 OPEN，冷却后进入 HALF_OPEN 探测恢复."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 1.0,
        name: str = "default-llm-breaker",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold 必须 >= 1")
        if recovery_timeout_s < 0:
            raise ValueError("recovery_timeout_s 不能为负数")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.name = name
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._success_count = 0

    @property
    def state(self) -> CircuitBreakerState:
        """读取当前状态（若 OPEN 且已过冷却期，则自动切至 HALF_OPEN）."""
        if (
            self._state == CircuitBreakerState.OPEN
            and self._last_failure_time is not None
            and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout_s
        ):
            self._state = CircuitBreakerState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def reset(self) -> None:
        """手动重置熔断器为 CLOSED."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """通过熔断器受保护地执行目标函数."""
        current = self.state
        if current == CircuitBreakerState.OPEN:
            raise CircuitBreakerOpenError(
                f"熔断器 [{self.name}] 处于 OPEN 状态，拒绝调用下游服务"
            )

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if current == CircuitBreakerState.HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
            raise

        self._failure_count = 0
        self._success_count += 1
        self._state = CircuitBreakerState.CLOSED
        return result


@dataclass
class LatencyBudget:
    """延迟预算守卫：监控执行耗时并在超时时触发告警或中断."""

    max_latency_ms: float
    enforce: bool = True

    def check(self, elapsed_ms: float) -> bool:
        """检查耗时是否超出预算；enforce=True 时超限抛出 LatencyBudgetExceededError."""
        if elapsed_ms > self.max_latency_ms:
            if self.enforce:
                raise LatencyBudgetExceededError(
                    f"执行耗时 {elapsed_ms:.2f}ms 超出延迟预算 {self.max_latency_ms:.2f}ms"
                )
            return False
        return True


# ---------------------------------------------------------------------------
# 4. End-to-End Guarded & Traced Agent Pipeline
# ---------------------------------------------------------------------------


class GuardedAgentRunner:
    """串联 Input Guardrail -> Traced Agent (CircuitBreaker + LatencyBudget) -> Output Guardrail -> TraceStore."""

    def __init__(
        self,
        tracer: Tracer | None = None,
        guardrails: GuardrailsEngine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        latency_budget: LatencyBudget | None = None,
    ) -> None:
        self.tracer = tracer or Tracer()
        self.guardrails = guardrails or GuardrailsEngine()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3, recovery_timeout_s=1.0
        )
        self.latency_budget = latency_budget

    def run(
        self,
        user_input: str,
        agent_fn: Callable[[str, Tracer], str | dict[str, Any]],
        output_schema: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """执行端到端受护栏保护且全程追踪的智能体请求."""
        result_payload: dict[str, Any] = {}
        active_trace_id = trace_id or ""
        with self.tracer.start_span(
            "agent_pipeline",
            span_type="chain",
            inputs={"user_input_preview": user_input[:80]},
            trace_id=trace_id,
        ) as root_span:
            active_trace_id = root_span.trace_id

            # Step 1: Input Guardrail
            with self.tracer.start_span(
                "input_guardrail",
                span_type="guardrail",
                inputs={"raw_length": len(user_input)},
            ) as in_span:
                in_res = self.guardrails.validate_input(user_input, raise_on_block=False)
                in_span.set_outputs(
                    {
                        "passed": in_res.passed,
                        "redaction_count": len(in_res.redactions),
                        "blocked_reason": in_res.blocked_reason,
                    }
                )

            if not in_res.passed:
                root_span.set_outputs({"status": "blocked_input", "reason": in_res.blocked_reason})
                result_payload = {
                    "status": "blocked",
                    "stage": "input_guardrail",
                    "trace_id": active_trace_id,
                    "reason": in_res.blocked_reason,
                    "output": None,
                }
            else:
                # Step 2: Traced Agent Execution with CircuitBreaker & LatencyBudget
                agent_start = time.perf_counter()
                with self.tracer.start_span(
                    "traced_agent",
                    span_type="chain",
                    inputs={"sanitized_input": in_res.sanitized_text},
                ) as agent_span:
                    raw_output = self.circuit_breaker.call(
                        agent_fn, in_res.sanitized_text, self.tracer
                    )
                    elapsed_ms = (time.perf_counter() - agent_start) * 1000.0
                    if self.latency_budget is not None:
                        self.latency_budget.check(elapsed_ms)
                    agent_span.set_outputs({"raw_output_type": type(raw_output).__name__})

                # Step 3: Output Guardrail
                with self.tracer.start_span(
                    "output_guardrail",
                    span_type="guardrail",
                    inputs={"has_schema": output_schema is not None},
                ) as out_span:
                    if output_schema is not None or isinstance(raw_output, dict):
                        out_res = self.guardrails.validate_json_output(
                            raw_output, schema=output_schema, redact_output_pii=True
                        )
                        final_output: Any = out_res.parsed_json if out_res.passed else None
                    else:
                        cleaned_text, out_redactions = self.guardrails.redact_pii(str(raw_output))
                        out_res = GuardrailResult(
                            passed=True,
                            sanitized_text=cleaned_text,
                            redactions=out_redactions,
                        )
                        final_output = cleaned_text

                    out_span.set_outputs(
                        {
                            "passed": out_res.passed,
                            "redaction_count": len(out_res.redactions),
                            "validation_errors": out_res.validation_errors,
                        }
                    )

                if not out_res.passed:
                    root_span.set_outputs(
                        {"status": "blocked_output", "errors": out_res.validation_errors}
                    )
                    result_payload = {
                        "status": "invalid_output",
                        "stage": "output_guardrail",
                        "trace_id": active_trace_id,
                        "reason": out_res.blocked_reason,
                        "validation_errors": out_res.validation_errors,
                        "output": None,
                    }
                else:
                    root_span.set_outputs({"status": "success"})
                    result_payload = {
                        "status": "success",
                        "trace_id": active_trace_id,
                        "output": final_output,
                        "input_redactions": in_res.redactions,
                        "output_redactions": out_res.redactions,
                    }

        result_payload["trace_summary"] = self.tracer.store.summary(active_trace_id)
        return result_payload
