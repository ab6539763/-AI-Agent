"""Day 10 新增模块：智枢平台统一自定义异常体系 (zhishu_agent.exceptions)"""


class ZhiShuError(Exception):
    """智枢平台所有业务与运行期异常的统一基类。"""

    def __init__(self, message: str, error_code: str = "ZHISHU_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")


class InvalidRoleError(ZhiShuError):
    """当对话消息角色不在允许白名单内时抛出。"""

    def __init__(self, role: object, valid_roles: tuple[str, ...]) -> None:
        self.role = role
        self.valid_roles = valid_roles
        msg = f"无效的消息角色: {role!r}，允许的角色为 {valid_roles}"
        super().__init__(message=msg, error_code="INVALID_ROLE")


class ModelConfigError(ZhiShuError):
    """当大模型名称、温度参数或输入消息结构配置非法时抛出。"""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, error_code="MODEL_CONFIG_ERROR")


class APIResponseError(ZhiShuError):
    """当调用上游大模型 API 发生超时、限流或响应异常时抛出。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        detail = f"{message} (status_code={status_code})" if status_code is not None else message
        super().__init__(message=detail, error_code="API_RESPONSE_ERROR")
