"""Day 24 SQLite 持久化仓储模块：负责会话与多轮对话历史存储。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_ROLES = {"system", "user", "assistant", "tool"}


def _utc_now_iso() -> str:
    """返回标准 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


class ChatDatabase:
    """基于 Python 标准库 sqlite3 的企业级对话持久化仓储。"""

    def __init__(self, db_path: str | Path = "data/zhishu_chat.db") -> None:
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
        """初始化 sessions 与 messages 两张核心表及索引。"""
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
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id, id);
                """
            )
            conn.commit()

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        title: str | None = None,
    ) -> int:
        """保存单条消息并自动创建或刷新对应会话记录，返回消息自增 ID。"""
        if not session_id or not session_id.strip():
            raise ValueError("session_id 不能为空")
        if role not in VALID_ROLES:
            raise ValueError(f"非法角色 '{role}'，必须属于 {sorted(VALID_ROLES)}")

        now = _utc_now_iso()
        default_title = title or (content.strip()[:24] if role == "user" and content.strip() else "新对话")

        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?;",
                (session_id,),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (session_id, default_title, now, now),
                )
            else:
                if title:
                    conn.execute(
                        "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?;",
                        (title, now, session_id),
                    )
                else:
                    conn.execute(
                        "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                        (now, session_id),
                    )

            cursor = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (session_id, role, content, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_history(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """按时间正序读取指定会话的历史消息列表。"""
        with self._get_conn() as conn:
            if limit is not None and limit > 0:
                rows = conn.execute(
                    """
                    SELECT id, session_id, role, content, created_at
                    FROM (
                        SELECT id, session_id, role, content, created_at
                        FROM messages
                        WHERE session_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    ORDER BY id ASC;
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, session_id, role, content, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC;
                    """,
                    (session_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话及其消息数量，按最近更新时间倒序排列。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC, s.rowid DESC;
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_session(self, session_id: str) -> bool:
        """删除指定会话及其全部消息记录，返回是否实际删除了记录。"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
            conn.commit()
            return cursor.rowcount > 0
