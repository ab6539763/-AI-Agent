"""智枢平台 Day 23 核心模块：FastAPI REST API 服务端 (v0.2.0-day23)。"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Literal
import uuid

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator

APP_VERSION = "0.2.0-day23"

SUPPORTED_MODELS: dict[str, dict[str, Any]] = {
    "deepseek-chat": {
        "model_id": "deepseek-chat",
        "provider": "DeepSeek",
        "context_window": 64000,
        "supports_tools": True,
        "status": "available",
        "pricing_per_1m_usd": {"input": 0.27, "output": 1.10},
    },
    "qwen-plus": {
        "model_id": "qwen-plus",
        "provider": "Alibaba Cloud",
        "context_window": 131072,
        "supports_tools": True,
        "status": "available",
        "pricing_per_1m_usd": {"input": 0.40, "output": 1.20},
    },
    "gpt-4o": {
        "model_id": "gpt-4o",
        "provider": "OpenAI",
        "context_window": 128000,
        "supports_tools": True,
        "status": "available",
        "pricing_per_1m_usd": {"input": 2.50, "output": 10.00},
    },
}


class HealthResponse(BaseModel):
    """健康检查响应模型。"""

    status: str = Field(..., description="服务健康状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="当前迭代版本号")
    timestamp: str = Field(..., description="UTC ISO-8601 时间戳")


class ModelInfoResponse(BaseModel):
    """模型元信息查询响应模型。"""

    model_id: str = Field(..., description="模型唯一标识符")
    provider: str = Field(..., description="模型提供厂商")
    context_window: int = Field(..., ge=1, description="最大上下文窗口大小")
    supports_tools: bool = Field(..., description="是否支持 Function Calling")
    status: str = Field(..., description="模型可用状态")
    detail_level: Literal["basic", "full"] = Field(..., description="信息详细程度")
    pricing_per_1m_usd: dict[str, float] | None = Field(
        default=None,
        description="每百万 Token 单价（美元），按需返回",
    )


class ChatRequest(BaseModel):
    """对话接口请求体（带 Pydantic v2 严格校验）。"""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="用户输入消息内容（1~4000 字符，不可为空白）",
    )
    model: str = Field(
        default="deepseek-chat",
        description="指定推理模型 ID",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="采样温度，范围 [0.0, 2.0]",
    )
    max_tokens: int = Field(
        default=512,
        ge=1,
        le=8192,
        description="最大生成 Token 数，范围 [1, 8192]",
    )
    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="可选会话 ID，缺省时服务端自动生成",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message 不能为空或仅包含空白字符")
        return stripped

    @field_validator("model")
    @classmethod
    def validate_supported_model(cls, value: str) -> str:
        if value not in SUPPORTED_MODELS:
            supported = ", ".join(sorted(SUPPORTED_MODELS))
            raise ValueError(f"不支持的模型 '{value}'，可选模型: {supported}")
        return value


class UsageInfo(BaseModel):
    """Token 消耗统计模型。"""

    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)


class ChatResponse(BaseModel):
    """对话接口响应体。"""

    request_id: str = Field(..., description="本次请求唯一追踪 ID")
    session_id: str = Field(..., description="会话 ID")
    model: str = Field(..., description="实际使用的模型 ID")
    reply: str = Field(..., description="智能体回复内容")
    temperature: float = Field(..., description="本次采样温度")
    usage: UsageInfo = Field(..., description="Token 消耗明细")
    latency_ms: int = Field(..., ge=0, description="服务端处理耗时（毫秒）")


def _estimate_tokens_simple(text: str) -> int:
    """轻量级离线 Token 估算辅助函数。"""
    if not text:
        return 0
    return max(1, len(text) // 2 + sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff"))


app = FastAPI(
    title="ZhiShu-Agent API",
    version=APP_VERSION,
    description="星辰数科《智枢企业级智能体平台》REST API 服务 (Day 23)",
)


@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """服务健康检查接口，供负载均衡器与监控探针调用。"""
    return HealthResponse(
        status="ok",
        service="ZhiShu-Agent API",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get(
    "/api/v1/models/{model_id}",
    response_model=ModelInfoResponse,
    tags=["Models"],
)
def get_model_info(
    model_id: str = Path(..., min_length=1, description="模型唯一 ID，如 deepseek-chat"),
    include_pricing: bool = Query(default=False, description="是否返回每百万 Token 定价"),
    detail_level: Literal["basic", "full"] = Query(
        default="basic",
        description="返回详情级别：basic 或 full",
    ),
) -> ModelInfoResponse:
    """根据路径参数查询模型元信息，并支持通过查询参数控制定价与详情级别。"""
    model_meta = SUPPORTED_MODELS.get(model_id)
    if model_meta is None:
        raise HTTPException(status_code=404, detail=f"未找到模型: {model_id}")

    pricing = (
        model_meta["pricing_per_1m_usd"]
        if (include_pricing or detail_level == "full")
        else None
    )
    return ModelInfoResponse(
        model_id=model_meta["model_id"],
        provider=model_meta["provider"],
        context_window=model_meta["context_window"],
        supports_tools=model_meta["supports_tools"],
        status=model_meta["status"],
        detail_level=detail_level,
        pricing_per_1m_usd=pricing,
    )


@app.post("/api/v1/chat", response_model=ChatResponse, tags=["Chat"])
def chat_completion(payload: ChatRequest) -> ChatResponse:
    """智能体对话接口：校验请求参数并返回结构化响应与 Token 统计。"""
    start_time = time.perf_counter()

    session_id = payload.session_id or f"sess-{uuid.uuid4().hex[:8]}"
    request_id = f"req-{uuid.uuid4().hex[:12]}"

    reply_text = (
        f"[{payload.model}] 已收到您的请求（temperature={payload.temperature}）："
        f"{payload.message}"
    )

    prompt_tokens = _estimate_tokens_simple(payload.message)
    completion_tokens = min(payload.max_tokens, _estimate_tokens_simple(reply_text))
    latency_ms = max(0, int((time.perf_counter() - start_time) * 1000))

    return ChatResponse(
        request_id=request_id,
        session_id=session_id,
        model=payload.model,
        reply=reply_text,
        temperature=payload.temperature,
        usage=UsageInfo(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        latency_ms=latency_ms,
    )
