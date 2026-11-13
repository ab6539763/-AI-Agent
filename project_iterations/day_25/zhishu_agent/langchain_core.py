"""Day 25：LangChain 核心抽象层（零外部重依赖、离线可确定性运行）。

提供与 LangChain `langchain_core` 对齐的三大核心抽象：
1. 消息协议体系：`BaseMessage`、`SystemMessage`、`HumanMessage`、`AIMessage`
2. 提示词模板：`ChatPromptTemplate.from_messages(...)` 与 `ChatPromptValue`
3. 统一模型接口：`BaseChatModel`、`DeepSeekChatModel`、`QwenChatModel` 与 `get_chat_model` 网关工厂
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from string import Formatter
from typing import Any, Sequence


@dataclass
class BaseMessage:
    """所有对话消息的基类，统一封装内容、角色与扩展元数据。"""

    content: str
    role: str = "generic"
    additional_kwargs: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        """与 LangChain 消息的 `.type` 属性保持一致。"""
        return self.role

    def to_dict(self) -> dict[str, str]:
        """转换为标准 OpenAI / 国产大模型 API 兼容的消息字典。"""
        return {"role": self.role, "content": self.content}

    def pretty_repr(self) -> str:
        """生成可读性良好的单行/多行消息展示文本。"""
        return f"[{self.role.upper()}] {self.content}"


@dataclass
class SystemMessage(BaseMessage):
    """系统提示词消息，用于设定智能体角色、约束与业务上下文。"""

    role: str = field(default="system", init=False)


@dataclass
class HumanMessage(BaseMessage):
    """用户提问消息，对应 API 协议中的 `user` 角色。"""

    role: str = field(default="user", init=False)


@dataclass
class AIMessage(BaseMessage):
    """大模型回复消息，对应 API 协议中的 `assistant` 角色。"""

    role: str = field(default="assistant", init=False)


@dataclass
class ChatPromptValue:
    """`ChatPromptTemplate.invoke(...)` 的标准化输出载体。"""

    messages: list[BaseMessage]

    def to_messages(self) -> list[BaseMessage]:
        return list(self.messages)

    def to_string(self) -> str:
        return "\n".join(msg.pretty_repr() for msg in self.messages)


_ROLE_ALIASES: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "human": HumanMessage,
    "user": HumanMessage,
    "ai": AIMessage,
    "assistant": AIMessage,
}


def _extract_placeholders(template: str) -> list[str]:
    """提取模板字符串中的占位符变量名（去重并保持首次出现顺序）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    formatter = Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if field_name is not None and field_name != "":
            # 仅取根变量名（兼容如 {user}）
            root_name = field_name.split(".")[0].split("[")[0]
            if root_name not in seen:
                seen.add(root_name)
                ordered.append(root_name)
    return ordered


class ChatPromptTemplate:
    """多角色对话提示词模板，支持 `(role, template)` 元组与 `BaseMessage` 混排。"""

    def __init__(self, message_specs: Sequence[tuple[str, str] | BaseMessage]) -> None:
        self._specs: list[tuple[str, str] | BaseMessage] = []
        input_vars: list[str] = []
        seen_vars: set[str] = set()

        for item in message_specs:
            if isinstance(item, BaseMessage):
                self._specs.append(item)
            elif isinstance(item, tuple) and len(item) == 2:
                role_raw, template = item
                role_key = role_raw.strip().lower()
                if role_key not in _ROLE_ALIASES:
                    raise ValueError(
                        f"不支持的消息角色 '{role_raw}'，可选值: {sorted(_ROLE_ALIASES.keys())}"
                    )
                if not isinstance(template, str):
                    raise TypeError("模板内容必须是字符串类型。")
                self._specs.append((role_key, template))
                for var in _extract_placeholders(template):
                    if var not in seen_vars:
                        seen_vars.add(var)
                        input_vars.append(var)
            else:
                raise TypeError(
                    "message_specs 元素必须是 `(role, template)` 元组或 `BaseMessage` 实例。"
                )

        self.input_variables: list[str] = input_vars

    @classmethod
    def from_messages(
        cls, messages: Sequence[tuple[str, str] | BaseMessage]
    ) -> ChatPromptTemplate:
        """LangChain 标准工厂方法：从消息列表构建 `ChatPromptTemplate`。"""
        return cls(messages)

    def format_messages(self, **kwargs: Any) -> list[BaseMessage]:
        """将模板变量注入消息列表，返回可直接传给 `BaseChatModel` 的 `BaseMessage` 列表。"""
        missing = [var for var in self.input_variables if var not in kwargs]
        if missing:
            raise KeyError(f"缺少模板必填变量: {', '.join(missing)}")

        rendered: list[BaseMessage] = []
        for spec in self._specs:
            if isinstance(spec, BaseMessage):
                rendered.append(spec)
            else:
                role_key, template = spec
                msg_cls = _ROLE_ALIASES[role_key]
                rendered.append(msg_cls(content=template.format(**kwargs)))
        return rendered

    def format(self, **kwargs: Any) -> str:
        """格式化为纯文本多轮对话字符串，便于日志打印与调试。"""
        messages = self.format_messages(**kwargs)
        return "\n".join(msg.pretty_repr() for msg in messages)

    def invoke(self, inputs: dict[str, Any]) -> ChatPromptValue:
        """以 Runnable 风格接收字典输入并返回 `ChatPromptValue`。"""
        if not isinstance(inputs, dict):
            raise TypeError("ChatPromptTemplate.invoke() 仅接收 dict 类型参数。")
        return ChatPromptValue(messages=self.format_messages(**inputs))


