"""Day 08 平台启动入口：演示 OOP ChatMessage 消息建模、校验、Token 估算与会话持久化"""
import tempfile
from pathlib import Path

from zhishu_agent.json_parser import load_session_json, save_session_json
from zhishu_agent.message import ChatMessage
from zhishu_agent.profile import get_environment_info


def run_demo() -> None:
    """运行 Day 08 核心功能演示"""
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day08 | Python {env['python_version']}")

    # 1. 静态方法：在创建对象前先校验角色字符串是否合法
    print("\n[角色校验]")
    for candidate in ("system", "user", "assistant", "tool", "admin"):
        print(f"  - 角色 {candidate!r:11s} -> 合法? {ChatMessage.is_valid_role(candidate)}")

    # 2. 实例化 ChatMessage 对象，并调用实例方法估算 Token
    messages = [
        ChatMessage(role="system", content="你是星辰数科智枢平台企业级 AI 助手。"),
        ChatMessage(role="user", content="请帮我查询上海今天的气温。", name="chenmo"),
        ChatMessage(role="tool", content='{"city": "上海", "temp_c": 22}', name="query_weather"),
        ChatMessage(role="assistant", content="上海今天气温为 22°C，天气晴朗。"),
    ]

    print("\n[消息建模与 Token 估算]")
    total_tokens = 0
    for msg in messages:
        tokens = msg.estimate_tokens()
        total_tokens += tokens
        print(f"  {msg!r} -> 约 {tokens} tokens")
    print(f"  [合计] 当前对话共 {len(messages)} 条消息，预估消耗 {total_tokens} tokens")

    # 3. 结合 Day 05 的 json_parser 实现 OOP -> JSON 持久化 -> OOP 恢复
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_file = Path(tmp_dir) / "oop_session.json"
        save_session_json(session_file, [m.to_dict() for m in messages])
        loaded_dicts = load_session_json(session_file)
        restored_messages = [ChatMessage.from_dict(item) for item in loaded_dicts]
        print(f"\n[持久化往返] 已保存并恢复 {len(restored_messages)} 条 ChatMessage 实例。")
        assert restored_messages == messages


if __name__ == "__main__":
    run_demo()
