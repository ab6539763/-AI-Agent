"""Day 06 单元测试：验证函数参数体系、高阶流水线与嵌套递归 Token 统计"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.pipeline_fn import (
    apply_pipeline,
    build_api_payload,
    count_nested_tokens,
)


class TestBuildApiPayload:
    """测试 build_api_payload 的位置参数、*args、默认关键字参数与 **kwargs"""

    def test_basic_positional_and_defaults(self):
        msg1 = {"role": "system", "content": "你是智枢助手"}
        msg2 = {"role": "user", "content": "你好"}
        payload = build_api_payload("deepseek-chat", msg1, msg2)

        assert payload["model"] == "deepseek-chat"
        assert payload["messages"] == [msg1, msg2]
        assert payload["temperature"] == 0.7

    def test_extra_kwargs_and_custom_temperature(self):
        msg = {"role": "user", "content": "分析财报"}
        payload = build_api_payload(
            "qwen-plus",
            msg,
            temperature=0.2,
            max_tokens=4096,
            stream=True,
            top_p=0.9,
        )

        assert payload["model"] == "qwen-plus"
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 4096
        assert payload["stream"] is True
        assert payload["top_p"] == 0.9

    def test_empty_messages_allowed(self):
        payload = build_api_payload("deepseek-chat")
        assert payload["messages"] == []
        assert payload["temperature"] == 0.7

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            build_api_payload("   ")

    def test_invalid_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature"):
            build_api_payload("deepseek-chat", temperature=2.5)
        with pytest.raises(ValueError, match="temperature"):
            build_api_payload("deepseek-chat", temperature=-0.1)

    def test_non_dict_message_raises(self):
        with pytest.raises(TypeError, match="dict"):
            build_api_payload("deepseek-chat", "not-a-dict")  # type: ignore[arg-type]


class TestApplyPipeline:
    """测试高阶函数 apply_pipeline 与 lambda 变换链"""

    def test_multiple_lambda_transforms_in_order(self):
        raw = "   请总结   【机密】星辰数科  财报！  "
        cleaned = apply_pipeline(
            raw,
            str.strip,
            lambda s: " ".join(s.split()),
            lambda s: s.replace("【机密】", "[REDACTED]"),
        )
        assert cleaned == "请总结 [REDACTED]星辰数科 财报！"

    def test_no_transforms_returns_original(self):
        assert apply_pipeline("智枢平台") == "智枢平台"

    def test_non_str_text_raises(self):
        with pytest.raises(TypeError, match="text"):
            apply_pipeline(123, str.strip)  # type: ignore[arg-type]

    def test_non_callable_transform_raises(self):
        with pytest.raises(TypeError, match="不可调用"):
            apply_pipeline("hello", "not_a_func")  # type: ignore[arg-type]


class TestCountNestedTokens:
    """测试递归函数 count_nested_tokens 对嵌套 JSON/消息树的遍历"""

    def test_plain_string(self):
        assert count_nested_tokens("智枢AI") == 4
        assert count_nested_tokens("") == 0

    def test_nested_dict_and_list(self):
        tree = {
            "model": "deepseek",  # 8
            "messages": [
                {"role": "user", "content": "你好"},  # 4 + 2 = 6
                {"role": "assistant", "content": "收到！"},  # 9 + 3 = 12
            ],
            "temperature": 0.7,  # scalar float -> 0
            "stream": True,  # scalar bool -> 0
            "extra": None,  # None -> 0
        }
        # 8 + 4 + 2 + 9 + 3 = 26
        assert count_nested_tokens(tree) == 26

    def test_deeply_nested_structures(self):
        deep = [{"a": [{"b": "12345"}]}, ["678", {"c": []}]]
        assert count_nested_tokens(deep) == 8

    def test_empty_containers(self):
        assert count_nested_tokens({}) == 0
        assert count_nested_tokens([]) == 0
