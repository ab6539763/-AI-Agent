"""Day 52 平台启动入口：微调指令数据集构建、清洗去重与双格式导出 (v0.5.0-day52)."""

import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    alpaca_to_sharegpt,
    clean_and_deduplicate_with_stats,
    compute_dataset_stats,
    export_jsonl,
    generate_customer_service_dataset,
    load_jsonl,
)


def main() -> None:
    """演示 Self-Instruct 合成、清洗去重、Alpaca/ShareGPT 转换与 JSONL 导出."""
    print("=" * 72)
    print("📦 智枢企业级智能体平台 v0.5.0-day52 · 指令微调数据集构建流水线")
    print("=" * 72)

    raw_samples = generate_customer_service_dataset(count=500, seed=42)
    cleaned_samples, dedup_stats = clean_and_deduplicate_with_stats(raw_samples)
    ds_stats = compute_dataset_stats(cleaned_samples)

    print(f"[1] 合成与清洗统计: 输入={dedup_stats.input_count}, 输出={dedup_stats.output_count}, "
          f"过短过滤={dedup_stats.filtered_short_count}, 精确去重={dedup_stats.exact_duplicate_count}, "
          f"近似去重={dedup_stats.near_duplicate_count}")
    print(f"[2] 分类分布: {ds_stats.category_distribution}")
    print(f"[3] 平均长度: instruction={ds_stats.avg_instruction_len}, "
          f"input={ds_stats.avg_input_len}, output={ds_stats.avg_output_len} | "
          f"有上下文占比={ds_stats.with_input_ratio:.1%}")

    sharegpt_samples = [alpaca_to_sharegpt(s) for s in cleaned_samples]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        alpaca_path = export_jsonl(cleaned_samples, tmp_path / "cs_alpaca_500.jsonl")
        sharegpt_path = export_jsonl(sharegpt_samples, tmp_path / "cs_sharegpt_500.jsonl")

        reloaded_alpaca = load_jsonl(alpaca_path, schema="alpaca")
        reloaded_sharegpt = load_jsonl(sharegpt_path, schema="sharegpt")
        print(f"[4] JSONL 导出与回读校验成功: Alpaca={len(reloaded_alpaca)} 条, ShareGPT={len(reloaded_sharegpt)} 条")


if __name__ == "__main__":
    main()
