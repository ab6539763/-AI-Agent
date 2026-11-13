# Day 70 课后作业与参考答案

## 作业题目

1. **70 天阶段校验拓展**：使用 `validate_curriculum_span()` 验证当前 6 大阶段的完整性；尝试构造一个“第 4 阶段结束于 Day 49、第 5 阶段开始于 Day 51”的断档数据，观察校验器抛出的异常信息。
2. **前沿趋势检索与方案设计**：利用 `TrendTracker` 筛选出所有成熟度为 `production` 的前沿趋势，并结合你最感兴趣的 1 个方向（如 MCP 或 Reasoning Models），写出它对智枢平台现有架构的 2 点具体改造方案。
3. **个人结业证书与 90 天路线图导出**：调用 `generate_graduation_certificate()` 与 `generate_career_roadmap()`，为你自己生成一份定制化的结业证书和面向 `Agent Engineer`（或 `RAG Engineer` / `AI Application Engineer`）的 30/60/90 天行动清单。

---

## 参考答案

### 1. 阶段校验与断档拦截
```python
from zhishu_agent.graduation_summary import (
    ZHISHU_STAGE_MILESTONES,
    StageMilestone,
    validate_curriculum_span,
)

# 正常校验
result = validate_curriculum_span(ZHISHU_STAGE_MILESTONES)
print(result)  # {'total_stages': 6, 'total_days': 70, 'start_day': 1, 'end_day': 70, ...}

# 构造断档数据：Stage 5 从 Day 52 开始（跳过 Day 51）
broken = list(ZHISHU_STAGE_MILESTONES)
broken[4] = StageMilestone(
    stage_number=5,
    stage_code="stage_05_finetuning_and_deployment",
    title="第五阶段",
    day_start=52,
    day_end=57,
    version_tag="v0.5.0",
    core_topics=("LoRA", "vLLM", "K8s"),
    platform_deliverable="推理加速",
    key_metrics="3.2x",
)
# 将抛出 ValueError: 阶段 5 起始天数不连续：期望 Day 51，实际 Day 52
validate_curriculum_span(broken)
```

### 2. 成熟趋势筛选与架构改造思路
```python
from zhishu_agent.graduation_summary import TrendTracker

tracker = TrendTracker()
prod_trends = tracker.filter_by_maturity("production")
for t in prod_trends:
    print(t.name, "->", t.impact_on_zhishu)
```
- **改造示例（MCP 协议落地）**：
  1. 将智枢 `tool_registry` 中的财报检索、SQLite 审批状态查询封装为标准 MCP Server，通过 JSON-RPC 2.0 暴露工具 Schema；
  2. 在网关层增加 MCP 工具调用的权限校验与审计日志，使外部 IDE（如 Cursor/VS Code）或内部客户端均可安全复用智枢能力。

### 3. 生成个人结业证书与 90 天路线图
```python
from zhishu_agent.graduation_summary import (
    generate_career_roadmap,
    generate_graduation_certificate,
)

print(generate_graduation_certificate(learner_name="你的名字", track="Agent Engineer"))
print(generate_career_roadmap(target_role="Agent Engineer", learner_name="你的名字"))
```
