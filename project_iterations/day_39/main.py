"""Day 39 平台启动入口：纯 Python ReAct 智能体范式演示 (v0.4.0-day39)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import ReActAgent


def main() -> None:
    """运行纯 Python ReAct 智能体多跳推理演示."""
    print("=" * 64)
    print("🤖 智枢企业级智能体平台 v0.4.0-day39 · 纯 Python ReAct 引擎")
    print("=" * 64)

    agent = ReActAgent(max_steps=5)
    demo_queries = [
        "先查询星辰数科高级工程师的差旅住宿标准，再计算连续出差 4 晚的总住宿预算上限。",
        "帮我计算 (128 + 72) * 3 / 4 的结果。",
    ]

    for idx, query in enumerate(demo_queries, start=1):
        print(f"\n>>> 示例 {idx}")
        trace = agent.run(query)
        print(trace.format_trace())


if __name__ == "__main__":
    main()
