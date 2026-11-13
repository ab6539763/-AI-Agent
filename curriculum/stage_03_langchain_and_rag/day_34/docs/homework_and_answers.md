# Day 34 课后作业与参考答案

## 作业一：基于 Faithfulness 的大模型幻觉（Hallucination）检测实战
**题目**：在星辰数科 HR 问答机器人测试中，检索器召回了正确的制度片段：
`contexts = ["星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。"]`
但模型分别生成了以下两条回答：
- 回答 A：`"入职满1年员工每年享有5天带薪年假。"`
- 回答 B：`"入职满1年员工每年享有15天带薪年假。此外公司还报销全部打车费。"`

请你使用 `zhishu_agent.rag_eval` 中的 `compute_faithfulness` 和 `RAGEvaluator`：
1. 分别计算回答 A 与回答 B 的 `Faithfulness` 分数。
2. 打印回答 B 被判定为疑似幻觉的陈述（`unsupported_claims`）和诊断标签（`diagnostics`），并解释为什么“5天变成15天”能被成功拦截。

### 参考答案：
```python
from zhishu_agent import EvalSample, RAGEvaluator, compute_faithfulness

contexts = ["星辰数科年假制度：入职满1年员工每年享有5天带薪年假，满10年享有10天。"]
ans_a = "入职满1年员工每年享有5天带薪年假。"
ans_b = "入职满1年员工每年享有15天带薪年假。此外公司还报销全部打车费。"

print("回答 A Faithfulness:", compute_faithfulness(ans_a, contexts))  # 1.0
print("回答 B Faithfulness:", compute_faithfulness(ans_b, contexts))  # 0.0

evaluator = RAGEvaluator()
res_b = evaluator.evaluate_sample(
    EvalSample(
        sample_id="hw-01",
        question="入职满1年员工有几天年假？",
        answer=ans_b,
        contexts=contexts,
        ground_truth=ans_a,
    )
)
print("诊断标签:", res_b.diagnostics)
print("疑似幻觉陈述:", res_b.unsupported_claims)
```
**原理解析**：`compute_faithfulness` 先把回答按标点拆分为独立陈述（Claims），然后对每条陈述执行“关键词/双字词覆盖率 + 数值一致性校验”。回答 B 的第一句虽然词汇高度相似，但数值 `15` 不在上下文数值集合 `{"1", "5", "10"}` 中，因此被判定为数值幻觉；第二句“报销全部打车费”在上下文中毫无支撑，最终两条陈述均未通过，Faithfulness 为 `0.0`，触发 `hallucination_risk`。

---

## 作业二：手动推导并编程验证 Context Recall（上下文召回率）
**题目**：某次知识库问答的标准答案（`ground_truth`）包含 3 条核心事实：
`ground_truth = "生产环境 Redis 禁止执行 KEYS * 命令。应使用 SCAN 分批遍历。单次 SCAN 建议 COUNT 不超过 1000。"`
而当前检索器只召回了 1 条上下文：
`contexts = ["生产环境 Redis 集群禁止执行 KEYS * 命令，请使用 SCAN 分批遍历。"]`
1. 请先手动计算该样本的 `Context Recall` 理论值。
2. 编写 Python 代码调用 `compute_context_recall` 与 `RAGEvaluator` 验证结果，并指出缺失的标准事实（`missing_gt_claims`）以及对应的工程优化方向。

### 参考答案：
**手动推导**：`ground_truth` 共包含 3 条独立事实陈述：
1. `生产环境 Redis 禁止执行 KEYS * 命令`（上下文已覆盖 ✅）
2. `应使用 SCAN 分批遍历`（上下文已覆盖 ✅）
3. `单次 SCAN 建议 COUNT 不超过 1000`（上下文未提及 ❌）
因此理论 `Context Recall = 2 / 3 ≈ 0.6667`。

