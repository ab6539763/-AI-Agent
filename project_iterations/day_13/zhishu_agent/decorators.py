"""Day 13 装饰器模块：提供自动重试 (@retry_on_error) 与耗时监控 (@log_latency) 装饰器。"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_error(
    max_retries: int = 3,
    delay: float = 0.01,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """异常自动重试装饰器。

    当被装饰函数抛出指定异常时，自动等待 `delay` 秒后重试，最多尝试 `max_retries` 次。
    若全部尝试均失败，则重新抛出最后一次捕获的异常。

    Args:
        max_retries: 最大尝试次数（必须 >= 1，默认 3）。
        delay: 每次重试前的等待秒数（必须 >= 0，默认 0.01）。
        exceptions: 需要捕获并重试的异常类型元组，默认 `(Exception,)`。
    """
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 1:
        raise ValueError(f"max_retries 必须是 >= 1 的整数，当前为 {max_retries!r}")
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or delay < 0:
        raise ValueError(f"delay 必须是 >= 0 的数值，当前为 {delay!r}")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries and delay > 0:
                        time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


def log_latency(func: F) -> F:
    """函数执行耗时日志装饰器（单位：毫秒 ms）。"""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"[Latency] {func.__name__} 耗时 {elapsed_ms:.2f} ms")

    return wrapper  # type: ignore[return-value]
