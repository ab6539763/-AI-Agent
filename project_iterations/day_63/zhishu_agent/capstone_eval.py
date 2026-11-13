"""Day 63 核心模块：智枢企业级智能体平台毕业设计 Ragas 评估与性能/成本压测优化器。

功能覆盖：
1. 离线 Ragas 风格四大核心指标：faithfulness、answer_relevancy、context_precision、citation_accuracy；
2. 性能与成本基准测试：p50_ms、p95_ms、tokens_per_req、cost_per_1k_req_cny、cache_hit_rate；
3. OptimizationAdvisor：对比 Baseline 与三重优化策略（Prompt Caching + Rerank Top-K 调优 + 模型路由），输出量化 ROI 建议与 Markdown 报告。
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, Field

VERSION = "v1.0.0-day63"

_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "请问",
        "什么",
        "如何",
        "多少",
        "the",
        "a",
        "an",
        "is",
        "are",
        "of",
        "to",
        "in",
        "for",
        "and",
        "or",
    }
)


def tokenize_mixed(text: str) -> set[str]:
    """针对中英文混合文本提取语义单元（英文/数字词 + 中文单字与双字词组）。"""
    if not text:
        return set()
    normalized = text.lower().strip()
    tokens: set[str] = set()

    for word in re.findall(r"[a-z0-9_.\-%]+", normalized):
        if word not in _STOPWORDS:
            tokens.add(word)

    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for run in cjk_runs:
        for ch in run:
            if ch not in _STOPWORDS:
                tokens.add(ch)
        for i in range(len(run) - 1):
            bigram = run[i : i + 2]
            if bigram not in _STOPWORDS:
                tokens.add(bigram)

    return tokens


def compute_faithfulness(generated_answer: str, retrieved_contexts: list[str]) -> float:
    """计算忠实度（Faithfulness）：生成答案中的事实单元被检索上下文支撑的比例。"""
    ans_tokens = tokenize_mixed(generated_answer)
    if not ans_tokens:
        return 0.0
    if not retrieved_contexts:
        return 0.0
    ctx_tokens: set[str] = set()
    for ctx in retrieved_contexts:
        ctx_tokens.update(tokenize_mixed(ctx))
    if not ctx_tokens:
        return 0.0
    supported = len(ans_tokens & ctx_tokens)
    return round(min(1.0, supported / len(ans_tokens)), 4)


def compute_answer_relevancy(
    query: str,
    generated_answer: str,
    expected_answer: str = "",
) -> float:
    """计算答案相关性（Answer Relevancy）：生成答案与用户问题及标准答案的语义对齐度。"""
    ans_tokens = tokenize_mixed(generated_answer)
    q_tokens = tokenize_mixed(query)
    if not ans_tokens or not q_tokens:
        return 0.0

    q_recall = len(ans_tokens & q_tokens) / len(q_tokens)
    if expected_answer.strip():
        exp_tokens = tokenize_mixed(expected_answer)
        if exp_tokens:
            overlap = len(ans_tokens & exp_tokens)
            precision = overlap / len(ans_tokens)
            recall = overlap / len(exp_tokens)
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
            score = 0.35 * q_recall + 0.65 * f1
            return round(min(1.0, score), 4)
    return round(min(1.0, q_recall), 4)


def _is_context_relevant(ctx: str, relevant_contexts: list[str]) -> bool:
    ctx_tokens = tokenize_mixed(ctx)
    if not ctx_tokens:
        return False
    for rel in relevant_contexts:
        rel_tokens = tokenize_mixed(rel)
        if not rel_tokens:
            continue
        overlap = len(ctx_tokens & rel_tokens)
        if overlap / min(len(ctx_tokens), len(rel_tokens)) >= 0.45:
            return True
    return False


def compute_context_precision(
    retrieved_contexts: list[str],
    relevant_contexts: list[str],
) -> float:
    """计算上下文精确率（Context Precision@K）：排序靠前的检索片段中相关证据的加权占比。"""
    if not retrieved_contexts or not relevant_contexts:
        return 0.0

    hits = 0
    precision_sum = 0.0
    for idx, ctx in enumerate(retrieved_contexts, start=1):
        if _is_context_relevant(ctx, relevant_contexts):
            hits += 1
            precision_sum += hits / idx

    if hits == 0:
        return 0.0
    return round(min(1.0, precision_sum / hits), 4)


def compute_citation_accuracy(citations: list[str], expected_citations: list[str]) -> float:
    """计算引用准确率（Citation Accuracy）：输出引用 ID 与标准引用集合的 F1 分数。"""
    pred_set = {c.strip() for c in citations if c.strip()}
    exp_set = {c.strip() for c in expected_citations if c.strip()}
    if not pred_set and not exp_set:
        return 1.0
    if not pred_set or not exp_set:
        return 0.0
    tp = len(pred_set & exp_set)
    if tp == 0:
        return 0.0
    precision = tp / len(pred_set)
    recall = tp / len(exp_set)
    return round(2 * precision * recall / (precision + recall), 4)


def compute_percentile(values: list[float], percentile: float) -> float:
    """计算有序序列的线性插值百分位数（如 P50、P95）。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(float(ordered[0]), 2)
    rank = (percentile / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(float(ordered[low]), 2)
    weight = rank - low
    interpolated = ordered[low] * (1.0 - weight) + ordered[high] * weight
    return round(float(interpolated), 2)


class PricingConfig(BaseModel):
    """模型计费配置（单位：人民币 CNY / 1,000 Tokens）。"""

    flagship_input_per_1k_cny: float = Field(default=0.02, ge=0.0)
    flagship_cached_input_per_1k_cny: float = Field(default=0.004, ge=0.0)
    flagship_output_per_1k_cny: float = Field(default=0.06, ge=0.0)
    lite_input_per_1k_cny: float = Field(default=0.002, ge=0.0)
    lite_cached_input_per_1k_cny: float = Field(default=0.0005, ge=0.0)
    lite_output_per_1k_cny: float = Field(default=0.006, ge=0.0)

    def calculate_cost_cny(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        model_tier: Literal["flagship", "lite"] = "flagship",
    ) -> float:
        """计算单次请求的模型调用成本（CNY）。"""
        effective_cached = min(max(cached_tokens, 0), max(prompt_tokens, 0))
        uncached_prompt = max(prompt_tokens - effective_cached, 0)

        if model_tier == "lite":
            in_price = self.lite_input_per_1k_cny
            cached_price = self.lite_cached_input_per_1k_cny
            out_price = self.lite_output_per_1k_cny
        else:
            in_price = self.flagship_input_per_1k_cny
            cached_price = self.flagship_cached_input_per_1k_cny
            out_price = self.flagship_output_per_1k_cny

        cost = (
            (uncached_prompt / 1000.0) * in_price
            + (effective_cached / 1000.0) * cached_price
            + (max(completion_tokens, 0) / 1000.0) * out_price
        )
        return round(cost, 6)


class EvalCase(BaseModel):
    """单条端到端评估用例。"""

    case_id: str
    query: str
    expected_answer: str
    generated_answer: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    relevant_contexts: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    latency_ms: float = Field(gt=0.0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    model_tier: Literal["flagship", "lite"] = "flagship"
    difficulty: Literal["simple", "complex"] = "complex"


class CaseScore(BaseModel):
    """单条用例的 Ragas 指标与成本明细。"""

    case_id: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    citation_accuracy: float
    ragas_score: float
    latency_ms: float
    total_tokens: int
    cost_cny: float


class PerfBenchmark(BaseModel):
    """性能与成本压测汇总指标。"""

    total_requests: int
    p50_ms: float
    p95_ms: float
    avg_ms: float
    tokens_per_req: float
    cost_per_1k_req_cny: float
    cache_hit_rate: float


class EvalReport(BaseModel):
    """智枢毕业设计端到端评估报告。"""

    profile_name: str
    total_cases: int
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_precision: float
    avg_citation_accuracy: float
    overall_ragas_score: float
    benchmark: PerfBenchmark
    case_scores: list[CaseScore]
    passed_quality_gate: bool

    def to_markdown(self) -> str:
        """生成结构化 Markdown 评估报告。"""
        gate_text = "PASS ✅" if self.passed_quality_gate else "FAIL ❌"
        lines = [
            f"# 智枢智能体平台评估报告（{self.profile_name} · {VERSION}）",
            "",
            f"- **样本总数**: `{self.total_cases}`",
            f"- **质量门禁状态**: **{gate_text}** (综合 Ragas 分数 `{self.overall_ragas_score:.4f}`)",
            "",
            "## 1. Ragas 质量指标",
            "",
            "| 指标 | 得分 | 说明 |",
            "| :--- | :---: | :--- |",
            f"| Faithfulness (忠实度) | `{self.avg_faithfulness:.4f}` | 生成内容被检索上下文支撑的比例 |",
            f"| Answer Relevancy (相关性) | `{self.avg_answer_relevancy:.4f}` | 回答与问题及标准答案的对齐度 |",
            f"| Context Precision (上下文精确率) | `{self.avg_context_precision:.4f}` | 排序靠前检索片段的证据纯度 |",
            f"| Citation Accuracy (引用准确率) | `{self.avg_citation_accuracy:.4f}` | 溯源引用 ID 的 F1 准确率 |",
            f"| **Overall Ragas Score** | **`{self.overall_ragas_score:.4f}`** | 四维核心指标综合均值 |",
            "",
            "## 2. 性能与 Token 成本基准",
            "",
            "| 基准项 | 数值 |",
            "| :--- | :---: |",
            f"| P50 延迟 | `{self.benchmark.p50_ms:.2f} ms` |",
            f"| P95 延迟 | `{self.benchmark.p95_ms:.2f} ms` |",
            f"| 平均每次请求 Token | `{self.benchmark.tokens_per_req:.1f}` |",
            f"| Prompt Cache 命中率 | `{self.benchmark.cache_hit_rate * 100:.2f}%` |",
            f"| 千次请求成本 (CNY) | `¥{self.benchmark.cost_per_1k_req_cny:.2f}` |",
        ]
        return "\n".join(lines)


class OptimizationRecommendation(BaseModel):
    """单条优化建议与 ROI 预估。"""

    strategy: str
    description: str
    estimated_cost_saving_pct: float
    estimated_latency_saving_pct: float
    quality_impact: str
    priority: Literal["P0", "P1", "P2"]


class OptimizationComparison(BaseModel):
    """Baseline 与优化方案的对比结果。"""

    baseline: EvalReport
    optimized: EvalReport
    latency_p95_reduction_pct: float
    cost_reduction_pct: float
    token_reduction_pct: float
    ragas_delta: float
    monthly_savings_cny_at_100k_req: float
    recommendations: list[OptimizationRecommendation]

    def to_markdown(self) -> str:
        """生成 Baseline vs Optimized 对比与 ROI 建议 Markdown 报告。"""
        lines = [
            f"# 智枢平台性能与成本优化对比报告（{VERSION}）",
            "",
            "## 1. 核心指标对比（Baseline vs Optimized）",
            "",
            "| 维度 | Baseline | Optimized | 变化幅度 |",
            "| :--- | :---: | :---: | :---: |",
            (
                f"| 综合 Ragas 评分 | `{self.baseline.overall_ragas_score:.4f}` | "
                f"`{self.optimized.overall_ragas_score:.4f}` | `{self.ragas_delta:+.4f}` |"
            ),
            (
                f"| P95 延迟 | `{self.baseline.benchmark.p95_ms:.2f} ms` | "
                f"`{self.optimized.benchmark.p95_ms:.2f} ms` | `-{self.latency_p95_reduction_pct:.2f}%` |"
            ),
            (
                f"| 单请求平均 Token | `{self.baseline.benchmark.tokens_per_req:.1f}` | "
                f"`{self.optimized.benchmark.tokens_per_req:.1f}` | `-{self.token_reduction_pct:.2f}%` |"
            ),
            (
                f"| Cache 命中率 | `{self.baseline.benchmark.cache_hit_rate * 100:.2f}%` | "
                f"`{self.optimized.benchmark.cache_hit_rate * 100:.2f}%` | "
                f"`+{(self.optimized.benchmark.cache_hit_rate - self.baseline.benchmark.cache_hit_rate) * 100:.2f}%` |"
            ),
            (
                f"| 千次请求成本 | `¥{self.baseline.benchmark.cost_per_1k_req_cny:.2f}` | "
                f"`¥{self.optimized.benchmark.cost_per_1k_req_cny:.2f}` | `-{self.cost_reduction_pct:.2f}%` |"
            ),
            "",
            f"> **ROI 预估**：按月均 100,000 次企业调用计算，优化后预计每月节省模型成本 **`¥{self.monthly_savings_cny_at_100k_req:.2f}`**。",
            "",
            "## 2. 落地优化建议清单",
            "",
        ]
        for rec in self.recommendations:
            lines.append(
                f"- **[{rec.priority}] {rec.strategy}**：{rec.description} "
                f"（预计降本 `{rec.estimated_cost_saving_pct:.1f}%`，降延迟 `{rec.estimated_latency_saving_pct:.1f}%`，质量影响：{rec.quality_impact}）"
            )
        return "\n".join(lines)


class CapstoneEvaluator:
    """智枢毕业设计端到端评估器。"""

    def __init__(self, pricing: PricingConfig | None = None) -> None:
        self.pricing = pricing or PricingConfig()

    def evaluate_case(self, case: EvalCase) -> CaseScore:
        faithfulness = compute_faithfulness(case.generated_answer, case.retrieved_contexts)
        relevancy = compute_answer_relevancy(
            case.query, case.generated_answer, case.expected_answer
        )
        precision = compute_context_precision(
            case.retrieved_contexts, case.relevant_contexts
        )
        citation = compute_citation_accuracy(case.citations, case.expected_citations)

        ragas_score = round(
            0.30 * faithfulness + 0.30 * relevancy + 0.25 * precision + 0.15 * citation,
            4,
        )
        total_tokens = case.prompt_tokens + case.completion_tokens
        cost_cny = self.pricing.calculate_cost_cny(
            prompt_tokens=case.prompt_tokens,
            completion_tokens=case.completion_tokens,
            cached_tokens=case.cached_tokens,
            model_tier=case.model_tier,
        )
        return CaseScore(
            case_id=case.case_id,
            faithfulness=faithfulness,
            answer_relevancy=relevancy,
            context_precision=precision,
            citation_accuracy=citation,
            ragas_score=ragas_score,
            latency_ms=case.latency_ms,
            total_tokens=total_tokens,
            cost_cny=cost_cny,
        )

    def evaluate_suite(
        self,
        cases: list[EvalCase],
        profile_name: str = "baseline",
        quality_threshold: float = 0.72,
    ) -> EvalReport:
        if not cases:
            raise ValueError("Evaluation cases must not be empty.")

        scores = [self.evaluate_case(c) for c in cases]
        n = len(scores)

        avg_f = round(sum(s.faithfulness for s in scores) / n, 4)
        avg_r = round(sum(s.answer_relevancy for s in scores) / n, 4)
        avg_p = round(sum(s.context_precision for s in scores) / n, 4)
        avg_c = round(sum(s.citation_accuracy for s in scores) / n, 4)
        overall = round(sum(s.ragas_score for s in scores) / n, 4)

        latencies = [c.latency_ms for c in cases]
        total_prompt = sum(c.prompt_tokens for c in cases)
        total_cached = sum(min(c.cached_tokens, c.prompt_tokens) for c in cases)
        total_tokens = sum(s.total_tokens for s in scores)
        total_cost = sum(s.cost_cny for s in scores)

        benchmark = PerfBenchmark(
            total_requests=n,
            p50_ms=compute_percentile(latencies, 50.0),
            p95_ms=compute_percentile(latencies, 95.0),
            avg_ms=round(sum(latencies) / n, 2),
            tokens_per_req=round(total_tokens / n, 2),
            cost_per_1k_req_cny=round((total_cost / n) * 1000.0, 4),
            cache_hit_rate=round((total_cached / total_prompt) if total_prompt > 0 else 0.0, 4),
        )

        return EvalReport(
            profile_name=profile_name,
            total_cases=n,
            avg_faithfulness=avg_f,
            avg_answer_relevancy=avg_r,
            avg_context_precision=avg_p,
            avg_citation_accuracy=avg_c,
            overall_ragas_score=overall,
            benchmark=benchmark,
            case_scores=scores,
            passed_quality_gate=overall >= quality_threshold,
        )


class OptimizationAdvisor:
    """性能与成本优化顾问：模拟并对比 Prompt Caching、Rerank Top-K 调优与模型路由。"""

    def __init__(self, evaluator: CapstoneEvaluator | None = None) -> None:
        self.evaluator = evaluator or CapstoneEvaluator()

    def simulate_optimized_cases(
        self,
        baseline_cases: list[EvalCase],
        enable_prompt_caching: bool = True,
        rerank_top_k: int = 2,
        enable_model_routing: bool = True,
    ) -> list[EvalCase]:
        """基于基线用例生成应用优化策略后的模拟压测数据集。"""
        optimized: list[EvalCase] = []
        for case in baseline_cases:
            new_contexts = list(case.retrieved_contexts)
            latency_factor = 1.0
            prompt_token_factor = 1.0

            # 1. Rerank Top-K 调优：优先保留高相关证据并裁剪尾部噪声，提升 Context Precision 并降低预填充 Token
            if rerank_top_k > 0 and len(new_contexts) > rerank_top_k:
                ranked = sorted(
                    new_contexts,
                    key=lambda ctx: 0 if _is_context_relevant(ctx, case.relevant_contexts) else 1,
                )
                kept_ratio = rerank_top_k / len(new_contexts)
                new_contexts = ranked[:rerank_top_k]
                prompt_token_factor *= 0.65 + 0.35 * kept_ratio
                latency_factor *= 0.86

            # 2. Prompt Caching：缓存系统提示词与高频制度前缀（约占 Prompt 的 55%）
            new_prompt_tokens = max(1, int(round(case.prompt_tokens * prompt_token_factor)))
            new_cached = case.cached_tokens
            if enable_prompt_caching:
                new_cached = max(new_cached, int(round(new_prompt_tokens * 0.55)))
                latency_factor *= 0.84

            # 3. 模型路由（Model Routing）：简单问答/制度检索路由至轻量级 Lite 模型
            new_tier = case.model_tier
            if enable_model_routing and case.difficulty == "simple":
                new_tier = "lite"
                latency_factor *= 0.58

            optimized.append(
                case.model_copy(
                    update={
                        "retrieved_contexts": new_contexts,
                        "prompt_tokens": new_prompt_tokens,
                        "cached_tokens": min(new_cached, new_prompt_tokens),
                        "latency_ms": round(max(45.0, case.latency_ms * latency_factor), 2),
                        "model_tier": new_tier,
                    }
                )
            )
        return optimized

    def compare(
        self,
        baseline_cases: list[EvalCase],
        enable_prompt_caching: bool = True,
        rerank_top_k: int = 2,
        enable_model_routing: bool = True,
    ) -> OptimizationComparison:
        """执行 Baseline vs Optimized 端到端对比评估。"""
        baseline_report = self.evaluator.evaluate_suite(
            baseline_cases, profile_name="Baseline"
        )
        opt_cases = self.simulate_optimized_cases(
            baseline_cases,
            enable_prompt_caching=enable_prompt_caching,
            rerank_top_k=rerank_top_k,
            enable_model_routing=enable_model_routing,
        )
        optimized_report = self.evaluator.evaluate_suite(
            opt_cases, profile_name="Optimized (Cache+Rerank+Routing)"
        )

        b_p95 = baseline_report.benchmark.p95_ms
        o_p95 = optimized_report.benchmark.p95_ms
        lat_red = round(((b_p95 - o_p95) / b_p95 * 100.0) if b_p95 > 0 else 0.0, 2)

        b_cost = baseline_report.benchmark.cost_per_1k_req_cny
        o_cost = optimized_report.benchmark.cost_per_1k_req_cny
        cost_red = round(((b_cost - o_cost) / b_cost * 100.0) if b_cost > 0 else 0.0, 2)

        b_tok = baseline_report.benchmark.tokens_per_req
        o_tok = optimized_report.benchmark.tokens_per_req
        tok_red = round(((b_tok - o_tok) / b_tok * 100.0) if b_tok > 0 else 0.0, 2)

        ragas_delta = round(
            optimized_report.overall_ragas_score - baseline_report.overall_ragas_score,
            4,
        )
        monthly_savings = round((b_cost - o_cost) * 100.0, 2)  # 100k req = 100 * 1k req

        recommendations: list[OptimizationRecommendation] = []
        if enable_prompt_caching:
            recommendations.append(
                OptimizationRecommendation(
                    strategy="Prompt Caching（系统提示词与制度前缀缓存）",
                    description="对智枢平台固定 System Prompt、合规红线清单与高频财报摘要前缀启用 KV Cache 复用。",
                    estimated_cost_saving_pct=38.0,
                    estimated_latency_saving_pct=16.0,
                    quality_impact="无损（严格等价推理）",
                    priority="P0",
                )
            )
        if enable_model_routing:
            recommendations.append(
                OptimizationRecommendation(
                    strategy="Model Routing（简单/复杂意图分级路由）",
                    description="通过轻量意图分类器将常规制度问答与单指标查询路由至 Lite 模型，复杂多跳财报分析保留 Flagship 模型。",
                    estimated_cost_saving_pct=32.0,
                    estimated_latency_saving_pct=35.0,
                    quality_impact="可控（简单任务准确率持平）",
                    priority="P0",
                )
            )
        if rerank_top_k > 0:
            recommendations.append(
                OptimizationRecommendation(
                    strategy=f"Rerank Top-{rerank_top_k} 精排裁剪",
                    description=f"混合检索后经 Cross-Encoder 精排仅保留 Top-{rerank_top_k} 高相关片段，剔除尾部噪声上下文。",
                    estimated_cost_saving_pct=20.0,
                    estimated_latency_saving_pct=14.0,
                    quality_impact="正向提升（Context Precision 显著提高）",
                    priority="P1",
                )
            )

        return OptimizationComparison(
            baseline=baseline_report,
            optimized=optimized_report,
            latency_p95_reduction_pct=lat_red,
            cost_reduction_pct=cost_red,
            token_reduction_pct=tok_red,
            ragas_delta=ragas_delta,
            monthly_savings_cny_at_100k_req=monthly_savings,
            recommendations=recommendations,
        )


def build_sample_capstone_cases() -> list[EvalCase]:
    """构建智枢企业级智能体平台 6 条典型财务与合规评估基准用例。"""
    return [
        EvalCase(
            case_id="CASE-01",
            query="星辰数科 2025 年第三季度营业收入和同比增长率是多少？",
            expected_answer="2025年第三季度营业收入为18.6亿元，同比增长24.3%。",
            generated_answer="根据财报数据，星辰数科2025年第三季度营业收入为18.6亿元，同比增长24.3%。",
            retrieved_contexts=[
                "星辰数科2025年Q3财报：第三季度营业收入为18.6亿元，同比增长24.3%，主要受企业级AI平台订阅增长驱动。",
                "员工差旅报销标准：一线城市住宿上限每日600元。",
                "星辰数科2025年Q3研发费用为3.2亿元，占营收比重17.2%。",
                "公司园区食堂工作日提供三餐补贴。",
            ],
            relevant_contexts=[
                "星辰数科2025年Q3财报：第三季度营业收入为18.6亿元，同比增长24.3%。",
            ],
            citations=["doc_q3_report#p1"],
            expected_citations=["doc_q3_report#p1"],
            latency_ms=1420.0,
            prompt_tokens=1850,
            completion_tokens=160,
            difficulty="simple",
        ),
        EvalCase(
            case_id="CASE-02",
            query="大额资金划拨超过多少金额必须触发 HITL 人工审批？",
            expected_answer="单笔资金划拨超过50万元必须触发HITL人工审批并由CFO复核。",
            generated_answer="根据内控规范，单笔资金划拨超过50万元必须触发HITL人工审批，并由CFO最终复核。",
            retrieved_contexts=[
                "企业资金内控红线：单笔资金划拨超过50万元必须触发HITL人工审批并由CFO复核。",
                "2025年Q3云基础设施成本同比下降12%。",
                "采购合同金额超过100万元需法务总监会签。",
            ],
            relevant_contexts=[
                "企业资金内控红线：单笔资金划拨超过50万元必须触发HITL人工审批并由CFO复核。",
            ],
            citations=["doc_compliance#sec3"],
            expected_citations=["doc_compliance#sec3"],
            latency_ms=1280.0,
            prompt_tokens=1620,
            completion_tokens=140,
            difficulty="simple",
        ),
        EvalCase(
            case_id="CASE-03",
            query="结合 Q3 研发投入与现金流情况，分析智枢平台的商业化健康度。",
            expected_answer="Q3研发费用3.2亿元占比17.2%，经营性现金流净额4.1亿元，商业化回款健康且具备持续研发造血能力。",
            generated_answer="星辰数科Q3研发费用为3.2亿元（占营收17.2%），同时经营性现金流净额达4.1亿元，表明智枢平台商业化回款健康，具备良好的研发自造血能力。",
            retrieved_contexts=[
                "研发投入说明：2025年Q3研发费用3.2亿元，占营收比重17.2%，重点投向多Agent编排与RAG引擎。",
                "现金流摘要：2025年Q3经营性现金流净额为4.1亿元，应收账款周转天数缩短至38天。",
                "办公用品领用需在OA系统提交申请。",
                "2024年年度团建预算执行率为92%。",
            ],
            relevant_contexts=[
                "研发投入说明：2025年Q3研发费用3.2亿元，占营收比重17.2%。",
                "现金流摘要：2025年Q3经营性现金流净额为4.1亿元，应收账款周转天数缩短至38天。",
            ],
            citations=["doc_q3_report#p4", "doc_cashflow#p2"],
            expected_citations=["doc_q3_report#p4", "doc_cashflow#p2"],
            latency_ms=2350.0,
            prompt_tokens=2600,
            completion_tokens=320,
            difficulty="complex",
        ),
        EvalCase(
            case_id="CASE-04",
            query="PII 脱敏中间件在入库前必须拦截或掩码哪些敏感字段？",
            expected_answer="必须掩码身份证号、银行卡号、手机号和个人邮箱四类PII敏感字段。",
            generated_answer="PII脱敏中间件在入库前必须对身份证号、银行卡号、手机号以及个人邮箱进行正则识别与掩码脱敏。",
            retrieved_contexts=[
                "数据安全合规规范：所有用户输入在进入LLM与SQLite存储前，必须对身份证号、银行卡号、手机号、个人邮箱进行脱敏掩码。",
                "FastAPI网关开启CORSMiddleware支持前端流式SSE调用。",
                "Prompt注入检测拦截包含忽略系统指令特征的恶意请求。",
            ],
            relevant_contexts=[
                "数据安全合规规范：所有用户输入在进入LLM与SQLite存储前，必须对身份证号、银行卡号、手机号、个人邮箱进行脱敏掩码。",
            ],
            citations=["doc_security#p2"],
            expected_citations=["doc_security#p2"],
            latency_ms=1190.0,
            prompt_tokens=1540,
            completion_tokens=135,
            difficulty="simple",
        ),
        EvalCase(
            case_id="CASE-05",
            query="如果企业客户要求私有化部署智枢平台，交付架构与SLA指标是什么？",
            expected_answer="私有化交付采用FastAPI+SQLite/PostgreSQL容器化部署，P95首字延迟低于2.5秒，可用性SLA为99.9%。",
            generated_answer="智枢平台私有化部署采用容器化FastAPI网关配合SQLite或PostgreSQL持久化存储，承诺P95延迟低于2.5秒且系统可用性SLA达到99.9%。",
            retrieved_contexts=[
                "私有化部署白皮书：支持Docker/K8s容器化交付，后端采用FastAPI与PostgreSQL/SQLite，P95响应延迟<2.5秒，可用性SLA 99.9%。",
                "前端使用fetch与ReadableStream解析SSE流式帧。",
                "年度员工体检将于11月开展。",
            ],
            relevant_contexts=[
                "私有化部署白皮书：支持Docker/K8s容器化交付，后端采用FastAPI与PostgreSQL/SQLite，P95响应延迟<2.5秒，可用性SLA 99.9%。",
            ],
            citations=["doc_deploy_sla#p1"],
            expected_citations=["doc_deploy_sla#p1"],
            latency_ms=1980.0,
            prompt_tokens=2200,
            completion_tokens=260,
            difficulty="complex",
        ),
        EvalCase(
            case_id="CASE-06",
            query="对比纯向量检索，混合 RAG（BM25 + 向量 RRF）在财报专有名词检索上有何优势？",
            expected_answer="BM25精确匹配科目代码与专有名词，向量检索捕捉语义关联，RRF倒数排名融合兼顾召回率与精确率。",
            generated_answer="混合RAG结合了BM25对财报科目代码及专有名词的精确词法匹配，以及向量检索的语义理解能力，通过RRF倒数排名融合显著提升了专有名词检索的召回率与精确率。",
            retrieved_contexts=[
                "架构设计文档：BM25擅长精确匹配财报科目编号、专有名词与数字，向量检索擅长同义语义匹配，RRF倒数排名融合将两者优势结合。",
                "混合检索默认取Top-K候选片段进行引用展示。",
                "会议室预约需提前半小时在企业微信操作。",
            ],
            relevant_contexts=[
                "架构设计文档：BM25擅长精确匹配财报科目编号、专有名词与数字，向量检索擅长同义语义匹配，RRF倒数排名融合将两者优势结合。",
            ],
            citations=["doc_rag_arch#p3"],
            expected_citations=["doc_rag_arch#p3"],
            latency_ms=2150.0,
            prompt_tokens=2350,
            completion_tokens=280,
            difficulty="complex",
        ),
    ]
