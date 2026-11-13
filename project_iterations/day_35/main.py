"""Day 35 平台启动入口：LlamaIndex 核心流水线与 LangChain 对比演示 (v0.3.0-day35)."""
from pathlib import Path
import sys
import tempfile

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    format_framework_comparison,
)


def main() -> None:
    """演示 SimpleDirectoryReader -> VectorStoreIndex -> QueryEngine / ChatEngine 全链路."""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day35 · LlamaIndex 框架与 LangChain 对比")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmpdir:
        kb_dir = Path(tmpdir)
        (kb_dir / "hr_leave.md").write_text(
            "星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。\n"
            "申请年假需提前3个工作日在 OA 系统提交主管审批。",
            encoding="utf-8",
        )
        (kb_dir / "travel_policy.md").write_text(
            "差旅报销标准：一线城市酒店住宿报销上限每晚600元，二线城市每晚450元，均需提供电子发票。",
            encoding="utf-8",
        )
        (kb_dir / "redis_ops.txt").write_text(
            "生产环境 Redis 集群严禁执行 KEYS * 命令，排查键空间请使用 SCAN 分批遍历。",
            encoding="utf-8",
        )

        # 1. SimpleDirectoryReader 加载文档
        docs = SimpleDirectoryReader(kb_dir).load_data()
        print(f"\n[1] SimpleDirectoryReader 加载文档数: {len(docs)}")

        # 2. VectorStoreIndex 构建索引
        index = VectorStoreIndex.from_documents(docs, chunk_size=120, chunk_overlap=20)
        print(f"[2] VectorStoreIndex 切分并索引 Node 数: {len(index.nodes)}")

        # 3. QueryEngine 单轮精准问答
        query_engine = index.as_query_engine(similarity_top_k=2, response_mode="compact")
        q_res = query_engine.query("生产环境 Redis 集群禁止执行什么命令？")
        print(f"\n[3] QueryEngine 单轮问答:\n    回答: {q_res.response}")
        print(f"    溯源:\n{q_res.format_sources()}")

        # 4. ChatEngine 多轮上下文对话
        chat_engine = index.as_chat_engine(similarity_top_k=2)
        c1 = chat_engine.chat("星辰数科入职满1年员工有多少天年假？")
        c2 = chat_engine.chat("申请它需要提前几天？")
        print(f"\n[4] ChatEngine 多轮对话:")
        print(f"    Turn 1 回答: {c1.response}")
        print(f"    Turn 2 改写后检索词: {c2.metadata.get('condensed_query')}")
        print(f"    Turn 2 回答: {c2.response}")

    # 5. LangChain vs LlamaIndex 架构对比
    print("\n" + format_framework_comparison(use_case="hybrid"))


if __name__ == "__main__":
    main()
