# Day 63 课后作业与参考答案

## 作业一：为什么 Ragas 评估需要同时观测 Faithfulness 与 Context Precision？
**题目**：在智枢平台的离线 Ragas 评估体系中，如果一个 RAG 系统仅追求高 `Faithfulness` 而忽略 `Context Precision`，可能会出现什么问题？请结合 `Rerank Top-K` 调优说明原因。

### 参考答案：
1. **只看 Faithfulness 的盲区**：
   - `Faithfulness` 只衡量“生成答案是否被检索到的上下文所支撑”，并不关心检索上下文里是否混杂了大量无关噪音。
   - 如果检索器把 Top-10 片段全部塞进 Prompt，即使答案忠实于其中 1 条片段，其余 9 条无关片段不仅浪费大量 Input Token、拉长首字延迟（TTFT），还容易引发 LLM 的 **Lost-in-the-Middle（中间迷失）** 现象。
2. **Rerank Top-K 的双重收益**：
   - 通过 Cross-Encoder 精排并裁剪至 Top-2/Top-3，把高相关证据排在最前并剔除尾部噪声，既能显著提升 `Context Precision`，又能同步降低单次请求的 Prompt Token 消耗与推理延迟。

---

## 作业二：计算 Prompt Caching 与 Model Routing 的单次请求成本
**题目**：假设智枢平台某次请求 `prompt_tokens = 2000`、`completion_tokens = 500`，沿用 `PricingConfig` 默认定价：
1. 若使用 `flagship` 模型且未命中缓存（`cached_tokens = 0`），单次成本是多少 CNY？
2. 若启用 Prompt Caching 后命中 `1000` 个缓存 Token，单次成本降至多少 CNY？
3. 若该请求属于简单制度查询并被路由至 `lite` 模型（无缓存），单次成本是多少 CNY？

### 参考答案：
1. **Flagship 无缓存**：
   - `(2000 / 1000) * 0.02 + (500 / 1000) * 0.06 = 0.04 + 0.03 = 0.070000 CNY`（千次成本 ¥70.00）。
2. **Flagship 命中 1000 Cached Tokens**：
   - 未缓存输入 `1000 * 0.02 / 1000 = 0.02`，缓存输入 `1000 * 0.004 / 1000 = 0.004`，输出 `500 * 0.06 / 1000 = 0.03`；
   - 合计 `0.054000 CNY`（成本下降 22.86%）。
3. **Lite 模型路由**：
   - `(2000 / 1000) * 0.002 + (500 / 1000) * 0.006 = 0.004 + 0.003 = 0.007000 CNY`（较 Flagship 无缓存降本 90%）。

---

## 作业三：使用 `OptimizationAdvisor` 生成并验证质量门禁报告
**题目**：请编写一段 Python 代码，使用 `build_sample_capstone_cases()` 与 `OptimizationAdvisor`，执行 `rerank_top_k=2` 的优化对比，并断言：
1. 优化后的 `overall_ragas_score` 不低于基线；
2. 优化后的 `cost_per_1k_req_cny` 至少降低 40%；
3. 输出 `comparison.to_markdown()` 中的核心摘要。

### 参考答案：
```python
from zhishu_agent.capstone_eval import (
    OptimizationAdvisor,
    build_sample_capstone_cases,
)

cases = build_sample_capstone_cases()
advisor = OptimizationAdvisor()
comparison = advisor.compare(cases, rerank_top_k=2)

assert comparison.optimized.overall_ragas_score >= comparison.baseline.overall_ragas_score
assert comparison.cost_reduction_pct >= 40.0
assert comparison.optimized.passed_quality_gate is True

print(comparison.to_markdown())
```
