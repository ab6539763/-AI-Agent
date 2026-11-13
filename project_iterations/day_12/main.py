"""Day 12 平台启动入口：使用 httpx.MockTransport 离线演示 OpenAI/DeepSeek 兼容 HTTP 客户端"""
import json

import httpx

from zhishu_agent.exceptions import AuthenticationError, RateLimitError, ServerError
from zhishu_agent.llm_client import LLMClient
from zhishu_agent.message import ChatMessage


def mock_llm_handler(request: httpx.Request) -> httpx.Response:
    """模拟大模型网关：校验路径、Bearer Token 与请求体，并返回标准 JSON。"""
    if request.url.path != "/v1/chat/completions":
        return httpx.Response(404, json={"error": {"message": "Not Found"}})

    auth_header = request.headers.get("Authorization", "")
    if auth_header == "Bearer sk-invalid":
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
    if auth_header == "Bearer sk-ratelimit":
        return httpx.Response(
            429,
            headers={"Retry-After": "5"},
            json={"error": {"message": "Rate limit exceeded"}},
        )
    if auth_header == "Bearer sk-server-err":
        return httpx.Response(500, json={"error": {"message": "Internal model engine error"}})

    payload = json.loads(request.content.decode("utf-8"))
    user_content = payload["messages"][-1]["content"]
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-day12-demo",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[离线网关回复 | {payload['model']}] 已收到你的问题：{user_content}",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 18, "completion_tokens": 24, "total_tokens": 42},
        },
    )


def run_demo() -> None:
    """运行 Day 12 核心功能演示（100% 离线确定性运行）。"""
    print("=== 智枢平台 v0.1.0-day12：HTTP 请求与大模型 API 客户端演示 ===\n")
    transport = httpx.MockTransport(mock_llm_handler)

    # 1. 正常调用演示
    with LLMClient(
        api_key="sk-zhishu-demo-2026",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        transport=transport,
    ) as client:
        messages = [
            ChatMessage(role="system", content="你是星辰数科智枢平台架构师。"),
            ChatMessage(role="user", content="请简述 HTTP POST 如何调用大模型接口？"),
        ]
        reply = client.chat(messages, temperature=0.3, max_tokens=512)
        print(f"[正常调用] {reply}\n")

    # 2. 状态码异常拦截演示 (401 / 429 / 500)
    scenarios = [
        ("sk-invalid", AuthenticationError, "401 鉴权失败"),
        ("sk-ratelimit", RateLimitError, "429 触发限流"),
        ("sk-server-err", ServerError, "500 服务端错误"),
    ]
    for key, expected_exc, label in scenarios:
        with LLMClient(api_key=key, transport=transport) as err_client:
            try:
                err_client.chat([ChatMessage(role="user", content="ping")])
            except expected_exc as exc:
                print(f"[{label}] 成功捕获 {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    run_demo()
