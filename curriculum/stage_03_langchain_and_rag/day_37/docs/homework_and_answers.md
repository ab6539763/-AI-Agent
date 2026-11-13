# Day 37 课后作业与参考答案

## 作业一：使用 `TestClient` 解析全栈知识库 SSE 事件流（`token` + `citations` + `done`）
**题目**：在将企业知识库接口接入前端之前，后端工程师需要编写自动化脚本验证 SSE 协议格式是否正确。请你使用 `fastapi.testclient.TestClient` 和临时目录 `tempfile.TemporaryDirectory()`：
1. 调用 `create_app(db_path=...)` 创建隔离的测试应用实例。
2. 通过 `POST /api/v1/kb/upload` 上传一份名为 `security_policy.md` 的文档，内容为：`"星辰数科安全规范：生产数据库密码必须每90天轮换一次，禁止在代码仓库中硬编码密钥。"`。
3. 使用 `client.stream("POST", "/api/v1/kb/chat/stream", ...)` 提问 `"生产数据库密码多久轮换一次？"`。
4. 解析所有 `data: {...}` 事件，分别断言 `token` 拼接后的完整回答包含 `"90天"`，且 `citations` 事件中包含 `security_policy.md`。

### 参考答案：
```python
import json
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.kb_web_app import create_app

with tempfile.TemporaryDirectory() as tmpdir:
    app = create_app(db_path=Path(tmpdir) / "hw1.db")
    client = TestClient(app)

    upload_res = client.post(
        "/api/v1/kb/upload",
        json={
            "filename": "security_policy.md",
            "content": "星辰数科安全规范：生产数据库密码必须每90天轮换一次，禁止在代码仓库中硬编码密钥。",
        },
    )
    assert upload_res.status_code == 200

    with client.stream(
        "POST",
        "/api/v1/kb/chat/stream",
        json={"session_id": "hw1-sess", "message": "生产数据库密码多久轮换一次？", "delay_ms": 0},
    ) as resp:
        raw = "".join(resp.iter_text())

    events = [
        json.loads(block.strip()[6:])
        for block in raw.split("\n\n")
        if block.strip().startswith("data: ")
    ]
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    citations = next(e["citations"] for e in events if e["type"] == "citations")

    assert "90天" in answer
    assert citations[0]["filename"] == "security_policy.md"
    print("完整回答:", answer)
    print("引用卡片:", citations)
```

---

## 作业二：验证多轮对话追问与 SQLite 引用卡片持久化恢复
**题目**：企业员工在知识库中常会进行连续追问（例如先问“差旅报销标准是什么？”，再追问“那二线城市呢？”），并且希望刷新页面后仍能看到历史回答和对应的引用卡片。请编写测试代码：
1. 上传包含一、二线城市住宿报销标准的文档。
2. 在同一个 `session_id` 下连续发起两轮 `POST /api/v1/kb/chat/stream` 请求。
3. 调用 `GET /api/v1/kb/sessions/{session_id}/history`，验证返回 4 条消息，且每条 `assistant` 消息的 `citations` 列表均非空。
4. 使用同一 `db_path` 重新调用 `create_app()` 模拟服务重启，确认文档数量与历史消息均完整保留。

### 参考答案：
```python
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from zhishu_agent.kb_web_app import create_app

with tempfile.TemporaryDirectory() as tmpdir:
    db_file = Path(tmpdir) / "hw2.db"
    client = TestClient(create_app(db_path=db_file))

    client.post(
        "/api/v1/kb/upload",
        json={
            "filename": "travel_policy.md",
            "content": "差旅住宿报销标准：一线城市每晚上限600元，二线城市每晚上限450元，需附电子发票。",
        },
    )

    client.post("/api/v1/kb/chat/stream", json={"session_id": "s-travel", "message": "差旅住宿报销标准是什么？", "delay_ms": 0})
    client.post("/api/v1/kb/chat/stream", json={"session_id": "s-travel", "message": "那二线城市呢？", "delay_ms": 0})

    history = client.get("/api/v1/kb/sessions/s-travel/history").json()["messages"]
    assert len(history) == 4
    assert len(history[1]["citations"]) >= 1
    assert len(history[3]["citations"]) >= 1

    # 模拟服务重启后恢复
    reloaded_client = TestClient(create_app(db_path=db_file))
    assert len(reloaded_client.get("/api/v1/kb/documents").json()["documents"]) == 1
    assert len(reloaded_client.get("/api/v1/kb/sessions/s-travel/history").json()["messages"]) == 4
    print("重启恢复校验通过！消息数:", len(history))
```

---

## 作业三：CORS 跨域预检与前端引用卡片交互机制分析
**题目**：
1. 在前后端分离部署场景下（例如前端运行在 `http://localhost:5173`，后端运行在 `http://127.0.0.1:8000`），浏览器在发送 `POST /api/v1/kb/chat/stream`（`Content-Type: application/json`）前会自动触发什么 HTTP 请求？FastAPI 中是如何处理的？
2. 为什么前端消费 `POST /api/v1/kb/chat/stream` 时使用 `fetch() + response.body.getReader()`，而不是浏览器原生的 `new EventSource(url)`？

### 参考答案：
1. **CORS 预检请求（Preflight）**：由于请求方法为 `POST` 且携带 `application/json` 自定义头，浏览器会先发送 `OPTIONS /api/v1/kb/chat/stream` 预检请求，携带 `Origin` 和 `Access-Control-Request-Method` 头。FastAPI 通过 `CORSMiddleware` 拦截 `OPTIONS` 并返回 `200 OK` 及 `Access-Control-Allow-Origin: *` 等响应头，浏览器确认安全后才放行真正的 `POST` 流式请求。
2. **为什么不用 `EventSource`**：浏览器原生 `EventSource` 规范**仅支持 `GET` 请求**且无法自定义请求体（JSON Body）和请求头；而知识库问答需要通过 `POST` 提交长文本问题、`session_id` 和 `top_k` 参数，因此全栈工程实践统一采用 `fetch()` 配合 `ReadableStream` (`response.body.getReader()`) 手动解码 `data: {...}\n\n` 数据块。
