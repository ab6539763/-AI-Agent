"""Day 49 自动化单元测试：覆盖 FastAPI 多 Agent 智能办公助手、CORS、HITL 审批中断与恢复及前端页面。"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.office_web_app import create_app


@pytest.fixture()
def client_and_db(tmp_path: Path) -> tuple[TestClient, Path]:
    """使用 tmp_path 临时 SQLite 数据库构建隔离的 FastAPI TestClient。"""
    db_file = tmp_path / "test_office.db"
    app = create_app(db_path=db_file, frontend_dir=DAY_DIR / "frontend")
    return TestClient(app), db_file


def test_frontend_serving_and_health(client_and_db: tuple[TestClient, Path]) -> None:
    """验证 GET / 返回多 Agent 智能办公助手前端页面，且健康检查接口正常。"""
    client, _ = client_and_db
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "/api/v1/office/run" in resp.text
    assert "/api/v1/office/resume" in resp.text
    assert "approval-container" in resp.text
    assert "Approve" in resp.text and "Reject" in resp.text

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "v0.4.0-day49"}


def test_cors_preflight_headers(client_and_db: tuple[TestClient, Path]) -> None:
    """验证 CORSMiddleware 正确处理 OPTIONS 预检请求。"""
    client, _ = client_and_db
    preflight = client.options(
        "/api/v1/office/run",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"


def test_low_risk_task_completes_immediately(client_and_db: tuple[TestClient, Path]) -> None:
    """验证只读检索类低风险任务无需人工审批，直接返回 completed 状态与最终输出。"""
    client, db_file = client_and_db
    bad = client.post("/api/v1/office/run", json={"task": "   "})
    assert bad.status_code == 400

    res = client.post(
        "/api/v1/office/run",
        json={"task": "查询公司 2026 差旅报销制度", "user_id": "chenmo"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["pending_action"] is None
    assert body["final_output"] is not None
    assert len(body["handoff_trace"]) == 4
    assert body["handoff_trace"][1]["to_agent"] == "kb_researcher"
    assert db_file.exists()

    # 验证可通过 GET /api/v1/office/threads/{thread_id} 持久化回查
    fetched = client.get(f"/api/v1/office/threads/{body['thread_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"


def test_hitl_interrupt_and_approve_resume(client_and_db: tuple[TestClient, Path]) -> None:
    """验证高风险任务触发 awaiting_approval 中断，批准后恢复执行并落盘 completed。"""
    client, _ = client_and_db
    run_resp = client.post(
        "/api/v1/office/run",
        json={"task": "发送全员邮件通知本周五晚系统升级维护", "user_id": "linxiao"},
    )
    assert run_resp.status_code == 200
    run_body = run_resp.json()
    thread_id = run_body["thread_id"]
    assert run_body["status"] == "awaiting_approval"
    assert run_body["pending_action"]["action_type"] == "send_email"
    assert run_body["pending_action"]["agent"] == "email_dispatcher"
    assert run_body["final_output"] is None

    # 批准恢复执行并微调 payload
    resume_resp = client.post(
        "/api/v1/office/resume",
        json={
            "thread_id": thread_id,
            "approved": True,
            "comment": "已核对维护窗口，准予发送",
            "edited_payload": {"subject": "【紧急通知】周五晚系统维护"},
        },
    )
    assert resume_resp.status_code == 200
    resumed = resume_resp.json()
    assert resumed["status"] == "completed"
    assert resumed["decision"] == "approved"
    assert resumed["pending_action"] is None
    assert resumed["resolved_action"]["payload"]["subject"] == "【紧急通知】周五晚系统维护"
    assert "人工审批通过" in resumed["final_output"]

    # 重复 resume 应返回 409 Conflict
    dup = client.post(
        "/api/v1/office/resume",
        json={"thread_id": thread_id, "approved": True},
    )
    assert dup.status_code == 409


def test_hitl_reject_and_error_cases(client_and_db: tuple[TestClient, Path]) -> None:
    """验证人工拒绝拦截流程及不存在的 thread_id 返回 404。"""
    client, _ = client_and_db
    run_resp = client.post(
        "/api/v1/office/run",
        json={"task": "审批张工的差旅报销申请 2480 元"},
    )
    assert run_resp.status_code == 200
    thread_id = run_resp.json()["thread_id"]
    assert run_resp.json()["status"] == "awaiting_approval"

    reject_resp = client.post(
        "/api/v1/office/resume",
        json={
            "thread_id": thread_id,
            "approved": False,
            "comment": "缺少发票附件，暂不批准",
        },
    )
    assert reject_resp.status_code == 200
    rejected = reject_resp.json()
    assert rejected["status"] == "rejected"
    assert rejected["decision"] == "rejected"
    assert "安全拦截" in rejected["final_output"]

    # 查询与恢复不存在的 thread_id 均应返回 404
    assert client.get("/api/v1/office/threads/thread-nonexistent").status_code == 404
    assert (
        client.post(
            "/api/v1/office/resume",
            json={"thread_id": "thread-nonexistent", "approved": True},
        ).status_code
        == 404
    )
