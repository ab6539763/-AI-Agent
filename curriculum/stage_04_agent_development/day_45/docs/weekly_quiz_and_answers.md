# 第七周综合测验与参考答案（Week 7 Assessment）

> **覆盖范围**：Day 39 ~ Day 45（ReAct 循环、LangGraph 状态图、SQLiteCheckpointer 与 Human-in-the-loop、Multi-Agent 协作、MCP 协议与工具治理、低代码 Workflow DSL 引擎）
> **满分**：100 分（10 道单选题 × 6 分 + 2 道编程实战题 × 20 分）

---

## 第一部分：单项选择题（每题 6 分，共 60 分）

### 题目 1（ReAct 范式核心机制）
在经典的 ReAct（Reasoning + Acting）智能体循环中，模型每轮推理产生 `Thought -> Action -> Action Input`，随后由运行时环境执行工具并返回 `Observation`。以下关于 ReAct 循环终止条件的说法，**最准确**的是：
- A. 只要工具返回了非空字符串，循环就必须立即终止
- B. 当模型输出 `Final Answer`（或不再产生 `tool_calls`）或达到 `max_iterations` 上限时终止
- C. ReAct 只能执行单步工具调用，无法在一次任务中连续调用多个工具
- D. `Observation` 由大模型自行编造生成，无需真实工具执行

### 题目 2（LangGraph StateGraph 与 Reducer）
在 LangGraph 中定义图状态 `AgentState(TypedDict)` 时，若多个并行节点都需要向同一个列表字段 `messages` 追加数据，通常应使用以下哪种机制避免后写入节点覆盖先写入节点的数据？
- A. 将 `messages` 定义为不可变元组 `tuple`
- B. 使用 `Annotated[list, operator.add]`（或自定义 Reducer 函数）声明增量归约策略
- C. 在每个节点中手动调用 `time.sleep()` 错开写入时间
- D. 将 `StateGraph` 降级为单节点线性函数

### 题目 3（Checkpointer 与 Thread 隔离）
在企业级智能体生产部署中，使用 `SQLiteCheckpointer` 或 `PostgresSaver` 持久化状态快照时，`thread_id` 的核心作用是：
- A. 仅用于日志打印美化，不参与数据库查询
- B. 作为不同用户会话或任务实例的隔离主键，实现跨请求断点恢复与时间旅行审计
- C. 控制大模型每次生成的最大 Token 数
- D. 替代 API Key 进行模型鉴权

### 题目 4（Human-in-the-loop 拦截与恢复）
在带有 `interrupt_before=["human_approval"]` 的状态图中，当图执行在 `human_approval` 节点前暂停后，人工审稿人修改了状态并调用 `graph.resume(thread_id, updated_state)`。以下哪项工程细节是**必须处理**的？
- A. 恢复执行时直接清空历史检查点表
- B. 恢复首轮必须跳过对 `human_approval` 的 `interrupt_before` 拦截检查，否则会陷入无限重复暂停死锁
- C. 必须重启 Python 进程才能读取 SQLite 中的检查点
- D. `resume()` 只能读取状态，绝对不能注入人工修改后的字段

### 题目 5（并行节点与确定性保序）
当使用 `ThreadPoolExecutor` 并发生成长文报告的 5 个章节时，第 3 章可能比第 1 章先返回结果。为保证最终拼接的文章章节顺序严格正确，最合理的做法是：
- A. 按 `as_completed()` 返回的时间先后直接拼接字符串
- B. 为每个任务绑定原始大纲索引 `index`，在汇总阶段按 `index` 排序或放入预分配槽位 `results[index]`
- C. 改为单线程串行执行并放弃并发
- D. 让大模型在最后一步重新猜测章节顺序

### 题目 6（Multi-Agent 编排模式）
在多智能体（Multi-Agent）系统中，“Supervisor（主管）模式”与“纯自由广播群聊模式”相比，在企业生产环境中最显著的优势是：
- A. 完全不需要任何提示词工程
- B. 路由决策集中可控、状态流转可预测、易于设置最大轮次与权限边界，避免智能体之间无限互相踢皮球
- C. 一定比单智能体消耗更少的 Token
- D. 只能使用同一个大模型，不能异构混用

### 题目 7（MCP 协议与传统 Function Calling）
关于 Model Context Protocol（MCP），以下描述**正确**的是：
- A. MCP 只能运行在浏览器端，不支持本地 STDIO 进程通信
- B. MCP 通过标准化的 Client-Server 协议统一了 Tools、Resources 与 Prompts 的发现与调用规范，解决了“M 个模型 × N 个数据源”的碎片化集成问题
- C. 使用 MCP 后，工具不再需要参数 Schema 校验
- D. MCP 是某一家云厂商专有的闭源私有协议

### 题目 8（低代码 vs 高代码边界）
星辰数科在架构评审中制定了低代码（Dify/Coze）与高代码（LangGraph）的选型边界。以下哪个场景**最适合**采用高代码（Pro-Code）方案而非纯低代码拖拉拽？
- A. 运营团队需要每两天调整一次提示词的常规活动 FAQ 机器人
- B. 需要复杂循环自愈重试、人工审批打回重写、跨数据库事务补偿的核心风控/长文编排引擎
- C. 仅包含“输入 -> 知识库检索 -> 大模型总结 -> 输出”的 4 步标准问答流
- D. 内部黑客松 1 小时快速演示的概念验证（Demo）

