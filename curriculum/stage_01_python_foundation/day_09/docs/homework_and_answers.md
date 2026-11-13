# Day 09 课后作业与参考答案

## 作业一：扩展适配器子类 `DeepSeekModel`（继承与多态）
**题目**：星辰数科决定接入国产高性价比大模型 DeepSeek。请你继承 `BaseLLMModel`，编写一个 `DeepSeekModel` 子类：
1. 在 `__init__` 中接收 `model_name: str = "deepseek-chat"`、`temperature: float = 0.7` 以及专属参数 `reasoning_mode: bool = False`（是否开启深度思考模式），并通过 `super().__init__` 复用父类初始化。
2. 重写 `generate(self, messages: list[ChatMessage]) -> ChatMessage` 方法，调用 `self._validate_messages(messages)` 后返回带有 `[DeepSeek:{self.model_name}|推理={mode_label}]` 前缀的 `ChatMessage(role="assistant", ...)`。

### 参考答案：
```python
from zhishu_agent.message import ChatMessage
from zhishu_agent.models import BaseLLMModel


class DeepSeekModel(BaseLLMModel):
    """DeepSeek 大模型适配器，支持开启深度思考（R1）模式。"""

    def __init__(
        self,
        model_name: str = "deepseek-chat",
        temperature: float = 0.7,
        reasoning_mode: bool = False,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)
        self.reasoning_mode = reasoning_mode

    def generate(self, messages: list[ChatMessage]) -> ChatMessage:
        last_msg = self._validate_messages(messages)
        mode_label = "深度思考" if self.reasoning_mode else "标准对话"
        reply = (
            f"[DeepSeek:{self.model_name}|temp={self.temperature}|模式={mode_label}] "
            f"已完成推理：{last_msg.content}"
        )
        return ChatMessage(role="assistant", content=reply)


# 验证多态调用
ds = DeepSeekModel(model_name="deepseek-reasoner", temperature=0.6, reasoning_mode=True)
print(ds("请分析一下企业级 Agent 的架构演进。"))
```

---

## 作业二：`@property` 实战——为模型增加 `max_tokens` 属性校验
**题目**：大模型调用中除了 `temperature`，另一个极易出错的参数是 `max_tokens`（单次最大输出 Token 数）。请为一个模型配置类添加 `@property def max_tokens` 及其 `@max_tokens.setter`：
1. 必须为整数 `int`（注意排除 `bool`，否则 `True` 会被误认为 `1`），若类型不对抛出 `TypeError`。
2. 取值范围必须在 `[1, 128000]` 闭区间内，越界时抛出 `ValueError`。

### 参考答案：
```python
class ModelConfig:
    """大模型推理参数配置类。"""

    def __init__(self, max_tokens: int = 2048) -> None:
        self.max_tokens = max_tokens

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        # Python 中 bool 是 int 的子类，必须先排除 bool
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"max_tokens 必须是整数 int，当前为 {type(value).__name__}")
        if not (1 <= value <= 128000):
            raise ValueError(f"max_tokens 必须在 1 到 128000 之间，当前值为 {value}")
        self._max_tokens = value


cfg = ModelConfig(4096)
print("当前 max_tokens:", cfg.max_tokens)
# cfg.max_tokens = 0       # 将触发 ValueError
# cfg.max_tokens = True    # 将触发 TypeError
```

---

## 作业三：魔术方法实战——为 `Conversation` 会话类实现 `__len__`
**题目**：在智枢平台中，我们经常需要统计一次多轮对话里已经累积了多少条消息（用于判断是否触发上下文裁剪）。请编写一个 `Conversation` 类：
1. 内部用列表 `self._messages: list[ChatMessage]` 存储消息。
2. 提供 `add(msg: ChatMessage) -> None` 方法添加消息。
3. 实现 `__len__(self) -> int` 魔术方法，使得外部可以直接使用 `len(conv)` 获取消息条数；同时实现 `__str__` 打印会话摘要。

### 参考答案：
```python
from zhishu_agent.message import ChatMessage


class Conversation:
    """多轮对话会话管理器。"""

    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []

    def add(self, msg: ChatMessage) -> None:
        if not isinstance(msg, ChatMessage):
            raise TypeError("只能向会话中添加 ChatMessage 对象")
        self._messages.append(msg)

    def __len__(self) -> int:
        """支持 len(conv) 直接返回当前对话消息总条数。"""
        return len(self._messages)

    def __str__(self) -> str:
        return f"Conversation(messages={len(self)})"


conv = Conversation()
conv.add(ChatMessage("system", "你是智枢平台架构师。"))
conv.add(ChatMessage("user", "什么是魔术方法？"))
print(f"当前对话轮数: {len(conv)}")  # 输出: 2
print(conv)                           # 输出: Conversation(messages=2)
```
