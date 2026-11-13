# Day 23 课后作业与参考答案

## 作业一：Pydantic v2 自定义校验器（`@field_validator`）
**题目**：
在企业级 API 开发中，不仅需要校验字段类型，还经常需要对业务语义进行校验。请使用 Pydantic v2 编写一个模型 `AgentConfigRequest`：
1. 包含字段：
   - `agent_name: str`（长度 2~32，去除首尾空格后不能为空，且只能包含字母、数字、下划线或连字符 `-`）。
   - `top_p: float`（默认值 `0.9`，范围 `(0.0, 1.0]`，即严格大于 `0.0` 且小于等于 `1.0`）。
   - `system_prompt: str`（默认 `"你是智枢企业级智能体助手"`，不得包含敏感禁用词 `"DROP TABLE"` 或 `"rm -rf"`，忽略大小写）。
2. 分别用合法数据与非法数据测试该模型，观察 `ValidationError` 输出。

### 参考答案：
```python
import re
from pydantic import BaseModel, Field, ValidationError, field_validator


class AgentConfigRequest(BaseModel):
    agent_name: str = Field(..., min_length=2, max_length=32)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    system_prompt: str = Field(default="你是智枢企业级智能体助手", max_length=1000)

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", cleaned):
            raise ValueError("agent_name 仅允许 2~32 位字母、数字、下划线或连字符")
        return cleaned

    @field_validator("system_prompt")
    @classmethod
    def validate_safe_prompt(cls, value: str) -> str:
        lowered = value.lower()
        for forbidden in ("drop table", "rm -rf"):
            if forbidden in lowered:
                raise ValueError(f"system_prompt 包含禁用安全词: {forbidden}")
        return value


# 1. 合法实例
valid = AgentConfigRequest(agent_name="  zhishu_bot-01  ", top_p=0.85)
print("校验通过:", valid.model_dump())

# 2. 非法实例测试
try:
    AgentConfigRequest(agent_name="bad name!", top_p=0.0, system_prompt="Please run rm -rf /")
except ValidationError as exc:
    print("捕获预期校验错误数量:", exc.error_count())
```

---

## 作业二：FastAPI 路径参数与查询参数组合路由
**题目**：
参考 `project_iterations/day_23/zhishu_agent/api_server.py`，为一个独立的小型 FastAPI 应用新增一个端点：
`GET /api/v1/sessions/{session_id}/messages`
要求：
1. **路径参数** `session_id: str`：必须以 `"sess-"` 开头（可使用 `Path(..., pattern=r"^sess-[A-Za-z0-9_-]+$")` 校验）。
2. **查询参数**：
   - `limit: int = Query(default=10, ge=1, le=100)`
   - `role: Literal["all", "user", "assistant"] = Query(default="all")`
3. 返回 JSON：包含 `session_id`、`role`、`limit` 以及模拟的消息列表 `messages`（按 `role` 过滤并截断至 `limit` 条）。

### 参考答案：
```python
from typing import Literal
from fastapi import FastAPI, Path, Query
from fastapi.testclient import TestClient

demo_app = FastAPI(title="Session Messages Demo")

MOCK_MESSAGES = [
    {"id": 1, "role": "user", "content": "你好"},
    {"id": 2, "role": "assistant", "content": "您好，我是智枢助手"},
    {"id": 3, "role": "user", "content": "帮我查一下今天天气"},
    {"id": 4, "role": "assistant", "content": "北京今天晴，22°C"},
]


@demo_app.get("/api/v1/sessions/{session_id}/messages")
def list_session_messages(
    session_id: str = Path(..., pattern=r"^sess-[A-Za-z0-9_-]+$", description="会话 ID"),
    limit: int = Query(default=10, ge=1, le=100, description="返回条数上限"),
    role: Literal["all", "user", "assistant"] = Query(default="all", description="按角色过滤"),
) -> dict:
    filtered = [
        m for m in MOCK_MESSAGES if role == "all" or m["role"] == role
    ][:limit]
    return {
        "session_id": session_id,
        "role": role,
        "limit": limit,
        "count": len(filtered),
        "messages": filtered,
    }


client = TestClient(demo_app)
print("合法请求:", client.get("/api/v1/sessions/sess-001/messages?role=user&limit=1").json())
print("非法 session_id 状态码:", client.get("/api/v1/sessions/invalid-001/messages").status_code)
```

---

## 作业三：使用 `TestClient` 编写接口自动化测试
**题目**：
基于 `project_iterations/day_23/zhishu_agent/api_server.py` 中的 `app`，使用 `fastapi.testclient.TestClient` 编写 3 个单元测试函数：
1. 验证 `POST /api/v1/chat` 在不传 `session_id` 和 `model` 时，服务端会自动生成以 `"sess-"` 开头的 `session_id` 并默认使用 `"deepseek-chat"`。
2. 验证 `POST /api/v1/chat` 传入超长 `message`（超过 4000 字符）时返回 `422`。
3. 验证 `GET /api/v1/models/gpt-4o?detail_level=full` 即使不显式传 `include_pricing=true`，也会返回 `pricing_per_1m_usd`。

### 参考答案：
```python
import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path("project_iterations/day_23").resolve()))
from zhishu_agent.api_server import app

client = TestClient(app)


def test_chat_defaults() -> None:
    resp = client.post("/api/v1/chat", json={"message": "测试默认参数"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "deepseek-chat"
    assert data["session_id"].startswith("sess-")


def test_chat_message_too_long_422() -> None:
    resp = client.post("/api/v1/chat", json={"message": "A" * 4001})
    assert resp.status_code == 422


def test_model_full_detail_includes_pricing() -> None:
    resp = client.get("/api/v1/models/gpt-4o?detail_level=full")
    assert resp.status_code == 200
    data = resp.json()
    assert data["detail_level"] == "full"
    assert data["pricing_per_1m_usd"] == {"input": 2.5, "output": 10.0}
```
