"""Day 14 核心模块：基于 httpx 的大模型客户端（支持真实 API 与 MockTransport 离线回退）"""
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from zhishu_agent.decorators import retry_on_error
from zhishu_agent.exceptions import (
    ConfigurationError,
    LLMAPIError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from zhishu_agent.message import ChatMessage


@dataclass
class LLMResponse:
    """大模型单次推理响应结构体。"""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def create_mock_transport() -> httpx.MockTransport:
    """构建离线 MockTransport，模拟 OpenAI /chat/completions 接口行为与多轮上下文记忆。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/chat/completions"):
            payload = json.loads(request.content.decode("utf-8"))
            model = payload.get("model", "gpt-4o-mini")
            messages: list[dict[str, str]] = payload.get("messages", [])

            user_messages = [m["content"] for m in messages if m.get("role") == "user"]
            last_user = user_messages[-1] if user_messages else ""
            turn_index = len(user_messages)

            # 模拟上下文记忆：若之前用户提到过姓名或关键信息，在后续提问中体现
            context_hint = ""
            if turn_index > 1 and ("记得" in last_user or "我是谁" in last_user or "刚才" in last_user):
                history_preview = "；".join(user_messages[:-1])
                context_hint = f"（我记得你在前文提到过：{history_preview}）"

            reply_text = (
                f"[Mock-{model} | 第{turn_index}轮] 已收到你的消息：「{last_user}」。"
                f"{context_hint}"
            )

            prompt_tokens = sum(max(1, len(m.get("content", "")) // 2) for m in messages)
            completion_tokens = max(1, len(reply_text) // 2)
            body: dict[str, Any] = {
                "id": f"chatcmpl-mock-{turn_index}",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            return httpx.Response(status_code=200, json=body)

        return httpx.Response(status_code=404, json={"error": {"message": "Not Found"}})

    return httpx.MockTransport(handler)


class LLMClient:
    """统一的大模型 HTTP 客户端：无 API Key 时自动启用 MockTransport，支持异常映射与重试。"""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_delay: float = 0.05,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ConfigurationError("model_name 必须为非空字符串")
        if timeout <= 0:
            raise ConfigurationError("timeout 必须大于 0")

        self.model_name = model_name.strip()
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        resolved_base = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.base_url = resolved_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if transport is not None:
            self._transport = transport
            self.is_mock = isinstance(transport, httpx.MockTransport)
        elif not self.api_key:
            self._transport = create_mock_transport()
            self.is_mock = True
        else:
            self._transport = None
            self.is_mock = False

        client_kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": self.timeout,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        self._client = httpx.Client(**client_kwargs)

    def _send_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行单次 HTTP POST 请求并将网络/HTTP 错误映射为平台自定义异常。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self._client.post(
                "/chat/completions",
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"请求大模型超时 ({self.timeout}s): {exc}") from exc
        except httpx.RequestError as exc:
            raise LLMAPIError(f"网络通信异常: {exc}", retryable=True) from exc

        if response.status_code == 429:
            raise LLMRateLimitError("触发大模型 API 限流 (HTTP 429)")
        if 500 <= response.status_code < 600:
            raise LLMAPIError(
                f"大模型服务端异常 (HTTP {response.status_code})",
                status_code=response.status_code,
                retryable=True,
            )
        if response.status_code >= 400:
            raise LLMAPIError(
                f"大模型请求被拒绝 (HTTP {response.status_code}): {response.text}",
                status_code=response.status_code,
                retryable=False,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise LLMAPIError(f"响应 JSON 解析失败: {exc}", status_code=response.status_code) from exc

    def chat_completion(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送多轮对话请求，内置指数退避重试与 Token 统计解析。"""
        if not messages:
            raise ValueError("messages 不能为空")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ConfigurationError("temperature 必须为数值类型")
        if not (0.0 <= float(temperature) <= 2.0):
            raise ConfigurationError(f"temperature 必须在 [0.0, 2.0] 之间，当前为 {temperature}")

        payload = {
            "model": self.model_name,
            "temperature": float(temperature),
            "messages": [m.to_dict() for m in messages],
        }

        retrying_call = retry_on_error(
            max_retries=self.max_retries,
            base_delay=self.retry_delay,
        )(self._send_request)

        data = retrying_call(payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMAPIError(f"大模型响应格式不符合 OpenAI 规范: {data}") from exc

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))

        return LLMResponse(
            content=content,
            model=data.get("model", self.model_name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def close(self) -> None:
        """关闭底层 httpx.Client 连接池。"""
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