```python
from zhishu_agent import EvalSample, RAGEvaluator, compute_context_recall

gt = "生产环境 Redis 禁止执行 KEYS * 命令。应使用 SCAN 分批遍历。单次 SCAN 建议 COUNT 不超过 1000。"
contexts = ["生产环境 Redis 集群禁止执行 KEYS * 命令，请使用 SCAN 分批遍历。"]

score = compute_context_recall(gt, contexts)
print(f"Context Recall = {score:.4f}")  # 0.6667

res = RAGEvaluator().evaluate_sample(
    EvalSample(
        sample_id="hw-02",
        question="生产环境 Redis 使用什么命令替代 KEYS *？",
        answer="禁止执行 KEYS *，应使用 SCAN 分批遍历。",
        contexts=contexts,
        ground_truth=gt,
    )
)
print("诊断标签:", res.diagnostics)
print("缺失标准事实:", res.missing_gt_claims)
```
**优化方向**：`missing_context` 表明检索器漏掉了“COUNT 不超过 1000”这一细节切片，工程上可通过适当增大 `Top-K`（如从 `k=1` 提到 `k=3`）、优化 Chunk 切分重叠度（`chunk_overlap`）或启用 BM25 + 向量混合检索来提升 Context Recall。

---

## 作业三：构建企业级 RAG 黄金评测集（Eval Testset）并生成聚合报告
**题目**：在将 RAG 系统接入 CI/CD 流水线前，需要建立一份覆盖不同业务场景的黄金评测集（至少包含 3 条样本：1 条健康样本、1 条包含检索噪音的样本、1 条存在回答跑题的样本）。请编写脚本：
1. 构造 `list[EvalSample]` 数据集。
2. 使用 `RAGEvaluator().evaluate_dataset(samples)` 运行批量评测。
3. 输出 `report.format_summary()` 与 `report.to_dict()` 中的 `pass_rate`，并说明如何在 CI 中设置质量门禁（Quality Gate）。

### 参考答案：
```python
from zhishu_agent import EvalSample, RAGEvaluator

testset = [
    EvalSample(
        sample_id="ci-001",
        question="一线城市差旅酒店住宿报销上限是多少？",
        answer="一线城市酒店住宿报销上限每晚600元，需提供电子发票。",
        contexts=["差旅报销标准：一线城市酒店住宿报销上限每晚600元，需提供电子发票。"],
        ground_truth="一线城市酒店住宿报销上限每晚600元，需提供电子发票。",
    ),
    EvalSample(
        sample_id="ci-002",
        question="智枢平台 RAG 默认召回多少条文档？",
        answer="智枢平台 RAG 检索默认召回 Top-3 文档片段。",
        contexts=[
            "公司每周五举办技术沙龙。",
            "行政前台提供办公文具领用。",
            "智枢平台 RAG 检索默认召回 Top-3 文档片段，支持元数据过滤。",
        ],
        ground_truth="智枢平台 RAG 检索默认召回 Top-3 文档片段。",
    ),
    EvalSample(
        sample_id="ci-003",
        question="申请年假需要提前几天在 OA 提交？",
        answer="公司食堂每周三提供免费水果，欢迎大家前往领取。",
        contexts=["员工申请年假需提前3个工作日在 OA 系统提交审批。"],
        ground_truth="员工申请年假需提前3个工作日在 OA 系统提交审批。",
    ),
]

report = RAGEvaluator().evaluate_dataset(testset)
print(report.format_summary())
print("Pass Rate:", report.pass_rate)
for item in report.sample_results:
    print(item.sample_id, "->", item.diagnostics)
```
**CI 质量门禁建议**：在自动化测试脚本中对 `EvalReport` 施加硬性断言，例如 `assert report.mean_faithfulness >= 0.85`、`assert report.mean_context_recall >= 0.80` 以及 `assert report.pass_rate >= 0.80`；一旦新提交的 Prompt 或 Chunk 策略导致任一指标跌破门禁阈值，CI 直接阻断合并（Merge Request），从而守住线上问答质量底线。
