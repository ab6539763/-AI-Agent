# Day 26 课后作业与参考答案

## 作业一：自定义 `Runnable` 子类并接入 `|` 管道
**题目**：在企业级日志脱敏场景中，我们需要一个可复用的组件，将文本中的手机号（11 位数字）自动替换为 `***`。请你继承 Day 26 的 `Runnable` 抽象基类，实现一个 `PhoneMaskRunnable(Runnable[str, str])`：
1. 实现 `invoke(self, input_data: str, config=None) -> str` 方法，使用正则将连续 11 位数字替换为 `***`。
2. 将其与 `RunnableLambda` 使用 `|` 管道符串联，先去除首尾空格（`.strip()`），再脱敏，最后加上 `" [已脱敏]"` 后缀。

### 参考答案：
```python
import re
from typing import Any, Dict, Optional
from zhishu_agent.lcel import Runnable, RunnableLambda


class PhoneMaskRunnable(Runnable[str, str]):
    """自定义手机号脱敏 Runnable 组件。"""

    def invoke(self, input_data: str, config: Optional[Dict[str, Any]] = None) -> str:
        return re.sub(r"\b1\d{10}\b", "***", input_data)


sanitize_chain = (
    RunnableLambda(lambda s: s.strip())
    | PhoneMaskRunnable()
    | (lambda s: f"{s} [已脱敏]")
)

print(sanitize_chain.invoke("  请联系工程师 13800138000 处理告警  "))
# 输出: 请联系工程师 *** 处理告警 [已脱敏]
```

---

## 作业二：使用 `RunnableParallel` 并行提取文本多维特征
**题目**：在文档入库 RAG 之前，通常需要同时计算文档的多个元信息（如字符数、行数、是否包含敏感词）。请使用 `RunnableParallel`（或字典自动转换语法）编写一个并行管道：
1. 输入为一段多行文本 `text: str`。
2. 并行输出三个键：`char_count`（总字符数）、`line_count`（行数）、`has_secret`（是否包含 `"SECRET"` 关键字，返回布尔值）。
3. 再通过 `|` 连接一个 `RunnableLambda`，将其格式化为可读的审计摘要字符串。

### 参考答案：
```python
from zhishu_agent.lcel import RunnableParallel, RunnableLambda

feature_chain = (
    RunnableParallel(
        char_count=lambda text: len(text),
        line_count=lambda text: len(text.splitlines()),
        has_secret=lambda text: "SECRET" in text,
    )
    | RunnableLambda(
        lambda meta: (
            f"审计结果：共 {meta['line_count']} 行 / {meta['char_count']} 字符，"
            f"敏感词检测={'发现风险' if meta['has_secret'] else '安全'}"
        )
    )
)

sample = "第一行：智枢平台上线\n第二行：SECRET_KEY=demo"
print(feature_chain.invoke(sample))
# 输出: 审计结果：共 2 行 / 28 字符，敏感词检测=发现风险
```

---

## 作业三：使用 `PydanticOutputParser` 强制校验大模型结构化输出
**题目**：大模型有时会在 JSON 外层包裹 ` ```json ... ``` ` 代码块，甚至输出不符合字段约束的脏数据。请基于 Day 26 的 `PydanticOutputParser`：
1. 定义一个 Pydantic 模型 `TicketClassification`，包含 `category: str`、`urgency: int`（约束范围为 `1 <= urgency <= 5`）和 `tags: list[str]`。
2. 实例化 `PydanticOutputParser(TicketClassification)`，打印 `get_format_instructions()`，并演示：
   - 成功解析带 ` ```json ``` ` 包裹的合法模型输出；
   - 当 `urgency=10`（超出范围）时，捕获 `ValueError` 并打印错误提示。

### 参考答案：
```python
from typing import List
from pydantic import BaseModel, Field
from zhishu_agent.lcel import AIMessage, PydanticOutputParser


class TicketClassification(BaseModel):
    category: str = Field(description="工单分类，如 network / database / auth")
    urgency: int = Field(ge=1, le=5, description="紧急程度，1-5 的整数")
    tags: List[str] = Field(description="关联标签列表")


parser = PydanticOutputParser(TicketClassification)
print("Schema 指令片段:\n", parser.get_format_instructions()[:160], "...\n")

valid_msg = AIMessage(
    content='```json\n{"category": "database", "urgency": 4, "tags": ["sqlite", "lock"]}\n```'
)
ticket = parser.invoke(valid_msg)
print("解析成功:", ticket)

try:
    parser.invoke('{"category": "database", "urgency": 10, "tags": []}')
except ValueError as err:
    print("拦截非法输出:", err)
```
