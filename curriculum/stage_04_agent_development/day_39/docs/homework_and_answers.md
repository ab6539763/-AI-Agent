# Day 39 课后作业与参考答案

## 作业一：Chain（固定流水线）与 Agent（自主智能体）的本质差异辨析
**题目**：在星辰数科的知识库问答场景中，业务方提出需求：“先查询高级工程师的差旅住宿标准，如果标准超过 400 元，再计算连续出差 4 晚的总预算；如果低于 400 元，则直接给出提示无需计算。”
1. 请分析为什么 Stage 3 所学的固定 `Chain`（如 `Retriever -> Prompt -> LLM`）难以优雅地处理这类“带动态分支与多跳工具调用”的任务？
2. `ReAct` 范式是如何通过 `Thought -> Action -> Observation` 循环解决这一问题的？如果模型在循环中一直不输出 `Final Answer`，工程上该如何兜底？

### 参考答案：
1. **Chain 的局限性**：`Chain` 是静态有向无环图（DAG），执行路径在编码阶段就已经写死（例如必须先检索再生成，步骤数固定）。面对不确定需要调用多少次工具、也不确定何时该调用计算器的动态需求时，硬编码 `if/else` 会导致分支爆炸且无法泛化到新问题。
2. **ReAct 的突破与工程兜底**：
   - ReAct 将控制权交给推理循环：每一步由模型根据当前上下文（包含历史 `Observation`）自主 `Thought`，决定下一步是调用某个工具（`Action`）还是结束任务（`Final Answer`）。
   - 针对死循环风险，工程上必须在外层循环设置 **`max_steps` 步数上限守卫**（如 `ReActAgent(max_steps=5)`），一旦超出阈值立即安全中止并记录 `stopped_reason="max_steps"`，避免无限消耗 Token 与算力。

---

## 作业二：ReAct 正则输出解析器实战与容错扩展
**题目**：大模型在实际输出时，有时会在 `Action Input:` 中包含多行文本或前后多余的空格。请使用 `zhishu_agent.parse_react_output` 对以下 3 段模拟输出进行解析测试：
1. 包含标准 `Thought`、`Action`、`Action Input` 的输出；
2. 包含多行 `Final Answer` 的输出；
3. 缺少 `Action` 与 `Final Answer` 的异常输出（验证是否正确抛出 `ValueError`）。

### 参考答案：
```python
from zhishu_agent import ParsedAction, ParsedFinalAnswer, parse_react_output

samples = [
    (
        "Thought: 需要先检索年假制度。\n"
        "Action: knowledge_search\n"
        "Action Input: 带薪年假 制度"
    ),
    (
        "Thought: 信息已齐备，可以总结。\n"
        "Final Answer: 1. 满1年享5天年假。\n"
        "2. 病假需附三甲医院证明。"
    ),
    "抱歉，我今天心情不好，不想按格式输出。",
]

for idx, text in enumerate(samples, start=1):
    try:
        res = parse_react_output(text)
        if isinstance(res, ParsedAction):
            print(f"样本 {idx} -> [Action] {res.action}({res.action_input!r})")
        elif isinstance(res, ParsedFinalAnswer):
            print(f"样本 {idx} -> [Final Answer] {res.final_answer!r}")
    except ValueError as exc:
        print(f"样本 {idx} -> [捕获异常] {exc}")
```
**原理解析**：`parse_react_output` 使用 `re.DOTALL` 标志使 `.` 能够匹配换行符，从而支持多行 `Action Input` 与多行 `Final Answer`；同时在正则均未命中时主动抛出 `ValueError`，交由 `ReActAgent.run()` 捕获并标记 `stopped_reason="parse_error"`。

---

## 作业三：为 `ReActAgent` 新增自定义工具 `get_date` 并完成多跳推理
**题目**：智枢平台需要支持查询“当前日期”并结合计算器回答“距离月底还有几天”之类的问题。请你：
1. 定义一个名为 `get_date` 的 `ToolSpec`，调用时返回固定测试日期 `"2026-11-13"`（或当天日期）；
2. 通过 `agent.register_tool(...)` 将其注册到 `ReActAgent` 中；
3. 编写一个自定义 `planner` 函数，模拟“第 1 步调用 `get_date` -> 第 2 步调用 `calculator` 计算 `30 - 13` -> 第 3 步输出 `Final Answer`”的完整 3 步轨迹并打印 `trace.format_trace()`。

### 参考答案：
```python
from zhishu_agent import ReActAgent, ReActStep, ToolSpec


def get_date_tool(_: str) -> str:
    """返回当前系统演示日期."""
    return "2026-11-13"


def date_countdown_planner(query: str, steps: list[ReActStep]) -> str:
    """演示 get_date + calculator 多跳推理的确定性规划器."""
    if len(steps) == 0:
        return (
            "Thought: 我需要先获取今天的日期，才能计算距离月底的天数。\n"
            "Action: get_date\n"
            "Action Input: today"
        )
    if len(steps) == 1:
        date_str = steps[0].observation or "2026-11-13"
        day = int(date_str.split("-")[-1])
        return (
            f"Thought: 今天是 {date_str}（11月共30天），用计算器算一下 30 - {day}。\n"
            "Action: calculator\n"
            f"Action Input: 30 - {day}"
        )
    remaining = steps[-1].observation or "0"
    return (
        "Thought: 已经得到精确剩余天数，可以输出最终答复。\n"
        f"Final Answer: 今天是 2026-11-13，距离 11 月底还有 {remaining} 天。"
    )


agent = ReActAgent(planner=date_countdown_planner, max_steps=5)
agent.register_tool(
    ToolSpec(
        name="get_date",
        description="获取当前日期（YYYY-MM-DD 格式）",
        func=get_date_tool,
    )
)

trace = agent.run("今天距离 11 月底还有几天？")
print(trace.format_trace())
```
**原理解析**：`ReActAgent` 将工具表 `self.tools` 与推理引擎解耦。通过 `register_tool()` 注入新工具后，无需修改主循环任何代码，智能体即可在 `Thought-Action-Observation` 循环中无缝组合新旧工具完成多跳任务。
