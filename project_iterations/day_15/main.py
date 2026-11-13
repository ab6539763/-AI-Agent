"""Day 15 平台演示入口：大模型 Token 估算与企业级 API 成本对比 (v0.2.0-day15)"""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.tokenizer import compare_models_cost, estimate_tokens


def main() -> None:
    """运行 Token 估算与多模型成本横向对比演示。"""
    sample_prompt = (
        "请作为星辰数科企业架构师，评估将客服知识库迁移至 RAG 架构的技术方案，"
        "并列出 Transformer 注意力机制的关键优势。"
    )
    sample_completion = (
        "好的，基于企业级 RAG 架构评估建议如下：\n"
        "1. Self-Attention 并行计算大幅提升长文本检索与上下文理解能力；\n"
        "2. 结合 DeepSeek-V3 与向量数据库可显著降低 API 调用成本。"
    )

    print("=" * 72)
    print("智枢企业级智能体平台 v0.2.0-day15 · Token 估算与 API 成本核算器")
    print("=" * 72)
    print(f"Prompt 字符数: {len(sample_prompt)} | 估算 Token: {estimate_tokens(sample_prompt)}")
    print(
        f"Completion 字符数: {len(sample_completion)} | 估算 Token: {estimate_tokens(sample_completion)}"
    )
    print("-" * 72)
    print(f"{'模型名称':<20} {'厂商':<16} {'总Token':>8} {'单次USD($)':>14} {'单次RMB(¥)':>14}")
    print("-" * 72)

    for item in compare_models_cost(sample_prompt, sample_completion):
        print(
            f"{item['model']:<20} {item['provider']:<16} {item['total_tokens']:>8} "
            f"{item['total_cost_usd']:>14.6f} {item['total_cost_rmb']:>14.6f}"
        )


if __name__ == "__main__":
    main()
