"""Day 36 单元测试：EnterpriseKBService 多格式入库、混合检索+重排、引用溯源与 SQLite 会话."""
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import EnterpriseKBService


def test_multi_format_ingest_txt_md_csv(tmp_path: Path) -> None:
    """测试 .txt / .md / .csv 三种格式文件解析入库与异常格式拦截."""
    txt_file = tmp_path / "policy.txt"
    txt_file.write_text("入职满1年员工每年享有5天带薪年假。" * 15, encoding="utf-8")

    md_file = tmp_path / "ops.md"
    md_file.write_text(
        "# 网关规范\nNginx 超时时间设置为 30 秒。\n\n## 熔断策略\n错误率超过 5% 触发自动熔断。",
        encoding="utf-8",
    )

    csv_file = tmp_path / "reimburse.csv"
    csv_file.write_text(
        "城市等级,住宿上限,餐饮补贴\n一线城市,600元/晚,150元/天\n二线城市,450元/晚,120元/天\n",
        encoding="utf-8",
    )

    bad_file = tmp_path / "archive.zip"
    bad_file.write_bytes(b"PK\x03\x04")

    kb = EnterpriseKBService(db_path=tmp_path / "kb.db", chunk_size=120, chunk_overlap=20)
    try:
        r_txt = kb.ingest_file(txt_file)
        r_md = kb.ingest_file(md_file)
        r_csv = kb.ingest_file(csv_file)

        assert r_txt.file_type == ".txt"
        assert r_txt.num_chunks >= 2
        assert r_md.file_type == ".md"
        assert r_md.num_chunks == 2
        assert r_csv.file_type == ".csv"
        assert r_csv.num_chunks == 2
        assert len(kb.list_documents()) == 3

        with pytest.raises(ValueError, match="不支持的文件格式"):
            kb.ingest_file(bad_file)
        with pytest.raises(FileNotFoundError):
            kb.ingest_file(tmp_path / "missing.txt")
    finally:
        kb.close()


def test_hybrid_retrieval_rrf_and_rerank(tmp_path: Path) -> None:
    """测试 BM25 + Vector 混合检索 + RRF + Rerank 对精准术语与语义的排序能力."""
    kb = EnterpriseKBService(db_path=tmp_path / "kb.db")
    try:
        kb.ingest_text(
            "公司每周三下午在茶水间提供免费水果与咖啡。",
            source="life.txt",
            file_type=".txt",
        )
        kb.ingest_text(
            "生产环境遇到 ERR_502 网关错误时，请检查上游服务健康状态并执行滚动重启。",
            source="runbook.md",
            file_type=".md",
        )
        kb.ingest_text(
            "员工申请年假需提前3个工作日在 OA 系统提交审批。",
            source="hr.txt",
            file_type=".txt",
        )

        hits = kb.retrieve("ERR_502 网关错误怎么处理？", top_k=2, use_rerank=True)
        assert len(hits) >= 1
        assert hits[0].chunk.source == "runbook.md"
        assert "ERR_502" in hits[0].chunk.content
        assert hits[0].bm25_score > 0.0
        assert hits[0].rrf_score > 0.0
        assert hits[0].rerank_score >= hits[-1].rerank_score
    finally:
        kb.close()


def test_grounded_answer_with_citations_and_refusal(tmp_path: Path) -> None:
    """测试带引用溯源的回答生成以及无依据时的安全拒答."""
    kb = EnterpriseKBService(db_path=tmp_path / "kb.db", min_relevance_score=0.08)
    try:
        csv_file = tmp_path / "travel.csv"
        csv_file.write_text(
            "城市等级,住宿上限,电子发票要求\n一线城市,每晚600元,必须提供增值税电子发票\n",
            encoding="utf-8",
        )
        kb.ingest_file(csv_file)

        resp_ok = kb.ask("一线城市住宿上限是多少？", session_id="s-cite", top_k=2)
        assert resp_ok.grounded is True
        assert "[1]" in resp_ok.answer
        assert len(resp_ok.citations) >= 1
        assert resp_ok.citations[0].source == "travel.csv"
        assert "600" in resp_ok.citations[0].snippet

        resp_miss = kb.ask("量子计算机的量子比特退相干时间是多少？", session_id="s-cite", top_k=2)
        assert resp_miss.grounded is False
        assert resp_miss.citations == []
        assert "未检索到" in resp_miss.answer
    finally:
        kb.close()


def test_sqlite_session_persistence_and_document_delete(tmp_path: Path) -> None:
    """测试 SQLite 多轮会话持久化（跨实例重连）及文档删除."""
    db_file = tmp_path / "sessions.db"
    kb1 = EnterpriseKBService(db_path=db_file)
    doc_res = kb1.ingest_text(
        "Redis 生产环境禁止执行 KEYS * 命令，请使用 SCAN 分批遍历。",
        source="redis.md",
        file_type=".md",
    )
    kb1.ask("Redis 禁止执行什么命令？", session_id="persist-01")
    kb1.ask("应该用什么命令替代？", session_id="persist-01")
    kb1.close()

    # 重新实例化服务，验证 SQLite 会话历史依然完整可读
    kb2 = EnterpriseKBService(db_path=db_file)
    try:
        history = kb2.get_session_history("persist-01")
        assert len(history) == 4
        assert [m.role for m in history] == ["user", "assistant", "user", "assistant"]
        assert len(history[1].citations) >= 1

        sessions = kb2.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "persist-01"
        assert sessions[0]["message_count"] == 4

        kb2.clear_session("persist-01")
        assert kb2.get_session_history("persist-01") == []
    finally:
        kb2.close()

    # 测试文档删除后检索不到旧文档
    kb3 = EnterpriseKBService(db_path=tmp_path / "del.db")
    try:
        res = kb3.ingest_text("测试文档内容：内部代号 PHOENIX。", source="secret.txt")
        assert len(kb3.retrieve("PHOENIX", top_k=1)) == 1
        assert kb3.delete_document(res.doc_id) is True
        assert kb3.delete_document("non-existent") is False
        assert kb3.retrieve("PHOENIX", top_k=1) == []
    finally:
        kb3.close()
