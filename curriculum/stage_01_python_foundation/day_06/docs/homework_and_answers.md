# Day 06 课后作业与参考答案

## 作业一：`*args` 与 `**kwargs` 实战 —— 动态 Agent 工具调用日志构造器
**题目**：在智枢平台中，Agent 调用外部工具（如天气查询、数据库检索）时，参数个数和附加元信息往往不固定。请编写函数 `build_tool_log(tool_name: str, *tags: str, level: str = "INFO", **metadata) -> dict`，要求：
1. `tool_name` 为必选位置/关键字参数；
2. `*tags` 接收任意多个标签字符串，转为列表存入 `"tags"`；
3. `level` 为默认关键字参数（默认 `"INFO"`）；
4. `**metadata` 接收任意扩展键值对（如 `latency_ms=120, user_id="u_001"`），合并到返回字典的 `"meta"` 字段中。

### 参考答案：
```python
from typing import Any


def build_tool_log(
    tool_name: str,
    *tags: str,
    level: str = "INFO",
    **metadata: Any,
) -> dict[str, Any]:
    """使用位置参数、*args、默认关键字参数与 **kwargs 构造工具调用日志。"""
    return {
        "tool_name": tool_name,
        "level": level,
        "tags": list(tags),
        "meta": metadata,
    }


# 验证运行
log_entry = build_tool_log(
    "query_knowledge_base",
    "rag",
    "enterprise",
    level="DEBUG",
    latency_ms=85,
    top_k=5,
)
print(log_entry)
# 输出: {'tool_name': 'query_knowledge_base', 'level': 'DEBUG', 'tags': ['rag', 'enterprise'], 'meta': {'latency_ms': 85, 'top_k': 5}}
```

---

## 作业二：`lambda` 高阶排序 —— 大模型按性价比与价格排序
**题目**：智枢平台接入了多个大模型，每个模型用字典表示（包含输入单价 `input_price` 和输出单价 `output_price`，单位：元/百万 Token）。请使用 `sorted()` 配合 `lambda` 表达式完成以下两项排序任务：
1. 按**输出单价 `output_price`** 从低到高升序排列；
2. 按**综合加权单价**（`0.4 * input_price + 0.6 * output_price`）从高到低降序排列，并打印排序后的模型名称与加权价格。

输入数据：
```python
models = [
    {"name": "deepseek-chat", "input_price": 1.0, "output_price": 2.0},
    {"name": "qwen-max", "input_price": 20.0, "output_price": 60.0},
    {"name": "glm-4-flash", "input_price": 0.1, "output_price": 0.1},
    {"name": "gpt-4o-mini", "input_price": 1.1, "output_price": 4.4},
]
```

### 参考答案：
```python
models = [
    {"name": "deepseek-chat", "input_price": 1.0, "output_price": 2.0},
    {"name": "qwen-max", "input_price": 20.0, "output_price": 60.0},
    {"name": "glm-4-flash", "input_price": 0.1, "output_price": 0.1},
    {"name": "gpt-4o-mini", "input_price": 1.1, "output_price": 4.4},
]

# 1. 按 output_price 从低到高排序
by_output_asc = sorted(models, key=lambda m: m["output_price"])
print("按输出单价升序:", [m["name"] for m in by_output_asc])
# 输出: ['glm-4-flash', 'deepseek-chat', 'gpt-4o-mini', 'qwen-max']

# 2. 按综合加权单价从高到低降序排序
by_weighted_desc = sorted(
    models,
    key=lambda m: 0.4 * m["input_price"] + 0.6 * m["output_price"],
    reverse=True,
)
for m in by_weighted_desc:
    weighted = 0.4 * m["input_price"] + 0.6 * m["output_price"]
    print(f"{m['name']}: 加权单价 = ¥{weighted:.2f}/百万Tokens")
```

---

## 作业三：递归遍历 —— 嵌套字典键检索（Recursive Dict Search）
**题目**：在解析复杂的 Agent 配置或大模型 Tool Calling 响应 JSON 时，目标字段可能藏在任意深度的嵌套 `dict` 或 `list` 中。请编写递归函数 `find_values_by_key(node: dict | list | object, target_key: str) -> list`，收集并返回嵌套结构中所有键名为 `target_key` 的值。

输入示例：
```python
agent_tree = {
    "name": "主路由Agent",
    "sub_agents": [
        {"name": "财务分析Agent", "tools": [{"name": "sql_query"}]},
        {"name": "法务审阅Agent", "config": {"name": "contract_checker"}},
    ],
}
```

### 参考答案：
```python
from typing import Any


def find_values_by_key(node: Any, target_key: str) -> list[Any]:
    """递归遍历任意深度的 dict / list 结构，收集指定键名的所有值。"""
    results: list[Any] = []

    if isinstance(node, dict):
        for key, value in node.items():
            if key == target_key:
                results.append(value)
            # 无论当前 key 是否命中，都要继续向 value 深层递归
            results.extend(find_values_by_key(value, target_key))
    elif isinstance(node, list):
        for item in node:
            results.extend(find_values_by_key(item, target_key))

    return results


# 验证运行
agent_tree = {
    "name": "主路由Agent",
    "sub_agents": [
        {"name": "财务分析Agent", "tools": [{"name": "sql_query"}]},
        {"name": "法务审阅Agent", "config": {"name": "contract_checker"}},
    ],
}
print(find_values_by_key(agent_tree, "name"))
# 输出: ['主路由Agent', '财务分析Agent', 'sql_query', '法务审阅Agent', 'contract_checker']
```
