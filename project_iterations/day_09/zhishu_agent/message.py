"""Day 08 延续模块：智枢平台标准对话消息模型 (ChatMessage)"""
from datetime import datetime, timezone

VALID_ROLES = ("system", "user", "assistant", "tool")


class ChatMessage:
    """统一的大模型对话消息类，用于封装单条消息的角色、内容与时间戳。"""

    def __init__(self, role: str, content: str, timestamp: str | None = None) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"无效的消息角色: {role!r}，允许的角色为 {VALID_ROLES}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("消息内容 content 必须为非空字符串")

        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, str]:
        """转换为标准 OpenAI 风格的字典结构，便于 JSON 序列化。"""
        return {
            "role": self.role,
            "content": self.content,
        }

    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"

    def __repr__(self) -> str:
        return f"ChatMessage(role={self.role!r}, content={self.content!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChatMessage):
            return NotImplemented
        return self.role == other.role and self.content == other.content
