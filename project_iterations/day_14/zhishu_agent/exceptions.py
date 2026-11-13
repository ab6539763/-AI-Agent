"""Day 14 核心模块：智枢平台统一异常体系 (ZhiShuError Hierarchy)"""


class ZhiShuError(Exception):
    """智枢平台基础异常类：所有自定义业务与通信异常的基类。"""

    def __init__(self, message: str, code: str = "ZHISHU_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(ZhiShuError):
    """配置异常：环境变量缺失、参数越界或初始化配置无效。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIG_ERROR")


class LLMAPIError(ZhiShuError):
    """大模型 API 调用异常：封装 HTTP 状态码与是否可重试标记。"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
        code: str = "LLM_API_ERROR",
    ) -> None:
        super().__init__(message, code=code)
        self.status_code = status_code
        self.retryable = retryable


class LLMRateLimitError(LLMAPIError):
    """大模型限流异常（HTTP 429），默认支持指数退避重试。"""

    def __init__(self, message: str = "触发大模型 API 限流 (429)") -> None:
        super().__init__(
            message=message,
            status_code=429,
            retryable=True,
            code="LLM_RATE_LIMIT",
        )


class LLMTimeoutError(LLMAPIError):
    """大模型请求超时异常，默认支持指数退避重试。"""

    def __init__(self, message: str = "大模型 API 请求超时") -> None:
        super().__init__(
            message=message,
            status_code=None,
            retryable=True,
            code="LLM_TIMEOUT",
        )


class CommandError(ZhiShuError):
    """CLI 斜杠命令执行异常：如指令未知、参数缺失或文件读写失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="COMMAND_ERROR")
