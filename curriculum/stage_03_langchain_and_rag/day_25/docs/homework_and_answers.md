# Day 25 课后作业与参考答案

## 作业一：`ChatPromptTemplate` 多角色模板编排与变量校验
**题目**：在企业智能体开发中，直接用 Python f-string 拼接多轮提示词既容易出错，又无法复用角色结构。请使用 Day 25 实现的 `ChatPromptTemplate.from_messages(...)` 完成以下需求：
1. 构建一个包含 `system` 角色（变量 `{department}`、`{tone}`）和 `human` 角色（变量 `{question}`）的对话模板。
2. 打印该模板自动识别出的 `input_variables` 列表。
3. 使用 `.format_messages(...)` 注入具体参数并打印每条消息的 `.type` 与 `.content`；随后故意漏传 `question` 参数，捕获并打印 `KeyError` 异常信息。

### 参考答案：
```python
from zhishu_agent import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是星辰数科 {department} 的智能助手，回答风格请保持 {tone}。"),
        ("human", "请帮我解答：{question}"),
    ]
)

print("自动提取的模板变量:", prompt.input_variables)

messages = prompt.format_messages(
    department="财务共享中心",
    tone="严谨专业",
    question="差旅报销发票超过 30 天还能提交吗？",
)
for msg in messages:
    print(f"[{msg.type}] {msg.content}")

try:
    prompt.format_messages(department="财务共享中心", tone="严谨专业")
except KeyError as exc:
    print("捕获到缺失变量异常:", exc)
```
**原理解析**：`ChatPromptTemplate` 在初始化阶段通过 `string.Formatter().parse()` 扫描每条消息模板的占位符并去重记录到 `input_variables`。在 `format_messages` 时先做前置完整性校验，避免缺失变量导致隐晦的运行期错误。

---

## 作业二：无缝切换 `DeepSeekChatModel` 与 `QwenChatModel`（统一网关实战）
**题目**：星辰数科要求同一套客服提问逻辑能够根据配置在 DeepSeek 与通义千问之间一键切换，且业务调用代码**不能出现 `if/else` 分支**。请编写一个函数 `ask_gateway(model: BaseChatModel, topic: str) -> str`：
1. 函数内部使用同一个 `ChatPromptTemplate` 构造提示词并调用 `model.invoke(...)`。
2. 分别传入 `DeepSeekChatModel(model_name="deepseek-reasoner")` 与 `QwenChatModel(model_name="qwen-max")` 执行调用，打印回复正文以及 `response_metadata["usage"]`。

### 参考答案：
```python
from zhishu_agent import (
    BaseChatModel,
    ChatPromptTemplate,
    DeepSeekChatModel,
    QwenChatModel,
)


def ask_gateway(model: BaseChatModel, topic: str) -> str:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是企业技术架构顾问。"),
            ("human", "请简述 {topic} 的核心工程收益。"),
        ]
    )
    prompt_value = prompt.invoke({"topic": topic})
    ai_msg = model.invoke(prompt_value)
    print(f"厂商={ai_msg.response_metadata['provider']} | 用量={ai_msg.response_metadata['usage']}")
    return ai_msg.content


for chat_model in (
    DeepSeekChatModel(model_name="deepseek-reasoner"),
    QwenChatModel(model_name="qwen-max"),
):
    print(ask_gateway(chat_model, "统一模型网关"))
    print("-" * 50)
```
**原理解析**：这就是面向对象**多态（Polymorphism）**与 **LangChain `BaseChatModel` 抽象**的威力——业务函数只依赖抽象基类 `BaseChatModel`，完全不感知底层是 DeepSeek 还是 Qwen，从而实现零代码侵入的模型替换与灰度路由。

---

## 作业三：多轮消息对象格式化与标准 API 字典转换
**题目**：在实际对接外部 HTTP 模型接口时，最终仍需将内存中的消息对象序列化为标准的 `[{"role": ..., "content": ...}]` JSON 载荷。请：
1. 手动构造一段包含 `SystemMessage`、两轮 `HumanMessage`/`AIMessage` 历史对话以及最新一条 `HumanMessage` 的消息列表。
2. 分别使用 `.pretty_repr()` 打印人类可读的调试日志，以及使用列表推导式 `[m.to_dict() for m in history]` 输出标准 API 请求载荷，并验证 `HumanMessage.role` 是否已自动映射为 `"user"`、`AIMessage.role` 是否映射为 `"assistant"`。

### 参考答案：
```python
from zhishu_agent import AIMessage, HumanMessage, SystemMessage

history = [
    SystemMessage(content="你是智枢平台运维专家。"),
    HumanMessage(content="Nginx 返回 502 Bad Gateway 怎么排查？"),
    AIMessage(content="请先检查上游 FastAPI 进程是否存活以及端口监听状态。"),
    HumanMessage(content="进程存活，但日志提示 connection refused。"),
]

print("=== 1. 调试日志格式 (pretty_repr) ===")
for msg in history:
    print(msg.pretty_repr())

print("\n=== 2. 标准 API 载荷格式 (to_dict) ===")
payload = [msg.to_dict() for msg in history]
for item in payload:
    print(item)

assert payload[1]["role"] == "user"
assert payload[2]["role"] == "assistant"
```
**原理解析**：LangChain 在上层语义上使用更贴近人类直觉的 `HumanMessage` / `AIMessage`，而在底层序列化（`to_dict()`）时自动映射为 OpenAI / 国产大模型通用协议的 `"user"` 与 `"assistant"`，兼顾了代码可读性与协议兼容性。
