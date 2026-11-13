# Day 52 课后作业与参考答案

## 作业一：Alpaca 与 ShareGPT 双格式 Schema 校验与双向无损转换
**题目**：
1. 构造一条包含 `instruction`、`input`、`output`、`system` 与 `category` 的 [`AlpacaSample`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 实例。
2. 调用 [`alpaca_to_sharegpt`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 将其转换为 [`ShareGPTSample`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py)，验证 JSON 序列化输出中角色字段名为 `"from"`（值分别为 `"human"` 和 `"gpt"`）。
3. 再调用 [`sharegpt_to_alpaca`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 转回 `AlpacaSample`，断言与原始样本完全一致。

### 参考答案：
```python
import json
from zhishu_agent import AlpacaSample, alpaca_to_sharegpt, sharegpt_to_alpaca

orig = AlpacaSample(
    instruction="核实企业专票红冲进度",
    input="发票单号：INV20263001 | 金额：4700元",
    output="您好！该笔跨月发票已完成红冲申请，新蓝字发票将在 1 个工作日内推送至财务邮箱。",
    system="你是智枢企业级智能客服助手。",
    category="invoice_billing",
)

sg = alpaca_to_sharegpt(orig)
payload = json.loads(sg.model_dump_json(by_alias=True))
assert payload["conversations"][0]["from"] == "human"
assert payload["conversations"][1]["from"] == "gpt"

restored = sharegpt_to_alpaca(sg)
assert restored == orig
print("作业一校验通过！双向转换 100% 无损。")
```

---

## 作业二：多级数据清洗与去重（空白规范化、长度过滤、Hash + Jaccard）
**题目**：构造包含以下 4 类样本的列表，调用 [`clean_and_deduplicate_with_stats`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py)：
1. 1 条含零宽字符 `\u200b` 与多余空格的正常样本；
2. 1 条规范化后与第 1 条完全相同的精确重复样本；
3. 1 条仅在末尾多出 `"谢谢"` 的近似重复样本（`jaccard_threshold=0.85`）；
4. 1 条 `instruction` 仅 2 个字符的过短噪声样本。
断言返回 `output_count == 1`，且 `filtered_short_count == 1`、`exact_duplicate_count == 1`、`near_duplicate_count == 1`。

### 参考答案：
```python
from zhishu_agent import AlpacaSample, clean_and_deduplicate_with_stats

raw = [
    AlpacaSample(
        instruction="  如何申请   数电增值税专用发票并推送到企业财务邮箱？\u200b ",
        input="",
        output=" 请在发票中心填写一般纳税人信息并提交开票申请。 ",
    ),
    AlpacaSample(
        instruction="如何申请 数电增值税专用发票并推送到企业财务邮箱？",
        input="",
        output="请在发票中心填写一般纳税人信息并提交开票申请。",
    ),
    AlpacaSample(
        instruction="如何申请 数电增值税专用发票并推送到企业财务邮箱？谢谢",
        input="",
        output="请在发票中心填写一般纳税人信息并提交开票申请。",
    ),
    AlpacaSample(
        instruction="在吗",
        input="",
        output="您好，请问有什么可以帮您？",
    ),
]

cleaned, stats = clean_and_deduplicate_with_stats(raw, jaccard_threshold=0.85)
assert stats.output_count == 1
assert stats.filtered_short_count == 1
assert stats.exact_duplicate_count == 1
assert stats.near_duplicate_count == 1
print("作业二校验通过！清洗去重统计:", stats.model_dump())
```

---

## 作业三：500 条垂直客服合成数据集统计分析与 JSONL 导出
**题目**：
1. 调用 [`generate_customer_service_dataset`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 生成 500 条合成样本（`seed=42`），并经过 [`clean_and_deduplicate`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 清洗。
2. 调用 [`compute_dataset_stats`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 验证总数为 500、5 大业务场景各占 100 条。
3. 使用 `tempfile.TemporaryDirectory` 将清洗后的数据分别导出为 Alpaca JSONL 与 ShareGPT JSONL，并调用 [`load_jsonl`](file:///home/antigravity/ab6539763/-AI-Agent/project_iterations/day_52/zhishu_agent/dataset_builder.py) 回读校验条数一致。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import (
    alpaca_to_sharegpt,
    clean_and_deduplicate,
    compute_dataset_stats,
    export_jsonl,
    generate_customer_service_dataset,
    load_jsonl,
)

raw_500 = generate_customer_service_dataset(count=500, seed=42)
cleaned_500 = clean_and_deduplicate(raw_500)
stats = compute_dataset_stats(cleaned_500)

assert stats.total_count == 500
assert len(stats.category_distribution) == 5
assert all(v == 100 for v in stats.category_distribution.values())

with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    p_alpaca = export_jsonl(cleaned_500, tmp_dir / "alpaca_500.jsonl")
    p_sharegpt = export_jsonl(
        [alpaca_to_sharegpt(s) for s in cleaned_500],
        tmp_dir / "sharegpt_500.jsonl",
    )
    assert len(load_jsonl(p_alpaca, schema="alpaca")) == 500
    assert len(load_jsonl(p_sharegpt, schema="sharegpt")) == 500
    print("作业三校验通过！500 条数据集统计:", stats.model_dump())
```
