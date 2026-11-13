"""Day 66 平台启动入口：STAR 法则简历生成器与 GitHub README 质量检查演示 (v1.0.0-day66)。"""

from __future__ import annotations

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.portfolio_builder import (
    STARBullet,
    audit_github_readme,
    audit_resume_bullets,
    generate_resume_markdown,
)


def main() -> None:
    """运行 STAR 简历质检、README 质量评分与三岗位简历生成示例。"""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v1.0.0-day66 · 简历与作品集打磨工具链")
    print("=" * 72)

    raw_bullets = [
        "负责公司智能体平台开发，做了 RAG 和审批功能，效果不错。",
        STARBullet(
            situation="企业财报问答中纯向量检索对股票代码与财务术语召回不足",
            task="主导搭建混合检索与引用溯源引擎",
            action="设计 BM25 + Dense Vector + RRF 倒数秩融合检索管线，并集成 Cross-Encoder Rerank",
            result="Top-5 召回率由 71% 提升至 92%，P95 检索延迟控制在 165ms 以内",
            tech_stack=["RAG", "BM25", "RRF", "Rerank", "FAISS"],
            role_tags=["RAG Engineer", "AI Application Engineer"],
        ),
        STARBullet(
            situation="高风险资金划拨与对外披露操作存在大模型幻觉越权风险",
            task="构建可挂起恢复的人机协同（HITL）审批闭环",
            action="基于 FastAPI SSE 与 SQLite 状态机实现 pending->approved/rejected 幂等流转与 PII 脱敏拦截",
            result="高风险动作 100% 强制人工复核，重复审批拦截率 100%，核心链路通过 25 项 pytest 回归",
            tech_stack=["FastAPI", "SSE", "HITL", "SQLite", "PII", "pytest"],
            role_tags=["Agent Engineer", "AI Application Engineer"],
        ),
    ]

    bullet_report = audit_resume_bullets(raw_bullets)
    print(f"\n[1/3] STAR 简历条目质检: 通过 {bullet_report.passed_bullets}/{bullet_report.total_bullets}，"
          f"平均分 {bullet_report.average_score}/100")
    for item in bullet_report.items:
        status = "✅ PASS" if item.passed else "⚠️ FLAG"
        print(f"  - #{item.index + 1} [{status} | {item.score}分] {item.text[:48]}...")
        for issue in item.issues:
            print(f"      问题: {issue}")

    sample_readme = """
# 智枢企业级智能体平台 (ZhiShu-Agent)

![Demo](docs/demo.gif)

## 系统架构
```mermaid
flowchart LR
  UI --> API[FastAPI SSE] --> Agent[Multi-Agent + HITL]
```

## 快速开始 (Quickstart)
```bash
pip install -r requirements.txt
uvicorn zhishu_agent.capstone_web:app --reload
pytest -v
```

## API 接口文档
- `POST /api/v1/capstone/chat/stream`

## 评测基线 (Benchmarks)
| 方案 | Recall@5 | P95 Latency |
| --- | --- | --- |
| Hybrid RRF | 92.0% | 165ms |

## License
MIT License
"""
    readme_report = audit_github_readme(sample_readme)
    print(f"\n[2/3] GitHub README 质量评分: {readme_report.score}/100 (等级 {readme_report.grade})")
    print(f"  摘要: {readme_report.summary}")

    star_only = [b for b in raw_bullets if isinstance(b, STARBullet)]
    resume_md = generate_resume_markdown(
        candidate_name="陈默",
        target_role="Agent Engineer",
        bullets=star_only,
        github_url="https://github.com/zhishu-ai/zhishu-agent",
    )
    print("\n[3/3] 生成 Agent Engineer 定制简历预览（前 12 行）：")
    for line in resume_md.splitlines()[:12]:
        print(f"  {line}")


if __name__ == "__main__":
    main()
