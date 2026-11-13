"""Day 13 流式输出与异步并发模块：提供生成器 stream_tokens 与异步批量调用 async_batch_ask。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator


def stream_tokens(text: str, chunk_size: int = 1) -> Iterator[str]:
    """使用 yield 生成器按切片流式吐出文本 Token（惰性求值，节省内存）。

    Args:
        text: 待流式输出的完整文本。
        chunk_size: 每次 yield 的字符切片大小，默认为 1。

    Yields:
        按顺序切分的文本片段。
    """
    if not isinstance(text, str):
        raise TypeError(f"text 必须是 str 类型，当前为 {type(text).__name__}")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError(f"chunk_size 必须是 >= 1 的整数，当前为 {chunk_size!r}")

    for idx in range(0, len(text), chunk_size):
        yield text[idx : idx + chunk_size]


async def _async_single_ask(
    prompt: str,
    model_name: str = "deepseek-chat",
    delay: float = 0.01,
) -> str:
    """模拟单次异步大模型请求（非阻塞 I/O 等待）。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt 必须为非空字符串")
    if delay > 0:
        await asyncio.sleep(delay)
    return f"[{model_name}] 已异步处理: {prompt.strip()}"


async def async_batch_ask(
    prompts: list[str],
    model_name: str = "deepseek-chat",
    delay: float = 0.01,
) -> list[str]:
    """使用 asyncio.gather 并发执行多条 Prompt 请求，总耗时约等于单次最慢请求耗时。

    Args:
        prompts: 待并发处理的提示词列表。
        model_name: 目标模型名称。
        delay: 模拟网络 I/O 延迟（秒）。

    Returns:
        与 prompts 顺序一一对应的模型响应列表。
    """
    if not isinstance(prompts, list):
        raise TypeError(f"prompts 必须是 list[str]，当前为 {type(prompts).__name__}")
    if not prompts:
        return []

    tasks = [_async_single_ask(prompt, model_name=model_name, delay=delay) for prompt in prompts]
    results = await asyncio.gather(*tasks)
    return list(results)
