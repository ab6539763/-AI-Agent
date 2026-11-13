"""Day 37 自动化单元测试：覆盖知识库文档上传、CORS、SSE 流式引用问答、SQLite 持久化与前端页面。"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.kb_web_app import create_app


def _parse_sse_events(raw_text: str) -> list[dict]:
    """解析 SSE 响应文本中的 data: JSON 事件列表。"""
    events: list[dict] = []
    for block in raw_text.split("\n\n"):
        line = block.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.fixture()
def client_and_db(tmp_path: Path) -> tuple[TestClient, Path]:
    """使用临时 SQLite 数据库构建隔离的 FastAPI TestClient。"""
    db_file = tmp_path / "test_kb.db"
    app = create_app(db_path=db_file, frontend_dir=DAY_DIR / "frontend")
    return TestClient(app), db_file


def test_frontend_serving_and_health(client_and_db: tuple[TestClient, Path]) -> None:
    """验证 GET / 返回企业知识库前端页面，包含上传面板、SSE 流式消费与引用卡片逻辑。"""
    client, _ = client_and_db
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "/api/v1/kb/upload" in resp.text
    assert "/api/v1/kb/chat/stream" in resp.text
    assert "citation-card" in resp.text
    assert "getReader()" in resp.text

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["version"] == "v0.3.0-day37"


def test_cors_preflight_headers(client_and_db: tuple[TestClient, Path]) -> None:
    """验证 CORSMiddleware 正确放行 OPTIONS 预检请求并注入 CORS 响应头。"""
    client, _ = client_and_db
    preflight = client.options(
        "/api/v1/kb/chat/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"


def test_kb_upload_and_validation(client_and_db: tuple[TestClient, Path]) -> None:
    """验证文档上传索引、文档列表查询与空内容校验拦截。"""
    client, _ = client_and_db
    bad = client.post("/api/v1/kb/upload", json={"filename": "empty.md", "content": "   "})
    assert bad.status_code == 400

    res = client.post(
        "/api/v1/kb/upload",
        json={
            "filename": "hr_leave_policy.md",
            "content": "星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。病假需提交三甲医院证明。",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "uploaded"
    assert data["document"]["filename"] == "hr_leave_policy.md"
    assert data["document"]["chunk_count"] >= 1

    docs_resp = client.get("/api/v1/kb/documents")
    assert docs_resp.status_code == 200
    assert len(docs_resp.json()["documents"]) == 1


def test_kb_sse_streaming_with_citations(client_and_db: tuple[TestClient, Path]) -> None:
    """验证 SSE 流式问答依次推送 token、citations 与 done 事件。"""
    client, _ = client_and_db
    client.post(
        "/api/v1/kb/upload",
        json={
            "filename": "travel_reimbursement.md",
            "content": "差旅报销标准：一线城市酒店住宿报销上限每晚600元，二线城市每晚450元，需提供电子发票。",
        },
    )

    with client.stream(
        "POST",
        "/api/v1/kb/chat/stream",
        json={
            "session_id": "sess-rag-01",
            "message": "一线城市酒店住宿报销上限是多少？",
            "top_k": 2,
            "delay_ms": 0,
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        raw = "".join(resp.iter_text())

    events = _parse_sse_events(raw)
    token_events = [e for e in events if e.get("type") == "token"]
    citation_events = [e for e in events if e.get("type") == "citations"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(token_events) > 0
    assert len(citation_events) == 1
    assert len(done_events) == 1

    full_answer = "".join(e["content"] for e in token_events)
    assert "600元" in full_answer

    citations = citation_events[0]["citations"]
    assert len(citations) >= 1
    assert citations[0]["filename"] == "travel_reimbursement.md"
    assert "600元" in citations[0]["snippet"]


def test_multiturn_history_and_restart_persistence(client_and_db: tuple[TestClient, Path]) -> None:
    """验证多轮对话上下文、引用卡片落库以及服务重建后的 SQLite 持久化恢复。"""
    client, db_file = client_and_db
    client.post(
        "/api/v1/kb/upload",
        json={
            "filename": "redis_ops_guide.md",
            "content": "生产环境 Redis 规范：严禁执行 KEYS * 命令，应使用 SCAN 分批遍历，单次 COUNT 不超过 1000。",
        },
    )

    # 第一轮提问
    r1 = client.post(
        "/api/v1/kb/chat/stream",
        json={"session_id": "sess-ops", "message": "生产环境 Redis 禁止什么命令？", "delay_ms": 0},
    )
    assert r1.status_code == 200

    # 第二轮追问
    r2 = client.post(
        "/api/v1/kb/chat/stream",
        json={"session_id": "sess-ops", "message": "那用什么替代？", "delay_ms": 0},
    )
    assert r2.status_code == 200

    hist_resp = client.get("/api/v1/kb/sessions/sess-ops/history")
    assert hist_resp.status_code == 200
    messages = hist_resp.json()["messages"]
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert len(messages[1]["citations"]) >= 1
    assert messages[1]["citations"][0]["filename"] == "redis_ops_guide.md"
    assert "第 2 轮" in messages[3]["content"]

    # 模拟服务重启：使用同一 SQLite 路径重新创建应用
    reloaded_app = create_app(db_path=db_file, frontend_dir=DAY_DIR / "frontend")
    reloaded_client = TestClient(reloaded_app)
    assert len(reloaded_client.get("/api/v1/kb/documents").json()["documents"]) == 1
    assert len(reloaded_client.get("/api/v1/kb/sessions/sess-ops/history").json()["messages"]) == 4

    del_resp = reloaded_client.delete("/api/v1/kb/sessions/sess-ops")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
