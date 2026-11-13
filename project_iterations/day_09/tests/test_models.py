"""Day 09 单元测试：覆盖 ChatMessage、BaseLLMModel、OpenAIModel、QwenModel 的继承、多态、@property 与魔术方法"""
import sys
from pathlib import Path

import pytest

# 确保可以直接导入 project_iterations/day_09 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.message import ChatMessage
from zhishu_agent.models import BaseLLMModel, OpenAIModel, QwenModel


class TestChatMessage:
    """测试 ChatMessage 基础行为。"""

    def test_create_valid_message(self) -> None:
        msg = ChatMessage(role="user", content="你好，智枢平台")
        assert msg.role == "user"
        assert msg.content == "你好，智枢平台"
        assert msg.to_dict() == {"role": "user", "content": "你好，智枢平台"}
        assert str(msg) == "[user] 你好，智枢平台"

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(ValueError, match="无效的消息角色"):
            ChatMessage(role="admin", content="test")

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="非空字符串"):
            ChatMessage(role="user", content="   ")


class TestBaseLLMModel:
    """测试 BaseLLMModel 基类的属性校验与魔术方法。"""

    def test_temperature_property_valid_boundaries(self) -> None:
        base = BaseLLMModel(model_name="base-v1", temperature=0.0)
        assert base.temperature == 0.0

        base.temperature = 2.0
        assert base.temperature == 2.0

        base.temperature = 1
        assert base.temperature == 1.0
        assert isinstance(base.temperature, float)

    @pytest.mark.parametrize("bad_temp", [-0.1, 2.01, 3.5, -10])
    def test_temperature_out_of_range_raises(self, bad_temp: float) -> None:
        base = BaseLLMModel(model_name="base-v1")
        with pytest.raises(ValueError, match="0.0 到 2.0"):
            base.temperature = bad_temp

    @pytest.mark.parametrize("bad_type", ["0.7", True, None, [0.5]])
    def test_temperature_invalid_type_raises(self, bad_type: object) -> None:
        with pytest.raises(TypeError, match="数值类型"):
            BaseLLMModel(model_name="base-v1", temperature=bad_type)  # type: ignore[arg-type]

    def test_empty_model_name_raises(self) -> None:
        with pytest.raises(ValueError, match="model_name"):
            BaseLLMModel(model_name="   ")

    def test_str_and_repr(self) -> None:
        base = BaseLLMModel(model_name="base-v1", temperature=0.5)
        assert str(base) == "[BaseLLMModel] base-v1 (temperature=0.5)"
        assert repr(base) == "BaseLLMModel(model_name='base-v1', temperature=0.5)"

    def test_generate_not_implemented(self) -> None:
        base = BaseLLMModel(model_name="base-v1")
        with pytest.raises(NotImplementedError):
            base.generate([ChatMessage(role="user", content="hi")])

    def test_empty_messages_raises(self) -> None:
        base = BaseLLMModel(model_name="base-v1")
        with pytest.raises(ValueError, match="非空"):
            base.generate([])


class TestSubclassesAndPolymorphism:
    """测试 OpenAIModel 与 QwenModel 的继承、多态与 __call__。"""

    def test_inheritance_and_super_init(self) -> None:
        openai_m = OpenAIModel(model_name="gpt-4o", temperature=0.2, api_base="https://custom.endpoint/v1")
        qwen_m = QwenModel(model_name="qwen-max", temperature=1.1, enable_search=True)

        assert issubclass(OpenAIModel, BaseLLMModel)
        assert issubclass(QwenModel, BaseLLMModel)
        assert isinstance(openai_m, BaseLLMModel)
        assert isinstance(qwen_m, BaseLLMModel)

        assert openai_m.model_name == "gpt-4o"
        assert openai_m.temperature == 0.2
        assert openai_m.api_base == "https://custom.endpoint/v1"

        assert qwen_m.model_name == "qwen-max"
        assert qwen_m.temperature == 1.1
        assert qwen_m.enable_search is True

    def test_polymorphic_generate(self) -> None:
        models: list[BaseLLMModel] = [
            OpenAIModel(model_name="gpt-4o-mini", temperature=0.5),
            QwenModel(model_name="qwen-plus", temperature=0.9, enable_search=True),
        ]
        history = [
            ChatMessage(role="system", content="你是智枢平台助手。"),
            ChatMessage(role="user", content="什么是多态？"),
        ]

        responses = [m.generate(history) for m in models]
        assert all(isinstance(r, ChatMessage) and r.role == "assistant" for r in responses)
        assert "OpenAI:gpt-4o-mini" in responses[0].content
        assert "2轮上下文" in responses[0].content
        assert "Qwen:qwen-plus" in responses[1].content
        assert "联网增强" in responses[1].content

    def test_call_magic_method_with_str_and_list(self) -> None:
        model = OpenAIModel(model_name="gpt-4o-mini", temperature=0.7)

        res_from_str = model("你好")
        assert isinstance(res_from_str, ChatMessage)
        assert res_from_str.role == "assistant"
        assert "你好" in res_from_str.content

        res_from_list = model([ChatMessage(role="user", content="多轮测试")])
        assert "多轮测试" in res_from_list.content