### 题目 9（Workflow DSL 变量插值）
在 Dify/Coze 风格的 Workflow DSL 中，节点配置里经常出现 `"prompt": "问题：{{sys.query}}\n资料：{{kb_1.context}}"`。以下关于变量池（Variable Pool）解析的说法错误的是：
- A. `sys` 命名空间通常存放工作流入口传入的系统/用户输入参数
- B. `kb_1.context` 引用了节点 ID 为 `kb_1` 的执行输出中的 `context` 字段
- C. 如果工作流存在循环依赖（如 A -> B -> A），拓扑排序（Kahn 算法）在解析阶段即可将其拦截
- D. 变量插值只能在 `LLMNode` 中使用，不能用于 `KnowledgeRetrievalNode` 或 `EndNode`

### 题目 10（ConditionNode 路由机制）
在声明式 DAG 工作流中，`ConditionNode` 执行完条件判断后返回 `selected_branch = "hit"`，引擎如何决定下一个要执行的节点？
- A. 随机挑选一个下游节点执行
- B. 仅激活并入队出边中 `sourceHandle`（分支标识）等于 `"hit"`（或未指定条件）的目标节点
- C. 同时执行所有分支的下游节点，最后丢弃其中一个
- D. 直接终止整个工作流

---

## 第二部分：编程实战题（每题 20 分，共 40 分）

### 编程题 1：手写基于 Kahn 算法的 DAG 环检测器
请实现函数 `validate_dag(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]`：
- 输入节点 ID 列表 `nodes` 与有向边列表 `edges`（每条边为 `(source, target)`）。
- 若存在自环、引用不存在节点或循环依赖，抛出 `ValueError`。
- 若为合法 DAG，返回该图的一个有效拓扑排序节点序列。

### 编程题 2：实现带嵌套路径与严格模式开关的模板渲染器
请实现函数 `render_dsl_template(template: str, pool: dict, strict: bool = True) -> str`：
- 支持 `{{sys.query}}`、`{{user.profile.city}}` 等任意深度点分路径（允许花括号内带前后空格如 `{{ sys.query }}`）。
- 当变量不存在时：若 `strict=True` 抛出 `KeyError`；若 `strict=False` 替换为空字符串 `""`。
- 当变量值为 `dict` 或 `list` 时，使用 `json.dumps(..., ensure_ascii=False)` 序列化。

---

## 第三部分：参考答案与解析

### 单选题答案速查表

| 题号 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **答案** | **B** | **B** | **B** | **B** | **B** | **B** | **B** | **B** | **D** | **B** |

### 单选题逐题精析
1. **B**：ReAct 是“思考-行动-观察”的迭代循环，只有当模型给出最终回答（不再调用工具）或触发最大步数熔断时才结束。
2. **B**：LangGraph 通过 `Annotated[list, operator.add]` 等 Reducer 机制实现多分支并行更新同一状态字段时的安全归约合并。
3. **B**：`thread_id` 是 Checkpointer 隔离多租户/多会话状态的唯一标识，也是恢复断点与回溯历史的关键键。
4. **B**：若恢复时不跳过首轮对当前中断节点的 `interrupt_before` 检查，图引擎会在同一节点再次触发暂停导致死锁。
5. **B**：并发执行耗时不可预测，必须通过任务索引 `index` 重排结果，兼顾吞吐量与输出顺序的 100% 确定性。
6. **B**：Supervisor 模式通过中心路由节点收敛控制流，可观测性强且便于设置终止条件。
7. **B**：MCP（Model Context Protocol）是开放标准，统一了工具/资源/提示词的接入契约，支持 STDIO 与 SSE/HTTP 传输。
8. **B**：高代码（Pro-Code）的核心价值在于处理复杂状态机、细粒度重试、人工审批与深度业务系统集成。
9. **D**：错误。变量插值在 `KnowledgeRetrievalNode`（渲染 `query_template`）、`ConditionNode`（读取变量值）、`LLMNode` 与 `EndNode`（映射最终输出）中均广泛使用。
10. **B**：`ConditionNode` 通过匹配出边的 `sourceHandle` 实现条件路由，未命中的分支节点不会被激活执行。

---

### 编程题参考实现

#### 编程题 1 参考答案
```python
from collections import defaultdict, deque


def validate_dag(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    node_set = set(nodes)
    if len(node_set) != len(nodes):
        raise ValueError("存在重复节点 ID")

    outgoing: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n: 0 for n in nodes}

    for src, dst in edges:
        if src not in node_set or dst not in node_set:
            raise ValueError(f"边引用了不存在的节点: {(src, dst)}")
        if src == dst:
            raise ValueError(f"检测到自环边: {src}")
        outgoing[src].append(dst)
        in_degree[dst] += 1

    queue = deque([n for n, deg in in_degree.items() if deg == 0])
    topo_order: list[str] = []
    while queue:
        curr = queue.popleft()
        topo_order.append(curr)
        for nxt in outgoing[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(topo_order) != len(nodes):
        raise ValueError("检测到循环依赖，非合法 DAG")
    return topo_order
```

#### 编程题 2 参考答案
```python
import json
import re
from typing import Any

_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*\}\}")


def render_dsl_template(template: str, pool: dict[str, Any], strict: bool = True) -> str:
    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        curr: Any = pool
        for part in path.split("."):
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                if strict:
                    raise KeyError(f"未定义变量: {path}")
                return ""
        if isinstance(curr, (dict, list)):
            return json.dumps(curr, ensure_ascii=False)
        return "" if curr is None else str(curr)

    return _PATTERN.sub(_replace, template)
```
