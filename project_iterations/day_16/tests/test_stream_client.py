"""Day 16 单元测试：覆盖 GenerationConfig 参数校验、SSE 行解析、[DONE] 终止与流式分片聚合"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

# 确保可以直接导入 project_iterations/day_16 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.stream_client import (
    GenerationConfig,
    StreamingLLMClient,
    create_mock_sse_transport,
    parse_sse_line,
)


class TestGenerationConfig:
    """测试 GenerationConfig 的默认值、导出与边界校验。"""

    def test_defaults_and_to_api_params(self) -> None:
        cfg = GenerationConfig()
        assert cfg.temperature == 0.7
        assert cfg.top_p == 1.0
        assert cfg.max_tokens == 1024
        assert cfg.frequency_penalty == 0.0
        assert cfg.stream is True
        assert cfg.to_api_params() == {
            "temperature": 0.7,
            "top_p": 1.0,
            "max_tokens": 1024,
            "frequency_penalty": 0.0,
            "stream": True,
        }

    @pytest.mark.parametrize("temp", [-0.1, 2.01])
    def test_invalid_temperature(self, temp: float) -> None:
        with pytest.raises(ValidationError):
            GenerationConfig(temperature=temp)

    @pytest.mark.parametrize("top_p", [0.0, -0.2, 1.05])
    def test_invalid_top_p(self, top_p: float) -> None:
        with pytest.raises(ValidationError):
            GenerationConfig(top_p=top_p)

    @pytest.mark.parametrize("max_tokens", [0, -10])
    def test_invalid_max_tokens(self, max_tokens: int) -> None:
        with pytest.raises(ValidationError):
            GenerationConfig(max_tokens=max_tokens)

    @pytest.mark.parametrize("penalty", [-2.1, 2.1])
    def test_invalid_frequency_penalty(self, penalty: float) -> None:
        with pytest.raises(ValidationError):
            GenerationConfig(frequency_penalty=penalty)


class TestParseSSELine:
    """测试 parse_sse_line 对各类 SSE 行的解析行为。"""

    def test_valid_content_chunk(self) -> None:
        line = 'data: {"choices":[{"index":0,"delta":{"content":"你好，智枢"}}]}'
        assert parse_sse_line(line) == "你好，智枢"

    def test_done_marker_returns_none(self) -> None:
        assert parse_sse_line("data: [DONE]") is None
        assert parse_sse_line("  data: [DONE]  ") is None

    def test_empty_and_comment_lines_return_none(self) -> None:
        assert parse_sse_line("") is None
        assert parse_sse_line("   ") is None
        assert parse_sse_line(": keep-alive") is None
        assert parse_sse_line("event: message") is None

    def test_role_only_delta_returns_none(self) -> None:
        line = 'data: {"choices":[{"index":0,"delta":{"role":"assistant"}}]}'
        assert parse_sse_line(line) is None

    def test_malformed_json_or_missing_choices_returns_none(self) -> None:
        assert parse_sse_line("data: {not-valid-json}") is None
        assert parse_sse_line('data: {"choices":[]}') is None


class TestStreamingLLMClient:
    """测试 StreamingLLMClient 的 SSE 流式产出、[DONE] 终止与分片聚合。"""

    def test_stream_chunks_and_aggregation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expected_chunks = ["智枢", "平台", "支持", "SSE", "流式输出。"]
        transport = create_mock_sse_transport(chunks=expected_chunks)
        client = StreamingLLMClient(transport=transport)

        assert client.is_mock is True
        messages = [
            {"role": "system", "content": "你是企业 AI 助手"},
            {"role": "user", "content": "测试流式输出"},
        ]
        cfg = GenerationConfig(temperature=0.2, top_p=0.9, max_tokens=256, frequency_penalty=0.1)

        received = list(client.stream_chat(messages, config=cfg))
        assert received == expected_chunks
        assert client.chat_aggregated(messages, config=cfg) == "".join(expected_chunks)

    def test_done_termination_ignores_trailing_chunks(self) -> None:
        transport = create_mock_sse_transport(
            chunks=["第一段", "第二段"],
            trailing_after_done=["[DONE]之后的脏数据"],
        )
        client = StreamingLLMClient(transport=transport)
        result = list(client.stream_chat([{"role": "user", "content": "hi"}]))
        assert result == ["第一段", "第二段"]

    def test_request_payload_carries_roles_and_generation_params(self) -> None:
        captured: dict[str, object] = {}

        def inspect_handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode("utf-8"))
            sse = (
                'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8")
            return httpx.Response(
                status_code=200,
                headers={"Content-Type": "text/event-stream"},
                content=sse,
            )

        client = StreamingLLMClient(transport=httpx.MockTransport(inspect_handler))
        messages = [
            {"role": "system", "content": "你是财务合规顾问"},
            {"role": "user", "content": "报销上限是多少？"},
            {"role": "assistant", "content": "一线城市住宿上限 600 元/晚。"},
            {"role": "user", "content": "二线城市呢？"},
        ]
        cfg = GenerationConfig(
            temperature=0.15,
            top_p=0.85,
            max_tokens=512,
            frequency_penalty=0.3,
            stream=False,  # stream_chat 会强制开启 stream=True
        )
        full_text = client.chat_aggregated(messages, config=cfg)
        assert full_text == "OK"

        body = captured["body"]
        assert isinstance(body, dict)
        assert body["temperature"] == 0.15
        assert body["top_p"] == 0.85
        assert body["max_tokens"] == 512
        assert body["frequency_penalty"] == 0.3
        assert body["stream"] is True
        assert body["messages"] == messages
