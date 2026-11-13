"""Day 48 平台启动入口：多 Agent 智能办公助手核心编排与 SQLite 断点恢复演示 (v0.4.0-day48)."""

import json
import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import OfficeSupervisor, OfficeWorkspace, SQLiteCheckpointer


def main() -> None:
    """运行 Day 48 多 Agent 智能办公助手端到端演示."""
    print("=" * 72)
    print("🏢 智枢企业级智能体平台 v0.4.0-day48 · 多 Agent 智能办公助手（Part 1）")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "office_checkpoints.db"
        workspace = OfficeWorkspace()
        checkpointer = SQLiteCheckpointer(db_path)
        supervisor = OfficeSupervisor(
            workspace=workspace,
            checkpointer=checkpointer,
            interrupt_before={"create_meeting", "send_email"},
        )

        # 场景 1：多 Agent 协同（调研 -> 预约会议[中断1] -> 起草并发送邮件[中断2]）
        print("\n[场景 1] 启动协同任务：调研 Q4 战略文档 + 预约评审会议 + 发送邮件通知...")
        res1 = supervisor.run(
            "请调研公司 Q4 AI 战略文档，帮我预约明天下午的评审会议，并发送邮件通知张工和林晓。",
            thread_id="demo-thread-001",
        )
        print("当前状态:", res1["status"])
        print("挂起高危动作:", json.dumps(res1["pending_action"], ensure_ascii=False))

        # 人工审批通过第一个中断（create_meeting），并微调会议时间
        print("\n[审批 1] 人工批准 create_meeting（微调开始时间为 16:30）...")
        res2 = supervisor.resume(
            "demo-thread-001",
            approved=True,
            modified_args={"start_time": "16:30"},
            feedback="避开 16:00 冲突",
        )
        print("当前状态:", res2["status"])
        print("下一个挂起动作:", res2["pending_action"]["tool_name"], "| 草稿内容已自动汇总前序结果")

        # 人工审批通过第二个中断（send_email）
        print("\n[审批 2] 人工批准 send_email...")
        res3 = supervisor.resume("demo-thread-001", approved=True, feedback="确认收件人与正文无误")
        print("最终状态:", res3["status"])
        print("最终回复:\n" + res3["final_response"])
        print("SQLite 检查点数量:", len(supervisor.get_history("demo-thread-001")))

        # 场景 2：人工拒绝高危发送操作
        print("\n[场景 2] 演示高危操作人工拒绝（approved=False）...")
        res_rej_start = supervisor.run(
            "请发送邮件通知全员下周放假",
            thread_id="demo-thread-002",
        )
        print("挂起动作:", res_rej_start["pending_action"]["tool_name"])
        res_rej_end = supervisor.resume(
            "demo-thread-002",
            approved=False,
            feedback="未收到行政正式红头文件，禁止发送",
        )
        print("拒绝后状态:", res_rej_end["status"], "| 说明:", res_rej_end["final_response"])


if __name__ == "__main__":
    main()
