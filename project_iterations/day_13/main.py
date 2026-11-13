"""Day 13 平台启动入口：演示装饰器 (@retry_on_error / @log_latency)、生成器 yield、asyncio 并发与 .env 安全配置"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from zhishu_agent.config import load_agent_config
from zhishu_agent.decorators import log_latency, retry_on_error
from zhishu_agent.streaming import async_batch_ask, stream_tokens


def run_demo() -> None:
    """运行 Day 13 核心特性演示。"""
    print("=== 智枢平台 v0.1.0-day13：Python 高级特性与工程化演示 ===\n")

    # 1. 安全加载 .env 配置（使用临时文件模拟生产环境 .env，密钥自动脱敏）
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text(
            "# 智枢平台环境配置\n"
            "ZHISHU_MODEL_NAME='deepseek-chat'\n"
            'ZHISHU_API_KEY="sk-live-secret-9527"\n'
            "ZHISHU_MAX_RETRIES=3\n",
            encoding="utf-8",
        )
        cfg = load_agent_config(env_path=env_file, override=True)
        print(f"1. 安全配置加载: {cfg}\n")

    # 2. 装饰器：@log_latency + @retry_on_error 组合使用
    attempts = {"count": 0}

    @log_latency
    @retry_on_error(max_retries=3, delay=0.01)
    def flaky_llm_call(prompt: str) -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError(f"第 {attempts['count']} 次请求网络抖动")
        return f"[{cfg.model_name}] 成功回复: {prompt}"

    print("2. 装饰器自动重试与耗时监控:")
    reply = flaky_llm_call("解释 Python 装饰器")
    print(f"   最终结果 (共尝试 {attempts['count']} 次): {reply}\n")

    # 3. 生成器 yield 流式吐出 Token
    print("3. 生成器流式输出 (yield):")
    tokens = list(stream_tokens("智枢智能体流式输出", chunk_size=2))
    print(f"   流式切片: {tokens}\n")

    # 4. asyncio.gather 并发批量调用
    print("4. asyncio.gather 异步批量并发请求:")
    prompts = ["什么是 RAG？", "什么是 MCP？", "什么是 LangGraph？"]
    batch_results = asyncio.run(async_batch_ask(prompts, model_name=cfg.model_name, delay=0.01))
    for item in batch_results:
        print(f"   {item}")


if __name__ == "__main__":
    run_demo()
