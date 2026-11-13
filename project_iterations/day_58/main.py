"""智枢企业级智能体平台 Day 58 主程序入口 (v1.0.0-day58)."""

from __future__ import annotations

from zhishu_agent import (
    CAPSTONE_TOPICS,
    TechnicalProposal,
    create_sample_proposal,
    review_proposal,
)


def run_demo() -> None:
    print(f"=== 1. 毕业项目 8 大行业赛道总览（共 {len(CAPSTONE_TOPICS)} 个）===")
    for idx, topic in enumerate(CAPSTONE_TOPICS.values(), start=1):
        print(f"{idx}. [{topic.domain}] {topic.name} ({topic.topic_id}) -> 核心护栏: {topic.key_guardrails[0]}")

    print("\n=== 2. 完整开题提案评审示例（法律咨询助手）===")
    good_proposal = create_sample_proposal("法律咨询助手", author="陈默")
    good_res = review_proposal(good_proposal)
    print(f"状态: {good_res.status} | 总分: {good_res.overall_score}/100")
    print(f"评审结论: {good_res.summary}")

    print("\n=== 3. 残缺开题提案拦截示例 ===")
    draft_proposal = TechnicalProposal(
        project_title="草稿版财报助手",
        author="实习生小王",
        topic_name="企业财报分析系统",
        problem_statement="快速汇总上市公司年报关键指标。",
        knowledge_sources=["上市公司年报 PDF"],
    )
    draft_res = review_proposal(draft_proposal)
    print(f"状态: {draft_res.status} | 总分: {draft_res.overall_score}/100")
    print("阻塞项:")
    for issue in draft_res.blocking_issues:
        print(f"  - {issue}")


if __name__ == "__main__":
    run_demo()
