# Day 05 课后作业与参考答案

## 作业一：嵌套字典精准提取（Nested Dict Extraction）
**题目**：大模型在触发工具调用（Function Calling）时，返回的 JSON 结构往往更深一层。请编写函数 `extract_tool_call(raw_json: str) -> dict`，从以下模拟响应中提取出：
- 工具名称 `tool_name`（位于 `choices[0]["message"]["tool_calls"][0]["function"]["name"]`）
- 工具参数字典 `arguments`（注意：`function["arguments"]` 本身是一个 **JSON 字符串**，需要再用 `json.loads()` 二次解析成 Python 字典！）

模拟输入数据：
```python
raw_tool_json = '''
{
  "id": "chatcmpl-tool-001",
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "query_weather",
              "arguments": "{\\"city\\": \\"上海\\", \\"unit\\": \\"celsius\\"}"
            }
          }
        ]
      }
    }
  ]
}
'''
```

### 参考答案：
```python
import json


def extract_tool_call(raw_json: str) -> dict:
    """从嵌套的 Function Calling JSON 响应中提取工具名与解析后的参数字典。"""
    data = json.loads(raw_json)
    message = data["choices"][0]["message"]
    first_tool = message["tool_calls"][0]["function"]

    tool_name = first_tool["name"]
    # 注意：OpenAI/DeepSeek 规范中 arguments 是字符串，需二次 json.loads()
    arguments = json.loads(first_tool["arguments"])

    return {
        "tool_name": tool_name,
        "arguments": arguments,
    }


# 验证运行
res = extract_tool_call(raw_tool_json)
print(res)
# 输出: {'tool_name': 'query_weather', 'arguments': {'city': '上海', 'unit': 'celsius'}}
```

---

## 作业二：JSON 序列化与中文编码实战（`ensure_ascii=False`）
**题目**：某同学在保存智枢平台用户的中文知识库标签时，直接写了 `json.dump(data, f)`，结果打开文件发现中文全变成了 `"\u667a\u67a2\u5e73\u53f0"`。请编写一段完整代码，使用 `pathlib.Path` 将如下包含中文的配置字典保存为 `agent_config.json`，要求：
1. 文件中**直接显示可读中文**，不能出现 `\uXXXX` 转义；
2. 使用 `indent=2` 美化缩进；
3. 重新读取该文件并验证 `loaded["agent_name"] == "智枢客服专员"`。

```python
config = {
    "agent_name": "智枢客服专员",
    "model": "deepseek-chat",
    "temperature": 0.3,
    "tags": ["企业知识库", "售后问答", "中文优先"],
}
```

### 参考答案：
```python
import json
from pathlib import Path

config = {
    "agent_name": "智枢客服专员",
    "model": "deepseek-chat",
    "temperature": 0.3,
    "tags": ["企业知识库", "售后问答", "中文优先"],
}

config_path = Path("agent_config.json")

# 1. 写入 JSON：务必指定 encoding="utf-8" 与 ensure_ascii=False
with config_path.open("w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

# 2. 查看原始文本内容，确认中文未被转义
print("文件内容如下：")
print(config_path.read_text(encoding="utf-8"))

# 3. 重新加载并断言验证
with config_path.open("r", encoding="utf-8") as f:
    loaded = json.load(f)

assert loaded["agent_name"] == "智枢客服专员"
print("中文配置校验通过！")
```

---

## 作业三：多模型 API 用量聚合器（API Usage Aggregator）
**题目**：在真实的企业平台中，智枢平台可能会同时调用 `deepseek-chat` 和 `qwen-plus` 两个模型。请编写函数 `aggregate_usage_by_model(responses: list[dict]) -> dict[str, dict[str, int]]`，按 `model` 字段分组统计每个模型的 `calls`（调用次数）和 `total_tokens`（总 Token 消耗）。

输入示例：
```python
logs = [
    {"model": "deepseek-chat", "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}},
    {"model": "qwen-plus", "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}},
    {"model": "deepseek-chat", "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}},
]
```

### 参考答案：
```python
def aggregate_usage_by_model(responses: list[dict]) -> dict[str, dict[str, int]]:
    """按模型名称分组统计调用次数与总 Token 消耗。"""
    stats: dict[str, dict[str, int]] = {}

    for resp in responses:
        model = resp.get("model", "unknown")
        usage = resp.get("usage", {})
        tokens = int(usage.get("total_tokens", 0))

        if model not in stats:
            stats[model] = {"calls": 0, "total_tokens": 0}

        stats[model]["calls"] += 1
        stats[model]["total_tokens"] += tokens

    return stats


# 验证运行
result = aggregate_usage_by_model(logs)
print(result)
# 输出: {'deepseek-chat': {'calls': 2, 'total_tokens': 450}, 'qwen-plus': {'calls': 1, 'total_tokens': 100}}
```
