"""Day 42 单元测试：SQLiteCheckpointer、Interrupt/Resume、并发节点、重试策略与 Writing Agent."""

import sys
import threading
import time
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    END,
    AdvancedStateGraph,
    ParallelSectionRunner,
    RetryPolicy,
    SQLiteCheckpointer,
    build_writing_agent_graph,
    execute_with_retry,
)


def test_sqlite_checkpointer_persistence_and_thread_isolation(tmp_path: Path) -> None:
    """验证 SQLiteCheckpointer 按 thread_id 隔离状态且支持跨实例持久化恢复."""
    db_file = tmp_path / "checkpoints.db"
    cp1 = SQLiteCheckpointer(db_file)

    cp1.save_checkpoint("thread-a", step=1, next_node="n2", state={"topic": "A", "v": 1}, status="running")
    cp1.save_checkpoint("thread-b", step=1, next_node="n2", state={"topic": "B", "v": 99}, status="interrupted")
    cp1.save_checkpoint("thread-a", step=2, next_node=END, state={"topic": "A", "v": 2}, status="completed")

    # 重新实例化 checkpointer 模拟服务重启
    cp2 = SQLiteCheckpointer(db_file)
    assert cp2.list_threads() == ["thread-a", "thread-b"]

    latest_a = cp2.get_latest("thread-a")
    latest_b = cp2.get_latest("thread-b")
    assert latest_a is not None and latest_a.state == {"topic": "A", "v": 2}
    assert latest_a.status == "completed"
    assert latest_b is not None and latest_b.state == {"topic": "B", "v": 99}
    assert latest_b.status == "interrupted"

    history_a = cp2.get_history("thread-a")
    assert [h.step for h in history_a] == [1, 2]

    deleted = cp2.delete_thread("thread-b")
    assert deleted == 1
    assert cp2.get_latest("thread-b") is None
    assert cp2.get_latest("thread-a") is not None


def test_interrupt_before_and_resume_with_updated_state(tmp_path: Path) -> None:
    """验证 interrupt_before 拦截与 resume(thread_id, updated_state) 注入恢复."""
    cp = SQLiteCheckpointer(tmp_path / "hitl.db")

    graph = AdvancedStateGraph()
    graph.add_node("draft", lambda s: {"draft": f"初稿:{s['topic']}"})
    graph.add_node("review", lambda s: {"reviewed": True, "final": f"{s['draft']}|审批:{s.get('reviewer')}"})
    graph.set_entry_point("draft")
    graph.add_edge("draft", "review")
    graph.add_edge("review", END)

    compiled = graph.compile(checkpointer=cp, interrupt_before=["review"])
    paused = compiled.invoke({"topic": "Agent 架构"}, thread_id="hitl-01")

    assert paused.status == "interrupted"
    assert paused.interrupted_at == "review"
    assert paused.state["draft"] == "初稿:Agent 架构"
    assert "final" not in paused.state

    resumed = compiled.resume(
        "hitl-01",
        updated_state={"reviewer": "张工", "draft": "修订稿:Agent 架构"},
    )
    assert resumed.status == "completed"
    assert resumed.state["reviewed"] is True
    assert resumed.state["final"] == "修订稿:Agent 架构|审批:张工"


def test_parallel_section_runner_concurrency_and_ordering() -> None:
    """验证 ParallelSectionRunner 使用多线程并发执行并按原始大纲顺序返回."""
    runner = ParallelSectionRunner(max_workers=4)
    seen_threads: set[int] = set()
    lock = threading.Lock()

    def slow_drafter(idx: int, title: str) -> str:
        with lock:
            seen_threads.add(threading.get_ident())
        # 故意让靠前章节睡得更久，验证输出仍按 idx 有序排列
        time.sleep(0.03 * (3 - idx))
        return f"[{idx}] {title}"

    sections = ["第一章", "第二章", "第三章", "第四章"]
    results = runner.run(sections, slow_drafter)

    assert [r.index for r in results] == [0, 1, 2, 3]
    assert [r.title for r in results] == sections
    assert [r.content for r in results] == [f"[{i}] {t}" for i, t in enumerate(sections)]
    assert len(seen_threads) >= 2


