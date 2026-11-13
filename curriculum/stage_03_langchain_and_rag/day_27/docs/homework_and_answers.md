# Day 27 课后作业与参考答案

## 作业一：滑动窗口记忆（`WindowMemory`）裁剪与 System Prompt 保护
**题目**：在长对话场景中，若把全部历史消息传给大模型会快速耗尽上下文窗口。请基于 `zhishu_agent.memory` 完成以下任务：
1. 向 `InMemoryChatMessageHistory` 写入 1 条 `system` 消息（`"你是智枢财务助手"`）和 4 轮完整对话（共 8 条 user/assistant 消息）。
2. 使用 `WindowMemory(k=2, keep_system=True)` 进行裁剪，验证返回结果总数为 **5 条**（1 条 system + 最近 2 轮共 4 条对话），并说明为什么生产环境中通常需要 `keep_system=True`。

### 参考答案：
```python
from zhishu_agent.memory import InMemoryChatMessageHistory, WindowMemory

history = InMemoryChatMessageHistory()
history.add_system_message("你是智枢财务助手")
for i in range(1, 5):
    history.add_user_message(f"第 {i} 轮报销问题")
    history.add_ai_message(f"第 {i} 轮报销解答")

window = WindowMemory(k=2, keep_system=True)
trimmed = window.load_memory_variables(history)

assert len(trimmed) == 5
assert trimmed[0].role == "system"
assert [m.content for m in trimmed[1:]] == [
    "第 3 轮报销问题",
    "第 3 轮报销解答",
    "第 4 轮报销问题",
    "第 4 轮报销解答",
]
```
**原理解析**：`System Prompt` 承载了智能体的角色设定、安全边界与输出格式约束。如果直接对整段列表做 `messages[-4:]` 切片，第 0 条的 `system` 消息会被丢弃，导致模型出现“人设漂移”或越权回答。因此必须先分离 `system` 消息与对话消息，仅对对话消息做 `-(2 * k)` 滑动裁剪，再重新拼接。

---

## 作业二：SQLite 持久化与进程重启恢复验证
**题目**：内存型记忆（`InMemoryChatMessageHistory`）在服务重启后会全部丢失。请使用 `SQLiteChatMessageHistory`：
1. 将会话 `"ops-oncall-01"` 的两轮对话写入临时数据库文件 `/tmp/day27_hw.db`。
2. 销毁原 Python 对象并重新实例化 `SQLiteChatMessageHistory("ops-oncall-01", "/tmp/day27_hw.db")`，验证消息条数与内容完整恢复，且严格按时间正序排列。

### 参考答案：
```python
from pathlib import Path
from zhishu_agent.memory import SQLiteChatMessageHistory

db_path = Path("/tmp/day27_hw.db")
if db_path.exists():
    db_path.unlink()

h1 = SQLiteChatMessageHistory(session_id="ops-oncall-01", db_path=db_path)
h1.add_user_message("线上 Redis 连接数告警怎么办？")
h1.add_ai_message("请先执行 INFO clients 检查闲置连接并核对超时配置。")
del h1  # 模拟服务重启，内存对象释放

h2 = SQLiteChatMessageHistory(session_id="ops-oncall-01", db_path=db_path)
msgs = h2.messages
assert len(msgs) == 2
assert msgs[0].role == "user"
assert msgs[1].role == "assistant"
print("恢复成功:", [m.to_dict() for m in msgs])
```

---

## 作业三：多租户 `session_id` 严格隔离与 `RunnableWithMessageHistory`
**题目**：某企业同时为 **HR 部门（`tenant-hr`）** 与 **法务部门（`tenant-legal`）** 提供智能体服务，两者共用同一个 SQLite 数据库文件。请使用 `RunnableWithMessageHistory` 配合 `SQLiteChatMessageHistory` 与 `SummaryMemory(max_recent_messages=2)`：
1. 分别以 `tenant-hr` 和 `tenant-legal` 的身份各发起 2 轮对话。
2. 验证在 `tenant-legal` 的对话上下文中**绝对不会出现** `tenant-hr` 的任何消息；同时验证当 `tenant-hr` 触发 `clear()` 清空会话时，`tenant-legal` 的历史记录依然完好无损。

### 参考答案：
```python
from pathlib import Path
from zhishu_agent.memory import (
    RunnableWithMessageHistory,
    SQLiteChatMessageHistory,
    SummaryMemory,
)

db_path = Path("/tmp/day27_multi_tenant.db")
if db_path.exists():
    db_path.unlink()

captured_context: dict[str, list[str]] = {}

def qa_chain(payload: dict) -> str:
    sid = payload["session_id"]
    captured_context[sid] = [m.content for m in payload["history"]]
    return f"[{sid}] 已处理: {payload['input']}"

app_chain = RunnableWithMessageHistory(
    runnable=qa_chain,
    get_session_history=lambda sid: SQLiteChatMessageHistory(sid, db_path),
    memory_strategy=SummaryMemory(max_recent_messages=2),
)

app_chain.invoke("HR 机密：Q4 调薪比例 8%", config={"configurable": {"session_id": "tenant-hr"}})
app_chain.invoke("HR 续问：年终奖何时发放？", config={"configurable": {"session_id": "tenant-hr"}})
app_chain.invoke("法务提问：保密协议违约金条款怎么写？", config={"configurable": {"session_id": "tenant-legal"}})

# 1. 验证法务租户上下文完全不包含 HR 机密
assert all("调薪" not in c for c in captured_context["tenant-legal"])
assert captured_context["tenant-legal"] == []

# 2. 清空 HR 会话，法务数据不受影响
SQLiteChatMessageHistory("tenant-hr", db_path).clear()
assert SQLiteChatMessageHistory("tenant-hr", db_path).messages == []
assert len(SQLiteChatMessageHistory("tenant-legal", db_path).messages) == 2
```
