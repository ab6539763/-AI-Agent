"""Day 12 单元测试：基于 httpx.MockTransport 的 100% 离线确定性测试"""
import json
import sys
from pathlib import Path

import httpx
import pytest

# 确保可以直接导入 project_iterations/day_12 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.exceptions import (
    AuthenticationError,
    InvalidResponseError,
    LLMAPIError,
    NetworkTimeoutError,
    RateLimitError,
    ServerError,
)
from zhishu_agent.llm_client import LLMClient
from zhishu_agent.message import ChatMessage


class TestLLMClientValidation:
    """测试客户端初始化与请求构造的参数校验。"""

    def test_empty_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            LLMClient(api_key="   ")

    def test_invalid_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            LLMClient(api_key="sk-test", timeout=0)
        with pytest.raises(ValueError, match="timeout"):
            LLMClient(api_key="sk-test", timeout=True)  # type: ignore[arg-type]

    def test_build_headers(self) -> None:
        client = LLMClient(api_key="sk-secret-123")
        headers = client.build_headers()
        assert headers["Authorization"] == "Bearer sk-secret-123"
        assert headers["Content-Type"] == "application/json"
        client.close()

    def test_build_payload_serialization(self) -> None:
        client = LLMClient(api_key="sk-test", model="deepseek-chat")
        msgs = [
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content="你好"),
        ]
        payload = client.build_payload(msgs, temperature=0.2, max_tokens=256)
        assert payload == {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是助手"},
                {"role": "user", "content": "你好"},
            ],
            "temperature": 0.2,
            "max_tokens": 256,
            "stream": False,
        }
        client.close()

    def test_build_payload_invalid_inputs(self) -> None:
        client = LLMClient(api_key="sk-test")
        with pytest.raises(ValueError, match="非空"):
            client.build_payload([])
        with pytest.raises(TypeError, match="ChatMessage"):
            client.build_payload(["not a message"])  # type: ignore[list-item]
        with pytest.raises(ValueError, match="temperature"):
            client.build_payload([ChatMessage(role="user", content="hi")], temperature=2.5)
        with pytest.raises(ValueError, match="max_tokens"):
            client.build_payload([ChatMessage(role="user", content="hi")], max_tokens=-1)
        client.close()


class TestLLMClientMockTransport:
    """使用 httpx.MockTransport 测试完整 HTTP 请求、响应解析与异常处理。"""

    def test_chat_success_and_request_inspection(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["content_type"] = request.headers.get("Content-Type")
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-001",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "你好！我是智枢助手。"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        transport = httpx.MockTransport(handler)
        with LLMClient(
            api_key="sk-live-abc",
            base_url="https://api.deepseek.com/",
            model="deepseek-chat",
            transport=transport,
        ) as client:
            reply = client.chat(
                [ChatMessage(role="user", content="你好")],
                temperature=0.5,
                max_tokens=512,
            )

        assert isinstance(reply, ChatMessage)
        assert reply.role == "assistant"
        assert reply.content == "你好！我是智枢助手。"
        assert captured["method"] == "POST"
        assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
        assert captured["auth"] == "Bearer sk-live-abc"
        assert captured["content_type"] == "application/json"
        assert captured["body"] == {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "你好"}],
            "temperature": 0.5,
            "max_tokens": 512,
            "stream": False,
        }

    def test_status_401_raises_authentication_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
        )
        with LLMClient(api_key="sk-bad", transport=transport) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.chat([ChatMessage(role="user", content="hi")])
            assert exc_info.value.status_code == 401
            assert "Incorrect API key" in str(exc_info.value)

    def test_status_429_raises_rate_limit_error_with_retry_after(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                429,
                headers={"Retry-After": "12"},
                json={"error": {"message": "Too many requests"}},
            )
        )
        with LLMClient(api_key="sk-limit", transport=transport) as client:
            with pytest.raises(RateLimitError) as exc_info:
                client.chat([ChatMessage(role="user", content="hi")])
            assert exc_info.value.status_code == 429
            assert exc_info.value.retry_after == 12.0

    @pytest.mark.parametrize("code", [500, 502, 503])
    def test_status_5xx_raises_server_error(self, code: int) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(code, json={"error": {"message": "Upstream down"}})
        )
        with LLMClient(api_key="sk-test", transport=transport) as client:
            with pytest.raises(ServerError) as exc_info:
                client.chat([ChatMessage(role="user", content="hi")])
            assert exc_info.value.status_code == code

    def test_status_400_raises_llm_api_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(400, json={"error": {"message": "Invalid model"}})
        )
        with LLMClient(api_key="sk-test", transport=transport) as client:
            with pytest.raises(LLMAPIError) as exc_info:
                client.chat([ChatMessage(role="user", content="hi")])
            assert exc_info.value.status_code == 400

    def test_invalid_json_response_raises(self) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<html>Bad Gateway</html>"))
        with LLMClient(api_key="sk-test", transport=transport) as client:
            with pytest.raises(InvalidResponseError, match="JSON"):
                client.chat([ChatMessage(role="user", content="hi")])

    def test_missing_choices_raises(self) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "x"}))
        with LLMClient(api_key="sk-test", transport=transport) as client:
            with pytest.raises(InvalidResponseError, match="choices"):
                client.chat([ChatMessage(role="user", content="hi")])

    def test_timeout_raises_network_timeout_error(self) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Simulated read timeout", request=request)

        transport = httpx.MockTransport(timeout_handler)
        with LLMClient(api_key="sk-test", timeout=5.0, transport=transport) as client:
            with pytest.raises(NetworkTimeoutError, match="超时"):
                client.chat([ChatMessage(role="user", content="hi")])
