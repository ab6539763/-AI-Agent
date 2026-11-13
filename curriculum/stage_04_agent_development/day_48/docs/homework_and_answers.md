# Day 48 课后作业与参考答案

## 作业一：6 大企业办公工具调用与草稿-发送状态联动
**题目**：在智能办公助手中，所有外部写操作都应有迹可循。请你基于 `OfficeWorkspace` 与 `create_default_tools` 完成以下验证：
1. 调用 `list_calendar(date="2026-11-16")`，确认初始有 2 场会议。
2. 调用 `search_company_docs(query="Q4 AI 战略", top_k=2)` 与 `web_search(query="HITL", top_k=1)`，确认均能返回命中结果。
3. 先调用 `draft_email` 起草一封主题为 `"周报同步"` 的草稿并获取 `draft_id`，再将该 `draft_id` 传入 `send_email` 完成发送，断言 `workspace.email_drafts[0]["status"] == "sent"` 且 `len(workspace.sent_emails) == 1`。

### 参考答案：
```python
from zhishu_agent import OfficeWorkspace, create_default_tools

ws = OfficeWorkspace()
tools = create_default_tools(ws)

assert tools["list_calendar"].invoke(date="2026-11-16")["count"] == 2
assert tools["search_company_docs"].invoke(query="Q4 AI 战略", top_k=2)["count"] >= 1
assert tools["web_search"].invoke(query="HITL", top_k=1)["count"] >= 1

draft_res = tools["draft_email"].invoke(
    to=["team@zhishu.cn"],
    subject="周报同步",
    body="本周已完成多 Agent 核心编排模块开发。",
)
draft_id = draft_res["draft"]["draft_id"]

send_res = tools["send_email"].invoke(
    to=["team@zhishu.cn"],
    subject="周报同步",
    body="本周已完成多 Agent 核心编排模块开发。",
    draft_id=draft_id,
)
assert send_res["status"] == "sent"
assert ws.email_drafts[0]["status"] == "sent"
assert len(ws.sent_emails) == 1
print("作业一校验通过！已发送邮件 ID:", send_res["email"]["email_id"])
```

---

## 作业二：多 Agent 协同编排与 `SQLiteCheckpointer` 跨实例断点恢复
**题目**：为了验证智能办公助手在服务重启后依然能精准恢复人工审批流程，请你使用 `OfficeSupervisor` 完成以下验证：
1. 使用临时路径 `db_path` 初始化 `SQLiteCheckpointer(db_path)`，并设置 `interrupt_before={"create_meeting", "send_email"}`。
2. 发起请求 `"请调研 Q4 战略文档，预约会议并发送邮件通知"`（`thread_id="hw-thread-01"`），断言返回 `status == "interrupted"` 且挂起工具为 `"create_meeting"`。
3. **重新实例化**一个新的 `OfficeSupervisor`（连接同一个 `db_path` 与 `ws`），调用 `resume("hw-thread-01", approved=True, modified_args={"start_time": "15:30"})`，断言进入第二个中断 `"send_email"`，且会议已按修改后的 `"15:30"` 创建。
4. 再次调用 `resume("hw-thread-01", approved=True)`，断言最终 `status == "completed"`。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import OfficeSupervisor, OfficeWorkspace, SQLiteCheckpointer

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "hw_ckpt.db"
    ws = OfficeWorkspace()

    sup1 = OfficeSupervisor(
        workspace=ws,
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before={"create_meeting", "send_email"},
    )
    r1 = sup1.run("请调研 Q4 战略文档，预约会议并发送邮件通知", thread_id="hw-thread-01")
    assert r1["status"] == "interrupted"
    assert r1["pending_action"]["tool_name"] == "create_meeting"

    # 模拟服务重启后新建 Supervisor 实例
    sup2 = OfficeSupervisor(
        workspace=ws,
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before={"create_meeting", "send_email"},
    )
    r2 = sup2.resume("hw-thread-01", approved=True, modified_args={"start_time": "15:30"})
    assert r2["status"] == "interrupted"
    assert r2["pending_action"]["tool_name"] == "send_email"
    assert ws.calendar_events[-1]["start_time"] == "15:30"

    r3 = sup2.resume("hw-thread-01", approved=True)
    assert r3["status"] == "completed"
    print("作业二校验通过！检查点总数:", len(sup2.get_history("hw-thread-01")))
```

---

## 作业三：高危操作人工拒绝（`approved=False`）与状态保护
**题目**：当审批人发现邮件内容或收件人不合规时，需要安全拒绝执行且防止重复恢复。请你验证：
1. 对 `"请发送邮件通知全员"` 执行 `run(..., thread_id="hw-reject")`，确认在 `send_email` 前中断。
2. 调用 `resume("hw-reject", approved=False, feedback="内容需补充预算明细")`，断言返回 `status == "rejected"` 且 `workspace.sent_emails` 为空。
3. 尝试再次对 `"hw-reject"` 调用 `resume(...)`，确认抛出 `ValueError`。

### 参考答案：
```python
from zhishu_agent import OfficeSupervisor, OfficeWorkspace, SQLiteCheckpointer

ws = OfficeWorkspace()
sup = OfficeSupervisor(
    workspace=ws,
    checkpointer=SQLiteCheckpointer(":memory:"),
    interrupt_before={"send_email"},
)

r1 = sup.run("请发送邮件通知全员", thread_id="hw-reject")
assert r1["status"] == "interrupted"

r2 = sup.resume("hw-reject", approved=False, feedback="内容需补充预算明细")
assert r2["status"] == "rejected"
assert len(ws.sent_emails) == 0

try:
    sup.resume("hw-reject", approved=True)
    raise AssertionError("预期应抛出 ValueError")
except ValueError as exc:
    print("作业三校验通过！捕获重复恢复异常:", exc)
```
