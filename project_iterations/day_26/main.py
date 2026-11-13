"""Day 26 平台演示入口：LCEL 表达式语言与多阶段可组合管道 (v0.3.0-day26)。"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    MockChatModel,
    PromptTemplate,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
    StrOutputParser,
    build_translate_polish_summary_chain,
)


def main() -> None:
    """演示 LCEL 基础管道、并行分支与 3 阶段「翻译 -> 润色 -> 摘要」链。"""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day26 · LCEL 可组合管道引擎")
    print("=" * 68)

    # 1. 基础 Prompt | Model | Parser
    prompt = PromptTemplate("请用一句话介绍：{topic}")
    model = MockChatModel()
    parser = StrOutputParser()
    basic_chain = prompt | model | parser
    print("\n[1] Prompt | Model | StrOutputParser:")
    print("   ->", basic_chain.invoke({"topic": "LCEL 管道运算符"}))

    # 2. RunnableParallel + RunnablePassthrough
    parallel_chain = RunnableParallel(
        original=RunnablePassthrough(),
        upper=RunnableLambda(lambda x: x["text"].upper()),
        length=lambda x: len(x["text"]),
    )
    print("\n[2] RunnableParallel 并行分支:")
    print("   ->", parallel_chain.invoke({"text": "ZhiShu LCEL"}))

    # 3. 3 阶段「翻译 -> 润色 -> 摘要」LCEL 链
    print("\n[3] 3 阶段「翻译 -> 润色 -> 摘要」LCEL 链:")
    pipeline = build_translate_polish_summary_chain()
    result = pipeline.invoke(
        {
            "source_text": (
                "ZhiShu Enterprise Agent Platform supports composable pipelines, "
                "automated operations, and secure data analytics."
            )
        }
    )
    print("   - 阶段1 翻译:", result["translated_text"])
    print("   - 阶段2 润色:", result["polished_text"])
    print("   - 阶段3 结构化摘要 (Pydantic):", result["final_summary"].model_dump())


if __name__ == "__main__":
    main()
