"""Day 62 平台启动入口：智枢企业财报与合规智能分析台全栈版 (v1.0.0-day62)。"""

from __future__ import annotations

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

import uvicorn

from zhishu_agent.capstone_web import app


def main() -> None:
    """启动 FastAPI + Uvicorn 全栈 SSE 与 HITL 审批服务。"""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v1.0.0-day62 · 财报与合规智能分析台全栈版")
    print("   访问地址: http://127.0.0.1:8000")
    print("   接口文档: http://127.0.0.1:8000/docs")
    print("=" * 72)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
