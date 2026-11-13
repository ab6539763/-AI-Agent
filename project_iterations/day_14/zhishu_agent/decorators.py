"""Day 14 核心模块：工程化装饰器（指数退避重试与耗时日志）"""
import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from zhishu_agent.exceptions import LLMAPIError

P = ParamSpec("P")
R = TypeVar("R")


def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 0.05,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (LLMAPIError,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """指数退避重试装饰器。

    - 若捕获到的异常为 LLMAPIError 且其 retryable=False（如 401/400），立即失败不重试。
    - 否则按 base_delay * (backoff_factor ** attempt) 退避重试，最多重试 max_retries 次。
    """
    if max_retries < 0:
        raise ValueError("max_retries 不能为负数")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    if isinstance(exc, LLMAPIError) and not exc.retryable:
                        raise
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor**attempt)
                        if delay > 0:
                            time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
