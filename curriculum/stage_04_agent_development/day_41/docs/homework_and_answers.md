# Day 41 课后作业与参考答案

## 作业一：基于条件边（`add_conditional_edges`）实现客服工单智能分级路由
**题目**：星辰数科客服中心需要根据用户工单的紧急程度（`priority`）与问题类别（`category`），将工单路由至不同的处理节点：
1. 定义状态 `TicketState`（包含 `ticket_id`、`priority`、`category`、`handler`）。
2. 构建包含 `classify`、`vip_support`、`tech_support`、`general_support` 四个节点的 `StateGraph`。
3. 使用 `add_conditional_edges("classify", router_fn, path_map)` 实现路由规则：
   - 若 `priority == "urgent"`，路由至 `vip_support`；
   - 否则若 `category == "bug"`，路由至 `tech_support`；
   - 其余情况路由至 `general_support`。
4. 编译并验证三条路径的 `invoke()` 输出结果。

### 参考答案：
```python
from typing import TypedDict
from zhishu_agent import END, START, StateGraph

class TicketState(TypedDict, total=False):
    ticket_id: str
    priority: str
    category: str
    handler: str

def classify(state: dict) -> dict:
    return {"ticket_id": state["ticket_id"]}

def route_ticket(state: dict) -> str:
    if state.get("priority") == "urgent":
        return "vip"
    if state.get("category") == "bug":
        return "tech"
    return "general"

graph = StateGraph(TicketState)
graph.add_node("classify", classify)
graph.add_node("vip_support", lambda s: {"handler": "VIP专属坐席"})
graph.add_node("tech_support", lambda s: {"handler": "研发二线工程师"})
graph.add_node("general_support", lambda s: {"handler": "标准客服机器人"})

graph.add_edge(START, "classify")
graph.add_conditional_edges(
    "classify",
    route_ticket,
    {"vip": "vip_support", "tech": "tech_support", "general": "general_support"},
)
graph.add_edge("vip_support", END)
graph.add_edge("tech_support", END)
graph.add_edge("general_support", END)

app = graph.compile()
assert app.invoke({"ticket_id": "T1", "priority": "urgent", "category": "billing"})["handler"] == "VIP专属坐席"
assert app.invoke({"ticket_id": "T2", "priority": "normal", "category": "bug"})["handler"] == "研发二线工程师"
assert app.invoke({"ticket_id": "T3", "priority": "normal", "category": "faq"})["handler"] == "标准客服机器人"
print("工单路由测试全部通过！")
```

---

## 作业二：设计带循环终止守卫（Cycle Termination Guard）的自动重试图
**题目**：在调用外部检索或 API 时，可能会遇到临时失败。请使用 `StateGraph` 构建一个带重试循环的图：
1. 状态包含 `attempt`（当前尝试次数）、`max_retries`（最大重试次数）、`success`（是否成功）。
2. 节点 `call_api` 每次将 `attempt` 加 1，并假设第 3 次尝试时才成功（`attempt >= 3` 时 `success = True`）。
3. 通过条件边判断：若 `success` 为 `True` 或 `attempt >= max_retries`，则结束（`END`）；否则循环回到 `call_api`。
4. 分别测试 `max_retries=3`（正常成功）、`max_retries=2`（达到最大重试次数安全退出）、以及使用 `config={"recursion_limit": 2}` 触发 `GraphRecursionError` 熔断保护。

### 参考答案：
```python
from zhishu_agent import END, START, GraphRecursionError, StateGraph

def call_api(state: dict) -> dict:
    attempt = state.get("attempt", 0) + 1
    return {"attempt": attempt, "success": attempt >= 3}

def should_retry(state: dict) -> str:
    if state.get("success") or state.get("attempt", 0) >= state.get("max_retries", 3):
        return "stop"
    return "retry"

g = StateGraph()
g.add_node("call_api", call_api)
g.add_edge(START, "call_api")
g.add_conditional_edges("call_api", should_retry, {"retry": "call_api", "stop": END})
app = g.compile()

# 1. 第 3 次成功
res_ok = app.invoke({"attempt": 0, "max_retries": 3})
assert res_ok["success"] is True and res_ok["attempt"] == 3

# 2. 业务级 max_retries=2 安全退出
res_cap = app.invoke({"attempt": 0, "max_retries": 2})
assert res_cap["success"] is False and res_cap["attempt"] == 2

# 3. 引擎级 recursion_limit=2 熔断保护
try:
    app.invoke({"attempt": 0, "max_retries": 5}, config={"recursion_limit": 2})
    raise AssertionError("预期应抛出 GraphRecursionError")
except GraphRecursionError as exc:
    print("成功触发熔断保护:", exc)
```

---

## 作业三：导出并校验状态图的 Mermaid `stateDiagram-v2` 拓扑文本
**题目**：在团队代码评审（MR）中，我们需要自动生成状态图的 Mermaid 文档以便在 GitLab 中可视化展示。请编写代码：
1. 调用 `build_approval_graph()` 获取编译后的审批流图。
2. 调用 `to_mermaid()` 导出 Mermaid 文本并打印。
3. 编写断言校验导出的文本以 `stateDiagram-v2` 开头，且包含 `[*] --> risk_assess`、`risk_assess --> human_review : high_risk` 以及 `reject_action --> [*]`。

### 参考答案：
```python
from zhishu_agent import build_approval_graph

approval_app = build_approval_graph(auto_approve_limit=1000.0)
mermaid_doc = approval_app.to_mermaid()
print(mermaid_doc)

assert mermaid_doc.startswith("stateDiagram-v2")
assert "[*] --> risk_assess" in mermaid_doc
assert "risk_assess --> human_review : high_risk" in mermaid_doc
assert "reject_action --> [*]" in mermaid_doc
print("Mermaid 拓扑导出校验通过！")
```
