"""Day 37 平台启动入口：全栈企业级知识库问答系统 (v0.3.0-day37)。"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

import uvicorn

from zhishu_agent.kb_web_app import app


def main() -> None:
    """启动 FastAPI + Uvicorn 企业知识库问答 Web 服务。"""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day37 · 企业知识库问答全栈版")
    print("   访问地址: http://127.0.0.1:8000")
    print("   接口文档: http://127.0.0.1:8000/docs")
    print("=" * 68)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
