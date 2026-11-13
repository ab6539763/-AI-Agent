# Day 13 课后作业与参考答案

## 作业一：装饰器实战——为 Agent 工具函数编写 `@retry_on_error`
**题目**：在智枢平台调用外部天气/搜索 API 时，网络经常出现偶发超时。请你手写一个带参数的装饰器 `retry_on_error(max_retries: int = 3, delay: float = 0.01)`：
1. 必须使用 `@functools.wraps(func)` 保留原函数的 `__name__` 与 `__doc__`。
2. 当被装饰函数抛出异常时，等待 `delay` 秒后重试，最多尝试 `max_retries` 次；若全部失败，抛出最后一次的异常。
3. 编写一个前 2 次抛出 `ConnectionError`、第 3 次返回 `"成功响应"` 的模拟函数验证你的装饰器。

### 参考答案：
```python
import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_error(max_retries: int = 3, delay: float = 0.01) -> Callable[[F], F]:
    """异常自动重试装饰器。"""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries and delay > 0:
                        time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


attempts = 0


@retry_on_error(max_retries=3, delay=0.01)
def call_search_tool(query: str) -> str:
    """模拟不稳定的外部搜索工具。"""
    global attempts
    attempts += 1
    if attempts < 3:
        raise ConnectionError(f"第 {attempts} 次请求超时")
    return f"搜索结果: {query}"


print(call_search_tool("智枢平台"))
print("保留的函数名:", call_search_tool.__name__)
```

---

## 作业二：生成器实战——基于 `yield` 的文档分块器 `chunk_document`
**题目**：在即将进入的 RAG（检索增强生成）阶段，我们需要把一篇长文档按固定字符长度切分为多个 Chunk，但直接返回大列表会占用大量内存。请你使用 `yield` 编写一个生成器函数 `chunk_document(text: str, chunk_size: int = 5) -> Iterator[str]`：
1. 每次仅 `yield` 长度为 `chunk_size` 的文本片段（最后一块可不足 `chunk_size`）。
2. 当 `chunk_size <= 0` 时抛出 `ValueError`。
3. 使用 `for chunk in chunk_document(...)` 遍历输出，并用 `inspect.isgeneratorfunction` 验证它确实是生成器函数。

### 参考答案：
```python
import inspect
from collections.abc import Iterator


def chunk_document(text: str, chunk_size: int = 5) -> Iterator[str]:
    """使用 yield 惰性切分长文档，避免一次性加载全量切片到内存。"""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须大于 0，当前为 {chunk_size}")
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


print("是否为生成器函数:", inspect.isgeneratorfunction(chunk_document))
doc = "智枢企业级智能体平台RAG知识库切分测试"
for idx, chunk in enumerate(chunk_document(doc, chunk_size=6), start=1):
    print(f"Chunk #{idx}: {chunk}")
```

---

## 作业三：`asyncio.gather` 实战——并发调用多个知识库检索源
**题目**：用户提问时，Agent 需要同时查询「产品文档库」「财务制度库」「技术架构库」3 个异步数据源。如果串行 `await` 每个需要 0.1 秒的查询，总耗时为 0.3 秒；请你使用 `asyncio.gather` 编写 `async def query_all_sources(question: str) -> list[str]`：
1. 定义 `async def query_source(source_name: str, question: str, delay: float = 0.05) -> str`，内部使用 `await asyncio.sleep(delay)` 模拟网络 I/O。
2. 在 `query_all_sources` 中用 `asyncio.gather` 并发执行 3 个数据源查询并返回结果列表。
3. 使用 `asyncio.run(...)` 运行并打印总耗时，验证并发总耗时远小于串行耗时之和。

### 参考答案：
```python
import asyncio
import time


async def query_source(source_name: str, question: str, delay: float = 0.05) -> str:
    """模拟单个知识库的异步检索。"""
    await asyncio.sleep(delay)
    return f"[{source_name}] 命中与 '{question}' 相关的文档"


async def query_all_sources(question: str) -> list[str]:
    """使用 asyncio.gather 并发检索多个知识库。"""
    sources = ["产品文档库", "财务制度库", "技术架构库"]
    tasks = [query_source(src, question, delay=0.05) for src in sources]
    results = await asyncio.gather(*tasks)
    return list(results)


start = time.perf_counter()
hits = asyncio.run(query_all_sources("差旅报销标准是什么？"))
elapsed_ms = (time.perf_counter() - start) * 1000

for hit in hits:
    print(hit)
print(f"并发检索总耗时: {elapsed_ms:.2f} ms (串行需 ~150 ms)")
```
