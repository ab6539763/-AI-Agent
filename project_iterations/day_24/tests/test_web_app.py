"""Day 24 自动化单元测试：覆盖 SQLite 持久化、CORS、SSE 流式接口与前端页面服务。"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.database import ChatDatabase
from zhishu_agent.web_app import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """使用临时 SQLite 数据库构建隔离的 FastAPI TestClient。"""
    db_file = tmp_path / "test_chat.db"
    app = create_app(db_path=db_file, frontend_dir=DAY_DIR / "frontend")
    return TestClient(app)


def test_database_crud_and_persistence(tmp_path: Path) -> None:
    """验证 ChatDatabase 的初始化、写入、历史查询、会话列表与清空功能。"""
    db_file = tmp_path / "unit_db.sqlite"
    db = ChatDatabase(db_file)

    msg1 = db.save_message("s1", "user", "你好，智枢")
    msg2 = db.save_message("s1", "assistant", "您好！我是智枢企业级智能体。")
    assert msg1 > 0 and msg2 > msg1

    history = db.get_history("s1")
    assert len(history) == 2
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "你好，智枢"

    sessions = db.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s1"
    assert sessions[0]["message_count"] == 2

    # 重新实例化 ChatDatabase 验证真实落盘持久化
    db_reloaded = ChatDatabase(db_file)
    assert len(db_reloaded.get_history("s1")) == 2

    assert db_reloaded.clear_session("s1") is True
    assert db_reloaded.clear_session("s1") is False
    assert db_reloaded.get_history("s1") == []


def test_database_validation(tmp_path: Path) -> None:
    """验证非法角色或空 session_id 会被拦截。"""
    db = ChatDatabase(tmp_path / "validate.db")
    with pytest.raises(ValueError):
        db.save_message("s1", "hacker", "bad")
    with pytest.raises(ValueError):
        db.save_message("   ", "user", "bad")


def test_frontend_serving_and_health(client: TestClient) -> None:
    """验证 GET / 返回前端 HTML5 页面，且包含 ReadableStream SSE 消费逻辑。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ReadableStream" in resp.text or "getReader()" in resp.text
    assert "/api/v1/chat/stream" in resp.text

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "v0.2.0-day24"


def test_cors_headers_and_preflight(client: TestClient) -> None:
    """验证 CORSMiddleware 正确注入跨域响应头并放行 OPTIONS 预检请求。"""
    preflight = client.options(
        "/api/v1/chat/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"

    resp = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_sse_streaming_and_sqlite_persistence(client: TestClient) -> None:
    """验证 POST /api/v1/chat/stream SSE 分块输出，以及多轮对话写入 SQLite。"""
    session_id = "sse-test-session"
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"session_id": session_id, "message": "请解释 SSE 流式输出原理", "delay_ms": 0},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    deltas = [e["content"] for e in events if e["type"] == "delta"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(deltas) >= 2
    assert len(done_events) == 1
    assembled = "".join(deltas)
    assert assembled == done_events[0]["full_content"]
    assert "SSE" in assembled

    # 验证用户提问与助手完整回复均已持久化至 SQLite
    history_resp = client.get(f"/api/v1/sessions/{session_id}/history")
    assert history_resp.status_code == 200
    messages = history_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "请解释 SSE 流式输出原理"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == assembled

    # 验证清空会话接口
    del_resp = client.delete(f"/api/v1/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    after_del = client.get(f"/api/v1/sessions/{session_id}/history")
    assert after_del.json()["messages"] == []
