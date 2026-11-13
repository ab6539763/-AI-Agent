"""智枢平台 Day 34：RAG 评估体系（Ragas 四大核心指标与自动化评测流水线）.

实现零外部依赖、确定性可复现的 RAG 评估核心模块，覆盖 Ragas 框架四大经典指标：
1. Faithfulness（忠实度）：评估生成回答中的陈述是否全部有检索上下文支撑，用于检测幻觉。
2. Answer Relevancy（答案相关性）：评估生成回答是否直接切中用户提问，避免答非所问。
3. Context Precision（上下文精确率）：基于 Precision@K 评估相关文档是否排在检索结果前列。
4. Context Recall（上下文召回率）：评估标准答案（Ground Truth）中的关键事实是否被检索上下文覆盖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import re
from typing import Any


_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "也", "都", "就", "而", "但",
    "吗", "呢", "啊", "吧", "呀", "么", "什么", "多少", "如何", "怎么", "为什么",
    "请问", "一下", "可以", "能否", "有", "没有", "这", "那", "这个", "那个",
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "and", "or", "by", "from",
    "what", "how", "why", "when", "where", "which", "who", "do", "does", "did",
}


def _split_claims(text: str) -> list[str]:
    """将文本按中英文句末/分句标点切分为独立陈述（Claims）."""
    if not text or not text.strip():
        return []
    raw_parts = re.split(r"[。！？；;\n.!?\r]+", text.strip())
    claims: list[str] = []
    for part in raw_parts:
        cleaned = part.strip(" ，,、：:\"'“”‘’()（）")
        if len(cleaned) >= 2:
            claims.append(cleaned)
    return claims


def _tokenize(text: str, include_bigrams: bool = True) -> list[str]:
    """中英文混合分词：英文单词 + 中文单字/双字切分，过滤常见虚词."""
    if not text:
        return []
    lowered = text.lower()
    tokens: list[str] = []

    # 提取英文单词与数字组合
    for word in re.findall(r"[a-z0-9_]+", lowered):
        if word not in _STOPWORDS:
            tokens.append(word)

    # 提取连续中文片段并生成 Unigram + Bigram
    for zh_seq in re.findall(r"[\u4e00-\u9fff]+", lowered):
        chars = [c for c in zh_seq if c not in _STOPWORDS]
        tokens.extend(chars)
        if include_bigrams and len(zh_seq) >= 2:
            for i in range(len(zh_seq) - 1):
                bg = zh_seq[i : i + 2]
                if bg not in _STOPWORDS:
                    tokens.append(bg)

    return tokens


def _extract_numbers(text: str) -> set[str]:
    """提取文本中的数字（用于幻觉检测中的数值一致性校验）."""
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _embed_text(text: str, dim: int = 256) -> list[float]:
    """基于 SHA-256 特征哈希的确定性 L2 归一化向量编码."""
    vec = [0.0] * dim
    tokens = _tokenize(text, include_bigrams=True)
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个归一化向量的余弦相似度，截断到 [0.0, 1.0]."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(0.0, min(1.0, dot))


def _is_claim_supported(claim: str, contexts: list[str], threshold: float = 0.42) -> bool:
    """判断单条陈述是否被检索上下文列表所支撑.

    综合考虑：
    1. 陈述中的关键词/双字词在上下文中的覆盖率（Token Overlap）；
    2. 数值一致性校验（防止上下文写 5 天而回答编造 15 天等数值幻觉）。
    """
    if not claim or not contexts:
        return False

    claim_tokens = set(_tokenize(claim, include_bigrams=True))
    if not claim_tokens:
        return False

    claim_nums = _extract_numbers(claim)
    merged_context = "\n".join(contexts)
    context_tokens = set(_tokenize(merged_context, include_bigrams=True))
    context_nums = _extract_numbers(merged_context)

    # 若陈述包含具体数字，但上下文中完全没有该数字，直接判定为不支持（数值幻觉）
    if claim_nums and not claim_nums.issubset(context_nums):
        return False

    # 计算单条上下文及合并上下文的最大覆盖率
    merged_overlap = len(claim_tokens & context_tokens) / len(claim_tokens)
    best_single_overlap = 0.0
    for ctx in contexts:
        ctx_tokens = set(_tokenize(ctx, include_bigrams=True))
        if not ctx_tokens:
            continue
        overlap = len(claim_tokens & ctx_tokens) / len(claim_tokens)
        if overlap > best_single_overlap:
            best_single_overlap = overlap

    return max(merged_overlap, best_single_overlap) >= threshold


def compute_faithfulness(
    answer: str,
    contexts: list[str],
    support_threshold: float = 0.42,
) -> float:
    """计算 Faithfulness（忠实度）.

    定义：Faithfulness = 被检索上下文支撑的回答陈述数 / 回答总陈述数。
    取值范围 [0.0, 1.0]，越接近 1.0 说明幻觉越少。
    """
    claims = _split_claims(answer)
    if not claims or not contexts:
        return 0.0
    supported = sum(
        1 for claim in claims if _is_claim_supported(claim, contexts, threshold=support_threshold)
    )
    return round(supported / len(claims), 4)


def compute_answer_relevancy(question: str, answer: str) -> float:
    """计算 Answer Relevancy（答案相关性）.

    定义：结合提问与回答的语义向量余弦相似度，以及提问核心词在回答中的覆盖率，
    衡量回答是否切中问题要害（取值范围 [0.0, 1.0]）。
    """
    if not question or not question.strip() or not answer or not answer.strip():
        return 0.0

    q_vec = _embed_text(question)
    a_vec = _embed_text(answer)
    cos_sim = _cosine_similarity(q_vec, a_vec)

    q_tokens = set(_tokenize(question, include_bigrams=False))
    a_tokens = set(_tokenize(answer, include_bigrams=False))
    if q_tokens:
        keyword_coverage = len(q_tokens & a_tokens) / len(q_tokens)
    else:
        keyword_coverage = cos_sim

    score = 0.55 * cos_sim + 0.45 * keyword_coverage
    return round(max(0.0, min(1.0, score)), 4)


def compute_context_precision(
    question: str,
    contexts: list[str],
    ground_truth: str = "",
    relevance_threshold: float = 0.25,
) -> float:
    """计算 Context Precision（上下文精确率 / Precision@K）.

    定义：
    Context Precision@K = sum_{k=1..K} (Precision@k * v_k) / sum_{k=1..K} v_k
    其中 v_k ∈ {0, 1} 表示第 k 条召回上下文是否与标准答案（或提问）相关。
    若相关文档排在越靠前的位置，分数越接近 1.0；若无关噪音排在前面，分数会显著下降。
    """
    if not contexts:
        return 0.0

    reference = ground_truth.strip() if ground_truth and ground_truth.strip() else question.strip()
    if not reference:
        return 0.0

    ref_vec = _embed_text(reference)
    ref_tokens = set(_tokenize(reference, include_bigrams=True))

    relevance_flags: list[int] = []
    for ctx in contexts:
        if not ctx or not ctx.strip():
            relevance_flags.append(0)
            continue
        ctx_vec = _embed_text(ctx)
        cos_sim = _cosine_similarity(ref_vec, ctx_vec)
        ctx_tokens = set(_tokenize(ctx, include_bigrams=True))
        overlap = (len(ref_tokens & ctx_tokens) / len(ref_tokens)) if ref_tokens else 0.0
        combined = 0.5 * cos_sim + 0.5 * overlap
        relevance_flags.append(1 if combined >= relevance_threshold else 0)

    total_relevant = sum(relevance_flags)
    if total_relevant == 0:
        return 0.0

    precision_sum = 0.0
    tp_so_far = 0
    for rank_idx, v_k in enumerate(relevance_flags, start=1):
        if v_k == 1:
            tp_so_far += 1
            precision_at_k = tp_so_far / rank_idx
            precision_sum += precision_at_k

    return round(precision_sum / total_relevant, 4)


def compute_context_recall(
    ground_truth: str,
    contexts: list[str],
    support_threshold: float = 0.42,
) -> float:
    """计算 Context Recall（上下文召回率）.

    定义：Context Recall = 被检索上下文覆盖的 Ground Truth 陈述数 / Ground Truth 总陈述数。
    取值范围 [0.0, 1.0]，反映检索器是否漏掉了关键知识片段。
    """
    gt_claims = _split_claims(ground_truth)
    if not gt_claims or not contexts:
        return 0.0
    covered = sum(
        1 for claim in gt_claims if _is_claim_supported(claim, contexts, threshold=support_threshold)
    )
    return round(covered / len(gt_claims), 4)


@dataclass
class EvalSample:
    """单条 RAG 评测样本."""

    question: str
    answer: str
    contexts: list[str]
    ground_truth: str = ""
    sample_id: str = ""


@dataclass
class SampleEvalResult:
    """单条样本的 Ragas 四维评分与诊断详情."""

    sample_id: str
    question: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float
    overall_score: float
    unsupported_claims: list[str] = field(default_factory=list)
    missing_gt_claims: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """数据集级 RAG 评测聚合报告."""

    total_samples: int
    mean_faithfulness: float
    mean_answer_relevancy: float
    mean_context_precision: float
    mean_context_recall: float
    overall_score: float
    passed_samples: int
    pass_rate: float
    sample_results: list[SampleEvalResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """导出为可序列化的字典结构."""
        return {
            "total_samples": self.total_samples,
            "mean_faithfulness": self.mean_faithfulness,
            "mean_answer_relevancy": self.mean_answer_relevancy,
            "mean_context_precision": self.mean_context_precision,
            "mean_context_recall": self.mean_context_recall,
            "overall_score": self.overall_score,
            "passed_samples": self.passed_samples,
            "pass_rate": self.pass_rate,
            "sample_results": [
                {
                    "sample_id": r.sample_id,
                    "question": r.question,
                    "faithfulness": r.faithfulness,
                    "answer_relevancy": r.answer_relevancy,
                    "context_precision": r.context_precision,
                    "context_recall": r.context_recall,
                    "overall_score": r.overall_score,
                    "unsupported_claims": r.unsupported_claims,
                    "missing_gt_claims": r.missing_gt_claims,
                    "diagnostics": r.diagnostics,
                }
                for r in self.sample_results
            ],
        }

    def format_summary(self) -> str:
        """生成人类可读的评测报告摘要."""
        lines = [
            "=== 智枢 RAG 评测报告 (Ragas Metrics) ===",
            f"样本总数: {self.total_samples} | 达标样本: {self.passed_samples} ({self.pass_rate:.1%})",
            f"Faithfulness (忠实度)       : {self.mean_faithfulness:.4f}",
            f"Answer Relevancy (相关性)   : {self.mean_answer_relevancy:.4f}",
            f"Context Precision (精确率)  : {self.mean_context_precision:.4f}",
            f"Context Recall (召回率)     : {self.mean_context_recall:.4f}",
            f"综合均分 (Overall Score)    : {self.overall_score:.4f}",
        ]
        return "\n".join(lines)


class RAGEvaluator:
    """智枢平台 RAG 自动化评测器."""

    def __init__(
        self,
        faithfulness_threshold: float = 0.7,
        relevancy_threshold: float = 0.5,
        precision_threshold: float = 0.6,
        recall_threshold: float = 0.7,
    ) -> None:
        self.faithfulness_threshold = faithfulness_threshold
        self.relevancy_threshold = relevancy_threshold
        self.precision_threshold = precision_threshold
        self.recall_threshold = recall_threshold

    def evaluate_sample(self, sample: EvalSample, index: int = 1) -> SampleEvalResult:
        """对单条 EvalSample 执行四维评估并生成诊断标签."""
        sample_id = sample.sample_id or f"sample-{index:03d}"

        faithfulness = compute_faithfulness(sample.answer, sample.contexts)
        answer_relevancy = compute_answer_relevancy(sample.question, sample.answer)
        context_precision = compute_context_precision(
            sample.question, sample.contexts, sample.ground_truth
        )
        context_recall = compute_context_recall(sample.ground_truth, sample.contexts)

        overall = round(
            (faithfulness + answer_relevancy + context_precision + context_recall) / 4.0,
            4,
        )

        unsupported = [
            c for c in _split_claims(sample.answer) if not _is_claim_supported(c, sample.contexts)
        ]
        missing_gt = [
            c
            for c in _split_claims(sample.ground_truth)
            if not _is_claim_supported(c, sample.contexts)
        ]

        diagnostics: list[str] = []
        if faithfulness < self.faithfulness_threshold:
            diagnostics.append("hallucination_risk")
        if answer_relevancy < self.relevancy_threshold:
            diagnostics.append("low_relevancy")
        if context_precision < self.precision_threshold:
            diagnostics.append("retrieval_noise")
        if context_recall < self.recall_threshold:
            diagnostics.append("missing_context")
        if not diagnostics:
            diagnostics.append("healthy")

        return SampleEvalResult(
            sample_id=sample_id,
            question=sample.question,
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_precision=context_precision,
            context_recall=context_recall,
            overall_score=overall,
            unsupported_claims=unsupported,
            missing_gt_claims=missing_gt,
            diagnostics=diagnostics,
        )

    def evaluate_dataset(self, samples: list[EvalSample]) -> EvalReport:
        """批量评测数据集并生成聚合 EvalReport."""
        if not samples:
            return EvalReport(
                total_samples=0,
                mean_faithfulness=0.0,
                mean_answer_relevancy=0.0,
                mean_context_precision=0.0,
                mean_context_recall=0.0,
                overall_score=0.0,
                passed_samples=0,
                pass_rate=0.0,
                sample_results=[],
            )

        results = [self.evaluate_sample(sample, index=i) for i, sample in enumerate(samples, start=1)]
        n = len(results)
        mean_f = round(sum(r.faithfulness for r in results) / n, 4)
        mean_ar = round(sum(r.answer_relevancy for r in results) / n, 4)
        mean_cp = round(sum(r.context_precision for r in results) / n, 4)
        mean_cr = round(sum(r.context_recall for r in results) / n, 4)
        overall = round((mean_f + mean_ar + mean_cp + mean_cr) / 4.0, 4)

        passed = sum(1 for r in results if r.diagnostics == ["healthy"])
        pass_rate = round(passed / n, 4)

        return EvalReport(
            total_samples=n,
            mean_faithfulness=mean_f,
            mean_answer_relevancy=mean_ar,
            mean_context_precision=mean_cp,
            mean_context_recall=mean_cr,
            overall_score=overall,
            passed_samples=passed,
            pass_rate=pass_rate,
            sample_results=results,
        )