ChatInput = str | Sequence[BaseMessage] | ChatPromptValue


def _normalize_chat_input(prompt_input: ChatInput) -> list[BaseMessage]:
    """将字符串、`ChatPromptValue` 或消息列表统一归一化为 `list[BaseMessage]`。"""
    if isinstance(prompt_input, str):
        return [HumanMessage(content=prompt_input)]
    if isinstance(prompt_input, ChatPromptValue):
        return prompt_input.to_messages()
    if isinstance(prompt_input, Sequence):
        messages = list(prompt_input)
        if not messages:
            raise ValueError("消息列表不能为空。")
        if not all(isinstance(m, BaseMessage) for m in messages):
            raise TypeError("消息列表中的所有元素都必须是 `BaseMessage` 子类。")
        return messages
    raise TypeError(
        "不支持的输入类型，请传入 str、list[BaseMessage] 或 ChatPromptValue。"
    )


class BaseChatModel(ABC):
    """统一聊天模型抽象基类（屏蔽各厂商 SDK 差异）。"""

    provider: str = "base"

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature 必须在 [0.0, 2.0] 范围内。")
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0。")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def _generate(self, messages: list[BaseMessage]) -> AIMessage:
        """子类实现具体模型的推理逻辑。"""

    def invoke(self, prompt_input: ChatInput) -> AIMessage:
        """统一同步调用入口，支持 str / list[BaseMessage] / ChatPromptValue。"""
        messages = _normalize_chat_input(prompt_input)
        return self._generate(messages)

    def batch(self, inputs: Sequence[ChatInput]) -> list[AIMessage]:
        """批量调用接口，保持输入输出顺序一致。"""
        return [self.invoke(item) for item in inputs]


def _extract_context_summary(messages: list[BaseMessage]) -> tuple[str, str]:
    """提取最近一条系统指令与用户消息，用于生成确定性离线回复。"""
    system_text = ""
    latest_user = ""
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_text = msg.content
        elif isinstance(msg, HumanMessage):
            latest_user = msg.content
    if not latest_user and messages:
        latest_user = messages[-1].content
    return system_text, latest_user


class DeepSeekChatModel(BaseChatModel):
    """DeepSeek 模型适配器（离线确定性仿真，接口完全对齐 LangChain ChatModel）。"""

    provider: str = "deepseek"

    def __init__(
        self,
        model_name: str = "deepseek-chat",
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature, max_tokens=max_tokens)

    def _generate(self, messages: list[BaseMessage]) -> AIMessage:
        system_text, latest_user = _extract_context_summary(messages)
        role_hint = f"（遵循系统设定：{system_text}）" if system_text else ""
        content = (
            f"[DeepSeek/{self.model_name}]{role_hint}\n"
            f"针对您的输入「{latest_user}」，已完成结构化推演："
            f"共接收 {len(messages)} 条上下文消息，建议采用分层解耦架构并保持接口契约稳定。"
        )
        return AIMessage(
            content=content,
            response_metadata={
                "provider": self.provider,
                "model_name": self.model_name,
                "temperature": self.temperature,
                "message_count": len(messages),
                "usage": {
                    "prompt_tokens": sum(len(m.content) for m in messages),
                    "completion_tokens": len(content),
                },
            },
        )


class QwenChatModel(BaseChatModel):
    """通义千问（Qwen）模型适配器（离线确定性仿真，接口完全对齐 LangChain ChatModel）。"""

    provider: str = "qwen"

    def __init__(
        self,
        model_name: str = "qwen-plus",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature, max_tokens=max_tokens)

    def _generate(self, messages: list[BaseMessage]) -> AIMessage:
        system_text, latest_user = _extract_context_summary(messages)
        role_hint = f"（角色设定：{system_text}）" if system_text else ""
        content = (
            f"[Qwen/{self.model_name}]{role_hint}\n"
            f"已收到问题「{latest_user}」（上下文共 {len(messages)} 轮次）。"
            f"通义千问为您生成企业级稳健方案：通过统一网关屏蔽底层模型差异，实现零代码侵入切换。"
        )
        return AIMessage(
            content=content,
            response_metadata={
                "provider": self.provider,
                "model_name": self.model_name,
                "temperature": self.temperature,
                "message_count": len(messages),
                "usage": {
                    "prompt_tokens": sum(len(m.content) for m in messages),
                    "completion_tokens": len(content),
                },
            },
        )


def get_chat_model(provider: str, **kwargs: Any) -> BaseChatModel:
    """统一多模型网关工厂：按配置动态切换 DeepSeek / Qwen 实现。"""
    normalized = provider.strip().lower()
    registry: dict[str, type[BaseChatModel]] = {
        "deepseek": DeepSeekChatModel,
        "qwen": QwenChatModel,
    }
    if normalized not in registry:
        raise ValueError(
            f"未知模型厂商 '{provider}'，当前仅支持: {', '.join(sorted(registry))}"
        )
    return registry[normalized](**kwargs)
