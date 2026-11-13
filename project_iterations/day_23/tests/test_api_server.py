"""Day 23 FastAPI 服务端单元测试：使用 TestClient 验证路由、路径/查询参数与 Pydantic 校验。"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.api_server import APP_VERSION, app  # noqa: E402

client = TestClient(app)


def test_health_check_200_ok() -> None:
    """测试 GET /api/v1/health 返回 200 OK 及预期字段。"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ZhiShu-Agent API"
    assert data["version"] == APP_VERSION
    assert "timestamp" in data


def test_get_model_info_default_query_params() -> None:
    """测试路径参数 model_id 与默认查询参数（不返回定价）。"""
    resp = client.get("/api/v1/models/deepseek-chat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "deepseek-chat"
    assert data["provider"] == "DeepSeek"
    assert data["detail_level"] == "basic"
    assert data["pricing_per_1m_usd"] is None


def test_get_model_info_with_pricing_and_full_detail() -> None:
    """测试查询参数 include_pricing=true 与 detail_level=full。"""
    resp = client.get("/api/v1/models/qwen-plus?include_pricing=true&detail_level=full")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "qwen-plus"
    assert data["detail_level"] == "full"
    assert data["pricing_per_1m_usd"] == {"input": 0.4, "output": 1.2}


def test_get_model_info_not_found_404() -> None:
    """测试查询不存在的模型返回 404 Not Found。"""
    resp = client.get("/api/v1/models/unknown-model")
    assert resp.status_code == 404
    assert "未找到模型" in resp.json()["detail"]


def test_get_model_info_invalid_detail_level_422() -> None:
    """测试非法的 detail_level 查询参数触发 422 校验错误。"""
    resp = client.get("/api/v1/models/gpt-4o?detail_level=verbose")
    assert resp.status_code == 422


def test_chat_completion_200_ok() -> None:
    """测试 POST /api/v1/chat 正常请求返回 200 OK 与结构化响应。"""
    payload = {
        "message": "你好，请介绍一下智枢平台！",
        "model": "deepseek-chat",
        "temperature": 0.5,
        "max_tokens": 256,
        "session_id": "sess-test-001",
    }
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-test-001"
    assert data["model"] == "deepseek-chat"
    assert data["temperature"] == 0.5
    assert "你好，请介绍一下智枢平台！" in data["reply"]
    assert data["usage"]["total_tokens"] == (
        data["usage"]["prompt_tokens"] + data["usage"]["completion_tokens"]
    )


def test_chat_completion_validation_errors_422() -> None:
    """测试空白消息、超范围 temperature、不支持的模型均返回 422 Unprocessable Entity。"""
    # 1. 空白消息
    resp_blank = client.post("/api/v1/chat", json={"message": "   "})
    assert resp_blank.status_code == 422

    # 2. temperature 超出 [0.0, 2.0]
    resp_temp = client.post(
        "/api/v1/chat",
        json={"message": "hello", "temperature": 2.5},
    )
    assert resp_temp.status_code == 422

    # 3. 不支持的模型
    resp_model = client.post(
        "/api/v1/chat",
        json={"message": "hello", "model": "nonexistent-llm"},
    )
    assert resp_model.status_code == 422

    # 4. max_tokens 小于 1
    resp_tokens = client.post(
        "/api/v1/chat",
        json={"message": "hello", "max_tokens": 0},
    )
    assert resp_tokens.status_code == 422
