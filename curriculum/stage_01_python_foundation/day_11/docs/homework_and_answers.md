# Day 11 课后作业与参考答案

## 作业一：`pathlib` 批量扫描与规范化重命名
**题目**：在知识库接入前，运营同学上传了一批命名杂乱的 `.txt` 和 `.md` 文档（例如 `会议纪要.txt`、`rag设计.md`）。请你使用 `pathlib.Path` 和 `datetime` 编写函数 `batch_prefix_rename(target_dir: Path, prefix: str | None = None) -> list[tuple[str, str]]`：
1. 仅扫描 `target_dir` 第一层中的 `.txt` 和 `.md` 文件（按文件名排序）。
2. 若未传入 `prefix`，则使用当前 UTC 日期（如 `20261113_`）作为前缀；若文件名已经以该前缀开头，则跳过不重复重命名。
3. 使用 `Path.rename()` 完成重命名，并返回 `[(旧文件名, 新文件名), ...]` 列表。

### 参考答案：
```python
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def batch_prefix_rename(
    target_dir: Path, prefix: str | None = None
) -> list[tuple[str, str]]:
    """为目录下的 .txt/.md 文件批量添加日期前缀。"""
    if not target_dir.is_dir():
        raise NotADirectoryError(f"目标不是有效目录: {target_dir}")

    date_prefix = prefix or datetime.now(timezone.utc).strftime("%Y%m%d_")
    renamed: list[tuple[str, str]] = []

    files = sorted(
        (
            p
            for p in target_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".txt", ".md"}
        ),
        key=lambda p: p.name,
    )

    for file_path in files:
        if file_path.name.startswith(date_prefix):
            continue
        new_path = file_path.with_name(f"{date_prefix}{file_path.name}")
        file_path.rename(new_path)
        renamed.append((file_path.name, new_path.name))

    return renamed


with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    (d / "rag_notes.md").write_text("RAG", encoding="utf-8")
    (d / "meeting.txt").write_text("纪要", encoding="utf-8")
    (d / "ignore.py").write_text("print(1)", encoding="utf-8")
    print("重命名结果:", batch_prefix_rename(d, prefix="20261113_"))
```

---

## 作业二：正则表达式 `re` 敏感信息脱敏（邮箱与手机号）
**题目**：企业知识库文档在送入大模型 Embedding 前，必须对员工个人隐私信息（PII）进行脱敏。请你使用 `re.sub` 编写函数 `mask_sensitive_info(text: str) -> str`：
1. 将中国大陆 11 位手机号（`1[3-9]\d{9}`）脱敏为保留前 3 位和后 4 位，中间 4 位替换为 `****`（如 `13812345678` -> `138****5678`）。
2. 将邮箱地址脱敏为保留用户名首字符与域名，其余用户名字符替换为 `***`（如 `chenmo@xingchen.ai` -> `c***@xingchen.ai`）。

### 参考答案：
```python
import re

PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def mask_sensitive_info(text: str) -> str:
    """对文本中的手机号与电子邮箱进行正则脱敏。"""
    masked = PHONE_PATTERN.sub(r"\1****\2", text)
    masked = EMAIL_PATTERN.sub(r"\1***\2", masked)
    return masked


raw_doc = (
    "联系人：陈默，手机 13812345678，工作邮箱 chenmo@xingchen.ai；"
    "备用邮箱 zhang_lead@example.com，工号 123456789012（12位非手机号不应误伤）。"
)
print("脱敏前:", raw_doc)
print("脱敏后:", mask_sensitive_info(raw_doc))
```

---

## 作业三：`csv` 与 `json` 结构化报告导出
**题目**：基于 `DocScanner` 的扫描结果思路，请你编写一个轻量函数 `export_summary(records: list[dict], csv_path: Path, json_path: Path) -> None`：
1. `records` 中每条记录包含 `file_name`、`size_bytes`、`hits` 三个字段。
2. 使用 `csv.DictWriter`（注意 `newline=""` 与 `utf-8` 编码）将记录写入 `csv_path`。
3. 使用 `json.dumps(..., ensure_ascii=False, indent=2)` 将带 `exported_at`（ISO 时间戳）与 `records` 的字典写入 `json_path`。

### 参考答案：
```python
import csv
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def export_summary(
    records: list[dict[str, object]],
    csv_path: Path,
    json_path: Path,
) -> None:
    """同时导出 CSV 明细表与带时间戳的 JSON 汇总报告。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["file_name", "size_bytes", "hits"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(records),
        "records": records,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


with tempfile.TemporaryDirectory() as tmp:
    out_dir = Path(tmp)
    sample_records = [
        {"file_name": "rag_intro.md", "size_bytes": 512, "hits": 4},
        {"file_name": "agent_design.txt", "size_bytes": 320, "hits": 2},
    ]
    csv_file = out_dir / "summary.csv"
    json_file = out_dir / "summary.json"
    export_summary(sample_records, csv_file, json_file)
    print("CSV 内容:\n" + csv_file.read_text(encoding="utf-8"))
    print("JSON 内容:\n" + json_file.read_text(encoding="utf-8"))
```
