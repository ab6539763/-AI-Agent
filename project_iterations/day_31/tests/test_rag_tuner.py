"""Day 31 自动化单元测试：覆盖 TuningConfig、chunk_text 与 run_grid_experiment。"""
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    EvalQAPair,
    TuningConfig,
    chunk_text,
    run_grid_experiment,
)


def test_tuning_config_validation() -> None:
    """验证 TuningConfig 参数合法性校验."""
    cfg = TuningConfig(chunk_size=100, chunk_overlap=20, top_k=3)
    assert cfg.to_dict() == {"chunk_size": 100, "chunk_overlap": 20, "top_k": 3}

    with pytest.raises(ValueError):
        TuningConfig(chunk_size=0, chunk_overlap=0, top_k=1)
    with pytest.raises(ValueError):
        TuningConfig(chunk_size=50, chunk_overlap=-1, top_k=1)
    with pytest.raises(ValueError):
        TuningConfig(chunk_size=50, chunk_overlap=50, top_k=1)
    with pytest.raises(ValueError):
        TuningConfig(chunk_size=50, chunk_overlap=10, top_k=0)


def test_chunk_text_overlap_and_bounds() -> None:
    """验证文本切分长度上限与相邻切片重叠窗口."""
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chunks = chunk_text(text, chunk_size=10, chunk_overlap=3)
    assert len(chunks) >= 3
    assert all(len(c) <= 10 for c in chunks)
    # 第一块末尾 3 个字符应出现在第二块开头
    assert chunks[0][-3:] == chunks[1][:3]
    assert chunk_text("   ", chunk_size=10, chunk_overlap=2) == []


def test_grid_experiment_metrics_and_best_config() -> None:
    """验证网格实验正确计算 Hit Rate@K 与 MRR 并选出最优配置."""
    corpus = [
        {
            "id": "doc-hr",
            "content": "星辰数科年假规定：入职满一年享有5天带薪年假，入职满十年享有10天带薪年假。",
        },
        {
            "id": "doc-it",
            "content": "生产环境 Redis 严禁使用 KEYS * 命令，必须使用 SCAN 进行安全遍历。",
        },
    ]
    eval_qa_pairs = [
        EvalQAPair(
            query="入职满一年有几天带薪年假？",
            expected_keywords=("5天带薪年假",),
            relevant_doc_ids=("doc-hr",),
        ),
        EvalQAPair(
            query="Redis 生产环境禁止什么命令？",
            expected_keywords=("KEYS *", "SCAN"),
            relevant_doc_ids=("doc-it",),
        ),
    ]

    # 过小 chunk_size 且无重叠会把关键词切碎，而较大 chunk_size + overlap 可以完整保留
    configs = [
        TuningConfig(chunk_size=15, chunk_overlap=0, top_k=1),
        TuningConfig(chunk_size=60, chunk_overlap=10, top_k=2),
    ]

    report = run_grid_experiment(corpus, eval_qa_pairs, configs)
    assert len(report.results) == 2
    assert report.best_config == TuningConfig(chunk_size=60, chunk_overlap=10, top_k=2)
    assert report.best_result.hit_rate == pytest.approx(1.0)
    assert 0.5 <= report.best_result.mrr <= 1.0
    assert "Hit Rate@K" in report.summary_table()


def test_corpus_and_qa_input_flexibility() -> None:
    """验证支持纯字符串语料、自定义 Document 对象与字典格式 QA 样本."""

    @dataclass
    class FakeDoc:
        id: str
        page_content: str

    corpus = [
        FakeDoc(id="d1", page_content="智枢平台支持 LangChain LCEL 管道语法与多会话记忆隔离。"),
        "差旅酒店一线城市报销上限为每晚600元。",
    ]
    qa_pairs = [
        {"query": "智枢平台支持什么管道语法？", "expected_answer": "LCEL"},
        {"query": "一线城市酒店报销上限？", "expected_keywords": ["600元"]},
    ]
    configs = [TuningConfig(chunk_size=80, chunk_overlap=10, top_k=2)]

    report = run_grid_experiment(corpus, qa_pairs, configs)
    assert report.best_result.hit_rate == pytest.approx(1.0)
    assert report.best_result.mrr == pytest.approx(1.0)


def test_empty_inputs_raise_value_error() -> None:
    """验证空语料、空评测集或空配置列表时抛出 ValueError."""
    cfg = [TuningConfig(chunk_size=50, chunk_overlap=10, top_k=2)]
    qa = [{"query": "test", "expected_answer": "test"}]

    with pytest.raises(ValueError):
        run_grid_experiment([], qa, cfg)
    with pytest.raises(ValueError):
        run_grid_experiment(["hello"], [], cfg)
    with pytest.raises(ValueError):
        run_grid_experiment(["hello"], qa, [])
