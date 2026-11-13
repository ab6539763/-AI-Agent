# Day 42 课后作业与参考答案

## 作业一：`SQLiteCheckpointer` 多线程隔离与跨实例持久化恢复
**题目**：在多租户智能体平台中，不同用户的对话和写作任务必须严格隔离，且服务重启后不能丢失历史进度。请你使用 `tempfile.TemporaryDirectory()` 和 `SQLiteCheckpointer` 完成以下验证：
1. 在同一 SQLite 数据库文件中分别保存 `thread_id="user-alice"` 与 `thread_id="user-bob"` 的检查点。
2. 重新实例化一个新的 `SQLiteCheckpointer` 对象（模拟进程重启），验证 `list_threads()` 包含两个线程，且各自 `get_latest()` 返回的状态互不串扰。
3. 调用 `delete_thread("user-bob")`，确认仅删除 Bob 的记录，Alice 的历史记录依然完整。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import END, SQLiteCheckpointer

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "hw1_ckpt.db"
    cp1 = SQLiteCheckpointer(db_path)

    cp1.save_checkpoint("user-alice", step=1, next_node="human_approval", state={"topic": "RAG 检索"}, status="interrupted")
    cp1.save_checkpoint("user-bob", step=1, next_node=END, state={"topic": "SQL 优化"}, status="completed")

    # 模拟服务重启后重新连接同一数据库
    cp2 = SQLiteCheckpointer(db_path)
    assert cp2.list_threads() == ["user-alice", "user-bob"]

    alice_latest = cp2.get_latest("user-alice")
    bob_latest = cp2.get_latest("user-bob")
    assert alice_latest is not None and alice_latest.state["topic"] == "RAG 检索"
    assert bob_latest is not None and bob_latest.state["topic"] == "SQL 优化"

    deleted = cp2.delete_thread("user-bob")
    assert deleted == 1
    assert cp2.get_latest("user-bob") is None
    assert cp2.get_latest("user-alice") is not None
    print("作业一校验通过！当前剩余线程:", cp2.list_threads())
```

---

## 作业二：Human-in-the-loop `interrupt_before` 拦截与 `resume()` 状态注入
**题目**：为了防止 AI 自动发布的周报出现事实错误，需要在发布节点 `publish` 前设置人工审核断点。请你使用 `AdvancedStateGraph` 构建 `draft -> publish -> END` 流程：
1. 编译图时配置 `interrupt_before=["publish"]` 与 `SQLiteCheckpointer`。
2. 调用 `invoke({"topic": "Q3 研发周报"}, thread_id="report-01")`，断言执行结果在 `publish` 前暂停（`status == "interrupted"`）。
3. 模拟主管审稿：调用 `resume("report-01", updated_state={"approved": True, "reviewer": "林晓", "draft": "Q3 研发周报（终审版）"})`，验证图恢复执行至 `completed` 并输出带审稿人签名的终稿。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import END, AdvancedStateGraph, SQLiteCheckpointer

with tempfile.TemporaryDirectory() as tmpdir:
    cp = SQLiteCheckpointer(Path(tmpdir) / "hw2_hitl.db")
    graph = AdvancedStateGraph()
    graph.add_node("draft", lambda s: {"draft": f"{s['topic']}（AI 初稿）"})
    graph.add_node(
        "publish",
        lambda s: {"published": True, "output": f"{s['draft']} - 审稿人:{s.get('reviewer')}"},
    )
    graph.set_entry_point("draft")
    graph.add_edge("draft", "publish")
    graph.add_edge("publish", END)

    app = graph.compile(checkpointer=cp, interrupt_before=["publish"])
    paused = app.invoke({"topic": "Q3 研发周报"}, thread_id="report-01")
    assert paused.status == "interrupted"
    assert paused.interrupted_at == "publish"

    resumed = app.resume(
        "report-01",
        updated_state={"approved": True, "reviewer": "林晓", "draft": "Q3 研发周报（终审版）"},
    )
    assert resumed.status == "completed"
    assert resumed.state["published"] is True
    assert resumed.state["output"] == "Q3 研发周报（终审版） - 审稿人:林晓"
    print("作业二校验通过！发布结果:", resumed.state["output"])
```

---

## 作业三：节点级 `RetryPolicy` 指数退避重试与异常白名单验证
**题目**：外部大模型接口常出现偶发性 `TimeoutError`，但如果是业务逻辑错误 `ValueError` 则不应盲目重试。请你：
1. 配置一个 `RetryPolicy(max_retries=2, initial_delay_s=0.005, backoff_factor=2.0, retry_on=(TimeoutError,))`。
2. 使用 `execute_with_retry` 测试一个前 2 次抛出 `TimeoutError`、第 3 次返回 `"success"` 的函数，断言返回 `"success"` 且尝试次数为 `3`。
3. 测试当函数抛出 `ValueError("参数非法")` 时，`execute_with_retry` 不会触发重试，而是在第 1 次尝试后立即向上抛出异常。

### 参考答案：
```python
from zhishu_agent import RetryPolicy, execute_with_retry

policy = RetryPolicy(
    max_retries=2,
    initial_delay_s=0.005,
    backoff_factor=2.0,
    retry_on=(TimeoutError,),
)

# 1. 瞬时 TimeoutError 自动重试并恢复
state = {"n": 0}
def flaky_api() -> str:
    state["n"] += 1
    if state["n"] < 3:
        raise TimeoutError("gateway timeout")
    return "success"

result, attempts = execute_with_retry(flaky_api, policy)
assert result == "success" and attempts == 3

# 2. 非白名单异常 ValueError 立即失败，不浪费重试配额
bad_calls = {"n": 0}
def invalid_param_api() -> str:
    bad_calls["n"] += 1
    raise ValueError("参数非法")

try:
    execute_with_retry(invalid_param_api, policy)
    raise AssertionError("预期应抛出 ValueError")
except ValueError:
    assert bad_calls["n"] == 1

print("作业三校验通过！瞬时重试次数:", attempts, "| 非白名单异常尝试次数:", bad_calls["n"])
```
