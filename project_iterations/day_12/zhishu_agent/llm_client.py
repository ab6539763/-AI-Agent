"""Day 12 核心模块：基于 httpx 的 OpenAI / DeepSeek 兼容大模型 HTTP 客户端"""
from __future__ import annotations

from typing import Any

import httpx

from zhishu_agent.exceptions import (
    AuthenticationError,
    InvalidResponseError,
    LLMAPIError,
    NetworkTimeoutError,
    RateLimitError,
    ServerError,
)
from zhishu_agent.message import ChatMessage


class LLMClient:
    """兼容 OpenAI / DeepSeek `/v1/chat/completions` 协议的轻量级 HTTP 客户端。

    支持注入 `httpx.BaseTransport`（如 `httpx.MockTransport`）以实现 100% 离线确定性单测。
    """

    CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key 必须为非空字符串")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url 必须为非空字符串")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model 必须为非空字符串")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须为大于 0 的数字")

        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = float(timeout)

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
            trust_env=trust_env,
        )

    def build_headers(self) -> dict[str, str]:
        """构造标准 Bearer 鉴权请求头。"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def build_payload(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        model: str | None = None,
    ) -> dict[str, Any]:
        """将 ChatMessage 列表与推理参数序列化为标准 JSON 请求体。"""
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("messages 必须为非空的 ChatMessage 列表")
        for msg in messages:
            if not isinstance(msg, ChatMessage):
                raise TypeError(f"messages 元素必须为 ChatMessage 实例，当前为 {type(msg).__name__}")

        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise TypeError("temperature 必须为数值类型")
        if not (0.0 <= float(temperature) <= 2.0):
            raise ValueError(f"temperature 必须在 0.0 到 2.0 之间，当前为 {temperature}")

        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens 必须为正整数")

        return {
            "model": (model or self.model).strip(),
            "messages": [msg.to_dict() for msg in messages],
            "temperature": float(temperature),
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _handle_error_response(self, response: httpx.Response) -> None:
        """根据 HTTP 状态码映射为精准的业务异常。"""
        status_code = response.status_code
        body_text = response.text

        # 尝试提取厂商 JSON 中的 error.message，提取不到则回退到原始文本
        error_msg = body_text or f"HTTP 请求失败，状态码 {status_code}"
        try:
            err_json = response.json()
            if isinstance(err_json, dict):
                err_obj = err_json.get("error")
                if isinstance(err_obj, dict) and err_obj.get("message"):
                    error_msg = str(err_obj["message"])
                elif err_json.get("message"):
                    error_msg = str(err_json["message"])
        except ValueError:
            pass

        if status_code == 401:
            raise AuthenticationError(
                message=f"鉴权失败，请检查 API Key: {error_msg}",
                status_code=status_code,
                response_body=body_text,
            )
        if status_code == 429:
            retry_after_raw = response.headers.get("Retry-After")
            retry_after: float | None = None
            if retry_after_raw is not None:
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = None
            raise RateLimitError(
                message=f"触发请求限流或配额不足: {error_msg}",
                status_code=status_code,
                response_body=body_text,
                retry_after=retry_after,
            )
        if 500 <= status_code < 600:
            raise ServerError(
                message=f"大模型服务端异常: {error_msg}",
                status_code=status_code,
                response_body=body_text,
            )
        raise LLMAPIError(
            message=error_msg,
            status_code=status_code,
            response_body=body_text,
        )

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """解析并校验大模型返回的 JSON 响应体。"""
        try:
            data = response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                message=f"响应体不是合法的 JSON 格式: {exc}",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

        if not isinstance(data, dict):
            raise InvalidResponseError(
                message="响应 JSON 根节点必须为对象 (dict)",
                status_code=response.status_code,
                response_body=response.text,
            )

        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise InvalidResponseError(
                message="响应 JSON 缺少有效的 choices 列表",
                status_code=response.status_code,
                response_body=response.text,
            )

        first_choice = choices[0]
        if not isinstance(first_choice, dict) or not isinstance(first_choice.get("message"), dict):
            raise InvalidResponseError(
                message="响应 choices[0] 缺少 message 对象",
                status_code=response.status_code,
                response_body=response.text,
            )

        content = first_choice["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise InvalidResponseError(
                message="响应 message.content 为空或非字符串",
                status_code=response.status_code,
                response_body=response.text,
            )

        return data

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> ChatMessage:
        """向 `/v1/chat/completions` 发送同步 POST 请求并返回助手回复消息。"""
        headers = self.build_headers()
        payload = self.build_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            model=model,
        )

        try:
            response = self._client.post(
                self.CHAT_COMPLETIONS_PATH,
                headers=headers,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise NetworkTimeoutError(f"请求超时（>{self.timeout}s）: {exc}") from exc
        except httpx.RequestError as exc:
            raise NetworkTimeoutError(f"网络请求异常: {exc}") from exc

        if response.status_code >= 400:
            self._handle_error_response(response)

        data = self._parse_response(response)
        reply_content = data["choices"][0]["message"]["content"]
        return ChatMessage(role="assistant", content=reply_content)

    def close(self) -> None:
        """关闭底层 httpx 连接池。"""
        self._client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