def test_node_level_retry_policy_success_and_exhaustion(tmp_path: Path) -> None:
    """验证 RetryPolicy 对瞬时异常的重试恢复以及耗尽次数后的异常抛出."""
    calls = {"count": 0}

    def flaky_fn() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("transient timeout")
        return "ok"

    val, attempts = execute_with_retry(
        flaky_fn,
        RetryPolicy(max_retries=2, initial_delay_s=0.001, retry_on=(TimeoutError,)),
    )
    assert val == "ok"
    assert attempts == 3

    cp = SQLiteCheckpointer(tmp_path / "retry.db")
    g = AdvancedStateGraph()
    g.add_node(
        "always_fail",
        lambda _s: (_ for _ in ()).throw(ValueError("fatal")),
        retry_policy=RetryPolicy(max_retries=2, initial_delay_s=0.001, retry_on=(ValueError,)),
    )
    g.set_entry_point("always_fail")
    g.add_edge("always_fail", END)
    app = g.compile(checkpointer=cp)

    with pytest.raises(ValueError, match="fatal"):
        app.invoke({}, thread_id="fail-thread")


def test_writing_agent_end_to_end_with_revision_and_restart_recovery(tmp_path: Path) -> None:
    """验证完整 Writing Agent：Outline -> 驳回重写 -> 审批通过 -> 并发写章 -> 终稿润色."""
    db_file = tmp_path / "writing.db"
    cp1 = SQLiteCheckpointer(db_file)

    section_calls: dict[int, int] = {}

    def section_drafter(topic: str, idx: int, title: str) -> str:
        section_calls[idx] = section_calls.get(idx, 0) + 1
        if idx == 1 and section_calls[idx] == 1:
            raise RuntimeError("章节 2 首次生成瞬时失败")
        return f"## {title}\n内容({topic}) [attempts={section_calls[idx]}]"

    app1 = build_writing_agent_graph(
        checkpointer=cp1,
        section_draft_fn=section_drafter,
        max_workers=3,
        node_retry_policy=RetryPolicy(max_retries=2, initial_delay_s=0.001),
    )

    # 第 1 次运行：生成大纲后在 human_approval 前中断
    step1 = app1.invoke({"topic": "LangGraph 高级编排"}, thread_id="book-1")
    assert step1.status == "interrupted"
    assert step1.interrupted_at == "human_approval"
    assert len(step1.state["outline"]) == 3
    assert step1.state["revision_count"] == 1

    # 模拟人工驳回（approved=False）：图路由回 generate_outline 重新生成大纲并再次中断
    step2 = app1.resume("book-1", updated_state={"approved": False, "human_feedback": "请再细化"})
    assert step2.status == "interrupted"
    assert step2.interrupted_at == "human_approval"
    assert step2.state["revision_count"] == 2

    # 模拟服务重启：使用新 SQLiteCheckpointer 和新编译图实例从磁盘恢复并审批通过
    cp2 = SQLiteCheckpointer(db_file)
    app2 = build_writing_agent_graph(
        checkpointer=cp2,
        section_draft_fn=section_drafter,
        max_workers=3,
        node_retry_policy=RetryPolicy(max_retries=2, initial_delay_s=0.001),
    )
    final_res = app2.resume(
        "book-1",
        updated_state={
            "approved": True,
            "human_feedback": "确认通过",
            "outline": ["第一章：状态机", "第二章：并发与重试"],
        },
    )

    assert final_res.status == "completed"
    assert len(final_res.state["chapters"]) == 2
    assert final_res.state["chapters"][1]["attempts"] == 2
    assert "# LangGraph 高级编排" in final_res.state["final_article"]
    assert "确认通过" in final_res.state["final_article"]
    assert "第一章：状态机" in final_res.state["final_article"]
    assert "第二章：并发与重试" in final_res.state["final_article"]
