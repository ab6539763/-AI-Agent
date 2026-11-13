"""Day 28 自动化单元测试：覆盖 Document、多格式 Loader 与三类 TextSplitter。"""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.document_loader import (
    CharacterTextSplitter,
    CSVLoader,
    Document,
    MarkdownHeaderTextSplitter,
    MarkdownLoader,
    RecursiveCharacterTextSplitter,
    TextLoader,
)


def test_document_creation_and_metadata_isolation() -> None:
    """验证 Document 数据结构及默认 metadata 不会在实例间共享。"""
    d1 = Document(page_content="hello")
    d2 = Document(page_content="world")
    d1.metadata["tag"] = "a"

    assert d1.metadata == {"tag": "a"}
    assert d2.metadata == {}
    assert d1.to_dict() == {"page_content": "hello", "metadata": {"tag": "a"}}

    with pytest.raises(TypeError):
        Document(page_content=123)  # type: ignore[arg-type]


def test_text_and_markdown_loaders(tmp_path: Path) -> None:
    """验证 TextLoader 与 MarkdownLoader 的读取、元数据注入及文件缺失异常。"""
    txt_file = tmp_path / "notice.txt"
    txt_file.write_text("智枢平台发布 v0.3.0-day28。", encoding="utf-8")

    txt_docs = TextLoader(txt_file).load()
    assert len(txt_docs) == 1
    assert txt_docs[0].page_content == "智枢平台发布 v0.3.0-day28。"
    assert txt_docs[0].metadata["file_name"] == "notice.txt"
    assert txt_docs[0].metadata["loader"] == "TextLoader"

    md_file = tmp_path / "handbook.md"
    md_file.write_text("# 研发手册\n\n## 第一章\n规范说明。", encoding="utf-8")
    md_docs = MarkdownLoader(md_file).load()
    assert len(md_docs) == 1
    assert md_docs[0].metadata["title"] == "研发手册"
    assert md_docs[0].metadata["loader"] == "MarkdownLoader"

    with pytest.raises(FileNotFoundError):
        TextLoader(tmp_path / "missing.txt").load()


def test_csv_loader(tmp_path: Path) -> None:
    """验证 CSVLoader 逐行转为 Document 并正确记录行号与 source_column。"""
    csv_file = tmp_path / "kb.csv"
    csv_file.write_text(
        "doc_id,title,content\n"
        "kb-01,VPN指南,使用公司SSO登录\n"
        "kb-02,报销流程,7日内提交电子发票\n",
        encoding="utf-8",
    )

    docs = CSVLoader(csv_file, source_column="doc_id").load()
    assert len(docs) == 2
    assert "title: VPN指南" in docs[0].page_content
    assert docs[0].metadata["source"] == "kb-01"
    assert docs[0].metadata["row"] == 0
    assert docs[1].metadata["source"] == "kb-02"
    assert docs[1].metadata["row"] == 1


def test_character_text_splitter() -> None:
    """验证 CharacterTextSplitter 切分、参数校验及 metadata 保留。"""
    with pytest.raises(ValueError):
        CharacterTextSplitter(chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        CharacterTextSplitter(chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValueError):
        CharacterTextSplitter(chunk_size=100, chunk_overlap=-1)

    splitter = CharacterTextSplitter(separator="\n", chunk_size=20, chunk_overlap=5)
    text = "第一行文本内容\n第二行文本内容\n第三行文本内容\n第四行文本内容"
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 20 for c in chunks)

    doc = Document(page_content=text, metadata={"source": "memo.txt"})
    split_docs = splitter.split_documents([doc])
    assert len(split_docs) == len(chunks)
    assert split_docs[0].metadata["source"] == "memo.txt"
    assert split_docs[0].metadata["chunk_index"] == 0
    assert split_docs[0].metadata["chunk_total"] == len(chunks)
    assert "chunk_index" not in doc.metadata


def test_recursive_character_text_splitter() -> None:
    """验证 RecursiveCharacterTextSplitter 多级分隔符（含中文句号与兜底字符切分）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=30,
        chunk_overlap=6,
        separators=["\n\n", "\n", "。", " ", ""],
    )
    text = (
        "智枢平台第三阶段正式开启。\n\n"
        "文档加载器负责接入多源异构数据。文本切分器负责将长文档切分为语义完整的片段。最后交给向量库检索。"
    )
    chunks = splitter.split_text(text)
    assert len(chunks) >= 3
    assert all(len(c) <= 30 for c in chunks)
    assert chunks[0] == "智枢平台第三阶段正式开启。"

    # 无任何标点或空格的超长字符串，触发 "" 字符级兜底切分
    long_token = "A" * 65
    fallback_chunks = splitter.split_text(long_token)
    assert len(fallback_chunks) >= 3
    assert all(len(c) <= 30 for c in fallback_chunks)


def test_markdown_header_text_splitter(tmp_path: Path) -> None:
    """验证 MarkdownHeaderTextSplitter 标题层级跟踪、代码块忽略与元数据合并。"""
    md_text = (
        "# 产品设计\n"
        "总体介绍。\n"
        "## 架构设计\n"
        "模块划分说明。\n"
        "### 数据层\n"
        "使用 SQLite 与向量库。\n"
        "```python\n"
        "# 这是代码块里的注释，不是一级标题\n"
        "x = 1\n"
        "```\n"
        "## 部署指南\n"
        "使用 Docker 启动。"
    )
    splitter = MarkdownHeaderTextSplitter()
    docs = splitter.split_text(md_text)

    assert len(docs) == 4
    assert docs[0].metadata == {"Header 1": "产品设计"}
    assert "总体介绍" in docs[0].page_content

    assert docs[1].metadata == {"Header 1": "产品设计", "Header 2": "架构设计"}
    assert docs[2].metadata == {
        "Header 1": "产品设计",
        "Header 2": "架构设计",
        "Header 3": "数据层",
    }
    assert "# 这是代码块里的注释" in docs[2].page_content

    # 切换到新的 Header 2 时，旧的 Header 3 必须被清除
    assert docs[3].metadata == {"Header 1": "产品设计", "Header 2": "部署指南"}
    assert "Header 3" not in docs[3].metadata

    # 结合 MarkdownLoader.load() 测试 split_documents 元数据合并
    md_file = tmp_path / "design.md"
    md_file.write_text(md_text, encoding="utf-8")
    loaded = MarkdownLoader(md_file).load()
    merged_docs = splitter.split_documents(loaded)
    assert merged_docs[2].metadata["file_name"] == "design.md"
    assert merged_docs[2].metadata["Header 3"] == "数据层"
