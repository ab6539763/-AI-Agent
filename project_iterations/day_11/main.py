"""Day 11 平台启动入口：演示基于标准库的知识库文档扫描与 CSV/JSON 报告导出"""
import tempfile
from pathlib import Path

from zhishu_agent.doc_scanner import DocScanner


def _prepare_sample_kb(base_dir: Path) -> Path:
    """在临时目录中创建示例企业知识库文档，用于离线演示。"""
    kb_dir = base_dir / "knowledge_base"
    (kb_dir / "architecture").mkdir(parents=True, exist_ok=True)

    (kb_dir / "rag_intro.md").write_text(
        "# 智枢平台 RAG 架构简介\n"
        "RAG（检索增强生成）结合了向量检索与大语言模型。\n"
        "在构建 RAG 管线时，文档切片与 Embedding 是核心环节。\n",
        encoding="utf-8",
    )
    (kb_dir / "architecture" / "agent_design.txt").write_text(
        "ZhiShu Agent 平台采用多智能体协作架构。\n"
        "Agent 通过 Tool 调用检索 RAG 知识库，提升问答准确率。\n",
        encoding="utf-8",
    )
    (kb_dir / "ignore_me.py").write_text(
        "# 非文本文档应被自动跳过\nprint('RAG Agent')\n",
        encoding="utf-8",
    )
    return kb_dir


def run_demo() -> None:
    """运行 Day 11 文档扫描与报告导出完整演示。"""
    print("=== 智枢平台 v0.1.0-day11：文档扫描与 RAG 预处理演示 ===\n")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        kb_dir = _prepare_sample_kb(tmp_dir)
        out_dir = tmp_dir / "reports"

        scanner = DocScanner(case_sensitive=False, whole_word=False)
        keywords = ["RAG", "Agent", "Embedding"]
        report = scanner.scan(kb_dir, keywords=keywords, recursive=True)

        print(f"扫描目录: {report.root_dir}")
        print(f"扫描时间: {report.scanned_at}")
        print(f"命中文档数: {report.total_files} | 总字节数: {report.total_size_bytes} | 总命中次数: {report.total_hits}")
        print(f"关键词总频次: {report.keyword_totals}\n")

        for item in report.files:
            print(
                f"  - {item.relative_path} ({item.size_bytes}B, {item.line_count}行) "
                f"-> hits={item.total_hits} {item.keyword_counts}"
            )

        json_path = scanner.export_json(report, out_dir / "scan_report.json")
        csv_path = scanner.export_csv(report, out_dir / "scan_report.csv")
        print(f"\n已导出 JSON 报告: {json_path.name} ({json_path.stat().st_size} bytes)")
        print(f"已导出 CSV 报告 : {csv_path.name} ({csv_path.stat().st_size} bytes)")


if __name__ == "__main__":
    run_demo()
