"""Day 40 平台启动入口：智枢 LangChain Agent & @tool 生态演示 (v0.4.0-day40)."""

import json
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    AgentExecutor,
    ToolCallingAgent,
    create_sandbox_file_tools,
    safe_math_eval,
    tavily_search,
)


def main() -> None:
    """运行 Day 40 @tool 生态与 AgentExecutor 安全沙箱演示."""
    print("=" * 64)
    print("🤖 智枢企业级智能体平台 v0.4.0-day40 · LangChain @tool 生态演示")
    print("=" * 64)

    with tempfile.TemporaryDirectory() as tmp:
        read_file, write_file = create_sandbox_file_tools(Path(tmp))
        tools = [tavily_search, safe_math_eval, read_file, write_file]

        print("\n[1] 自动生成的 OpenAI Function Calling Tool Schemas:")
        print(json.dumps(safe_math_eval.to_openai_tool(), ensure_ascii=False, indent=2))

        agent = ToolCallingAgent(tools=tools)
        executor = AgentExecutor(agent=agent, tools=tools, max_iterations=5)

        queries = [
            "搜索 LangChain Tool Calling 最佳实践",
            "请计算 (128 + 72) * 3 / 4 并写入 calc_result.txt",
        ]
        for query in queries:
            print(f"\n[2] 用户提问: {query}")
            res = executor.invoke({"input": query})
            print(f"    最终输出: {res['output']}")
            print(f"    中间步骤数: {len(res['intermediate_steps'])}")
            for idx, (action, obs) in enumerate(res["intermediate_steps"], start=1):
                print(f"      Step {idx}: tool={action.tool}, input={action.tool_input} -> obs={obs}")


if __name__ == "__main__":
    main()
