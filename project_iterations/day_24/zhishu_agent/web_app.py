"""Day 24 FastAPI Web 应用：SSE 流式输出 + CORS 跨域 + SQLite 持久化 + 前端静态页面。"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from zhishu_agent.database import ChatDatabase

DEFAULT_DAY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_DIR = DEFAULT_DAY_DIR / "frontend"
DEFAULT_DB_PATH = DEFAULT_DAY_DIR / "data" / "zhishu_chat.db"


class ChatStreamRequest(BaseModel):
    """流式对话请求体校验模型。"""

    session_id: str = Field(..., min_length=1, max_length=128, description="会话唯一标识")
    message: str = Field(..., min_length=1, max_length=8000, description="用户输入内容")
    delay_ms: int = Field(default=15, ge=0, le=500, description="打字机分块延迟（毫秒）")


def _generate_assistant_reply(message: str, history: list[dict[str, Any]]) -> str:
    """离线智能回复生成器（支持上下文轮次感知，免 API Key 确定性运行）。"""
    turn_index = sum(1 for item in history if item.get("role") == "user") + 1
    cleaned = message.strip()
    lower = cleaned.lower()

    if "sse" in lower or "流式" in cleaned:
        return (
            f"【智枢平台 · 第 {turn_index} 轮回复】\n"
            "SSE（Server-Sent Events）基于标准 HTTP 长连接与 `text/event-stream` 协议，"
            "由后端通过 `StreamingResponse` 逐块推送 `data: {...}\\n\\n` 事件，"
            "前端再借助 `fetch()` + `response.body.getReader()` 实现逐字打字机渲染。"
        )
    if "sqlite" in lower or "持久化" in cleaned or "数据库" in cleaned:
        return (
            f"【智枢平台 · 第 {turn_index} 轮回复】\n"
            "当前对话已接入 SQLite 持久化仓储（`ChatDatabase`）："
            "用户提问与助手完整回复均会写入 `sessions` 与 `messages` 表，"
            "刷新浏览器或重启服务后仍可通过 `/api/v1/sessions/{session_id}/history` 恢复上下文。"
        )
    if "cors" in lower or "跨域" in cleaned:
        return (
            f"【智枢平台 · 第 {turn_index} 轮回复】\n"
            "FastAPI 通过 `CORSMiddleware` 注入 `Access-Control-Allow-Origin` 等响应头，"
            "解决前后端分离部署时浏览器同源策略（SOP）拦截预检请求（OPTIONS）与流式接口的问题。"
        )
    return (
        f"【智枢企业级智能体 · 第 {turn_index} 轮回复】\n"
        f"已收到您的指令：「{cleaned}」。\n"
        "当前运行于 FastAPI SSE 流式通道 + SQLite 本地持久化模式，"
        "历史消息已自动归档，您可以继续追问或切换左侧会话。"
    )


def _chunk_text(text: str, chunk_size: int = 4) -> list[str]:
    """将完整回复切分为适合打字机逐字渲染的小片段。"""
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def create_app(
    db_path: str | Path | None = None,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    """构建并配置 Day 24 FastAPI 应用实例。"""
    resolved_db = Path(db_path or os.getenv("ZHISHU_DB_PATH") or DEFAULT_DB_PATH)
    resolved_frontend = Path(frontend_dir or DEFAULT_FRONTEND_DIR)

    db = ChatDatabase(resolved_db)

    application = FastAPI(
        title="智枢企业级智能体平台 API",
        description="Day 24 全栈 Web ChatGPT 克隆版：FastAPI SSE 流式输出 + CORS + SQLite 持久化",
        version="v0.2.0-day24",
    )

    # 配置 CORS 中间件，允许前端跨域调试与流式读取
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载仓储实例以便测试与诊断访问
    application.state.db = db

    @application.get("/", response_class=HTMLResponse, tags=["Frontend"])
    async def serve_frontend() -> HTMLResponse:
        """返回 Web ChatGPT 克隆版单页前端应用。"""
        index_file = resolved_frontend / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="前端页面 frontend/index.html 不存在")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @application.get("/api/v1/health", tags=["System"])
    async def health_check() -> dict[str, str]:
        """服务健康检查端点。"""
        return {
            "status": "ok",
            "version": "v0.2.0-day24",
            "db_path": str(db.db_path),
        }

    @application.get("/api/v1/sessions", tags=["Sessions"])
    async def list_sessions() -> dict[str, Any]:
        """获取全部历史会话摘要列表。"""
        return {"sessions": db.list_sessions()}

    @application.get("/api/v1/sessions/{session_id}/history", tags=["Sessions"])
    async def get_session_history(session_id: str) -> dict[str, Any]:
        """查询指定会话的完整多轮对话历史。"""
        messages = db.get_history(session_id)
        return {"session_id": session_id, "messages": messages}

    @application.delete("/api/v1/sessions/{session_id}", tags=["Sessions"])
    async def delete_session(session_id: str) -> dict[str, Any]:
        """清空并删除指定会话及其消息历史。"""
        deleted = db.clear_session(session_id)
        return {"session_id": session_id, "deleted": deleted}

    @application.post("/api/v1/chat/stream", tags=["Chat"])
    async def chat_stream(payload: ChatStreamRequest) -> StreamingResponse:
        """SSE 流式对话端点：先落库用户消息，再逐块推送回复，最后落库助手消息。"""
        history = db.get_history(payload.session_id)
        db.save_message(payload.session_id, "user", payload.message)
        full_reply = _generate_assistant_reply(payload.message, history)

        async def event_stream() -> AsyncIterator[str]:
            for chunk in _chunk_text(full_reply, chunk_size=4):
                event_payload = json.dumps(
                    {"type": "delta", "content": chunk},
                    ensure_ascii=False,
                )
                yield f"data: {event_payload}\n\n"
                if payload.delay_ms > 0:
                    await asyncio.sleep(payload.delay_ms / 1000.0)

            msg_id = db.save_message(payload.session_id, "assistant", full_reply)
            done_payload = json.dumps(
                {
                    "type": "done",
                    "session_id": payload.session_id,
                    "message_id": msg_id,
                    "full_content": full_reply,
                },
                ensure_ascii=False,
            )
            yield f"data: {done_payload}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return application


app = create_app()
