"""Day 37 FastAPI 全栈企业知识库问答应用：SSE 流式输出 + 引用卡片 + SQLite 持久化。"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from zhishu_agent.kb_service import KnowledgeBaseService

DEFAULT_DAY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_DIR = DEFAULT_DAY_DIR / "frontend"
DEFAULT_DB_PATH = DEFAULT_DAY_DIR / "data" / "zhishu_kb.db"

VALID_ROLES = {"system", "user", "assistant", "tool"}


def _utc_now_iso() -> str:
    """返回标准 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


class KBDatabase:
    """基于 SQLite 的知识库文档与多轮引用对话持久化仓储。"""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """初始化 sessions、messages 与 kb_documents 三张核心表。"""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kb_messages_session_id
                ON messages(session_id, id);
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_documents (
                    doc_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    char_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_document(
        self,
        doc_id: str,
        filename: str,
        content: str,
        chunk_count: int,
        char_count: int,
        created_at: str,
    ) -> None:
        """持久化上传的知识库文档原文与元信息。"""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO kb_documents (doc_id, filename, content, chunk_count, char_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    filename = excluded.filename,
                    content = excluded.content,
                    chunk_count = excluded.chunk_count,
                    char_count = excluded.char_count,
                    created_at = excluded.created_at;
                """,
                (doc_id, filename, content, chunk_count, char_count, created_at),
            )

    def load_documents(self) -> list[dict[str, Any]]:
        """加载所有已持久化文档，供服务启动时重建索引。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT doc_id, filename, content, chunk_count, char_count, created_at FROM kb_documents ORDER BY created_at ASC;"
            ).fetchall()
        return [dict(row) for row in rows]

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> int:
        """写入一条对话消息及其关联引用列表，返回消息自增 ID。"""
        clean_sid = session_id.strip()
        if not clean_sid:
            raise ValueError("session_id 不能为空")
        if role not in VALID_ROLES:
            raise ValueError(f"非法角色: {role}")

        now = _utc_now_iso()
        citations_json = json.dumps(citations or [], ensure_ascii=False)

        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?;",
                (clean_sid,),
            ).fetchone()
            if existing is None:
                title = content.strip()[:32] or "新知识库会话"
                conn.execute(
                    "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                    (clean_sid, title, now, now),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                    (now, clean_sid),
                )

            cur = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (clean_sid, role, content, citations_json, now),
            )
            return int(cur.lastrowid)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """查询指定会话的完整历史记录（含引用卡片数据）。"""
        clean_sid = session_id.strip()
        if not clean_sid:
            return []
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, citations_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (clean_sid,),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                citations = json.loads(row["citations_json"] or "[]")
            except json.JSONDecodeError:
                citations = []
            results.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "citations": citations,
                    "created_at": row["created_at"],
                }
            )
        return results

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出全部会话摘要及消息条数。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC;
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_session(self, session_id: str) -> bool:
        """删除指定会话及其消息。"""
        clean_sid = session_id.strip()
        if not clean_sid:
            return False
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?;",
                (clean_sid,),
            )
            return cur.rowcount > 0


class UploadDocumentRequest(BaseModel):
    """知识库文档上传请求模型。"""

    filename: str = Field(..., min_length=1, max_length=256, description="文档文件名")
    content: str = Field(..., min_length=1, max_length=200000, description="文档文本内容")


class KBChatStreamRequest(BaseModel):
    """知识库流式问答请求模型。"""

    session_id: str = Field(..., min_length=1, max_length=128, description="会话唯一标识")
    message: str = Field(..., min_length=1, max_length=8000, description="用户提问内容")
    top_k: int = Field(default=3, ge=1, le=10, description="检索返回的最大引用片段数")
    delay_ms: int = Field(default=10, ge=0, le=500, description="打字机分块延迟（毫秒）")


