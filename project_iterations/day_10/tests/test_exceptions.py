"""Day 10 单元测试：覆盖自定义异常继承体系、ChatMessage/模型校验重构与 APIResponseError"""
import sys
from pathlib import Path

import pytest

# 确保可以直接导入 project_iterations/day_10 下的 zhishu_agent
DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from main import safe_invoke
from zhishu_agent import (
    APIResponseError,
    BaseLLMModel,
    ChatMessage,
    InvalidRoleError,
    ModelConfigError,
    OpenAIModel,
    QwenModel,
    ZhiShuError,
)


class TestExceptionHierarchy:
    """测试自定义异常类的继承关系与元数据字段。"""

    def test_inheritance_chain(self) -> None:
        assert issubclass(ZhiShuError, Exception)
        assert issubclass(InvalidRoleError, ZhiShuError)
        assert issubclass(ModelConfigError, ZhiShuError)
        assert issubclass(APIResponseError, ZhiShuError)

    def test_error_codes_and_str(self) -> None:
        role_err = InvalidRoleError("hacker", ("system", "user"))
        assert role_err.error_code == "INVALID_ROLE"
        assert role_err.role == "hacker"
        assert "[INVALID_ROLE]" in str(role_err)

        cfg_err = ModelConfigError("温度超出范围")
        assert cfg_err.error_code == "MODEL_CONFIG_ERROR"
        assert "[MODEL_CONFIG_ERROR]" in str(cfg_err)

        api_err = APIResponseError("服务不可用", status_code=503)
        assert api_err.error_code == "API_RESPONSE_ERROR"
        assert api_err.status_code == 503
        assert "503" in str(api_err)


class TestMessageCustomExceptions:
    """测试 ChatMessage 抛出的自定义异常。"""

    def test_valid_message(self) -> None:
        msg = ChatMessage(role="user", content="你好，Day 10")
        assert msg.role == "user"
        assert msg.to_dict() == {"role": "user", "content": "你好，Day 10"}

    def test_invalid_role_raises_custom_error(self) -> None:
        with pytest.raises(InvalidRoleError, match="无效的消息角色") as exc_info:
            ChatMessage(role="admin", content="test")
        assert isinstance(exc_info.value, ZhiShuError)
        assert exc_info.value.role == "admin"

    def test_empty_content_raises_zhishu_error(self) -> None:
        with pytest.raises(ZhiShuError, match="非空字符串"):
            ChatMessage(role="user", content="   ")


class TestModelConfigAndAPIErrors:
    """测试模型配置异常 (ModelConfigError) 与接口异常 (APIResponseError)。"""

    def test_empty_model_name_raises_model_config_error(self) -> None:
        with pytest.raises(ModelConfigError, match="model_name"):
            BaseLLMModel(model_name="   ")

    @pytest.mark.parametrize("bad_temp", [-0.5, 2.1, 10.0])
    def test_temperature_out_of_range_raises_model_config_error(self, bad_temp: float) -> None:
        model = OpenAIModel(model_name="gpt-4o-mini", temperature=0.7)
        with pytest.raises(ModelConfigError, match="0.0 到 2.0"):
            model.temperature = bad_temp

    @pytest.mark.parametrize("bad_type", ["0.7", True, None, [0.5]])
    def test_temperature_bad_type_raises_model_config_error(self, bad_type: object) -> None:
        with pytest.raises(ModelConfigError, match="数值类型"):
            QwenModel(model_name="qwen-plus", temperature=bad_type)  # type: ignore[arg-type]

    def test_empty_messages_raises_model_config_error(self) -> None:
        model = OpenAIModel()
        with pytest.raises(ModelConfigError, match="非空"):
            model.generate([])

    def test_non_chat_message_item_raises_model_config_error(self) -> None:
        model = QwenModel()
        with pytest.raises(ModelConfigError, match="ChatMessage"):
            model.generate(["not a ChatMessage"])  # type: ignore[list-item]

    def test_api_response_error_triggered_on_simulate_flag(self) -> None:
        model = OpenAIModel(simulate_error=True)
        with pytest.raises(APIResponseError, match="模拟限流") as exc_info:
            model("你好")
        assert exc_info.value.status_code == 503

    def test_api_response_error_triggered_on_prompt_marker(self) -> None:
        model = QwenModel()
        with pytest.raises(APIResponseError, match="超时") as exc_info:
            model("[SIMULATE_ERROR] 触发超时")
        assert exc_info.value.status_code == 504


class TestSafeInvokeFlow:
    """测试 main.py 中 try/except/else/finally 容错链路。"""

    def test_safe_invoke_success_else_branch(self, capsys: pytest.CaptureFixture[str]) -> None:
        model = OpenAIModel(model_name="gpt-4o-mini", temperature=0.5)
        res = safe_invoke(model, role="user", prompt="测试正常链路")
        captured = capsys.readouterr().out
        assert "OpenAI:gpt-4o-mini" in res
        assert "[成功-else分支]" in captured
        assert "[收尾-finally分支]" in captured

    def test_safe_invoke_invalid_role_finally_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        model = QwenModel()
        res = safe_invoke(model, role="guest", prompt="测试异常链路")
        captured = capsys.readouterr().out
        assert res == "FALLBACK(role): INVALID_ROLE"
        assert "[拦截-角色异常]" in captured
        assert "[收尾-finally分支]" in captured

    def test_safe_invoke_api_error_finally_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        model = OpenAIModel(simulate_error=True)
        res = safe_invoke(model, role="user", prompt="你好")
        captured = capsys.readouterr().out
        assert res == "FALLBACK(api): API_RESPONSE_ERROR"
        assert "[拦截-接口异常]" in captured
        assert "[收尾-finally分支]" in captured
