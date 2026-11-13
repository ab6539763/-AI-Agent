"""Day 49 FastAPI 全栈多 Agent 智能办公助手应用：HITL 人工审批中断与恢复。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from zhishu_agent.office_agents import (
    InvalidThreadStateError,
    OfficeCheckpointer,
    OfficeOrchestrator,
    ThreadNotFoundError,
    ThreadState,
)

DEFAULT_DAY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_DIR = DEFAULT_DAY_DIR / "frontend"
DEFAULT_DB_PATH = DEFAULT_DAY_DIR / "data" / "zhishu_office.db"


class RunOfficeRequest(BaseModel):
    """启动多 Agent 智能办公任务的请求体。"""

    task: str = Field(..., description="自然语言办公指令")
    thread_id: str | None = Field(default=None, description="可选自定义线程 ID")
    user_id: str = Field(default="default", description="发起用户标识")


class ResumeOfficeRequest(BaseModel):
    """Human-in-the-Loop 人工审批恢复请求体。"""

    thread_id: str = Field(..., description="挂起的线程 ID")
    approved: bool = Field(..., description="True 表示批准执行，False 表示拒绝拦截")
    comment: str = Field(default="", description="审批人备注或拒绝理由")
    edited_payload: dict[str, Any] | None = Field(
        default=None,
        description="可选：审批人微调后的动作参数",
    )


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    frontend_dir: Path = DEFAULT_FRONTEND_DIR,
) -> FastAPI:
    """构建隔离配置的 Day 49 FastAPI 应用实例（便于测试注入 tmp_path）。"""
    application = FastAPI(
        title="智枢企业级智能体平台 · 多 Agent 智能办公助手",
        version="v0.4.0-day49",
        description="Milestone Project 3 Part 2: FastAPI + Human-in-the-Loop Approval UI",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    checkpointer = OfficeCheckpointer(db_path=db_path)
    orchestrator = OfficeOrchestrator(checkpointer=checkpointer)
    frontend_path = Path(frontend_dir)

    @application.get("/", response_class=HTMLResponse)
    def serve_frontend() -> HTMLResponse:
        index_file = frontend_path / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Frontend index.html not found")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "v0.4.0-day49"}

    @application.post("/api/v1/office/run", response_model=ThreadState)
    def run_office_task(req: RunOfficeRequest) -> ThreadState:
        if not req.task or not req.task.strip():
            raise HTTPException(status_code=400, detail="task must not be empty")
        return orchestrator.run(
            task=req.task,
            thread_id=req.thread_id,
            user_id=req.user_id,
        )

    @application.post("/api/v1/office/resume", response_model=ThreadState)
    def resume_office_task(req: ResumeOfficeRequest) -> ThreadState:
        try:
            return orchestrator.resume(
                thread_id=req.thread_id,
                approved=req.approved,
                comment=req.comment,
                edited_payload=req.edited_payload,
            )
        except ThreadNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidThreadStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/v1/office/threads/{thread_id}", response_model=ThreadState)
    def get_thread(thread_id: str) -> ThreadState:
        try:
            return checkpointer.load(thread_id)
        except ThreadNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/v1/office/threads", response_model=list[ThreadState])
    def list_threads() -> list[ThreadState]:
        return checkpointer.list_threads()

    return application


app = create_app()
