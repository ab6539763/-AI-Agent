"""智枢平台 Day 20 核心模块：多模态消息构建、本地确定性向量嵌入与语义 FAQ 检索 (v0.2.0-day20)"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable


def build_multimodal_message(
    text: str,
    image_url: str,
    *,
    detail: str = "auto",
) -> dict:
    """构造符合 OpenAI Vision 协议的多模态 user 消息字典。

    Args:
        text: 用户的文本提问或指令。
        image_url: 图片 URL（支持 https://... 或 data:image/png;base64,...）。
        detail: 图像解析精度（'auto' / 'low' / 'high'）。

    Returns:
        标准 OpenAI 多模态消息字典，content 为文本与图片块组成的列表。
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 必须为非空字符串")
    if not isinstance(image_url, str) or not image_url.strip():
        raise ValueError("image_url 必须为非空字符串")
    if detail not in {"auto", "low", "high"}:
        raise ValueError(f"不支持的 detail 取值: {detail}，仅支持 auto/low/high")

    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text.strip()},
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url.strip(),
                    "detail": detail,
                },
            },
        ],
    }


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """使用纯 Python stdlib math 计算两个向量的余弦相似度，范围 [-1.0, 1.0]。"""
    if len(vec_a) != len(vec_b):
        raise ValueError(
            f"向量维度不一致: len(vec_a)={len(vec_a)}, len(vec_b)={len(vec_b)}"
        )
    if not vec_a:
        raise ValueError("向量不能为空")

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    score = dot_product / (norm_a * norm_b)
    return max(-1.0, min(1.0, score))


class LocalEmbeddingModel:
    """纯 Python 确定性字符/双字切分（Unigram + Bigram）向量嵌入模型。

    不依赖 numpy 或外部 Embedding API，通过 MD5 确定性特征哈希与 L2 归一化，
    保证跨进程、跨平台输出完全一致的定长单位向量，适用于离线语义检索演示与单测。
    """

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions 必须为正整数")
        self.dimensions = dimensions

    @staticmethod
    def _extract_features(text: str) -> list[tuple[str, float]]:
        """提取去除空白后的字符 unigram 与 bigram 特征及其权重。"""
        cleaned = "".join(text.strip().lower().split())
        if not cleaned:
            return []

        features: list[tuple[str, float]] = []
        for ch in cleaned:
            features.append((f"u:{ch}", 1.0))
        for i in range(len(cleaned) - 1):
            features.append((f"b:{cleaned[i : i + 2]}", 1.5))
        return features

    def _hash_feature(self, feature: str) -> tuple[int, float]:
        """将特征确定性映射到 [0, dimensions) 槽位及符号 (+1 / -1)。"""
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % self.dimensions
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        return bucket, sign

    def embed(self, text: str) -> list[float]:
        """将单条文本编码为 L2 归一化后的定长浮点向量。"""
        if not isinstance(text, str):
            raise TypeError("text 必须为字符串类型")

        vec = [0.0] * self.dimensions
        features = self._extract_features(text)
        if not features:
            return vec

        for feat, weight in features:
            idx, sign = self._hash_feature(feat)
            vec[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        """批量将多条文本编码为定长向量列表。"""
        return [self.embed(t) for t in texts]


@dataclass(frozen=True)
class FAQItem:
    """企业知识库单条 FAQ 记录。"""

    question: str
    answer: str
    category: str = "通用"


@dataclass(frozen=True)
class FAQMatch:
    """语义检索返回的匹配结果与余弦相似度得分。"""

    question: str
    answer: str
    category: str
    score: float


class SemanticFAQMatcher:
    """基于余弦相似度的轻量级语义 FAQ 检索器。"""

    def __init__(self, model: LocalEmbeddingModel | None = None) -> None:
        self.model = model or LocalEmbeddingModel(dimensions=128)
        self._items: list[FAQItem] = []
        self._vectors: list[list[float]] = []

    def add_faq(self, question: str, answer: str, category: str = "通用") -> None:
        """向索引中添加单条 FAQ，并预先计算问题向量。"""
        if not question.strip():
            raise ValueError("FAQ 问题不能为空")
        item = FAQItem(question=question.strip(), answer=answer.strip(), category=category)
        self._items.append(item)
        self._vectors.append(self.model.embed(item.question))

    def add_faqs(self, items: Iterable[FAQItem | tuple[str, str] | tuple[str, str, str]]) -> None:
        """批量添加 FAQ 记录。"""
        for entry in items:
            if isinstance(entry, FAQItem):
                self.add_faq(entry.question, entry.answer, entry.category)
            elif len(entry) == 2:
                self.add_faq(entry[0], entry[1])
            elif len(entry) == 3:
                self.add_faq(entry[0], entry[1], entry[2])
            else:
                raise ValueError(f"不支持的 FAQ 条目格式: {entry!r}")

    def __len__(self) -> int:
        return len(self._items)

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.0,
    ) -> list[FAQMatch]:
        """检索与用户提问语义最相近的 Top-K 条 FAQ。"""
        if top_k <= 0:
            raise ValueError("top_k 必须为正整数")
        if not self._items or not query.strip():
            return []

        query_vec = self.model.embed(query)
        scored: list[FAQMatch] = []
        for item, item_vec in zip(self._items, self._vectors):
            sim = cosine_similarity(query_vec, item_vec)
            if sim >= min_score:
                scored.append(
                    FAQMatch(
                        question=item.question,
                        answer=item.answer,
                        category=item.category,
                        score=round(sim, 6),
                    )
                )

        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]


DEFAULT_FAQS: list[FAQItem] = [
    FAQItem(
        question="差旅费用和发票怎么提交报销？",
        answer="请登录智枢 OA 系统 -> 财务报销 -> 差旅报销，上传电子发票 PDF 并关联出差审批单，每周五统一打款。",
        category="财务制度",
    ),
    FAQItem(
        question="员工年假怎么申请以及有多少天？",
        answer="司龄满 1 年享 5 天带薪年假，满 5 年享 10 天；在 OA 请假模块提交申请并由直属主管审批即可。",
        category="人事考勤",
    ),
    FAQItem(
        question="公司内网 VPN 密码忘记了如何重置？",
        answer="访问 IT 自助服务台（it.xingchen.local）点击“忘记密码”，通过企业微信扫码验证后即可重置 VPN 密码。",
        category="IT 支持",
    ),
    FAQItem(
        question="如何预订星辰大厦三楼会议室？",
        answer="打开企业日历新建会议，在“会议室”栏选择 301/302 或星辰厅并填写参会人即可完成锁定。",
        category="行政办公",
    ),
    FAQItem(
        question="新员工入职第一天需要办理哪些手续？",
        answer="请携带身份证原件至前台领取工牌与办公电脑，随后前往 HRBP 处签署入职确认单并开通飞书/GitLab 账号。",
        category="入职指引",
    ),
]


def create_default_faq_matcher(dimensions: int = 128) -> SemanticFAQMatcher:
    """创建并预置星辰数科企业知识库 FAQ 的语义检索器。"""
    matcher = SemanticFAQMatcher(model=LocalEmbeddingModel(dimensions=dimensions))
    matcher.add_faqs(DEFAULT_FAQS)
    return matcher
