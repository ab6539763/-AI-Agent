"""Day 16 核心模块：LLM API 核心参数配置与 SSE 流式响应客户端 (v0.2.0-day16)"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from typing import Any

import httpx
from pydantic import BaseModel, Field


class GenerationConfig(BaseModel):
    """大模型生成核心参数配置（基于 Pydantic v2 强校验）。

    Attributes:
        temperature: 采样温度 [0.0, 2.0]，越低越确定，越高越随机发散。
        top_p: 核采样概率阈值 (0.0, 1.0]，仅从累积概率达到 top_p 的词表中采样。
        max_tokens: 单次生成的最大 Token 数，必须 >= 1。
        frequency_penalty: 频率惩罚 [-2.0, 2.0]，正值抑制重复用词。
        stream: 是否开启 SSE 流式输出，默认 True。
    """

    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="采样温度 [0.0, 2.0]")
    top_p: float = Field(default=1.0, gt=0.0, le=1.0, description="核采样阈值 (0.0, 1.0]")
    max_tokens: int = Field(default=1024, ge=1, le=128000, description="最大输出 Token 数")
    frequency_penalty: float = Field(
        default=0.0, ge=-2.0, le=2.0, description="频率惩罚 [-2.0, 2.0]"
    )
    stream: bool = Field(default=True, description="是否开启流式传输")

    def to_api_params(self) -> dict[str, Any]:
        """导出可直接合并进 OpenAI /chat/completions 请求体的参数字典。"""
        return self.model_dump()


def parse_sse_line(line: str) -> str | None:
    """解析单行 Server-Sent Events (SSE) 文本，提取增量文本片段。

    规则：
    1. 空行、注释行（以 ':' 开头）或非 'data:' 前缀行返回 None。
    2. 'data: [DONE]' 表示流结束，返回 None。
    3. 解析 JSON 中的 `choices[0].delta.content` 并返回字符串；若无 content 或 JSON 异常则返回 None。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None

    payload = stripped[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    delta = first_choice.get("delta")
    if not isinstance(delta, dict):
        return None

    content = delta.get("content")
    if isinstance(content, str):
        return content
    return None


def _is_sse_done(line: str) -> bool:
    """判断当前 SSE 行是否为结束标记 `data: [DONE]`。"""
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return False
    return stripped[len("data:") :].strip() == "[DONE]"


def create_mock_sse_transport(
    chunks: Sequence[str] | None = None,
    *,
    include_role_delta: bool = True,
    trailing_after_done: Sequence[str] = (),
) -> httpx.MockTransport:
    """构造离线 SSE 流式模拟传输层（无需外网或 API Key）。

    Args:
        chunks: 预设分片文本列表；若为 None，则根据请求体中的参数与最后一条用户消息动态生成分片。
        include_role_delta: 是否在首帧发送 `{"delta": {"role": "assistant"}}`。
        trailing_after_done: 用于测试 `[DONE]` 终止逻辑的尾部干扰分片（正常客户端应忽略）。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            temperature = body.get("temperature", 0.7)
            top_p = body.get("top_p", 1.0)
            messages = body.get("messages", [])
            last_user = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user = str(msg.get("content", ""))
                    break

            if chunks is not None:
                active_chunks = list(chunks)
            else:
                active_chunks = [
                    "【智枢流式引擎】",
                    f"已接收提问「{last_user}」，",
                    f"当前参数(temperature={temperature}, top_p={top_p})：",
                    "正在通过 SSE 逐字推送回答内容！",
                ]

            lines: list[str] = [": sse-stream-start\n\n"]
            if include_role_delta:
                role_event = {"choices": [{"index": 0, "delta": {"role": "assistant"}}]}
                lines.append(f"data: {json.dumps(role_event, ensure_ascii=False)}\n\n")

            for chunk in active_chunks:
                event = {"choices": [{"index": 0, "delta": {"content": chunk}}]}
                lines.append(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")

            lines.append("data: [DONE]\n\n")

            for extra in trailing_after_done:
                extra_event = {"choices": [{"index": 0, "delta": {"content": extra}}]}
                lines.append(f"data: {json.dumps(extra_event, ensure_ascii=False)}\n\n")

            sse_bytes = "".join(lines).encode("utf-8")
            return httpx.Response(
                status_code=200,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                content=sse_bytes,
            )

        return httpx.Response(status_code=404, json={"error": "Not Found"})

    return httpx.MockTransport(handler)


class StreamingLLMClient:
    """支持 OpenAI SSE 流式协议与 MockTransport 离线回退的 LLM 客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model_name: str = "gpt-4o-mini",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

        if transport is not None:
            self._transport = transport
            self.is_mock = isinstance(transport, httpx.MockTransport)
        elif not self.api_key:
            self._transport = create_mock_sse_transport()
            self.is_mock = True
        else:
            self._transport = httpx.HTTPTransport()
            self.is_mock = False

    def build_payload(
        self,
        messages: Sequence[dict[str, str]],
        config: GenerationConfig | None = None,
    ) -> dict[str, Any]:
        """组装 `/chat/completions` 请求体。"""
        cfg = config or GenerationConfig()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": list(messages),
            **cfg.to_api_params(),
        }
        return payload

    def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        config: GenerationConfig | None = None,
    ) -> Iterator[str]:
        """以生成器形式流式产出文本分片，遇到 `data: [DONE]` 立即终止。"""
        cfg = config or GenerationConfig(stream=True)
        if not cfg.stream:
            cfg = cfg.model_copy(update={"stream": True})

        payload = self.build_payload(messages, cfg)
        headers = {
            "Authorization": f"Bearer {self.api_key or 'mock-key'}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        with httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
        ) as client:
            with client.stream(
                "POST",
                "/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if _is_sse_done(line):
                        break
                    chunk = parse_sse_line(line)
                    if chunk is not None:
                        yield chunk

    def chat_aggregated(
        self,
        messages: Sequence[dict[str, str]],
        config: GenerationConfig | None = None,
    ) -> str:
        """消费完整 SSE 流并聚合为最终字符串。"""
        return "".join(self.stream_chat(messages, config))
