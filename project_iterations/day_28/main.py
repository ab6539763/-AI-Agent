"""Day 28 演示入口：企业级文档加载与智能文本切分流水线 (v0.3.0-day28)。"""
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.document_loader import (
    CSVLoader,
    MarkdownHeaderTextSplitter,
    MarkdownLoader,
    RecursiveCharacterTextSplitter,
    TextLoader,
)


def main() -> None:
    """使用临时目录演示多种格式文档加载与多策略切分流程。"""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day28 · RAG Step 1: 文档加载与文本切分")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        txt_path = base / "policy.txt"
        txt_path.write_text(
            "星辰数科员工差旅报销规范。\n\n"
            "第一条：出差前需在 OA 系统提交申请。审批通过后方可预订机票与酒店。\n"
            "第二条：发票抬头必须为星辰数科有限公司。电子发票需在归来后 7 个工作日内上传。",
            encoding="utf-8",
        )

        md_path = base / "rag_guide.md"
        md_path.write_text(
            "# 智枢 RAG 架构指南\n\n"
            "## 1. 文档加载\n支持 TXT、Markdown 与 CSV 结构化数据接入。\n\n"
            "## 2. 文本切分\n```python\n# 代码块中的注释不会被误识别为标题\nchunk_size = 500\n```\n"
            "推荐使用 RecursiveCharacterTextSplitter 保持语义完整。",
            encoding="utf-8",
        )

        csv_path = base / "faq.csv"
        csv_path.write_text(
            "id,question,answer\n"
            "1,如何重置VPN密码,请访问内网自助门户点击忘记密码\n"
            "2,报销审批周期多久,通常为3个工作日内完成打款\n",
            encoding="utf-8",
        )

        txt_docs = TextLoader(txt_path).load()
        md_docs = MarkdownLoader(md_path).load()
        csv_docs = CSVLoader(csv_path).load()
        print(f"[加载完成] TXT={len(txt_docs)} 篇, MD={len(md_docs)} 篇, CSV={len(csv_docs)} 条")

        recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=45, chunk_overlap=10
        )
        txt_chunks = recursive_splitter.split_documents(txt_docs)
        print(f"\n[RecursiveCharacterTextSplitter] 切分 TXT 得到 {len(txt_chunks)} 个 Chunk:")
        for doc in txt_chunks:
            print(f"  - chunk#{doc.metadata['chunk_index']}: {doc.page_content!r}")

        md_splitter = MarkdownHeaderTextSplitter()
        md_chunks = md_splitter.split_documents(md_docs)
        print(f"\n[MarkdownHeaderTextSplitter] 切分 MD 得到 {len(md_chunks)} 个 Chunk:")
        for doc in md_chunks:
            print(f"  - meta={doc.metadata} | content={doc.page_content!r}")


if __name__ == "__main__":
    main()
