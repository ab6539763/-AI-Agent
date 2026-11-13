# Day 16 课后作业与参考答案

## 作业一：`temperature` 与 `top_p` 参数对比实验
**题目**：在智枢平台的“参数调优实验室”中，产品经理希望对比「严谨财务问答」与「创意营销文案」两种场景下的采样参数配置。请你使用 `GenerationConfig` 与 `StreamingLLMClient` 完成以下实验：
1. 分别构造两套 `GenerationConfig`：
   - 严谨模式：`temperature=0.1, top_p=0.85, max_tokens=256, frequency_penalty=0.0`
   - 创意模式：`temperature=1.3, top_p=0.95, max_tokens=512, frequency_penalty=0.6`
2. 编写一个辅助函数 `validate_and_build(temp: float, top_p: float) -> GenerationConfig | str`，当传入非法参数（如 `temperature=2.5` 或 `top_p=0.0`）时捕获 `ValidationError` 并返回错误提示字符串。
3. 使用 `StreamingLLMClient`（离线 `MockTransport`）分别运行两种模式，打印请求携带的参数差异与流式聚合结果。

### 参考答案：
```python
from pydantic import ValidationError
from zhishu_agent.stream_client import GenerationConfig, StreamingLLMClient


def validate_and_build(temp: float, top_p: float) -> GenerationConfig | str:
    """尝试构造 GenerationConfig，拦截非法采样参数。"""
    try:
        return GenerationConfig(temperature=temp, top_p=top_p)
    except ValidationError as exc:
        return f"参数校验失败: {exc.errors()[0]['msg']}"


print("非法 temperature 测试:", validate_and_build(2.5, 0.9))
print("非法 top_p 测试:", validate_and_build(0.7, 0.0))

strict_cfg = GenerationConfig(temperature=0.1, top_p=0.85, max_tokens=256, frequency_penalty=0.0)
creative_cfg = GenerationConfig(temperature=1.3, top_p=0.95, max_tokens=512, frequency_penalty=0.6)

client = StreamingLLMClient()
prompt = [{"role": "user", "content": "请生成一条智枢智能体平台的产品介绍。"}]

for name, cfg in [("严谨模式", strict_cfg), ("创意模式", creative_cfg)]:
    reply = client.chat_aggregated(prompt, config=cfg)
    print(f"[{name}] params={cfg.to_api_params()}")
    print(f"  -> {reply}")
```

---

## 作业二：手写 SSE 数据帧解析器 `parse_sse_line`
**题目**：OpenAI 流式接口返回的原始 HTTP 响应体是由多行 `text/event-stream` 文本组成的。请你独立实现并测试一个 SSE 批量解析函数 `extract_sse_text(raw_lines: list[str]) -> str`：
1. 遇到空行、`: keep-alive` 注释行、非 `data:` 开头行时跳过。
2. 遇到 `data: [DONE]` 时**立即停止解析**，忽略其后可能出现的任何多余行。
3. 从 `data: {"choices":[{"delta":{"content":"..."}}]}` 中提取 `content` 并拼接成完整文本。

### 参考答案：
```python
import json


def parse_sse_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = choices[0].get("delta", {}).get("content")
    return content if isinstance(content, str) else None


def extract_sse_text(raw_lines: list[str]) -> str:
    chunks: list[str] = []
    for line in raw_lines:
        if line.strip() == "data: [DONE]":
            break
        piece = parse_sse_line(line)
        if piece is not None:
            chunks.append(piece)
    return "".join(chunks)


sample_stream = [
    ": keep-alive",
    "",
    'data: {"choices":[{"delta":{"role":"assistant"}}]}',
    'data: {"choices":[{"delta":{"content":"智枢"}}]}',
    'data: {"choices":[{"delta":{"content":"SSE"}}]}',
    'data: {"choices":[{"delta":{"content":"解析成功！"}}]}',
    "data: [DONE]",
    'data: {"choices":[{"delta":{"content":"不应被读取的脏数据"}}]}',
]
print("聚合结果:", extract_sse_text(sample_stream))
```

---

## 作业三：`system` / `user` / `assistant` 三角色多轮编排实战
**题目**：在大模型对话 API 中，`messages` 列表通过三种核心角色控制上下文：`system`（人设与规则）、`user`（用户输入）、`assistant`（历史回复/Few-Shot 示例）。请你编写一段代码：
1. 构造包含 `system`（设定为“只输出 JSON 的财务审核员”）、一组 `user` + `assistant`（Few-Shot 示例对话）以及一条最新 `user` 提问的 `messages` 列表。
2. 使用自定义的 `httpx.MockTransport` 捕获请求体，校验 `messages` 中三条角色依次齐全且 `stream=True`。
3. 通过 `StreamingLLMClient.stream_chat()` 消费流式响应并打印结果。

### 参考答案：
```python
import json
import httpx
from zhishu_agent.stream_client import GenerationConfig, StreamingLLMClient

captured_roles: list[str] = []


def role_check_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content.decode("utf-8"))
    captured_roles.extend(msg["role"] for msg in body["messages"])
    assert body["stream"] is True
    sse_payload = (
        'data: {"choices":[{"delta":{"content":"{\\"approved\\": true, "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"\\"limit\\": 600}"}}]}\n\n'
        "data: [DONE]\n\n"
    ).encode("utf-8")
    return httpx.Response(
        status_code=200,
        headers={"Content-Type": "text/event-stream"},
        content=sse_payload,
    )


messages = [
    {"role": "system", "content": "你是只输出 JSON 的财务审核员。"},
    {"role": "user", "content": "上海出差住宿 500 元能否报销？"},
    {"role": "assistant", "content": '{"approved": true, "limit": 600}'},
    {"role": "user", "content": "北京出差住宿 580 元能否报销？"},
]

client = StreamingLLMClient(transport=httpx.MockTransport(role_check_handler))
cfg = GenerationConfig(temperature=0.0, stream=True)
result = "".join(client.stream_chat(messages, config=cfg))

print("请求携带的角色序列:", captured_roles)
print("流式返回 JSON:", result)
```
