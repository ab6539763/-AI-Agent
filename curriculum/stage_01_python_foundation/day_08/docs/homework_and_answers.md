# Day 08 课后作业与参考答案

## 作业一：对话容器类 `Conversation` 设计与实现（OOP 组合模式）
**题目**：在实际的智枢平台中，单条 `ChatMessage` 需要被放进一个多轮对话容器中进行统一管理。请基于今天的 `ChatMessage` 类，编写一个 `Conversation` 类，要求：
1. `__init__(self, system_prompt: str | None = None)`：内部维护一个 `self.messages: list[ChatMessage] = []`；如果传入了 `system_prompt`，自动追加一条 `role="system"` 的 `ChatMessage`；
2. 实例方法 `add_message(self, message: ChatMessage) -> None`：向对话中添加一条消息（需校验类型为 `ChatMessage`，否则抛出 `TypeError`）；
3. 实例方法 `total_tokens(self) -> int`：汇总当前所有消息的 `estimate_tokens()` 之和；
4. 实例方法 `to_dict_list(self) -> list[dict]`：返回所有消息调用 `to_dict()` 后的字典列表，方便直接传给大模型 API 或 `save_session_json`。

### 参考答案：
```python
from typing import Any


class Conversation:
    """多轮对话容器类，管理一组有序的 ChatMessage 实例。"""

    def __init__(self, system_prompt: str | None = None) -> None:
        self.messages: list[ChatMessage] = []
        if system_prompt is not None:
            self.messages.append(ChatMessage(role="system", content=system_prompt))

    def add_message(self, message: ChatMessage) -> None:
        """向对话中追加一条 ChatMessage 实例。"""
        if not isinstance(message, ChatMessage):
            raise TypeError(f"必须传入 ChatMessage 实例，实际收到: {type(message).__name__}")
        self.messages.append(message)

    def total_tokens(self) -> int:
        """统计当前会话所有消息的预估 Token 总量。"""
        return sum(msg.estimate_tokens() for msg in self.messages)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """导出为大模型 API 兼容的消息字典列表。"""
        return [msg.to_dict() for msg in self.messages]


# 验证运行
conv = Conversation(system_prompt="你是星辰数科企业级智能体助手。")
conv.add_message(ChatMessage(role="user", content="请介绍面向对象编程的好处。"))
conv.add_message(ChatMessage(role="assistant", content="OOP 可以将消息数据与校验行为封装在一起。"))
print("总消息数:", len(conv.messages))
print("预估总 Token:", conv.total_tokens())
print("API 载荷:", conv.to_dict_list())
```

---

## 作业二：`@classmethod` 快捷工厂方法扩展（Classmethod Factory）
**题目**：在日常编码中，每次都要写 `ChatMessage(role="user", content="...")` 略显繁琐。请为 `ChatMessage` 扩展三个 `@classmethod` 快捷工厂方法：
- `ChatMessage.system(cls, content: str) -> "ChatMessage"`
- `ChatMessage.user(cls, content: str, name: str | None = None) -> "ChatMessage"`
- `ChatMessage.assistant(cls, content: str) -> "ChatMessage"`

要求通过 `cls(...)` 构造并返回实例，同时编写一段测试代码验证 `ChatMessage.user("你好", name="chenmo").to_dict()` 的输出。

### 参考答案：
```python
class ExtendedChatMessage(ChatMessage):
    """演示使用 @classmethod 扩展快捷工厂方法。"""

    @classmethod
    def system(cls, content: str) -> "ExtendedChatMessage":
        """快捷创建 system 角色消息。"""
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str, name: str | None = None) -> "ExtendedChatMessage":
        """快捷创建 user 角色消息。"""
        return cls(role="user", content=content, name=name)

    @classmethod
    def assistant(cls, content: str) -> "ExtendedChatMessage":
        """快捷创建 assistant 角色消息。"""
        return cls(role="assistant", content=content)


# 验证运行
sys_msg = ExtendedChatMessage.system("你是严谨的技术顾问。")
usr_msg = ExtendedChatMessage.user("你好", name="chenmo")
ast_msg = ExtendedChatMessage.assistant("你好！请问有什么可以帮你？")

assert isinstance(usr_msg, ExtendedChatMessage)
print(sys_msg.to_dict())
print(usr_msg.to_dict())
print(ast_msg.to_dict())
```

---

## 作业三：`@staticmethod` 消息内容与角色合规校验器（Staticmethod Validator）
**题目**：在金融、政务等企业级场景下，用户发送给大模型的消息不能是纯空白字符，也不能超过单次输入长度上限（如 4000 字符）。请编写一个包含 `@staticmethod` 的校验工具类 `MessageValidator`：
1. `@staticmethod def is_non_empty_content(content: str) -> bool`：判断 `content` 是否为 `str` 且 `strip()` 后非空；
2. `@staticmethod def is_within_length(content: str, max_length: int = 4000) -> bool`：判断 `content` 长度是否不超过 `max_length`；
3. `@staticmethod def validate_payload(data: dict) -> bool`：综合使用 `ChatMessage.is_valid_role`、`is_non_empty_content` 与 `is_within_length` 校验一条原始字典消息是否同时满足角色合法、内容非空且长度不超限。

### 参考答案：
```python
class MessageValidator:
    """企业级消息合规校验工具类（纯静态方法集合）。"""

    @staticmethod
    def is_non_empty_content(content: str) -> bool:
        """校验消息内容是否为非空字符串（去除首尾空白后长度 > 0）。"""
        return isinstance(content, str) and len(content.strip()) > 0

    @staticmethod
    def is_within_length(content: str, max_length: int = 4000) -> bool:
        """校验消息内容长度是否在允许上限之内。"""
        return isinstance(content, str) and len(content) <= max_length

    @staticmethod
    def validate_payload(data: dict, max_length: int = 4000) -> bool:
        """综合校验原始消息字典的角色、非空性与长度限制。"""
        if not isinstance(data, dict):
            return False
        role = data.get("role")
        content = data.get("content")
        return (
            ChatMessage.is_valid_role(role)
            and MessageValidator.is_non_empty_content(content)
            and MessageValidator.is_within_length(content, max_length=max_length)
        )


# 验证运行
assert MessageValidator.validate_payload({"role": "user", "content": "请总结今日周报"}) is True
assert MessageValidator.validate_payload({"role": "user", "content": "   "}) is False
assert MessageValidator.validate_payload({"role": "hacker", "content": "hi"}) is False
assert MessageValidator.validate_payload({"role": "user", "content": "a" * 10}, max_length=5) is False
print("所有 @staticmethod 校验用例全部通过！")
```
