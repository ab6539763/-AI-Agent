"""Day 20 平台启动入口：多模态消息构造与 Embedding 语义 FAQ 检索演示 (v0.2.0-day20)"""
import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.embeddings import (
    build_multimodal_message,
    cosine_similarity,
    create_default_faq_matcher,
)


def run_demo() -> None:
    """运行多模态消息封装与语义 FAQ Top-K 检索演示。"""
    print("=" * 64)
    print("🤖 智枢企业级智能体平台 v0.2.0-day20 · Multimodal & Embedding")
    print("=" * 64)

    # 1. 多模态 Vision 消息构建演示
    mm_msg = build_multimodal_message(
        text="请识别这张报销发票上的金额与开票日期。",
        image_url="https://example.xingchen.local/assets/invoice_demo.png",
        detail="high",
    )
    print("\n[1] 多模态 Vision 消息载荷:")
    print(json.dumps(mm_msg, ensure_ascii=False, indent=2))

    # 2. 语义相似度与 FAQ 检索演示
    matcher = create_default_faq_matcher(dimensions=128)
    vec_a = matcher.model.embed("出差发票怎么报销")
    vec_b = matcher.model.embed("差旅费用和发票怎么提交报销？")
    vec_c = matcher.model.embed("今天中午食堂吃什么")
    print(f"\n[2] 余弦相似度对比:")
    print(f"    同义句 ('出差发票怎么报销' vs '差旅费用和发票怎么提交报销？'): {cosine_similarity(vec_a, vec_b):.4f}")
    print(f"    无关句 ('出差发票怎么报销' vs '今天中午食堂吃什么'):           {cosine_similarity(vec_a, vec_c):.4f}")

    queries = [
        "出差回来发票去哪里报销？",
        "忘记内网 VPN 密码了怎么办？",
        "我想休年假怎么在系统申请？",
    ]
    print(f"\n[3] 语义 FAQ Top-2 检索结果（共索引 {len(matcher)} 条知识）:")
    for q in queries:
        print(f"\n  [提问] {q}")
        matches = matcher.search(q, top_k=2)
        for rank, m in enumerate(matches, start=1):
            print(f"    Top-{rank} (score={m.score:.4f}) [{m.category}] {m.question}")
            print(f"           -> {m.answer}")


if __name__ == "__main__":
    run_demo()
