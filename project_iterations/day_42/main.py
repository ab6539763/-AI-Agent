"""Day 42 平台启动入口：高级 LangGraph 状态图与写作智能体演示 (v0.4.0-day42)."""

import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    RetryPolicy,
    SQLiteCheckpointer,
    build_writing_agent_graph,
)


def main() -> None:
    """运行 Day 42 Writing Agent 端到端工作流演示."""
    print("=" * 68)
    print("✍️  智枢企业级智能体平台 v0.4.0-day42 · 高级 LangGraph 写作智能体")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "writing_agent.db"
        checkpointer = SQLiteCheckpointer(db_path)

        attempts_by_section: dict[int, int] = {}

        def flaky_drafter(topic: str, index: int, title: str) -> str:
            """模拟第 1 章首次调用抖动失败、重试后成功."""
            attempts_by_section[index] = attempts_by_section.get(index, 0) + 1
            if index == 0 and attempts_by_section[index] == 1:
                raise RuntimeError("模拟模型 API 瞬时超时")
            return (
                f"### {title}\n"
                f"围绕“{topic}”第 {index + 1} 节撰写完成（尝试次数: {attempts_by_section[index]}）。"
            )

        graph = build_writing_agent_graph(
            checkpointer=checkpointer,
            section_draft_fn=flaky_drafter,
            max_workers=3,
            node_retry_policy=RetryPolicy(max_retries=2, initial_delay_s=0.005),
        )

        thread_id = "demo-writing-001"
        print(f"\n[阶段 1] 启动任务 thread_id={thread_id!r}，生成大纲后触发人工审批拦截...")
        paused = graph.invoke({"topic": "企业级 AI Agent 生产治理"}, thread_id=thread_id)
        print(f"状态: {paused.status} | 暂停节点: {paused.interrupted_at}")
        print("初始大纲:", paused.state["outline"])

        print("\n[阶段 2] 人工审稿：补充第四章并确认 approved=True，执行 resume()...")
        updated_outline = list(paused.state["outline"]) + [
            "第四章：企业级 AI Agent 生产治理 的合规审计与灰度发布"
        ]
        resumed = graph.resume(
            thread_id,
            updated_state={
                "approved": True,
                "outline": updated_outline,
                "human_feedback": "大纲结构完整，已补充合规审计章节",
            },
        )
        print(f"恢复后状态: {resumed.status} | 执行轨迹: {resumed.execution_trace}")
        print("\n[阶段 3] 终稿输出预览:")
        print("-" * 68)
        print(resumed.state["final_article"])
        print("-" * 68)
        print(f"检查点历史记录数: {len(checkpointer.get_history(thread_id))}")


if __name__ == "__main__":
    main()
