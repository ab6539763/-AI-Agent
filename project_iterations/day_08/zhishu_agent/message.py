"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 08 迭代模块
功能：面向对象重构（OOP Part 1）—— 标准对话消息实体类 ChatMessage

业务背景：
在 Day 05 中，我们用裸字典 {"role": "user", "content": "..."} 表示对话消息，
但在企业级工程中，裸字典缺乏字段校验（比如把 role 拼成 "usr" 也不会报错），
也无法自带 Token 估算等业务行为。
从 Day 08 起，我们引入面向对象编程（OOP），用 ChatMessage 类统一封装消息的数据与行为。
"""

from typing import Any


class ChatMessage:
    """
    大模型标准对话消息实体类。

    类属性:
        VALID_ROLES (tuple[str, ...]): 允许的消息角色白名单
    """

    VALID_ROLES: tuple[str, ...] = ("system", "user", "assistant", "tool")

    def __init__(self, role: str, content: str, name: str | None = None) -> None:
        """
        初始化一条对话消息，并在构造阶段完成角色合法性校验。

        参数:
            role (str): 消息角色，仅支持 "system" / "user" / "assistant" / "tool"
            content (str): 消息文本内容
            name (str | None): 可选的发送者名称或工具名称（默认为 None）

        异常:
            ValueError: 当 role 不在合法角色白名单中时抛出
            TypeError: 当 content 不是字符串或 name 不是字符串/None 时抛出
        """
        if not self.is_valid_role(role):
            allowed = ", ".join(self.VALID_ROLES)
            raise ValueError(f"无效的消息角色: {role!r}，合法角色仅限: {allowed}")

        if not isinstance(content, str):
            raise TypeError(f"消息内容 content 必须为 str，实际收到: {type(content).__name__}")

        if name is not None and not isinstance(name, str):
            raise TypeError(f"可选字段 name 必须为 str 或 None，实际收到: {type(name).__name__}")

        self.role: str = role
        self.content: str = content
        self.name: str | None = name

    def to_dict(self) -> dict[str, Any]:
        """
        实例方法：将 ChatMessage 对象序列化为 OpenAI / DeepSeek API 兼容字典。
        仅当 name 不为 None 时才写入 "name" 键，保持请求载荷干净。
        """
        payload: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.name is not None:
            payload["name"] = self.name
        return payload

    def estimate_tokens(self) -> int:
        """
        实例方法：估算当前消息文本的 Token 消耗量（启发式工程估算）。

        估算规则：
        - 空字符串返回 0
        - 中文汉字（\u4e00 - \u9fff）约按 1.5 Token/字 估算
        - 英文、数字、标点与空白符约按 0.3 Token/字符 估算
        - 非空文本至少返回 1 Token
        """
        if not self.content:
            return 0

        cjk_count = sum(1 for ch in self.content if "\u4e00" <= ch <= "\u9fff")
        other_count = len(self.content) - cjk_count
        estimated = round(cjk_count * 1.5 + other_count * 0.3)
        return max(1, estimated)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        """
        类方法（工厂方法）：从 API 请求/响应字典反序列化构造 ChatMessage 实例。

        参数:
            data (dict[str, Any]): 包含 "role" 与 "content" 键的字典，可选包含 "name"

        异常:
            ValueError: 当输入不是字典或缺少必要字段时抛出
        """
        if not isinstance(data, dict):
            raise ValueError("from_dict 参数必须为 dict 类型")

        if "role" not in data or "content" not in data:
            raise ValueError("消息字典必须包含 'role' 和 'content' 字段")

        return cls(
            role=data["role"],
            content=data["content"],
            name=data.get("name"),
        )

    @staticmethod
    def is_valid_role(role: str) -> bool:
        """
        静态方法（工具校验器）：判断给定字符串是否为合法的大模型对话角色。
        无需实例化对象即可通过 ChatMessage.is_valid_role(...) 直接调用。
        """
        return isinstance(role, str) and role in ChatMessage.VALID_ROLES

    def __repr__(self) -> str:
        name_part = f", name={self.name!r}" if self.name is not None else ""
        return f"ChatMessage(role={self.role!r}, content={self.content!r}{name_part})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChatMessage):
            return NotImplemented
        return (
            self.role == other.role
            and self.content == other.content
            and self.name == other.name
        )
