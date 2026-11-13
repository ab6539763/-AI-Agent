"""Day 12 模块：智枢平台统一异常体系 (HTTP 与大模型 API 调用异常)"""


class ZhiShuError(Exception):
    """智枢平台所有自定义异常的基类。"""


class LLMAPIError(ZhiShuError):
    """大模型 HTTP API 调用异常基类。"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        detail = f"[HTTP {status_code}] {message}" if status_code is not None else message
        super().__init__(detail)


class AuthenticationError(LLMAPIError):
    """HTTP 401：API Key 无效、过期或未提供。"""


class RateLimitError(LLMAPIError):
    """HTTP 429：触发大模型厂商限流（RPM / TPM 超限）或配额耗尽。"""

    def __init__(
        self,
        message: str,
        status_code: int | None = 429,
        response_body: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message=message, status_code=status_code, response_body=response_body)


class ServerError(LLMAPIError):
    """HTTP 5xx：大模型服务端内部错误或网关不可用（如 500、502、503）。"""


class InvalidResponseError(LLMAPIError):
    """响应体不是合法 JSON 或缺少标准 OpenAI/DeepSeek 字段（如 choices）。"""


class NetworkTimeoutError(LLMAPIError):
    """网络请求超时或底层连接异常。"""
