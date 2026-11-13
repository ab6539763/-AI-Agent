"""Day 24 平台启动入口：FastAPI 全栈 Web ChatGPT 克隆版 (v0.2.0-day24)。"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

import uvicorn

from zhishu_agent.web_app import app


def main() -> None:
    """启动 FastAPI + Uvicorn 本地 Web 服务。"""
    print("=" * 64)
    print("🚀 智枢企业级智能体平台 v0.2.0-day24 · Web ChatGPT 全栈版")
    print("   访问地址: http://127.0.0.1:8000")
    print("   接口文档: http://127.0.0.1:8000/docs")
    print("=" * 64)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
