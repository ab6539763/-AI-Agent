"""Day 23 平台启动入口：Uvicorn FastAPI Web 服务启动器 (v0.2.0-day23)"""

import argparse
import sys
from pathlib import Path

import uvicorn

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.api_server import APP_VERSION, app  # noqa: E402


def main() -> None:
    """解析命令行参数并启动 Uvicorn HTTP 服务。"""
    parser = argparse.ArgumentParser(description=f"启动智枢平台 FastAPI 服务 ({APP_VERSION})")
    parser.add_argument("--host", default="127.0.0.1", help="监听主机地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")
    parser.add_argument("--reload", action="store_true", help="是否开启热重载模式")
    args = parser.parse_args()

    print("=" * 64)
    print(f"🚀 智枢企业级智能体平台 {APP_VERSION} · FastAPI 服务启动")
    print(f"   Swagger UI 文档: http://{args.host}:{args.port}/docs")
    print(f"   ReDoc 文档:      http://{args.host}:{args.port}/redoc")
    print("=" * 64)

    if args.reload:
        uvicorn.run("zhishu_agent.api_server:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
