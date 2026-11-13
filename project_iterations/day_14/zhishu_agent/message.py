"""Day 14 核心模块：智枢平台标准对话消息模型 (ChatMessage)"""
from datetime import datetime, timezone
from typing import Any

VALID_ROLES = ("system", "user", "assistant", "tool")


class ChatMessage:
    """统一的大模型对话消息类，支持 OpenAI 协议转换与 JSON 持久化序列化。"""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str | None = None,
    ) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"无效的消息角色: {role!r}，允许的角色为 {VALID_ROLES}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("消息内容 content 必须为非空字符串")

        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, str]:
        """转换为标准 OpenAI 风格的字典结构，用于 API 请求载荷。"""
        return {
            "role": self.role,
            "content": self.content,
        }

    def to_full_dict(self) -> dict[str, str]:
        """转换为包含时间戳的完整字典，用于 /save 会话持久化。"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        """从字典反序列化构造 ChatMessage（用于 /load 会话恢复）。"""
        if not isinstance(data, dict):
            raise ValueError("消息数据必须为字典对象")
        role = data.get("role")
        content = data.get("content")
        timestamp = data.get("timestamp")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ValueError("消息字典必须包含字符串类型的 role 与 content 字段")
        return cls(role=role, content=content, timestamp=timestamp)

    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"

    def __repr__(self) -> str:
        return f"ChatMessage(role={self.role!r}, content={self.content!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChatMessage):
            return NotImplemented
        return self.role == other.role and self.content == other.content
