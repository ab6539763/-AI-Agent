# Day 15 课后作业与参考答案

## 作业一：Transformer 注意力机制（Self-Attention）类比与简化计算
**题目**：
在 Transformer 中，每个词（Token）都会生成三个向量：**Query（查询）**、**Key（键）**、**Value（值）**。
1. 请用“图书馆检索”或“企业内部知识库检索”的通俗类比，解释 `Q`、`K`、`V` 以及 `Softmax(Q·K^T / sqrt(d_k)) · V` 的物理含义。
2. 编写一段纯 Python 代码（仅使用 `math` 标准库），计算当 `Q = [1.0, 0.5]`、两个候选词的键向量 `K1 = [1.0, 0.0]`、`K2 = [0.0, 1.0]`，对应值向量 `V1 = [10.0, 0.0]`、`V2 = [0.0, 10.0]`（维度 `d_k = 2`）时的缩放点积注意力输出向量。

### 参考答案：
**1. 图书馆检索类比**：
- **Query (`Q`)**：你带着问题走进图书馆时脑海里的“检索关键词”（例如：“如何报销差旅费”）。
- **Key (`K`)**：每本书封面上的“索引标签/目录摘要”（例如：《财务报销制度》、《代码规范》）。
- **点积与缩放 (`Q·K^T / sqrt(d_k)`)**：用你的关键词去匹配每本书的索引标签，计算相似度得分；除以 `sqrt(d_k)` 是为了防止维度过高导致点积数值过大、Softmax 梯度消失。
- **Softmax 权重**：把匹配得分归一化为总和为 1 的“注意力分配比例”（例如：90% 关注《财务制度》，10% 关注其他）。
- **Value (`V`) 与加权求和**：每本书里真正的“正文内容”。最终输出就是按注意力权重加权融合后的知识向量。

**2. 纯 Python 缩放点积注意力计算代码**：
```python
import math


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def softmax(scores: list[float]) -> list[float]:
    max_s = max(scores)
    exps = [math.exp(s - max_s) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


q = [1.0, 0.5]
keys = [[1.0, 0.0], [0.0, 1.0]]
values = [[10.0, 0.0], [0.0, 10.0]]
d_k = len(q)

# 1. 计算缩放点积得分
raw_scores = [dot(q, k) / math.sqrt(d_k) for k in keys]
# 2. Softmax 归一化得到注意力权重
weights = softmax(raw_scores)
# 3. 对 Value 加权求和
output = [
    sum(weights[i] * values[i][dim] for i in range(len(values)))
    for dim in range(len(values[0]))
]

print("注意力权重:", [round(w, 4) for w in weights])
print("输出向量:", [round(v, 4) for v in output])
```

---

## 作业二：多语言 Token 密度估算与 BPE 规律验证
**题目**：
在 BPE（Byte Pair Encoding）分词器下，中文通常比英文消耗更多 Token。
1. 请导入 `project_iterations/day_15` 中的 `estimate_tokens`，分别估算以下两句语义相同的文本的 Token 数：
   - 中文：`"请帮我总结这篇关于大语言模型架构的技术文档。"`
   - 英文：`"Please help me summarize this technical document about LLM architecture."`
2. 编写一个辅助函数 `analyze_token_density(text: str) -> dict`，统计文本的字符总数、估算 Token 数以及“每字符平均 Token 数（`tokens_per_char`）”，对比中英文的差异。

### 参考答案：
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("project_iterations/day_15").resolve()))
from zhishu_agent.tokenizer import estimate_tokens


def analyze_token_density(text: str) -> dict:
    tokens = estimate_tokens(text)
    char_count = len(text)
    ratio = round(tokens / char_count, 3) if char_count > 0 else 0.0
    return {
        "char_count": char_count,
        "estimated_tokens": tokens,
        "tokens_per_char": ratio,
    }


zh_text = "请帮我总结这篇关于大语言模型架构的技术文档。"
en_text = "Please help me summarize this technical document about LLM architecture."

print("中文分析:", analyze_token_density(zh_text))
print("英文分析:", analyze_token_density(en_text))
```
> **结论**：中文单字信息密度高，在常见通用词表中往往被拆分为 1~2 个 Token（约 1.5 tokens/字符）；而英文由多个字母组成一个词根 Token（约 0.25 tokens/字符），因此同等字符长度下中文 Token 消耗显著更高。

---

## 作业三：企业级月度 API 预算测算与多模型选型
**题目**：
假设星辰数科的智能客服系统每天处理 **10,000 次** 用户问答（每月按 30 天计，共 **300,000 次**）：
- 每次平均输入 Prompt 约 **400 个汉字**（含系统人设与检索片段）；
- 每次平均输出 Completion 约 **200 个汉字**。
请使用 `compare_models_cost` 计算这 5 个主流模型（`DeepSeek-V3`、`Qwen-Plus`、`Llama-3.1-70B`、`GPT-4o`、`Claude-3.5-Sonnet`）的**月度总费用（人民币 RMB）**，并给出高性价比选型建议。

### 参考答案：
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("project_iterations/day_15").resolve()))
from zhishu_agent.tokenizer import compare_models_cost

prompt = "智" * 400
completion = "答" * 200
monthly_calls = 300_000

comparison = compare_models_cost(prompt, completion)
print(f"{'模型':<20} {'单次(RMB)':>12} {'月度总预算(RMB)':>16}")
print("-" * 52)
for item in comparison:
    monthly_rmb = item["total_cost_rmb"] * monthly_calls
    print(f"{item['model']:<20} ¥{item['total_cost_rmb']:>11.6f} ¥{monthly_rmb:>15,.2f}")
```
> **选型建议**：对于高频日常客服问答，优先选用 `DeepSeek-V3` 或 `Qwen-Plus`（月度成本仅数百元人民币级别）；对于复杂代码生成或高难度推理路由，再按需路由至 `GPT-4o` 或 `Claude-3.5-Sonnet`，实现“分级路由 + 成本可控”。
