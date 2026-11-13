"""Day 08 单元测试：验证 ChatMessage 类的构造校验、序列化、Token 估算、类方法与静态方法"""
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.json_parser import load_session_json, save_session_json
from zhishu_agent.message import ChatMessage


@pytest.mark.parametrize("role", ["system", "user", "assistant", "tool"])
def test_chat_message_valid_roles(role: str):
    """测试所有合法角色均可正常实例化"""
    msg = ChatMessage(role=role, content="测试消息内容")
    assert msg.role == role
    assert msg.content == "测试消息内容"
    assert msg.name is None


@pytest.mark.parametrize("bad_role", ["admin", "usr", "model", "", "USER"])
def test_chat_message_invalid_role_raises(bad_role: str):
    """测试传入非法角色时构造函数抛出 ValueError"""
    with pytest.raises(ValueError, match="无效的消息角色"):
        ChatMessage(role=bad_role, content="非法角色测试")


def test_chat_message_invalid_types_raise():
    """测试 content 或 name 类型错误时抛出 TypeError"""
    with pytest.raises(TypeError, match="content"):
        ChatMessage(role="user", content=123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="name"):
        ChatMessage(role="user", content="你好", name=999)  # type: ignore[arg-type]


def test_to_dict_without_and_with_name():
    """测试 to_dict() 在 name 为 None 与非 None 时的输出结构"""
    msg_no_name = ChatMessage(role="user", content="你好，智枢！")
    assert msg_no_name.to_dict() == {
        "role": "user",
        "content": "你好，智枢！",
    }

    msg_with_name = ChatMessage(role="tool", content='{"temp": 22}', name="query_weather")
    assert msg_with_name.to_dict() == {
        "role": "tool",
        "content": '{"temp": 22}',
        "name": "query_weather",
    }


def test_from_dict_success_and_roundtrip():
    """测试类方法 from_dict() 反序列化以及与 to_dict() 的往返一致性"""
    raw = {"role": "assistant", "content": "已完成查询", "name": "planner_agent"}
    msg = ChatMessage.from_dict(raw)
    assert isinstance(msg, ChatMessage)
    assert msg.role == "assistant"
    assert msg.content == "已完成查询"
    assert msg.name == "planner_agent"
    assert msg.to_dict() == raw


def test_from_dict_invalid_input_raises():
    """测试 from_dict() 遇到非字典、缺少字段或非法角色时抛出 ValueError"""
    with pytest.raises(ValueError, match="dict"):
        ChatMessage.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="role"):
        ChatMessage.from_dict({"role": "user"})

    with pytest.raises(ValueError, match="无效的消息角色"):
        ChatMessage.from_dict({"role": "unknown", "content": "hi"})


def test_is_valid_role_static_method():
    """测试静态方法 is_valid_role() 无需实例化即可直接校验角色"""
    assert ChatMessage.is_valid_role("system") is True
    assert ChatMessage.is_valid_role("user") is True
    assert ChatMessage.is_valid_role("assistant") is True
    assert ChatMessage.is_valid_role("tool") is True
    assert ChatMessage.is_valid_role("developer") is False
    assert ChatMessage.is_valid_role(123) is False  # type: ignore[arg-type]


def test_estimate_tokens():
    """测试实例方法 estimate_tokens() 对空文本、英文与中文的估算逻辑"""
    empty_msg = ChatMessage(role="user", content="")
    assert empty_msg.estimate_tokens() == 0

    short_en = ChatMessage(role="user", content="Hi")
    assert short_en.estimate_tokens() >= 1

    zh_msg = ChatMessage(role="assistant", content="星辰数科智枢平台")
    en_msg = ChatMessage(role="assistant", content="hello world")
    assert zh_msg.estimate_tokens() > en_msg.estimate_tokens()


def test_repr_and_equality():
    """测试 __repr__ 与 __eq__ 魔术方法"""
    m1 = ChatMessage(role="user", content="你好", name="chenmo")
    m2 = ChatMessage(role="user", content="你好", name="chenmo")
    m3 = ChatMessage(role="user", content="再见", name="chenmo")
    assert m1 == m2
    assert m1 != m3
    assert (m1 == {"role": "user", "content": "你好"}) is False
    assert "ChatMessage(role='user', content='你好', name='chenmo')" == repr(m1)


def test_integration_with_json_parser(tmp_path: Path):
    """测试 ChatMessage 列表与 Day 05 json_parser 的持久化往返集成"""
    messages = [
        ChatMessage(role="system", content="你是企业级智能体助手"),
        ChatMessage(role="user", content="请总结今日架构升级", name="chenmo"),
    ]
    session_file = tmp_path / "day08_session.json"
    save_session_json(session_file, [m.to_dict() for m in messages])

    loaded_dicts = load_session_json(session_file)
    restored = [ChatMessage.from_dict(d) for d in loaded_dicts]
    assert restored == messages
