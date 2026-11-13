"""Day 69 平台启动入口：一对一全真模拟面试引擎（技术面 + HR 面全闭环演示）。"""

from __future__ import annotations

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.mock_interview import MockInterviewEngine


def main() -> None:
    """运行完整的技术面（3轮）+ HR面（1轮）模拟面试并输出评估报告。"""
    print("=" * 72)
    print("🎙️ 智枢企业级智能体平台 v1.0.0-day69 · 一对一全真模拟面试系统")
    print("=" * 72)

    engine = MockInterviewEngine(candidate_name="陈默", target_role="AI Agent Engineer")
    first_round = engine.start_interview()
    print(f"候选人：{engine.candidate_name} | 目标岗位：{engine.target_role}")
    print(f"首轮开始：Round {first_round.round_id} - {first_round.name}（面试官：{first_round.interviewer}）\n")

    simulated_responses = [
        # Round 1: 自我介绍
        (
            "面试官您好！我叫陈默，在星辰数科担任全栈 AI 工程师。"
            "首先，我主导了『智枢企业级智能体平台』的 RAG 混合检索与 HITL 人机协同审批核心模块研发。"
            "其次，针对企业财报问答漏召回痛点，我通过 BM25 + FAISS + RRF 融合与 Cross-Encoder Rerank，"
            "将 Top-5 召回率从 71% 提升至 92%，P95 延迟控制在 165ms 以内。"
            "最后，我独立负责 FastAPI SSE 流式网关与 pytest 自动化回归体系，核心链路测试通过率 100%。"
        ),
        # Round 2: 项目深挖
        (
            "当时我们的线上痛点有两个：第一是股票代码与财务术语在纯向量检索下召回率只有 71%；"
            "第二是高风险资金划拨工具存在 Agent 幻觉越权风险。"
            "我的职责是主导检索与安全网关重构。首先，我设计了 BM25 与 Dense 双路召回加 RRF 倒数秩融合，"
            "并在 Rerank 前引入引用溯源；其次，基于 FastAPI SSE 与 SQLite 状态机实现 HITL 审批闭环，"
            "在工具调用前做 PII 脱敏与幂等校验。"
            "最终结果是 Top-5 召回率提升至 92%，高风险操作 100% 强制人工复核，重复审批拦截率达到 100%。"
        ),
        # Round 3: 场景手撕/架构
        (
            "针对并发重复提交与下游 LLM 超时问题，我采用三层容错架构。"
            "首先，在接口层使用基于请求指纹的幂等 Token 与 SQLite 状态机（pending -> approved/rejected），"
            "状态迁移使用原子条件更新，确保并发下时间复杂度 O(1) 判重。"
            "其次，在下游 LLM 调用层设计熔断与降级策略：当 60s 内超时率超过 20% 或 P95 超过 3s 时触发熔断，"
            "自动降级到本地缓存或轻量规则兜底，避免线程池雪崩。"
            "最后，我反思当前单机 SQLite 在多实例扩展时存在锁竞争边界，后续演进已规划切换为 Redis 分布式锁。"
        ),
        # Round 4: 行为面试 HR 面
        (
            "当时我们在推进 HITL 审批改造时，产品同学希望先跳过幂等校验以赶在周五大促上线，而我认为这有资损风险。"
            "我负责该模块的安全底线，因此首先我没有情绪化争执，而是用 30 分钟用 pytest 复现了并发重复审批导致双倍划拨的测试案例。"
            "其次，我主动提出折中方案：当天加班先用轻量 SQLite 唯一索引实现核心幂等，非核心日志埋点延后到下周迭代。"
            "最终我们按期上线且零线上事故。事后我也复盘反思：自己前期沟通需求边界不够前置，之后我在 PRD 评审阶段就主动拉齐风险清单。"
        ),
    ]

    for resp in simulated_responses:
        spec = engine.current_round()
        assert spec is not None
        print(f"▶ Round {spec.round_id} [{spec.name}] ({spec.category.upper()}) | 面试官：{spec.interviewer}")
        print(f"  提问：{spec.prompt}")
        turn = engine.submit_response(resp)
        print(
            f"  得分：{turn.weighted_score:.1f} | "
            f"Clarity={turn.scores.clarity:.0f}, Tech={turn.scores.technical_depth:.0f}, "
            f"STAR={turn.scores.star_structure:.0f}, Honesty={turn.scores.honesty_ownership:.0f}\n"
        )

    report = engine.generate_feedback()
    print("-" * 72)
    print(report.format_markdown())


if __name__ == "__main__":
    main()
