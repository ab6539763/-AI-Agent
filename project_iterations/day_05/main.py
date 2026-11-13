"""Day 05 平台启动入口：演示 LLM API JSON 解析、会话持久化与 Token 用量统计"""
import json
import tempfile
from pathlib import Path

from zhishu_agent.json_parser import (
    extract_llm_response,
    load_session_json,
    save_session_json,
    summarize_usage,
)
from zhishu_agent.profile import get_environment_info

SAMPLE_API_JSON = """
{
  "id": "chatcmpl-day05-001",
  "object": "chat.completion",
  "created": 1731456000,
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！我是星辰数科智枢平台助手，今天我们来解析大模型 JSON 响应。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 32,
    "completion_tokens": 28,
    "total_tokens": 60
  }
}
"""


def run_demo() -> None:
    """运行 Day 05 核心功能演示"""
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day05 | Python {env['python_version']}")

    # 1. 解析模拟大模型响应 JSON
    parsed = extract_llm_response(SAMPLE_API_JSON)
    print(f"\n[响应解析] 模型: {parsed['model']} | ID: {parsed['id']}")
    print(f"[模型回复] {parsed['content']}")
    print(
        f"[Token 消耗] 输入={parsed['prompt_tokens']}, "
        f"输出={parsed['completion_tokens']}, 总计={parsed['total_tokens']}"
    )

    # 2. 保存与加载中文对话会话
    messages = [
        {"role": "system", "content": "你是星辰数科的企业级 AI 助手。"},
        {"role": "user", "content": "请介绍 JSON 在大模型 API 中的作用。"},
        {"role": "assistant", "content": parsed["content"]},
    ]
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_file = Path(tmp_dir) / "session_001.json"
        save_session_json(session_file, messages)
        loaded = load_session_json(session_file)
        print(f"\n[会话持久化] 已保存并重新加载 {len(loaded)} 条中文对话消息。")

    # 3. 汇总多次调用的 Token 用量
    raw_resp_1 = json.loads(SAMPLE_API_JSON)
    raw_resp_2 = {
        "id": "chatcmpl-day05-002",
        "model": "deepseek-chat",
        "usage": {"prompt_tokens": 50, "completion_tokens": 40, "total_tokens": 90},
    }
    summary = summarize_usage([raw_resp_1, raw_resp_2])
    print(f"[用量汇总] {summary}")


if __name__ == "__main__":
    run_demo()
