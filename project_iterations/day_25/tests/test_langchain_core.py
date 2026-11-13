"""Day 25 单元测试：验证 LangChain 核心消息、ChatPromptTemplate 与多模型无缝切换。"""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.langchain_core import (
    AIMessage,
    BaseChatModel,
    BaseMessage,
    ChatPromptTemplate,
    ChatPromptValue,
    DeepSeekChatModel,
    HumanMessage,
    QwenChatModel,
    SystemMessage,
    get_chat_model,
)


def test_message_hierarchy_and_serialization() -> None:
    """验证 System/Human/AIMessage 继承关系、角色标识与字典序列化。"""
    sys_msg = SystemMessage(content="你是星辰数科技术助手")
    human_msg = HumanMessage(content="如何降低多模型接入成本？")
    ai_msg = AIMessage(content="通过 BaseChatModel 统一接口层。")

    assert isinstance(sys_msg, BaseMessage)
    assert isinstance(human_msg, BaseMessage)
    assert isinstance(ai_msg, BaseMessage)

    assert sys_msg.role == "system" and sys_msg.type == "system"
    assert human_msg.role == "user" and human_msg.type == "user"
    assert ai_msg.role == "assistant" and ai_msg.type == "assistant"

    assert sys_msg.to_dict() == {"role": "system", "content": "你是星辰数科技术助手"}
    assert human_msg.to_dict() == {"role": "user", "content": "如何降低多模型接入成本？"}
    assert ai_msg.to_dict() == {"role": "assistant", "content": "通过 BaseChatModel 统一接口层。"}


def test_chat_prompt_template_from_messages_and_validation() -> None:
    """验证 ChatPromptTemplate.from_messages 占位符提取、格式化与缺失变量校验。"""
    static_ai = AIMessage(content="好的，请问需要分析哪个模块？")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是{company}的{role}。"),
            ("human", "请检查 {module} 模块。"),
            static_ai,
            ("user", "重点关注 {focus}。"),
        ]
    )

    assert prompt.input_variables == ["company", "role", "module", "focus"]

    messages = prompt.format_messages(
        company="星辰数科",
        role="架构师",
        module="RAG 检索",
        focus="响应延迟",
    )
    assert len(messages) == 4
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == "你是星辰数科的架构师。"
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "请检查 RAG 检索 模块。"
    assert messages[2] is static_ai
    assert isinstance(messages[3], HumanMessage)
    assert messages[3].content == "重点关注 响应延迟。"

    prompt_val = prompt.invoke(
        {"company": "星辰数科", "role": "架构师", "module": "RAG 检索", "focus": "响应延迟"}
    )
    assert isinstance(prompt_val, ChatPromptValue)
    assert len(prompt_val.to_messages()) == 4

    with pytest.raises(KeyError, match="focus"):
        prompt.format_messages(company="星辰数科", role="架构师", module="RAG 检索")


def test_base_chat_model_is_abstract() -> None:
    """验证 BaseChatModel 不可直接实例化，强制子类实现 _generate。"""
    with pytest.raises(TypeError):
        BaseChatModel(model_name="invalid")  # type: ignore[abstract]


def test_unified_model_switching_deepseek_and_qwen() -> None:
    """验证同一套 ChatPromptTemplate 可无缝切换 DeepSeekChatModel 与 QwenChatModel。"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是企业知识库助手"),
            ("human", "请解释 {concept} 的核心价值"),
        ]
    )
    prompt_value = prompt.invoke({"concept": "统一模型网关"})

    deepseek = get_chat_model("deepseek")
    qwen = get_chat_model("qwen")

    assert isinstance(deepseek, DeepSeekChatModel)
    assert isinstance(qwen, QwenChatModel)

    ds_reply = deepseek.invoke(prompt_value)
    qw_reply = qwen.invoke(prompt_value)

    assert isinstance(ds_reply, AIMessage)
    assert isinstance(qw_reply, AIMessage)
    assert "DeepSeek/deepseek-chat" in ds_reply.content
    assert "统一模型网关" in ds_reply.content
    assert ds_reply.response_metadata["provider"] == "deepseek"

    assert "Qwen/qwen-plus" in qw_reply.content
    assert "统一模型网关" in qw_reply.content
    assert qw_reply.response_metadata["provider"] == "qwen"

    # 校验确定性：相同输入重复调用返回完全一致内容
    assert deepseek.invoke(prompt_value).content == ds_reply.content
    assert qwen.invoke("单句字符串直传测试").response_metadata["message_count"] == 1


def test_batch_and_invalid_provider() -> None:
    """验证批量推理与非法厂商名异常提示。"""
    model = DeepSeekChatModel(model_name="deepseek-reasoner")
    results = model.batch(["问题一", [HumanMessage(content="问题二")]])
    assert len(results) == 2
    assert "问题一" in results[0].content
    assert "问题二" in results[1].content

    with pytest.raises(ValueError, match="未知模型厂商"):
        get_chat_model("unknown-llm")
