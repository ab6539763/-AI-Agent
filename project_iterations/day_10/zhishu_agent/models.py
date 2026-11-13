"""Day 10 重构模块：基于面向对象继承与自定义异常的统一大模型适配器"""
from zhishu_agent.exceptions import APIResponseError, ModelConfigError
from zhishu_agent.message import ChatMessage


class BaseLLMModel:
    """大模型适配器基类：定义统一接口、参数校验（抛出 ModelConfigError）与魔术方法。"""

    def __init__(self, model_name: str, temperature: float = 0.7) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ModelConfigError("model_name 必须为非空字符串")
        self.model_name = model_name.strip()
        # 通过 @property setter 赋值，初始化时即触发范围校验
        self.temperature = temperature

    @property
    def temperature(self) -> float:
        """获取当前采样温度。"""
        return self._temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        """设置采样温度，强制校验必须在 [0.0, 2.0] 闭区间内，非法时抛出 ModelConfigError。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ModelConfigError(
                f"temperature 必须是数值类型 (int/float)，当前为 {type(value).__name__}"
            )
        temp = float(value)
        if not (0.0 <= temp <= 2.0):
            raise ModelConfigError(f"temperature 必须在 0.0 到 2.0 之间，当前值为 {temp}")
        self._temperature = temp

    def _validate_messages(self, messages: list[ChatMessage]) -> ChatMessage:
        """校验消息列表非空且元素均为 ChatMessage，返回最后一条消息。"""
        if not isinstance(messages, list) or len(messages) == 0:
            raise ModelConfigError("messages 必须是非空的 ChatMessage 列表")
        for msg in messages:
            if not isinstance(msg, ChatMessage):
                raise ModelConfigError(
                    f"messages 中的元素必须是 ChatMessage，当前为 {type(msg).__name__}"
                )
        return messages[-1]

    def generate(self, messages: list[ChatMessage]) -> ChatMessage:
        """核心推理接口：接收消息列表并返回助手回复（由子类多态实现）。"""
        self._validate_messages(messages)
        raise NotImplementedError(f"{self.__class__.__name__} 必须重写 generate() 方法")

    def __call__(self, prompt_or_messages: str | list[ChatMessage]) -> ChatMessage:
        """魔术方法：允许像调用函数一样直接调用模型实例，如 model('你好')。"""
        if isinstance(prompt_or_messages, str):
            messages = [ChatMessage(role="user", content=prompt_or_messages)]
        else:
            messages = prompt_or_messages
        return self.generate(messages)

    def __str__(self) -> str:
        """面向用户/日志的友好字符串表示。"""
        return f"[{self.__class__.__name__}] {self.model_name} (temperature={self.temperature})"

    def __repr__(self) -> str:
        """面向开发者的精确调试表示。"""
        return f"{self.__class__.__name__}(model_name={self.model_name!r}, temperature={self.temperature!r})"


class OpenAIModel(BaseLLMModel):
    """OpenAI 模型适配器（离线模拟推理实现，支持模拟 API 异常以验证容错链路）。"""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        api_base: str = "https://api.openai.com/v1",
        simulate_error: bool = False,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)
        self.api_base = api_base
        self.simulate_error = simulate_error

    def generate(self, messages: list[ChatMessage]) -> ChatMessage:
        """多态实现 OpenAI 风格的对话生成。"""
        last_msg = self._validate_messages(messages)
        if self.simulate_error or "[SIMULATE_ERROR]" in last_msg.content:
            raise APIResponseError(
                f"OpenAI 接口 ({self.api_base}) 模拟限流或上游服务不可用",
                status_code=503,
            )
        reply = (
            f"[OpenAI:{self.model_name}|temp={self.temperature}] "
            f"已收到你的消息({len(messages)}轮上下文)：{last_msg.content}"
        )
        return ChatMessage(role="assistant", content=reply)


class QwenModel(BaseLLMModel):
    """通义千问 (Qwen) 模型适配器（离线模拟推理实现）。"""

    def __init__(
        self,
        model_name: str = "qwen-plus",
        temperature: float = 0.7,
        enable_search: bool = False,
        simulate_error: bool = False,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)
        self.enable_search = enable_search
        self.simulate_error = simulate_error

    def generate(self, messages: list[ChatMessage]) -> ChatMessage:
        """多态实现通义千问风格的对话生成。"""
        last_msg = self._validate_messages(messages)
        if self.simulate_error or "[SIMULATE_ERROR]" in last_msg.content:
            raise APIResponseError(
                "通义千问 DashScope 接口响应超时",
                status_code=504,
            )
        search_tag = "联网增强" if self.enable_search else "纯模型推理"
        reply = (
            f"[Qwen:{self.model_name}|temp={self.temperature}|{search_tag}] "
            f"通义千问已处理请求：{last_msg.content}"
        )
        return ChatMessage(role="assistant", content=reply)
