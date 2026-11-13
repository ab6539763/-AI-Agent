"""Day 36 平台启动入口：里程碑项目 2 Part 1 — 企业知识库问答系统后端演示 (v0.3.0-day36)."""
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import EnterpriseKBService


def main() -> None:
    """演示多格式文档入库、混合检索+重排、带引用问答与 SQLite 会话持久化."""
    print("=" * 68)
    print("🚀 智枢企业级智能体平台 v0.3.0-day36 · 里程碑项目 2 Part 1: 企业知识库后端")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        txt_file = tmp_dir / "hr_policy.txt"
        txt_file.write_text(
            "星辰数科员工年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。\n"
            "申请年假需提前3个工作日在 OA 系统提交审批。",
            encoding="utf-8",
        )

        md_file = tmp_dir / "sre_runbook.md"
        md_file.write_text(
            "# Redis 生产运维规范\n"
            "生产环境 Redis 集群严禁执行 KEYS * 命令，应使用 SCAN 命令分批遍历。\n\n"
            "## 故障应急码 ERR_502\n"
            "出现网关 ERR_502 时，请优先检查上游 Pod 健康状态并执行滚动重启。",
            encoding="utf-8",
        )

        csv_file = tmp_dir / "travel_budget.csv"
        csv_file.write_text(
            "城市等级,住宿上限,餐饮补贴\n"
            "一线城市,600元/晚,150元/天\n"
            "二线城市,450元/晚,120元/天\n",
            encoding="utf-8",
        )

        kb = EnterpriseKBService(db_path=tmp_dir / "kb_sessions.db", chunk_size=200, chunk_overlap=30)
        try:
            for f in (txt_file, md_file, csv_file):
                res = kb.ingest_file(f)
                print(f"📄 已入库: {res.source} ({res.file_type}) -> {res.num_chunks} 个切片")

            session_id = "demo-session-001"
            questions = [
                "生产环境 Redis 集群出现 ERR_502 或者要遍历 key 该怎么办？",
                "一线城市差旅住宿报销上限是多少？",
                "公司食堂今天中午吃什么？",
            ]
            for q in questions:
                print(f"\n❓ 用户提问: {q}")
                resp = kb.ask(q, session_id=session_id, top_k=2)
                print(f"🤖 grounded={resp.grounded}")
                print(resp.format_with_sources())

            history = kb.get_session_history(session_id)
            print(f"\n💾 SQLite 会话 [{session_id}] 共持久化 {len(history)} 条消息记录。")
        finally:
            kb.close()


if __name__ == "__main__":
    main()
