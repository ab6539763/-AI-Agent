"""Day 25 平台启动入口：LangChain 统一多模型网关演示 (v0.3.0-day25)。"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import ChatPromptTemplate, get_chat_model


def main() -> None:
    """演示同一套 ChatPromptTemplate 无缝切换 DeepSeek 与 Qwen 模型。"""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day25 · LangChain 统一模型网关")
    print("=" * 68)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是星辰数科的企业级 AI 架构师，专注 {domain} 领域。"),
            ("human", "请用一句话说明为什么需要引入 {topic}？"),
        ]
    )

    prompt_value = prompt.invoke(
        {"domain": "大模型网关", "topic": "LangChain BaseChatModel 统一抽象"}
    )

    print("\n--- 1. 格式化后的标准消息序列 ---")
    print(prompt_value.to_string())

    for provider in ("deepseek", "qwen"):
        model = get_chat_model(provider)
        reply = model.invoke(prompt_value)
        print(f"\n--- 2. 切换至厂商: {provider.upper()} ({model.model_name}) ---")
        print(reply.content)
        print("元数据:", reply.response_metadata)


if __name__ == "__main__":
    main()
