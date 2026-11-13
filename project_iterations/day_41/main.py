"""Day 41 平台启动入口：LangGraph 状态图、ReAct 循环与人工审批流演示 (`v0.4.0-day41`)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import build_approval_graph, build_react_graph


def main() -> None:
    """运行 Day 41 ReAct 状态图与人工审批流演示."""
    print("=" * 64)
    print("🚀 智枢企业级智能体平台 v0.4.0-day41 · LangGraph 状态机编排演示")
    print("=" * 64)

    # 1. ReAct 工具调用循环图
    react_app = build_react_graph()
    print("\n[1] ReAct 状态图 Mermaid 拓扑：")
    print(react_app.to_mermaid())

    print("\n[2] ReAct 流式执行：'请帮我计算 25 * 4'")
    for event in react_app.stream({"query": "请帮我计算 25 * 4", "messages": [], "iteration": 0}):
        print("  step ->", event)

    # 2. 费用报销与高风险操作审批流图
    approval_app = build_approval_graph(auto_approve_limit=1000.0)
    print("\n[3] 审批流 Mermaid 拓扑：")
    print(approval_app.to_mermaid())

    low_res = approval_app.invoke(
        {"request_id": "REQ-101", "applicant": "陈默", "action_type": "expense", "amount": 450.0, "audit_log": []}
    )
    print("\n[4] 低额度报销结果：", low_res["approval_status"], "|", low_res["execution_result"])

    high_res = approval_app.invoke(
        {
            "request_id": "REQ-102",
            "applicant": "陈默",
            "action_type": "expense",
            "amount": 3200.0,
            "human_decision": True,
            "audit_log": [],
        }
    )
    print("[5] 高额度人工审批结果：", high_res["approval_status"], "|", high_res["execution_result"])


if __name__ == "__main__":
    main()