def _chunk_tokens(text: str, chunk_size: int = 6) -> list[str]:
    """将完整回复切分为适合 SSE 逐块推送的 token 片段。"""
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def create_app(
    db_path: str | Path | None = None,
    frontend_dir: str | Path | None = None,
    kb_service: KnowledgeBaseService | None = None,
) -> FastAPI:
    """构建并配置 Day 37 企业级知识库问答 FastAPI 应用。"""
    resolved_db = Path(db_path or os.getenv("ZHISHU_KB_DB_PATH") or DEFAULT_DB_PATH)
    resolved_frontend = Path(frontend_dir or DEFAULT_FRONTEND_DIR)

    db = KBDatabase(resolved_db)
    kb = kb_service or KnowledgeBaseService()

    # 启动时从 SQLite 恢复已上传的知识库文档索引
    for doc_row in db.load_documents():
        kb.ingest_document(
            filename=doc_row["filename"],
            content=doc_row["content"],
            doc_id=doc_row["doc_id"],
            created_at=doc_row["created_at"],
        )

    application = FastAPI(
        title="智枢企业级知识库问答平台 API",
        description="Day 37 全栈项目：FastAPI + SSE 流式输出 + 引用卡片 + 多轮历史持久化",
        version="v0.3.0-day37",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.db = db
    application.state.kb = kb

    @application.get("/", response_class=HTMLResponse, tags=["Frontend"])
    async def serve_frontend() -> HTMLResponse:
        """返回企业知识库问答全栈前端页面。"""
        index_file = resolved_frontend / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="前端页面 frontend/index.html 不存在")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @application.get("/api/v1/health", tags=["System"])
    async def health_check() -> dict[str, Any]:
        """服务健康检查端点。"""
        return {
            "status": "ok",
            "version": "v0.3.0-day37",
            "db_path": str(db.db_path),
            "document_count": len(kb.list_documents()),
        }

    @application.post("/api/v1/kb/upload", tags=["KnowledgeBase"])
    async def upload_document(payload: UploadDocumentRequest) -> dict[str, Any]:
        """上传并索引企业知识库文档（持久化至 SQLite）。"""
        try:
            doc = kb.ingest_document(filename=payload.filename, content=payload.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        db.save_document(
            doc_id=doc.doc_id,
            filename=doc.filename,
            content=payload.content.strip(),
            chunk_count=doc.chunk_count,
            char_count=doc.char_count,
            created_at=doc.created_at,
        )
        return {"status": "uploaded", "document": doc.to_dict()}

    @application.get("/api/v1/kb/documents", tags=["KnowledgeBase"])
    async def list_documents() -> dict[str, Any]:
        """获取当前已入库的知识库文档列表。"""
        return {"documents": kb.list_documents()}

    @application.get("/api/v1/kb/sessions", tags=["Sessions"])
    async def list_sessions() -> dict[str, Any]:
        """获取全部知识库问答会话摘要。"""
        return {"sessions": db.list_sessions()}

    @application.get("/api/v1/kb/sessions/{session_id}/history", tags=["Sessions"])
    async def get_session_history(session_id: str) -> dict[str, Any]:
        """查询指定会话的多轮对话与引用卡片历史。"""
        messages = db.get_history(session_id)
        return {"session_id": session_id, "messages": messages}

    @application.delete("/api/v1/kb/sessions/{session_id}", tags=["Sessions"])
    async def delete_session(session_id: str) -> dict[str, Any]:
        """删除指定会话及全部历史记录。"""
        deleted = db.clear_session(session_id)
        return {"session_id": session_id, "deleted": deleted}

    @application.post("/api/v1/kb/chat/stream", tags=["KnowledgeBase"])
    async def kb_chat_stream(payload: KBChatStreamRequest) -> StreamingResponse:
        """SSE 流式知识库问答端点：逐块推送 token + 最终推送 citations 事件 + 落库历史。"""
        history = db.get_history(payload.session_id)
        db.save_message(payload.session_id, "user", payload.message)

        result = kb.answer_question(
            query=payload.message,
            history=history,
            top_k=payload.top_k,
        )
        citations_dicts = [c.to_dict() for c in result.citations]

        async def event_stream() -> AsyncIterator[str]:
            for token in _chunk_tokens(result.answer, chunk_size=6):
                token_event = json.dumps(
                    {"type": "token", "content": token},
                    ensure_ascii=False,
                )
                yield f"data: {token_event}\n\n"
                if payload.delay_ms > 0:
                    await asyncio.sleep(payload.delay_ms / 1000.0)

            citations_event = json.dumps(
                {"type": "citations", "citations": citations_dicts},
                ensure_ascii=False,
            )
            yield f"data: {citations_event}\n\n"

            msg_id = db.save_message(
                payload.session_id,
                "assistant",
                result.answer,
                citations=citations_dicts,
            )
            done_event = json.dumps(
                {
                    "type": "done",
                    "message_id": msg_id,
                    "session_id": payload.session_id,
                },
                ensure_ascii=False,
            )
            yield f"data: {done_event}\n\n"

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
