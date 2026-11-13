# Day 62 课后作业与参考答案

## 作业一：为什么 `POST` SSE 接口需要前端使用 `fetch` + `ReadableStream` 而不是 `EventSource`？
**题目**：在智枢全栈分析台中，`POST /api/v1/capstone/chat/stream` 采用 `text/event-stream` 返回流式数据。请说明：
1. 为什么不能直接使用浏览器原生 `new EventSource(url)` 对接该接口？
2. 服务端响应头中 `X-Accel-Buffering: no` 与 `Cache-Control: no-cache` 分别解决什么生产环境问题？

### 参考答案：
1. **不能使用 `EventSource` 的原因**：
   - W3C `EventSource` 规范仅支持 `HTTP GET` 方法，不支持 `POST` 请求体（JSON Payload），也不支持自定义 `Authorization` 等请求头。
   - 若把长段财报分析提示词拼在 URL QueryString 中，会受限于 URL 长度上限，且容易将敏感业务参数暴露在网关/代理访问日志中。
   - 因此前端采用 `fetch('/api/v1/capstone/chat/stream', { method: 'POST', ... })` 配合 `response.body.getReader()` + `TextDecoder` 按 `\n\n` 分帧解析 `event:` 与 `data:`。
2. **关键响应头的工程意义**：
   - `Cache-Control: no-cache`：防止中间代理或浏览器缓存流式分片。
   - `X-Accel-Buffering: no`：通知 Nginx/Ingress 网关关闭响应缓冲，确保后端每 `yield` 一帧 SSE 数据就能毫秒级推送到浏览器，避免“攒够一整包才一次性吐出”的假卡顿现象。

---

## 作业二：HITL 人工审批状态机与幂等防重放设计
**题目**：在 `CapstoneStore.resolve_approval` 中，如果同一张 `approval_id` 被两个审批人（或前端连点两次）同时提交 `POST /api/v1/capstone/approve`，系统应当如何保证状态一致？请写出核心校验逻辑与对应的 HTTP 状态码。

### 参考答案：
1. **核心状态机规则**：
   - 审批单初始状态必须为 `pending`，仅允许单向流转为 `approved` 或 `rejected`（终态不可逆）。
   - 在 `resolve_approval` 中先查询当前 `status`：
     - 若记录不存在，抛出 `ApprovalNotFoundError`，FastAPI 映射为 **`404 Not Found`**；
     - 若 `row["status"] != "pending"`，抛出 `InvalidApprovalStateError`，FastAPI 映射为 **`409 Conflict`**。
2. **参考代码片段**：
   ```python
   if row is None:
       raise ApprovalNotFoundError(f"Approval '{approval_id}' not found")
   if row["status"] != "pending":
       raise InvalidApprovalStateError(
           f"Approval '{approval_id}' is already '{row['status']}'"
       )
   ```

---

## 作业三：使用 `TestClient` 端到端验证 SSE + SQLite 持久化
**题目**：请编写一段不启动外部端口的 Python 测试代码，使用 `fastapi.testclient.TestClient` 和 `tmp_path` 临时数据库：
1. 调用 `POST /api/v1/capstone/chat/stream` 触发一次高风险“资金划拨”请求；
2. 解析返回的 SSE 帧，提取 `hitl_required` 中的 `approval_id`；
3. 调用 `POST /api/v1/capstone/approve` 完成批准，并通过 `GET /api/v1/capstone/history/{session_id}` 验证 SQLite 中共有 3 条消息记录。

### 参考答案：
```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.capstone_web import create_app

def test_e2e_sse_and_hitl(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "hw.db")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/capstone/chat/stream",
        json={"query": "申请划拨 10 万元研发资金", "session_id": "sess-hw-1"},
    ) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())

    approval_id = None
    for frame in raw.strip().split("\n\n"):
        lines = frame.splitlines()
        if any(l == "event: hitl_required" for l in lines):
            data_line = next(l for l in lines if l.startswith("data:"))
            approval_id = json.loads(data_line[5:].strip())["approval_id"]

    assert approval_id is not None
    res = client.post(
        "/api/v1/capstone/approve",
        json={"approval_id": approval_id, "approved": True, "reviewer": "CFO"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    hist = client.get("/api/v1/capstone/history/sess-hw-1").json()
    assert len(hist["messages"]) == 3
```
