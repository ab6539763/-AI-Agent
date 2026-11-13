"""Day 14 单元测试：全面覆盖多轮对话记忆、斜杠命令 (/clear, /save, /load, /stats, /exit)、异常映射与重试恢复"""
import json
import sys
from pathlib import Path

import httpx
import pytest

# 确保可以直接导入 project_iterations/day_14 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.chat_assistant import MultiTurnAssistant
from zhishu_agent.exceptions import (
    CommandError,
    ConfigurationError,
    LLMAPIError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from zhishu_agent.llm_client import LLMClient
from zhishu_agent.message import ChatMessage


class TestChatMessage:
    """测试 ChatMessage 校验与序列化/反序列化。"""

    def test_roundtrip_serialization(self) -> None:
        msg = ChatMessage(role="user", content="你好，智枢")
        full = msg.to_full_dict()
        restored = ChatMessage.from_dict(full)
        assert restored == msg
        assert restored.timestamp == msg.timestamp
        assert msg.to_dict() == {"role": "user", "content": "你好，智枢"}

    def test_invalid_role_and_empty_content(self) -> None:
        with pytest.raises(ValueError, match="无效的消息角色"):
            ChatMessage(role="root", content="hi")
        with pytest.raises(ValueError, match="非空字符串"):
            ChatMessage(role="user", content="   ")


class TestMultiTurnConversation:
    """测试多轮对话上下文记忆与请求载荷透传。"""

    def test_multi_turn_memory_accumulates_and_sends_full_history(self) -> None:
        captured_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(payload)
            turn = sum(1 for m in payload["messages"] if m["role"] == "user")
            return httpx.Response(
                200,
                json={
                    "model": "gpt-4o-mini",
                    "choices": [{"message": {"role": "assistant", "content": f"第{turn}轮回复"}}],
                    "usage": {"prompt_tokens": 10 * turn, "completion_tokens": 5, "total_tokens": 10 * turn + 5},
                },
            )

        client = LLMClient(api_key="test-key", transport=httpx.MockTransport(handler))
        assistant = MultiTurnAssistant(client=client, system_prompt="你是测试助手")

        reply1 = assistant.ask("我叫陈默")
        reply2 = assistant.ask("请问我叫什么？")

        assert reply1 == "第1轮回复"
        assert reply2 == "第2轮回复"
        assert len(assistant.messages) == 5  # system + user1 + assistant1 + user2 + assistant2
        assert [m.role for m in assistant.messages] == ["system", "user", "assistant", "user", "assistant"]

        # 验证第 2 次请求携带了完整的 4 条前置上下文（system + user1 + assistant1 + user2）
        assert len(captured_payloads[1]["messages"]) == 4
        assert captured_payloads[1]["messages"][1]["content"] == "我叫陈默"
        assert captured_payloads[1]["messages"][2]["content"] == "第1轮回复"

    def test_default_mock_fallback_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assistant = MultiTurnAssistant()
        assert assistant.client.is_mock is True

        r1 = assistant.ask("我叫陈默")
        r2 = assistant.ask("你还记得我是谁吗？")
        assert "第1轮" in r1
        assert "陈默" in r2


class TestSlashCommands:
    """测试 /clear, /save, /load, /stats, /help, /exit 斜杠命令。"""

    def test_clear_keeps_system_prompt_and_resets_stats(self) -> None:
        assistant = MultiTurnAssistant(system_prompt="系统提示词：严禁胡编乱造")
        assistant.ask("第一轮问题")
        assistant.ask("第二轮问题")
        assert len(assistant.messages) == 5
        assert assistant.turns == 2

        cont, msg = assistant.process_input("/clear")
        assert cont is True
        assert "已清空" in msg
        assert len(assistant.messages) == 1
        assert assistant.messages[0].role == "system"
        assert assistant.messages[0].content == "系统提示词：严禁胡编乱造"
        assert assistant.turns == 0
        assert assistant.total_tokens == 0

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        save_file = tmp_path / "sessions" / "chat_history.json"
        bot1 = MultiTurnAssistant(system_prompt="我是智枢助手")
        bot1.ask("介绍一下 Python 装饰器")
        bot1.ask("再举个重试的例子")

        cont, save_msg = bot1.process_input(f"/save {save_file}")
        assert cont is True
        assert save_file.exists()
        assert "已保存" in save_msg

        bot2 = MultiTurnAssistant(system_prompt="另一个初始提示")
        cont, load_msg = bot2.process_input(f"/load {save_file}")
        assert cont is True
        assert "已从" in load_msg
        assert bot2.messages == bot1.messages
        assert bot2.turns == 2
        assert bot2.total_tokens == bot1.total_tokens

    def test_save_and_load_error_handling(self, tmp_path: Path) -> None:
        assistant = MultiTurnAssistant()
        with pytest.raises(CommandError, match="用法: /save"):
            assistant.process_input("/save")

        with pytest.raises(CommandError, match="不存在"):
            assistant.process_input(f"/load {tmp_path / 'missing.json'}")

        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(CommandError, match="解析会话 JSON 失败"):
            assistant.process_input(f"/load {bad_json}")

    def test_stats_and_exit_and_unknown_command(self) -> None:
        assistant = MultiTurnAssistant()
        assistant.ask("测试统计")

        cont, stats_text = assistant.process_input("/stats")
        assert cont is True
        assert "对话轮数   : 1 轮" in stats_text
        assert "上下文消息 : 3 条" in stats_text
        assert "total=" in stats_text

        cont_help, help_text = assistant.process_input("/help")
        assert cont_help is True
        assert "/clear" in help_text

        cont_exit, exit_text = assistant.process_input("/exit")
        assert cont_exit is False
        assert "再见" in exit_text

        with pytest.raises(CommandError, match="未知指令"):
            assistant.process_input("/unknown_cmd")


class TestRetryAndErrorRecovery:
    """测试限流重试、非可重试异常快速失败以及对话历史异常回滚。"""

    def test_retry_succeeds_after_transient_429_and_503(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(429, json={"error": "rate limit"})
            if attempts["count"] == 2:
                return httpx.Response(503, json={"error": "service unavailable"})
            return httpx.Response(
                200,
                json={
                    "model": "gpt-4o-mini",
                    "choices": [{"message": {"role": "assistant", "content": "重试后成功回复"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                },
            )

        client = LLMClient(
            api_key="test-key",
            max_retries=2,
            retry_delay=0.0,
            transport=httpx.MockTransport(handler),
        )
        assistant = MultiTurnAssistant(client=client)
        reply = assistant.ask("测试瞬时故障恢复")
        assert reply == "重试后成功回复"
        assert attempts["count"] == 3
        assert len(assistant.messages) == 3

    def test_non_retryable_401_fails_fast_and_rolls_back_user_message(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(401, text="Invalid API Key")

        client = LLMClient(
            api_key="bad-key",
            max_retries=3,
            retry_delay=0.0,
            transport=httpx.MockTransport(handler),
        )
        assistant = MultiTurnAssistant(client=client, system_prompt="sys")

        with pytest.raises(LLMAPIError) as exc_info:
            assistant.ask("这句提问不应残留在历史中")

        assert exc_info.value.status_code == 401
        assert attempts["count"] == 1  # 401 不可重试，立即失败
        # 验证未提交的 user 消息已被回滚，历史中仅剩 system 消息
        assert len(assistant.messages) == 1
        assert assistant.messages[0].role == "system"
        assert assistant.turns == 0

    def test_timeout_retries_and_rolls_back_on_exhaustion(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            raise httpx.ReadTimeout("read timed out")

        client = LLMClient(
            api_key="test-key",
            max_retries=2,
            retry_delay=0.0,
            transport=httpx.MockTransport(handler),
        )
        assistant = MultiTurnAssistant(client=client, system_prompt="sys")

        with pytest.raises(LLMTimeoutError):
            assistant.ask("超时测试")

        assert attempts["count"] == 3  # 初次 + 2 次重试
        assert len(assistant.messages) == 1

    def test_rate_limit_exhaustion_raises_specific_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Too Many Requests")

        client = LLMClient(
            api_key="test-key",
            max_retries=1,
            retry_delay=0.0,
            transport=httpx.MockTransport(handler),
        )
        assistant = MultiTurnAssistant(client=client)
        with pytest.raises(LLMRateLimitError):
            assistant.ask("限流耗尽")

    def test_invalid_temperature_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError):
            MultiTurnAssistant(temperature=2.5)
