# Day 49 课后作业与参考答案

## 作业一：基于 `TestClient` 验证低风险直通与高风险 HITL 中断
**题目**：使用 `FastAPI` 的 `TestClient` 与 `create_app(db_path=...)` 启动隔离实例，分别测试以下两类指令：
1. 发送 `"查询公司 2026 年假与报销制度"` 到 `POST /api/v1/office/run`，断言返回 `status == "completed"` 且 `pending_action is None`。
2. 发送 `"发送全员邮件通知周六凌晨停机维护"` 到 `POST /api/v1/office/run`，断言返回 `status == "awaiting_approval"`，且 `pending_action["action_type"] == "send_email"`。

### 参考答案：
```python
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.office_web_app import create_app

with tempfile.TemporaryDirectory() as tmp:
    app = create_app(db_path=Path(tmp) / "hw1.db")
    client = TestClient(app)

    # 1. 低风险只读检索直接完成
    r1 = client.post("/api/v1/office/run", json={"task": "查询公司 2026 年假与报销制度"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "completed"
    assert r1.json()["pending_action"] is None

    # 2. 高风险发邮件触发 HITL 中断
    r2 = client.post("/api/v1/office/run", json={"task": "发送全员邮件通知周六凌晨停机维护"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "awaiting_approval"
    assert body2["pending_action"]["action_type"] == "send_email"
    print("作业一校验通过！挂起线程:", body2["thread_id"])
```

---

## 作业二：HITL 人工批准微调（`edited_payload`）与重复审批 `409` 防护
**题目**：在上一题触发 `awaiting_approval` 的基础上：
1. 调用 `POST /api/v1/office/resume`，传入 `approved=True`、`comment="核准发送"` 以及 `edited_payload={"subject": "【运维公告】周六停机维护"}`。
2. 断言返回 `status == "completed"`、`resolved_action["payload"]["subject"] == "【运维公告】周六停机维护"`。
3. 再次对同一 `thread_id` 调用 `POST /api/v1/office/resume`，断言返回 HTTP `409 Conflict`。

### 参考答案：
```python
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.office_web_app import create_app

with tempfile.TemporaryDirectory() as tmp:
    app = create_app(db_path=Path(tmp) / "hw2.db")
    client = TestClient(app)

    run_res = client.post("/api/v1/office/run", json={"task": "发送全员邮件通知周六停机"})
    tid = run_res.json()["thread_id"]

    resumed = client.post(
        "/api/v1/office/resume",
        json={
            "thread_id": tid,
            "approved": True,
            "comment": "核准发送",
            "edited_payload": {"subject": "【运维公告】周六停机维护"},
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["resolved_action"]["payload"]["subject"] == "【运维公告】周六停机维护"

    # 防重入校验
    dup = client.post("/api/v1/office/resume", json={"thread_id": tid, "approved": True})
    assert dup.status_code == 409
    print("作业二校验通过！409 状态机防重入生效。")
```

---

## 作业三：人工拒绝拦截与跨实例 SQLite 检查点恢复
**题目**：验证即使在任务挂起后重建一个新的 `create_app(db_path=...)` 实例（模拟服务重启），依然能通过 `GET /api/v1/office/threads/{thread_id}` 查询到挂起状态，并通过 `approved=False` 完成安全拦截（`status == "rejected"`）。

### 参考答案：
```python
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.office_web_app import create_app

with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "persist.db"

    # 实例 1：发起报销审批任务并挂起
    client1 = TestClient(create_app(db_path=db_path))
    tid = client1.post("/api/v1/office/run", json={"task": "审批李明差旅报销 1800 元"}).json()["thread_id"]

    # 实例 2：模拟服务重启后使用同一 db_path 恢复
    client2 = TestClient(create_app(db_path=db_path))
    state = client2.get(f"/api/v1/office/threads/{tid}").json()
    assert state["status"] == "awaiting_approval"

    rejected = client2.post(
        "/api/v1/office/resume",
        json={"thread_id": tid, "approved": False, "comment": "预算超标，退回修改"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    print("作业三校验通过！跨实例恢复与拒绝拦截成功。")
```
