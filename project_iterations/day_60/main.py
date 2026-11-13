"""智枢企业级智能体平台 Day 60 主程序入口 (v1.0.0-day60)."""
from __future__ import annotations

import json

from zhishu_agent import CapstoneRAGEngine, KnowledgeChunk


def build_demo_corpus() -> list[KnowledgeChunk]:
    """构建星辰数科企业知识库演示切片."""
    return [
        KnowledgeChunk(
            chunk_id="kb-reimburse-01",
            doc_id="doc-fin-2026",
            title="差旅与报销管理规范",
            section="第3章 报销时效",
            source="finance_policy_2026.md",
            content="员工出差返回后需在 15 个工作日内通过智枢财务系统提交报销单，单笔超过 5000 元需部门总监与财务复核。",
        ),
        KnowledgeChunk(
            chunk_id="kb-reimburse-02",
            doc_id="doc-fin-2026",
            title="差旅与报销管理规范",
            section="第4章 发票合规",
            source="finance_policy_2026.md",
            content="电子发票需核验税号与开票日期，连号出租车票或无明细餐饮发票不予报销。",
        ),
        KnowledgeChunk(
            chunk_id="kb-sre-502",
            doc_id="doc-sre-runbook",
            title="网关与推理服务故障排查手册",
            section="ERR_502 网关超时",
            source="sre_runbook_v3.md",
            content="当线上出现 ERR_502 错误码时，优先检查 vLLM 推理 Pod 的显存占用与上游 Nginx proxy_read_timeout 配置（建议 >= 120s）。",
        ),
        KnowledgeChunk(
            chunk_id="kb-sec-pii",
            doc_id="doc-sec-compliance",
            title="大模型数据安全与脱敏准则",
            section="2.1 PII 脱敏要求",
            source="security_compliance.md",
            content="所有进入大模型推理链路的身份证号、银行卡号与手机号必须经过网关脱敏，审计日志严禁落盘明文 PII。",
        ),
    ]


def run_demo() -> None:
    engine = CapstoneRAGEngine(min_confidence=0.22, max_citations=2)
    indexed = engine.index_documents(build_demo_corpus())
    print(f"已索引知识切片数量: {indexed} | 引擎配置: {engine.stats()}")

    print("\n=== 1. 高置信度业务问答（带行内引用）===")
    res1 = engine.query("员工出差报销单需要在多少个工作日内提交？超过5000元怎么审批？")
    print(res1.answer)
    print("引用详情:", json.dumps([c.to_dict() for c in res1.citations], ensure_ascii=False, indent=2))

    print("\n=== 2. 精确错误码混合检索（BM25 + Vector + RRF）===")
    res2 = engine.query("线上网关报错 ERR_502 如何排查？")
    print(res2.answer)
    print("检索追踪:", res2.trace)

    print("\n=== 3. 域外问题低置信度拒答 ===")
    res3 = engine.query("明天沪深300指数会涨多少？")
    print(f"refused={res3.refused}, confidence={res3.confidence:.4f}, reason={res3.refusal_reason}")
    print(res3.answer)


if __name__ == "__main__":
    run_demo()
