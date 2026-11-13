"""Day 54 核心模块：微调前后对比评测、LoRA 权重合并与量化体积估算 (v0.5.0-day54)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

# 常见量化格式的每参数平均占用字节数（含 group-wise scale/zero-point 或 block 元数据开销）
QUANT_BYTES_PER_PARAM: dict[str, float] = {
    "FP16": 2.0,          # 16-bit float (2.000 B/param)
    "GPTQ-4bit": 0.53125, # 4-bit + FP16 scale & 4-bit zero per 128 weights (~4.25 bpw)
    "AWQ-4bit": 0.53125,  # 4-bit + activation-aware group-128 scale/zero (~4.25 bpw)
    "GGUF-Q4_K_M": 0.606, # llama.cpp Q4_K_M 混合精度 (~4.85 bpw)
    "GGUF-Q8_0": 1.0625,  # llama.cpp Q8_0: 32 weights + 2B FP16 scale = 34B/32 (~8.5 bpw)
}

QUANT_FORMAT_ALIASES: dict[str, str] = {
    "fp16": "FP16",
    "float16": "FP16",
    "gptq": "GPTQ-4bit",
    "gptq-4bit": "GPTQ-4bit",
    "gptq_4bit": "GPTQ-4bit",
    "awq": "AWQ-4bit",
    "awq-4bit": "AWQ-4bit",
    "awq_4bit": "AWQ-4bit",
    "gguf-q4_k_m": "GGUF-Q4_K_M",
    "q4_k_m": "GGUF-Q4_K_M",
    "gguf-q8_0": "GGUF-Q8_0",
    "q8_0": "GGUF-Q8_0",
}

QUANT_DEPLOYMENT_NOTES: dict[str, str] = {
    "FP16": "全精度基线，适合高显存 A100/H100 推理或作为量化校准源模型",
    "GPTQ-4bit": "基于二阶 Hessian 误差补偿的 4-bit 权重量化，适合 vLLM/ExLlamaV2 GPU 高吞吐部署",
    "AWQ-4bit": "激活感知权重量化，保护 1% 显著权重通道，泛化稳健且 vLLM/TGI 推理速度极快",
    "GGUF-Q4_K_M": "llama.cpp 生态主流 4-bit 混合量化，支持 CPU / Apple Silicon / 消费级显卡混合推理",
    "GGUF-Q8_0": "近无损 8-bit GGUF 量化，适合对精度极度敏感的本地私有化部署场景",
}


@dataclass(frozen=True)
class EvalCase:
    """微调前后对比评测用例."""

    case_id: str
    prompt: str
    expected_answer: str
    base_output: str
    finetuned_output: str
    expected_format: str = "text"  # "text" | "json" | "sql" | "tool_call"
    required_keys: tuple[str, ...] = ()


def merge_lora_weights(
    base_w: Sequence[Sequence[float]],
    lora_a: Sequence[Sequence[float]],
    lora_b: Sequence[Sequence[float]],
    lora_alpha: float,
    lora_rank: int,
) -> list[list[float]]:
    """使用纯 Python 矩阵乘法执行 LoRA 权重合并：W' = W + (alpha / r) * (B @ A).

    Args:
        base_w: 基础模型权重矩阵，形状为 (m, n)。
        lora_a: LoRA 降维矩阵 A，形状为 (r, n)。
        lora_b: LoRA 升维矩阵 B，形状为 (m, r)。
        lora_alpha: LoRA 缩放超参数 alpha。
        lora_rank: LoRA 秩 r，必须为正整数。

    Returns:
        合并后的新权重矩阵 W'，形状为 (m, n)（不修改原始 base_w）。
    """
    if lora_rank <= 0:
        raise ValueError(f"lora_rank 必须为正整数，当前为: {lora_rank}")
    if not base_w or not base_w[0]:
        raise ValueError("base_w 不能为空矩阵")
    if not lora_a or not lora_a[0]:
        raise ValueError("lora_a 不能为空矩阵")
    if not lora_b or not lora_b[0]:
        raise ValueError("lora_b 不能为空矩阵")

    m = len(base_w)
    n = len(base_w[0])
    if any(len(row) != n for row in base_w):
        raise ValueError("base_w 各行列数必须一致")

    r_a = len(lora_a)
    n_a = len(lora_a[0])
    if any(len(row) != n_a for row in lora_a):
        raise ValueError("lora_a 各行列数必须一致")

    m_b = len(lora_b)
    r_b = len(lora_b[0])
    if any(len(row) != r_b for row in lora_b):
        raise ValueError("lora_b 各行列数必须一致")

    if r_a != lora_rank or r_b != lora_rank:
        raise ValueError(
            f"LoRA 矩阵秩维度不匹配: lora_rank={lora_rank}, "
            f"lora_a 行数={r_a}, lora_b 列数={r_b}"
        )
    if m_b != m or n_a != n:
        raise ValueError(
            f"权重矩阵维度不兼容: base_w=({m}, {n}), "
            f"lora_b=({m_b}, {r_b}), lora_a=({r_a}, {n_a})"
        )

    scale = float(lora_alpha) / float(lora_rank)
    merged: list[list[float]] = []

    for i in range(m):
        row_out: list[float] = []
        b_row = lora_b[i]
        w_row = base_w[i]
        for j in range(n):
            delta_ij = 0.0
            for k in range(lora_rank):
                delta_ij += float(b_row[k]) * float(lora_a[k][j])
            row_out.append(round(float(w_row[j]) + scale * delta_ij, 10))
        merged.append(row_out)

    return merged


def _check_format_compliance(
    output: str,
    expected_format: str,
    required_keys: Sequence[str] = (),
) -> bool:
    """校验模型输出是否符合预期结构化格式."""
    fmt = expected_format.strip().lower()
    text = output.strip()
    if not text:
        return False

    if fmt == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        return all(k in parsed for k in required_keys)

    if fmt == "tool_call":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        has_tool_fields = "tool" in parsed and "arguments" in parsed
        return has_tool_fields and all(k in parsed for k in required_keys)

    if fmt == "sql":
        upper = text.upper()
        # 要求纯 SQL SELECT 查询，不包含 Markdown 围栏或闲聊前缀
        if "```" in text:
            return False
        return upper.startswith("SELECT ") and " FROM " in upper

    # 默认文本格式：非空即可
    return True


def _check_answer_accuracy(output: str, expected_answer: str) -> bool:
    """校验输出是否准确命中预期答案（支持 JSON 键值语义匹配与文本归一化匹配）."""
    out_norm = re.sub(r"\s+", " ", output.strip().lower())
    exp_norm = re.sub(r"\s+", " ", expected_answer.strip().lower())
    if not exp_norm:
        return False
    if exp_norm in out_norm:
        return True

    # 若预期答案和输出均为 JSON，比较核心键值是否一致
    try:
        out_json = json.loads(output)
        exp_json = json.loads(expected_answer)
        if isinstance(out_json, dict) and isinstance(exp_json, dict):
            return all(out_json.get(k) == v for k, v in exp_json.items())
    except json.JSONDecodeError:
        pass

    return False


def evaluate_before_after(
    test_cases: Sequence[EvalCase | Mapping[str, Any]],
) -> dict[str, Any]:
    """对比基座模型（Base）与微调模型（Fine-tuned）的准确率与格式合规率.

    Args:
        test_cases: 评测用例列表，元素可为 EvalCase 或字典。

    Returns:
        包含 base/finetuned 准确率、格式合规率、提升幅度（delta）及逐条明细的字典。
    """
    if not test_cases:
        raise ValueError("test_cases 不能为空")

    total = len(test_cases)
    base_acc_hits = 0
    ft_acc_hits = 0
    base_fmt_hits = 0
    ft_fmt_hits = 0
    details: list[dict[str, Any]] = []

    for idx, raw_case in enumerate(test_cases, start=1):
        if isinstance(raw_case, EvalCase):
            case_id = raw_case.case_id
            expected_answer = raw_case.expected_answer
            base_output = raw_case.base_output
            finetuned_output = raw_case.finetuned_output
            expected_format = raw_case.expected_format
            required_keys = tuple(raw_case.required_keys)
        else:
            case_id = str(raw_case.get("case_id", f"case_{idx:02d}"))
            expected_answer = str(raw_case["expected_answer"])
            base_output = str(raw_case["base_output"])
            finetuned_output = str(raw_case["finetuned_output"])
            expected_format = str(raw_case.get("expected_format", "text"))
            required_keys = tuple(raw_case.get("required_keys", ()))

        base_acc = _check_answer_accuracy(base_output, expected_answer)
        ft_acc = _check_answer_accuracy(finetuned_output, expected_answer)
        base_fmt = _check_format_compliance(base_output, expected_format, required_keys)
        ft_fmt = _check_format_compliance(finetuned_output, expected_format, required_keys)

        base_acc_hits += int(base_acc)
        ft_acc_hits += int(ft_acc)
        base_fmt_hits += int(base_fmt)
        ft_fmt_hits += int(ft_fmt)

        details.append(
            {
                "case_id": case_id,
                "expected_format": expected_format,
                "base_accurate": base_acc,
                "finetuned_accurate": ft_acc,
                "base_format_compliant": base_fmt,
                "finetuned_format_compliant": ft_fmt,
            }
        )

    base_accuracy = round(base_acc_hits / total, 4)
    finetuned_accuracy = round(ft_acc_hits / total, 4)
    base_format_compliance = round(base_fmt_hits / total, 4)
    finetuned_format_compliance = round(ft_fmt_hits / total, 4)

    return {
        "total_cases": total,
        "base_accuracy": base_accuracy,
        "finetuned_accuracy": finetuned_accuracy,
        "accuracy_delta": round(finetuned_accuracy - base_accuracy, 4),
        "base_format_compliance": base_format_compliance,
        "finetuned_format_compliance": finetuned_format_compliance,
        "format_compliance_delta": round(
            finetuned_format_compliance - base_format_compliance, 4
        ),
        "improved": (
            finetuned_accuracy >= base_accuracy
            and finetuned_format_compliance >= base_format_compliance
        ),
        "case_details": details,
    }


def _normalize_quant_format(quant_format: str) -> str:
    """将用户输入的量化格式名称归一化为标准名称."""
    key = quant_format.strip().lower()
    if key in QUANT_FORMAT_ALIASES:
        return QUANT_FORMAT_ALIASES[key]
    for canonical in QUANT_BYTES_PER_PARAM:
        if canonical.lower() == key:
            return canonical
    supported = ", ".join(QUANT_BYTES_PER_PARAM.keys())
    raise ValueError(f"不支持的量化格式 '{quant_format}'，支持格式: {supported}")


def estimate_quantized_size_gb(params_billion: float, quant_format: str) -> float:
    """估算指定参数规模（单位：十亿 B）与量化格式下的模型权重体积（GB）.

    Args:
        params_billion: 模型参数量（B），例如 7、14、32、72，必须大于 0。
        quant_format: 量化格式（FP16、GPTQ-4bit、AWQ-4bit、GGUF-Q4_K_M、GGUF-Q8_0 / Q8_0）。

    Returns:
        估算的模型权重存储体积（GB，保留 3 位小数）。
    """
    if params_billion <= 0:
        raise ValueError(f"params_billion 必须大于 0，当前为: {params_billion}")

    canonical = _normalize_quant_format(quant_format)
    bytes_per_param = QUANT_BYTES_PER_PARAM[canonical]
    # 1B 参数 = 1e9 个参数；按十进制 GB (10^9 bytes) 估算，直接等于 params_billion * bytes_per_param
    size_gb = float(params_billion) * bytes_per_param
    return round(size_gb, 3)


def compare_quantization_formats(params_billion: float) -> list[dict[str, Any]]:
    """生成指定参数量模型在 FP16 / GPTQ-4bit / AWQ-4bit / GGUF-Q4_K_M / GGUF-Q8_0 下的对比表."""
    fp16_gb = estimate_quantized_size_gb(params_billion, "FP16")
    rows: list[dict[str, Any]] = []
    for fmt, bpp in QUANT_BYTES_PER_PARAM.items():
        size_gb = estimate_quantized_size_gb(params_billion, fmt)
        # 推理所需显存通常为权重体积的 ~1.2 倍（预留 KV Cache 与激活值开销）
        recommended_vram_gb = round(size_gb * 1.2, 2)
        rows.append(
            {
                "quant_format": fmt,
                "bits_per_weight": round(bpp * 8, 2),
                "size_gb": size_gb,
                "compression_vs_fp16": round(fp16_gb / size_gb, 2),
                "recommended_vram_gb": recommended_vram_gb,
                "deployment_note": QUANT_DEPLOYMENT_NOTES[fmt],
            }
        )
    return rows


def build_default_eval_cases() -> list[EvalCase]:
    """构造智枢企业智能体（ZhiShu-Agent）微调前后对比默认评测集."""
    return [
        EvalCase(
            case_id="eval_01_tool_call_leave",
            prompt="帮我查一下研发部张伟今年剩余年假天数",
            expected_answer='{"tool": "query_leave_balance", "arguments": {"employee": "张伟"}}',
            base_output='好的，我来帮您查询张伟的年假：```json\n{"tool": "query_leave_balance", "arguments": {"employee": "张伟"}}\n```',
            finetuned_output='{"tool": "query_leave_balance", "arguments": {"employee": "张伟"}}',
            expected_format="tool_call",
            required_keys=("tool", "arguments"),
        ),
        EvalCase(
            case_id="eval_02_json_expense",
            prompt="提取报销单关键字段：差旅费 1280 元，申请人李敏",
            expected_answer='{"category": "差旅费", "amount": 1280, "applicant": "李敏"}',
            base_output='申请人是李敏，报销差旅费 1280 元。',
            finetuned_output='{"category": "差旅费", "amount": 1280, "applicant": "李敏"}',
            expected_format="json",
            required_keys=("category", "amount", "applicant"),
        ),
        EvalCase(
            case_id="eval_03_sql_readonly",
            prompt="生成只读 SQL 查询 Q3 销售额前 5 的产品",
            expected_answer="SELECT product_name, SUM(revenue) FROM sales WHERE quarter = 'Q3' GROUP BY product_name LIMIT 5;",
            base_output="```sql\nSELECT product_name, SUM(revenue) FROM sales LIMIT 5;\n```",
            finetuned_output="SELECT product_name, SUM(revenue) FROM sales WHERE quarter = 'Q3' GROUP BY product_name LIMIT 5;",
            expected_format="sql",
        ),
        EvalCase(
            case_id="eval_04_tool_call_meeting",
            prompt="预约明天下午 3 点 302 会议室做架构评审",
            expected_answer='{"tool": "book_meeting_room", "arguments": {"room": "302", "time": "15:00"}}',
            base_output='{"tool": "book_meeting_room", "arguments": {"room": "302", "time": "15:00"}}',
            finetuned_output='{"tool": "book_meeting_room", "arguments": {"room": "302", "time": "15:00"}}',
            expected_format="tool_call",
            required_keys=("tool", "arguments"),
        ),
        EvalCase(
            case_id="eval_05_json_risk_route",
            prompt="判定操作风险等级：批量删除生产数据库表",
            expected_answer='{"risk_level": "HIGH", "requires_hitl": true}',
            base_output='{"risk_level": "MEDIUM"}',
            finetuned_output='{"risk_level": "HIGH", "requires_hitl": true}',
            expected_format="json",
            required_keys=("risk_level", "requires_hitl"),
        ),
    ]


__all__ = [
    "QUANT_BYTES_PER_PARAM",
    "QUANT_FORMAT_ALIASES",
    "QUANT_DEPLOYMENT_NOTES",
    "EvalCase",
    "asdict",
    "merge_lora_weights",
    "evaluate_before_after",
    "estimate_quantized_size_gb",
    "compare_quantization_formats",
    "build_default_eval_cases",
]
