# Day 12 课后作业与参考答案

## 作业一：HTTP 状态码诊断与重试策略分类器
**题目**：在调用大模型 API 时，不同 HTTP 状态码意味着完全不同的处理策略（例如 `401` 绝对不能重试，而 `429` 和 `503` 通常可以退避重试）。请你编写一个函数 `classify_http_status(status_code: int) -> dict[str, object]`：
1. 返回字典包含两个字段：`category`（类别描述）和 `should_retry`（布尔值，是否建议重试）。
2. 覆盖以下状态码：
   - `200`：`category="请求成功"`，`should_retry=False`
   - `400`：`category="客户端请求参数错误"`，`should_retry=False`
   - `401`：`category="鉴权失败（API Key 无效或过期）"`，`should_retry=False`
   - `429`：`category="触发限流（RPM/TPM 超限）"`，`should_retry=True`
   - `500` / `502` / `503`：`category="服务端临时故障"`，`should_retry=True`
   - 其他状态码：`category="未知状态码"`，`should_retry=False`

### 参考答案：
```python
def classify_http_status(status_code: int) -> dict[str, object]:
    """根据 HTTP 状态码给出企业级诊断分类与重试建议。"""
    if status_code == 200:
        return {"category": "请求成功", "should_retry": False}
    if status_code == 400:
        return {"category": "客户端请求参数错误", "should_retry": False}
    if status_code == 401:
        return {"category": "鉴权失败（API Key 无效或过期）", "should_retry": False}
    if status_code == 429:
        return {"category": "触发限流（RPM/TPM 超限）", "should_retry": True}
    if status_code in (500, 502, 503):
        return {"category": "服务端临时故障", "should_retry": True}
    return {"category": f"未知状态码 ({status_code})", "should_retry": False}


for code in (200, 400, 401, 429, 503):
    print(code, "->", classify_http_status(code))
```

---

## 作业二：DeepSeek API 标准请求体（Payload）构造器
**题目**：请编写一个函数 `build_deepseek_payload(system_prompt: str, user_prompt: str, model: str = "deepseek-chat", temperature: float = 0.7, max_tokens: int = 2048, stream: bool = False) -> dict`：
1. 校验 `system_prompt` 和 `user_prompt` 均不能为空字符串（否则抛出 `ValueError`）。
2. 校验 `temperature` 必须在 `[0.0, 2.0]` 之间，`max_tokens` 必须为大于 0 的整数。
3. 返回符合 DeepSeek `/v1/chat/completions` 接口规范的字典，其中 `messages` 按顺序包含 `system` 和 `user` 两条消息字典。

### 参考答案：
```python
import json


def build_deepseek_payload(
    system_prompt: str,
    user_prompt: str,
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
) -> dict[str, object]:
    """构造符合 DeepSeek /v1/chat/completions 规范的 JSON 请求体。"""
    if not system_prompt.strip() or not user_prompt.strip():
        raise ValueError("system_prompt 和 user_prompt 均不能为空")
    if not (0.0 <= temperature <= 2.0):
        raise ValueError("temperature 必须在 0.0 到 2.0 之间")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens 必须为正整数")

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        "temperature": float(temperature),
        "max_tokens": max_tokens,
        "stream": stream,
    }


payload = build_deepseek_payload(
    system_prompt="你是智枢平台资深 Python 讲师。",
    user_prompt="请解释 HTTP Authorization Bearer 请求头的作用。",
    temperature=0.3,
)
print(json.dumps(payload, ensure_ascii=False, indent=2))
```

---

## 作业三：基于 `httpx.MockTransport` 的 `401` / `429` 容错调用器
**题目**：结合今天学到的 `LLMClient` 与 `httpx.MockTransport`，编写一个安全调用函数 `safe_ask(client: LLMClient, question: str) -> str`：
1. 调用 `client.chat([ChatMessage(role="user", content=question)])`。
2. 如果捕获 `AuthenticationError`（401），直接返回 `"错误：API Key 无效，请立即停止并检查环境变量配置。"`。
3. 如果捕获 `RateLimitError`（429），读取 `exc.retry_after`（若为 `None` 则默认 `1.0`），并返回 `f"限流告警：请求过于频繁，建议 {wait_sec} 秒后重试。"`。
4. 使用 `httpx.MockTransport` 分别模拟 `401` 和 `429` 响应进行离线验证。

### 参考答案：
```python
import httpx
from zhishu_agent.exceptions import AuthenticationError, RateLimitError
from zhishu_agent.llm_client import LLMClient
from zhishu_agent.message import ChatMessage


def safe_ask(client: LLMClient, question: str) -> str:
    """带 401 / 429 业务兜底的智枢安全调用封装。"""
    try:
        reply = client.chat([ChatMessage(role="user", content=question)])
        return reply.content
    except AuthenticationError:
        return "错误：API Key 无效，请立即停止并检查环境变量配置。"
    except RateLimitError as exc:
        wait_sec = exc.retry_after if exc.retry_after is not None else 1.0
        return f"限流告警：请求过于频繁，建议 {wait_sec} 秒后重试。"


# 离线模拟 401 与 429
t_401 = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": {"message": "Bad key"}}))
t_429 = httpx.MockTransport(
    lambda req: httpx.Response(429, headers={"Retry-After": "8"}, json={"error": {"message": "Slow down"}})
)

with LLMClient(api_key="sk-bad", transport=t_401) as c1:
    print(safe_ask(c1, "你好"))

with LLMClient(api_key="sk-limit", transport=t_429) as c2:
    print(safe_ask(c2, "你好"))
```
