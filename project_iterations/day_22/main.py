"""Day 22 平台启动入口：前端静态对话台校验与静态资源服务信息 (v0.2.0-day22)"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.ui_validator import (
    describe_static_serving,
    validate_frontend_file,
)


def run_check() -> int:
    """校验 frontend/index.html 结构并打印静态托管信息。"""
    result = validate_frontend_file()
    serving = describe_static_serving(port=8080)

    print("=" * 64)
    print("🤖 智枢企业级智能体平台 v0.2.0-day22 · Static Chat UI 校验")
    print("=" * 64)
    print(f"页面标题   : {result.title}")
    print(f"UTF-8 编码 : {'PASS' if result.has_utf8_meta else 'FAIL'}")
    print(f"响应式视口 : {'PASS' if result.has_viewport_meta else 'FAIL'}")
    print(f"JS fetch() : {'PASS' if result.has_fetch_call else 'FAIL'}")
    print(f"已检出 ID  : {', '.join(result.found_ids)}")
    print(f"总体校验   : {'PASS' if result.is_valid else 'FAIL'}")
    if result.errors:
        print(f"错误详情   : {'; '.join(result.errors)}")
    print("-" * 64)
    print(f"静态目录   : {serving['frontend_dir']}")
    print(f"入口文件   : {serving['index_html']}")
    print(f"预览命令   : {serving['serve_command']}")
    print(f"访问地址   : {serving['preview_url']}")
    return 0 if result.is_valid else 1


def serve_static(port: int = 8080) -> None:
    """启动本地静态文件 HTTP 服务器预览对话台。"""
    serving = describe_static_serving(port=port)
    handler = partial(SimpleHTTPRequestHandler, directory=serving["frontend_dir"])
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"静态对话台已启动: {serving['preview_url']} (按 Ctrl+C 退出)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止静态预览服务器。")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 22 前端静态对话台校验与预览")
    parser.add_argument("--serve", action="store_true", help="启动本地静态文件 HTTP 服务器")
    parser.add_argument("--port", type=int, default=8080, help="静态服务器端口（默认 8080）")
    args = parser.parse_args()

    exit_code = run_check()
    if exit_code != 0:
        sys.exit(exit_code)
    if args.serve:
        serve_static(port=args.port)


if __name__ == "__main__":
    main()
