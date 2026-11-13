"""Day 09 平台启动入口：演示多厂商大模型统一适配器、继承多态、@property 校验与魔术方法"""
from zhishu_agent.message import ChatMessage
from zhishu_agent.models import BaseLLMModel, OpenAIModel, QwenModel


def ask_agent(model: BaseLLMModel, prompt: str) -> ChatMessage:
    """多态调用函数：不关心具体厂商实现，只要继承自 BaseLLMModel 即可统一调用。"""
    print(f"正在路由至模型 -> {model}")
    # 利用 __call__ 魔术方法直接调用实例
    return model(prompt)


def run_demo() -> None:
    """运行 Day 09 核心功能演示。"""
    print("=== 智枢平台 v0.1.0-day09：多模型统一适配器演示 ===\n")

    openai_llm = OpenAIModel(model_name="gpt-4o-mini", temperature=0.3)
    qwen_llm = QwenModel(model_name="qwen-plus", temperature=0.8, enable_search=True)

    # 1. __str__ 与 __repr__ 演示
    print(f"str(openai_llm)  -> {openai_llm}")
    print(f"repr(qwen_llm)   -> {repr(qwen_llm)}\n")

    # 2. 多态调用演示：同一函数无缝切换不同厂商模型
    for model in (openai_llm, qwen_llm):
        reply = ask_agent(model, "请用一句话解释什么是面向对象多态？")
        print(f"回复内容: {reply}\n")

    # 3. @property 温度参数校验演示
    try:
        print("尝试将温度设为非法值 2.5 ...")
        openai_llm.temperature = 2.5
    except ValueError as exc:
        print(f"成功拦截非法参数: {exc}")


if __name__ == "__main__":
    run_demo()
