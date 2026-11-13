"""Day 66 单元测试：STAR 简历生成器与 GitHub README 质量检查器。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.portfolio_builder import (
    STARBullet,
    audit_github_readme,
    audit_resume_bullets,
    format_star_bullet,
    generate_resume_markdown,
)


def test_star_bullet_formatting_and_validation() -> None:
    """验证 STARBullet 格式化输出与空字段校验。"""
    bullet = STARBullet(
        situation="企业财报检索存在长尾术语漏召回",
        task="搭建混合检索与引用溯源模块",
        action="设计 BM25 + 向量 RRF 融合链路",
        result="Top-5 召回率提升至 92%，P95 延迟 165ms",
        tech_stack=["RAG", "BM25", "RRF"],
        role_tags=["RAG Engineer"],
    )
    formatted = format_star_bullet(bullet)
    assert "针对企业财报检索存在长尾术语漏召回" in formatted
    assert "Top-5 召回率提升至 92%" in formatted
    assert "RAG / BM25 / RRF" in formatted
    assert bullet.has_quantified_metrics() is True

    invalid = STARBullet(situation="背景", task="", action="做了优化", result="提升了 10%")
    with pytest.raises(ValueError):
        format_star_bullet(invalid)


def test_audit_resume_bullets_flags_vague_and_passes_quantified() -> None:
    """验证简历质检器能准确拦截无指标/无技术词的空洞描述，并放行高质量 STAR 条目。"""
    vague_bullet = "负责公司智能体开发，参与了日常接口联调，效果不错。"
    strong_bullet = (
        "主导搭建基于 FastAPI SSE 与 HITL 状态机的企业级审批网关，"
        "实现高风险动作 100% 人工复核，P99 响应延迟降至 120ms，pytest 覆盖率达 95%。"
    )
    report = audit_resume_bullets([vague_bullet, strong_bullet])

    assert report.total_bullets == 2
    assert report.flagged_bullets == 1
    assert report.passed_bullets == 1

    vague_item = report.items[0]
    assert vague_item.passed is False
    assert vague_item.has_metrics is False
    assert vague_item.has_tech_keywords is False
    assert len(vague_item.issues) >= 2

    strong_item = report.items[1]
    assert strong_item.passed is True
    assert strong_item.has_metrics is True
    assert "FastAPI" in strong_item.detected_tech_keywords
    assert "HITL" in strong_item.detected_tech_keywords


def test_audit_github_readme_complete_vs_incomplete() -> None:
    """验证 GitHub README 完整性评分（满分 100 vs 缺失章节扣分）。"""
    complete_readme = """
# ZhiShu-Agent
![Demo](assets/demo.gif)

## Architecture
```mermaid
flowchart LR
  User --> FastAPI --> Agent
```

## Quickstart
```bash
pip install -r requirements.txt
pytest -v
```

## API Docs
- `POST /api/v1/capstone/chat/stream`

## Benchmarks
- Recall@5: 92%, P95 Latency: 165ms

## License
MIT License
"""
    full_report = audit_github_readme(complete_readme)
    assert full_report.score == 100
    assert full_report.grade == "A"
    assert full_report.passed is True
    assert full_report.missing_sections == []

    sparse_readme = "# My Project\nJust some python scripts."
    sparse_report = audit_github_readme(sparse_readme)
    assert sparse_report.score == 0
    assert sparse_report.grade == "D"
    assert sparse_report.passed is False
    assert len(sparse_report.missing_sections) == 6


def test_generate_resume_markdown_role_tailoring() -> None:
    """验证面向不同目标岗位（Agent / RAG / AI Application）的定制简历生成与排序。"""
    rag_bullet = STARBullet(
        situation="财报长文档问答准确率偏低",
        task="重构混合检索管道",
        action="落地 BM25 + FAISS + RRF 融合与 Cross-Encoder Rerank",
        result="Recall@5 从 70% 提升至 93%",
        tech_stack=["RAG", "BM25", "FAISS", "RRF", "Rerank"],
        role_tags=["RAG Engineer"],
    )
    agent_bullet = STARBullet(
        situation="多工具调用存在越权风险",
        task="设计 HITL 人工审批与 MCP 沙箱网关",
        action="基于 LangGraph 与 FastAPI SSE 实现挂起恢复与幂等审批",
        result="越权拦截率达 100%，审批平均耗时缩短 45%",
        tech_stack=["Agent", "HITL", "MCP", "LangGraph", "SSE"],
        role_tags=["Agent Engineer"],
    )

    agent_md = generate_resume_markdown(
        candidate_name="陈默",
        target_role="Agent Engineer",
        bullets=[rag_bullet, agent_bullet],
    )
    assert "# 陈默 — 大模型智能体工程师 (Agent Engineer)" in agent_md
    assert agent_md.index("HITL 人工审批") < agent_md.index("混合检索管道")

    rag_md = generate_resume_markdown(
        candidate_name="陈默",
        target_role="RAG工程师",
        bullets=[rag_bullet, agent_bullet],
    )
    assert "# 陈默 — 检索增强生成工程师 (RAG Engineer)" in rag_md
    assert rag_md.index("混合检索管道") < rag_md.index("HITL 人工审批")


def test_generate_resume_markdown_invalid_inputs() -> None:
    """验证非法岗位或空候选人时的防御性异常。"""
    bullet = STARBullet(
        situation="高并发对话场景",
        task="优化网关吞吐",
        action="引入 FastAPI 异步流式推送",
        result="QPS 提升 3 倍",
        tech_stack=["FastAPI", "SSE"],
    )
    with pytest.raises(ValueError):
        generate_resume_markdown("陈默", "Unknown Role", [bullet])

    with pytest.raises(ValueError):
        generate_resume_markdown("", "AI Application Engineer", [bullet])
