"""Day 14 核心模块：项目一《命令行多轮对话 AI 助手》(MultiTurnAssistant)"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zhishu_agent.exceptions import CommandError, ConfigurationError, ZhiShuError
from zhishu_agent.llm_client import LLMClient
from zhishu_agent.message import ChatMessage

DEFAULT_SYSTEM_PROMPT = (
    "你是智枢企业级智能体平台（ZhiShu-Agent）的 AI 研发助手，回答简洁、准确、专业。"
)


@dataclass
class AssistantStats:
    """会话统计信息快照。"""

    turns: int
    total_messages: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model_name: str
    mode: str


class MultiTurnAssistant:
    """多轮对话 AI 助手：维护上下文消息列表、斜杠命令、会话持久化与异常回滚。"""

    def __init__(
        self,
        client: LLMClient | None = None,
        system_prompt: str | None = DEFAULT_SYSTEM_PROMPT,
        temperature: float = 0.7,
    ) -> None:
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ConfigurationError("temperature 必须为数值类型")
        if not (0.0 <= float(temperature) <= 2.0):
            raise ConfigurationError(f"temperature 必须在 [0.0, 2.0] 之间，当前为 {temperature}")

        self.client = client or LLMClient()
        self.temperature = float(temperature)
        self._system_prompt = system_prompt.strip() if isinstance(system_prompt, str) and system_prompt.strip() else None

        self.messages: list[ChatMessage] = []
        if self._system_prompt is not None:
            self.messages.append(ChatMessage(role="system", content=self._system_prompt))

        self.turns: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def ask(self, user_input: str) -> str:
        """发送一轮用户提问并维护多轮上下文；若推理失败则自动回滚未提交的用户消息。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        user_msg = ChatMessage(role="user", content=user_input.strip())
        self.messages.append(user_msg)

        try:
            response = self.client.chat_completion(
                self.messages,
                temperature=self.temperature,
            )
        except ZhiShuError:
            # 异常恢复：回滚刚才追加的 user 消息，避免对话历史出现孤立提问
            self.messages.pop()
            raise
        except Exception as exc:
            self.messages.pop()
            raise ZhiShuError(f"对话推理发生未预期错误: {exc}") from exc

        assistant_msg = ChatMessage(role="assistant", content=response.content)
        self.messages.append(assistant_msg)

        self.turns += 1
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.total_tokens += response.total_tokens
        return response.content

    def clear_history(self) -> str:
        """清空对话历史，仅保留初始 System Prompt，并重置本轮统计。"""
        system_msgs = [m for m in self.messages if m.role == "system"]
        if not system_msgs and self._system_prompt is not None:
            system_msgs = [ChatMessage(role="system", content=self._system_prompt)]

        self.messages = system_msgs[:1]
        self.turns = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        return "✅ 对话历史已清空（已保留 System Prompt）。"

    def save_session(self, file_path: str | Path) -> str:
        """将当前多轮对话历史与统计信息保存为 UTF-8 JSON 文件。"""
        path_str = str(file_path).strip()
        if not path_str:
            raise CommandError("用法: /save <文件路径>")

        target = Path(path_str)
        payload: dict[str, Any] = {
            "version": "v0.1.0-day14",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "model_name": self.client.model_name,
            "stats": {
                "turns": self.turns,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "messages": [m.to_full_dict() for m in self.messages],
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise CommandError(f"保存会话文件失败 ({target}): {exc}") from exc

        return f"💾 会话已保存至 {target}（共 {len(self.messages)} 条消息）。"

    def load_session(self, file_path: str | Path) -> str:
        """从 JSON 文件恢复多轮对话历史与统计信息。"""
        path_str = str(file_path).strip()
        if not path_str:
            raise CommandError("用法: /load <文件路径>")

        target = Path(path_str)
        if not target.exists():
            raise CommandError(f"会话文件不存在: {target}")

        try:
            raw = target.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"读取或解析会话 JSON 失败 ({target}): {exc}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise CommandError("无效的会话文件格式：缺少 messages 列表")

        try:
            restored_messages = [ChatMessage.from_dict(item) for item in data["messages"]]
        except ValueError as exc:
            raise CommandError(f"会话消息反序列化失败: {exc}") from exc

        self.messages = restored_messages
        stats = data.get("stats") or {}
        self.turns = int(stats.get("turns", sum(1 for m in restored_messages if m.role == "assistant")))
        self.prompt_tokens = int(stats.get("prompt_tokens", 0))
        self.completion_tokens = int(stats.get("completion_tokens", 0))
        self.total_tokens = int(stats.get("total_tokens", 0))
        return f"📂 已从 {target} 加载会话（共 {len(self.messages)} 条消息，{self.turns} 轮对话）。"

    def get_stats(self) -> AssistantStats:
        """返回结构化的会话统计对象。"""
        return AssistantStats(
            turns=self.turns,
            total_messages=len(self.messages),
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            model_name=self.client.model_name,
            mode="Mock 离线模拟" if self.client.is_mock else "Live 在线 API",
        )

    def format_stats(self) -> str:
        """格式化输出 /stats 统计摘要。"""
        s = self.get_stats()
        return (
            "📊 会话统计摘要\n"
            f"  - 模型与模式 : {s.model_name} ({s.mode})\n"
            f"  - 对话轮数   : {s.turns} 轮\n"
            f"  - 上下文消息 : {s.total_messages} 条\n"
            f"  - Token 消耗 : prompt={s.prompt_tokens}, completion={s.completion_tokens}, total={s.total_tokens}"
        )

    def handle_command(self, raw_command: str) -> tuple[bool, str]:
        """解析并执行斜杠指令，返回 (是否继续运行, 输出文本)。"""
        stripped = raw_command.strip()
        parts = stripped.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/clear":
            return True, self.clear_history()
        if cmd == "/save":
            return True, self.save_session(arg)
        if cmd == "/load":
            return True, self.load_session(arg)
        if cmd == "/stats":
            return True, self.format_stats()
        if cmd in ("/exit", "/quit"):
            return False, "👋 再见！感谢使用智枢智能体平台。"
        if cmd == "/help":
            return True, (
                "🛠️ 可用斜杠指令：\n"
                "  /clear        清空对话历史（保留 System Prompt）\n"
                "  /save <path>  保存当前会话为 JSON 文件\n"
                "  /load <path>  从 JSON 文件恢复会话\n"
                "  /stats        查看对话轮数与 Token 消耗统计\n"
                "  /help         显示本帮助信息\n"
                "  /exit         退出命令行助手"
            )

        raise CommandError(f"未知指令: {cmd}，输入 /help 查看可用指令")

    def process_input(self, user_input: str) -> tuple[bool, str]:
        """统一入口：自动区分斜杠指令与普通对话输入。"""
        stripped = user_input.strip()
        if not stripped:
            return True, ""
        if stripped.startswith("/"):
            return self.handle_command(stripped)
        reply = self.ask(stripped)
        return True, reply
