# Day 24 课后作业与参考答案

## 作业一：使用 FastAPI `StreamingResponse` 实现标准 SSE 倒计时流
**题目**：大模型流式输出之所以能实现“打字机效果”，核心在于后端遵循 Server-Sent Events（SSE）协议。请你使用 FastAPI 的 `StreamingResponse` 编写一个 `GET /api/v1/countdown/{seconds}` 接口：
1. `media_type` 必须设置为 `"text/event-stream"`。
2. 通过异步生成器 `async def event_gen()` 从 `seconds` 倒数到 `1`，每条事件严格按照 `data: {"remaining": n}\n\n` 格式推送。
3. 倒数结束后，额外推送一条 `data: {"type": "done"}\n\n` 结束信号。

### 参考答案：
```python
import asyncio
import json
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.get("/api/v1/countdown/{seconds}")
async def countdown_sse(seconds: int) -> StreamingResponse:
    async def event_gen() -> AsyncIterator[str]:
        for remaining in range(seconds, 0, -1):
            payload = json.dumps({"remaining": remaining}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.05)
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

---

## 作业二：SQLite 多轮对话历史 CRUD 与上下文窗口截断
**题目**：在实际企业智能体中，一个会话可能累积数百条消息，直接全部喂给大模型会超出 Token 上限。请基于 Day 24 的 `ChatDatabase`：
1. 演示向会话 `"ops-001"` 写入 4 条消息（2 轮 user/assistant 对话）。
2. 调用 `get_history("ops-001", limit=2)`，验证返回的永远是**最近 2 条消息**且保持**时间正序（user 在前、assistant 在后）**，并解释 SQL 子查询为什么需要外层再 `ORDER BY id ASC`。

### 参考答案：
```python
from pathlib import Path
from zhishu_agent.database import ChatDatabase

db = ChatDatabase(Path("/tmp/homework_chat.db"))
db.clear_session("ops-001")

db.save_message("ops-001", "user", "第一轮提问：服务器 CPU 过高怎么办？")
db.save_message("ops-001", "assistant", "第一轮回复：请先用 top 或 htop 定位高占用进程。")
db.save_message("ops-001", "user", "第二轮提问：确认是 Python 进程，如何排查？")
db.save_message("ops-001", "assistant", "第二轮回复：可使用 py-spy dump 抓取火焰图。")

recent = db.get_history("ops-001", limit=2)
for msg in recent:
    print(f"[{msg['role']}] {msg['content']}")
```
**原理解析**：SQLite 中要取“最近 N 条”，内层子查询必须按 `ORDER BY id DESC LIMIT N` 倒序截断；但如果直接返回内层结果，消息顺序会变成“助手在前、用户在后”，违背大模型对话协议。因此外层必须再包裹一层 `ORDER BY id ASC` 将其恢复为正常时间正序。

---

## 作业三：CORS 跨域中间件配置与浏览器预检（Preflight）原理
**题目**：当你的前端运行在 `http://localhost:5173`（Vite），而 FastAPI 后端运行在 `http://127.0.0.1:8000` 时，浏览器发起 `POST /api/v1/chat/stream`（携带 `Content-Type: application/json`）会被拦截并报错 `No 'Access-Control-Allow-Origin' header is present`。请回答：
1. 为什么浏览器在发送 `POST` 之前会先自动发送一个 `OPTIONS` 请求？
2. 在 FastAPI 中如何配置 `CORSMiddleware` 仅允许 `http://localhost:5173` 跨域访问，同时允许携带 Cookie 凭证（`allow_credentials=True`）？为什么此时不能再将 `allow_origins` 设为 `["*"]`？

### 参考答案：
1. **预检请求（Preflight）原理**：因为 `POST` 请求携带了 `application/json` 请求头，属于浏览器定义中的“非简单请求”。出于同源策略（SOP）安全保护，浏览器必须先发一次 `OPTIONS` 预检请求询问服务器是否允许该 `Origin` 和 `Method`，收到服务器返回的 `200 OK` 及 `Access-Control-Allow-*` 响应头后，才会真正发送 `POST` 请求。
2. **FastAPI 安全配置**：
   ```python
   from fastapi.middleware.cors import CORSMiddleware

   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:5173"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```
   **注意**：根据 W3C CORS 规范，当 `allow_credentials=True`（允许携带 Cookie / Authorization 凭证）时，响应头 `Access-Control-Allow-Origin` **禁止使用通配符 `*`**，必须明确指定具体的可信域名列表，否则浏览器会直接拒绝接收响应。
