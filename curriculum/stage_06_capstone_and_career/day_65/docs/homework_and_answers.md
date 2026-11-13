# Day 65 课后实战练习与参考答案

## 练习一：自定义企业 ARB（架构评审委员会）评分权重并校验边界
**题目**：假设某金融客户更加看重系统稳定性与安全合规，要求将 `DefenseRubric` 调整为：
- `business_value` (15%)
- `architecture_depth` (25%)
- `engineering_quality` (35%)
- `demo_fluency` (10%)
- `qa_performance` (15%)
请使用 `RubricDimension` 与 `DefenseRubric` 构建该自定义标准，并验证当某组权重总和为 `0.95` 时会抛出 `ValueError`。

<details>
<summary>参考答案</summary>

```python
from zhishu_agent.defense_scorer import DefenseRubric, RubricDimension, evaluate_defense

custom_dims = [
    RubricDimension(key="business_value", name="业务价值", weight=0.15, description="ROI与落地场景"),
    RubricDimension(key="architecture_depth", name="技术架构与RAG/Agent深度", weight=0.25, description="RAG与安全设计"),
    RubricDimension(key="engineering_quality", name="工程质量与可观测性", weight=0.35, description="测试、Trace与容灾"),
    RubricDimension(key="demo_fluency", name="演示流畅度", weight=0.10, description="演示稳定性"),
    RubricDimension(key="qa_performance", name="评委问答表现", weight=0.15, description="边界权衡回答"),
]
rubric = DefenseRubric(dimensions=custom_dims)
res = evaluate_defense(
    {
        "business_value": 85,
        "architecture_depth": 90,
        "engineering_quality": 92,
        "demo_fluency": 88,
        "qa_performance": 89,
    },
    rubric=rubric,
)
print(res.total_score, res.grade)  # 89.6 A
```

</details>

---

## 练习二：扩展 `JudgeQuestionBank` 新增「多 Agent 死循环与预算失控」考题
**题目**：在金融多 Agent 协作中，Planner 与 Reviewer 可能出现互相踢皮球导致 Token 消耗失控。请向 `JudgeQuestionBank` 补充一道 `JQ-06`（分类：`Agent循环控制`），并测试 `match_question("多Agent互相调用死循环怎么限制步数和预算？")` 能准确命中该题。

<details>
<summary>参考答案</summary>

```python
from zhishu_agent.defense_scorer import DEFAULT_JUDGE_QUESTIONS, JudgeQuestion, JudgeQuestionBank

jq06 = JudgeQuestion(
    question_id="JQ-06",
    category="Agent循环控制",
    judge_role="首席架构师",
    question="多 Agent 协作出现互相调用死循环或任务不收敛时，如何限制步数与 Token 预算？",
    keywords=("死循环", "步数", "max_steps", "预算", "收敛", "熔断", "agent"),
    key_points=(
        "全局 max_steps 与单节点重试上限",
        "会话级 Token 预算熔断与超时中断",
        "状态转移防抖与重复工具调用检测",
    ),
    model_answer="通过全局 max_steps 步数上限、Token 预算熔断器及重复 Tool-Call 指纹检测强制收敛。",
)
bank = JudgeQuestionBank(questions=(*DEFAULT_JUDGE_QUESTIONS, jq06))
top_q, score = bank.match_question("多Agent互相调用死循环怎么限制步数和预算？", top_k=1)[0]
assert top_q.question_id == "JQ-06"
```

</details>

---

## 练习三：导出答辩评分卡并在团队内部进行复盘
**题目**：运行 `evaluate_defense` 聚合 3 位评委的打分，调用 `result.to_markdown()` 生成评分卡，解释为什么工程上要将 `total_score` 基于未四舍五入的维度均分直接计算，而不是对已舍入的贡献分求和？

<details>
<summary>参考答案</summary>

若先对每个维度的贡献分（`均分 * 权重`）进行 `round(..., 2)` 四舍五入再相加，在 `0.15` 权重乘以 `.5` 分数（如 `69.5 * 0.15 = 10.425`）时会触发 Python 银行家舍入法（`10.42`），导致 5 个维度相加后出现 `69.49` 的累计舍入漂移。先对未舍入的精确加权项求和再统一 `round(..., 2)`，可保证总分与单评委加权分完全一致，避免在 `70.0 / 80.0 / 90.0` 等级边界产生误判。

</details>
