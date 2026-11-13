# Day 19 课后作业与参考答案

## 作业一：为企业工具编写标准 OpenAI JSON Schema
**题目**：智枢平台需要新增一个“会议室预订”工具 `book_meeting_room(room_name: str, date: str, duration_minutes: int = 60)`。请你严格按照 OpenAI Function Calling 规范，写出它的 `dict` 格式 JSON Schema，要求：
1. `room_name`（会议室名称）和 `date`（日期，格式 `YYYY-MM-DD`）为必填项。
2. `duration_minutes` 为可选整数，枚举值限定为 `[30, 60, 90, 120]`。
3. 禁止传入未定义的额外参数（`additionalProperties: False`）。

### 参考答案：
```python
BOOK_MEETING_ROOM_SCHEMA = {
    "type": "function",
    "function": {
        "name": "book_meeting_room",
        "description": "预订星辰数科公司内部会议室。",
        "parameters": {
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "会议室名称，例如 '星辰厅' 或 '302会议室'。",
                },
                "date": {
                    "type": "string",
                    "description": "预订日期，格式为 YYYY-MM-DD。",
                },
                "duration_minutes": {
                    "type": "integer",
                    "enum": [30, 60, 90, 120],
                    "description": "会议时长（分钟），默认 60 分钟。",
                },
            },
            "required": ["room_name", "date"],
            "additionalProperties": False,
        },
    },
}
```

---

## 作业二：单轮并行多工具分发（Multi-Tool Dispatch）
**题目**：大模型在 Round 1 经常会在同一个 `assistant` 消息的 `tool_calls` 列表中返回多个待调用工具（例如同时查天气和做数学计算）。请你基于 `ToolRegistry` 编写一个函数 `execute_tool_calls(registry: ToolRegistry, tool_calls: list[dict]) -> list[dict]`：
1. 遍历 `tool_calls` 中的每一项。
2. 调用 `registry.dispatch(name, arguments)` 执行工具。
3. 返回符合 OpenAI 协议的 `role="tool"` 消息列表（每条消息必须包含 `role`、`tool_call_id`、`name`、`content` 四个字段）。

### 参考答案：
```python
from zhishu_agent.tool_calling import ToolRegistry, create_default_registry


def execute_tool_calls(registry: ToolRegistry, tool_calls: list[dict]) -> list[dict]:
    """批量执行模型返回的 tool_calls，生成标准 role='tool' 消息列表。"""
    tool_messages: list[dict] = []
    for tc in tool_calls:
        call_id = tc["id"]
        fn_name = tc["function"]["name"]
        fn_args = tc["function"].get("arguments", "{}")
        result_json = registry.dispatch(fn_name, fn_args)
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": fn_name,
                "content": result_json,
            }
        )
    return tool_messages


registry = create_default_registry()
mock_calls = [
    {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "上海"}'}},
    {"id": "call_2", "type": "function", "function": {"name": "calculate_math", "arguments": '{"expression": "15 * 4"}'}},
]
print(execute_tool_calls(registry, mock_calls))
```

---

## 作业三：处理模型幻觉出的“未知工具名”（Graceful Error Handling）
**题目**：在实际生产中，大模型偶尔会产生幻觉，请求调用一个未注册的工具（例如 `"delete_all_files"`）。如果直接用 `self._functions[name]` 索引会抛出 `KeyError` 导致整个智能体进程崩溃。请说明：
1. 在 Pure-API Function Calling 架构中，遇到未知工具名时应该如何优雅处理？
2. 为什么将错误信息包装成 JSON 字符串并通过 `role="tool"` 回传给模型，比直接抛出异常更好？

### 参考答案：
1. **处理方式**：在 `ToolRegistry.dispatch()` 中先检查 `if name not in self._functions:`，若不存在，不抛出未捕获异常，而是构造包含错误说明与当前可用工具列表的 JSON 字符串返回：
   ```python
   return json.dumps(
       {"error": f"未知工具: {name}", "available_tools": self.list_tools()},
       ensure_ascii=False,
   )
   ```
2. **原因分析**：
   - **协议完整性**：OpenAI `/chat/completions` 协议严格要求 `assistant` 消息中的每一个 `tool_call_id` 都必须有对应的 `role="tool"` 消息作为响应，否则后续对话历史会变成非法状态。
   - **模型自愈能力（Self-Correction）**：把 `available_tools` 和错误原因作为观测结果（Observation）喂回给大模型后，大模型在 Round 2 能够意识到“自己幻觉了工具名”，从而自动改用正确的工具重试，或礼貌地告知用户当前能力边界。
