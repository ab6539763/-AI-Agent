"""Day 27 演示入口：多会话记忆管理（滑动窗口、摘要压缩与 SQLite 会话隔离）。"""
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.memory import (
    RunnableWithMessageHistory,
    SQLiteChatMessageHistory,
    SummaryMemory,
    WindowMemory,
)


def mock_enterprise_chain(payload: dict) -> str:
    """模拟企业知识库问答链：回显当前输入与注入的历史消息条数。"""
    history = payload["history"]
    user_input = payload["input"]
    session_id = payload["session_id"]
    return f"[{session_id}] 已收到「{user_input}」（上下文注入 {len(history)} 条历史消息）"


def main() -> None:
    print("=" * 68)
    print("🧠 智枢企业级智能体平台 v0.3.0-day27 · 多会话记忆与隔离演示")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "zhishu_memory.db"

        def get_history(session_id: str) -> SQLiteChatMessageHistory:
            return SQLiteChatMessageHistory(session_id=session_id, db_path=db_path)

        # 1. 滑动窗口记忆演示（k=1 轮 = 最近 2 条消息）
        window_chain = RunnableWithMessageHistory(
            runnable=mock_enterprise_chain,
            get_session_history=get_history,
            memory_strategy=WindowMemory(k=1),
        )
        print("\n[1] 租户 A（财务部）开启 WindowMemory(k=1) 多轮对话：")
        print(" ->", window_chain.invoke("报销审批需要几级？", config={"configurable": {"session_id": "tenant-fin"}}))
        print(" ->", window_chain.invoke("差旅住宿标准是多少？", config={"configurable": {"session_id": "tenant-fin"}}))
        print(" ->", window_chain.invoke("发票抬头怎么填？", config={"configurable": {"session_id": "tenant-fin"}}))

        # 2. 摘要记忆与多租户隔离演示
        summary_chain = RunnableWithMessageHistory(
            runnable=mock_enterprise_chain,
            get_session_history=get_history,
            memory_strategy=SummaryMemory(max_recent_messages=2),
        )
        print("\n[2] 租户 B（研发部）开启 SummaryMemory(max_recent_messages=2)：")
        print(" ->", summary_chain.invoke("GitLab 分支规范是什么？", session_id="tenant-rd"))
        print(" ->", summary_chain.invoke("CI 流水线怎么触发？", session_id="tenant-rd"))

        print("\n[3] 验证 SQLite 持久化与会话列表：")
        sessions = SQLiteChatMessageHistory.list_sessions(db_path)
        print("   数据库中的独立会话:", sessions)
        for sid in sessions:
            msgs = get_history(sid).messages
            print(f"   - {sid}: 共持久化 {len(msgs)} 条消息")


if __name__ == "__main__":
    main()
