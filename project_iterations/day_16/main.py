"""Day 16 平台启动入口：LLM 核心参数调优与 SSE 流式打字机演示 (v0.2.0-day16)"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from pydantic import ValidationError

# 支持直接 python project_iterations/day_16/main.py 启动
DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.stream_client import GenerationConfig, StreamingLLMClient


def run_demo(delay_sec: float = 0.03) -> None:
    """运行 Day 16 流式输出与参数校验演示。"""
    print("=" * 64)
    print("🚀 智枢企业级智能体平台 v0.2.0-day16 · LLM 核心参数与 SSE 流式演示")
    print("=" * 64)

    # 1. 参数校验演示
    try:
        GenerationConfig(temperature=2.8)
    except ValidationError as exc:
        print(f"[参数哨兵] 成功拦截非法 temperature=2.8 -> {exc.errors()[0]['msg']}")

    strict_cfg = GenerationConfig(temperature=0.1, top_p=0.9, max_tokens=512, frequency_penalty=0.2)
    creative_cfg = GenerationConfig(temperature=1.2, top_p=0.95, max_tokens=1024, frequency_penalty=0.5)

    client = StreamingLLMClient()
    mode_label = "Mock 离线模拟通道" if client.is_mock else "Live 在线 API 通道"
    print(f"当前运行模式: {mode_label} | 模型: {client.model_name}\n")

    messages = [
        {"role": "system", "content": "你是智枢平台企业级研发助手，回答简明专业。"},
        {"role": "user", "content": "你好，请介绍一下什么是 SSE 流式输出？"},
        {"role": "assistant", "content": "SSE（Server-Sent Events）是一种基于 HTTP 长连接的服务端单向推送协议。"},
        {"role": "user", "content": "在企业客服场景下，temperature 应该怎么选？"},
    ]

    for label, cfg in [("严谨客服模式", strict_cfg), ("创意营销模式", creative_cfg)]:
        print(f"--- [{label}] (temperature={cfg.temperature}, top_p={cfg.top_p}) ---")
        print("AI: ", end="", flush=True)
        chunks: list[str] = []
        for chunk in client.stream_chat(messages, config=cfg):
            print(chunk, end="", flush=True)
            chunks.append(chunk)
            if delay_sec > 0:
                time.sleep(delay_sec)
        print(f"\n[聚合校验] 共接收 {len(chunks)} 个分片，总字符数: {len(''.join(chunks))}\n")


if __name__ == "__main__":
    run_demo()
