"""Day 27 自动化单元测试：覆盖内存/SQLite 历史、窗口裁剪、摘要记忆与多租户会话隔离。"""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.memory import (
    BaseChatMessageHistory,
    ChatMessage,
    InMemoryChatMessageHistory,
    RunnableWithMessageHistory,
    SQLiteChatMessageHistory,
    SummaryMemory,
    WindowMemory,
)


def test_in_memory_history_crud() -> None:
    """验证 InMemoryChatMessageHistory 的基本增删查与角色校验。"""
    history = InMemoryChatMessageHistory()
    assert isinstance(history, BaseChatMessageHistory)
    assert history.messages == []

    history.add_user_message("你好")
    history.add_ai_message("你好，请问有什么可以帮您？")
    assert len(history.messages) == 2
    assert [m.role for m in history.messages] == ["user", "assistant"]

    history.clear()
    assert history.messages == []

    with pytest.raises(ValueError):
        ChatMessage(role="invalid_role", content="bad")


def test_window_memory_keeps_last_k_turns() -> None:
    """验证 WindowMemory(k=2) 仅保留系统提示词与最近 2 轮（4 条）对话。"""
    history = InMemoryChatMessageHistory()
    history.add_system_message("你是智枢企业助手。")
    for i in range(1, 5):
        history.add_user_message(f"第{i}轮问题")
        history.add_ai_message(f"第{i}轮回答")

    window = WindowMemory(k=2, keep_system=True)
    trimmed = window.load_memory_variables(history)

    assert len(trimmed) == 5  # 1 条 system + 2 轮 * 2 条
    assert trimmed[0].role == "system"
    assert [m.content for m in trimmed[1:]] == [
        "第3轮问题",
        "第3轮回答",
        "第4轮问题",
        "第4轮回答",
    ]

    zero_window = WindowMemory(k=0, keep_system=False)
    assert zero_window.load_memory_variables(history) == []


def test_summary_memory_compresses_older_turns() -> None:
    """验证 SummaryMemory 将超出近期窗口的旧对话压缩为系统摘要。"""
    history = InMemoryChatMessageHistory()
    history.add_user_message("我叫张伟，来自财务部")
    history.add_ai_message("您好张伟，很高兴为您服务")
    history.add_user_message("请问差旅报销上限是多少？")
    history.add_ai_message("一线城市每日住宿上限 600 元。")

    summary_mem = SummaryMemory(max_recent_messages=2)
    result = summary_mem.load_memory_variables(history)

    assert "张伟" in result["summary"]
    assert "财务部" in result["summary"]
    assert [m.content for m in result["recent_messages"]] == [
        "请问差旅报销上限是多少？",
        "一线城市每日住宿上限 600 元。",
    ]
    assert result["messages"][0].role == "system"
    assert len(result["messages"]) == 3


def test_sqlite_persistence_and_session_isolation(tmp_path: Path) -> None:
    """验证 SQLiteChatMessageHistory 持久化落盘与多租户 session_id 严格隔离。"""
    db_file = tmp_path / "sessions.db"

    alice_v1 = SQLiteChatMessageHistory(session_id="alice", db_path=db_file)
    bob_v1 = SQLiteChatMessageHistory(session_id="bob", db_path=db_file)

    alice_v1.add_user_message("Alice 机密预算：100 万")
    alice_v1.add_ai_message("已记录 Alice 预算。")
    bob_v1.add_user_message("Bob 提问：今天天气如何？")

    # 重新实例化模拟进程重启
    alice_v2 = SQLiteChatMessageHistory(session_id="alice", db_path=db_file)
    bob_v2 = SQLiteChatMessageHistory(session_id="bob", db_path=db_file)

    assert len(alice_v2.messages) == 2
    assert len(bob_v2.messages) == 1
    assert all("Alice" not in m.content for m in bob_v2.messages)
    assert SQLiteChatMessageHistory.list_sessions(db_file) == ["alice", "bob"]

    # 清空 alice 不影响 bob
    alice_v2.clear()
    assert alice_v2.messages == []
    assert len(bob_v2.messages) == 1

    with pytest.raises(ValueError):
        SQLiteChatMessageHistory(session_id="   ", db_path=db_file)


def test_runnable_with_message_history_end_to_end(tmp_path: Path) -> None:
    """验证 RunnableWithMessageHistory 结合 SQLite 与 WindowMemory 的端到端闭环。"""
    db_file = tmp_path / "runnable.db"
    observed_histories: list[list[str]] = []

    def fake_llm_chain(payload: dict) -> str:
        observed_histories.append([m.content for m in payload["history"]])
        return f"回复:{payload['input']}"

    chain = RunnableWithMessageHistory(
        runnable=fake_llm_chain,
        get_session_history=lambda sid: SQLiteChatMessageHistory(sid, db_file),
        memory_strategy=WindowMemory(k=1),
    )

    cfg_a = {"configurable": {"session_id": "dept-hr"}}
    cfg_b = {"configurable": {"session_id": "dept-it"}}

    chain.invoke({"input": "第一问"}, config=cfg_a)
    chain.invoke({"input": "第二问"}, config=cfg_a)
    chain.invoke({"input": "第三问"}, config=cfg_a)
    chain.invoke({"input": "IT 第一问"}, config=cfg_b)

    # 第 3 次调用 dept-hr 时，由于 k=1，仅注入第 2 轮（第二问 + 回复:第二问）
    assert observed_histories[0] == []
    assert observed_histories[1] == ["第一问", "回复:第一问"]
    assert observed_histories[2] == ["第二问", "回复:第二问"]
    # dept-it 完全隔离，首次调用历史为空
    assert observed_histories[3] == []

    with pytest.raises(ValueError):
        chain.invoke({"input": "缺少 session_id"})
