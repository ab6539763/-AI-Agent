# Day 43 课后作业与参考答案

## 作业一：架构对比——Supervisor 集中式编排 vs Peer-to-Peer 网状协作
**题目**：在星辰数科企业级智能体平台选型评审中，团队需要决定研报生成系统采用 **Supervisor 模式** 还是 **Peer-to-Peer（点对点去中心化）模式**。请你从以下四个维度进行对比分析，并给出明确的企业选型建议：
1. 路由复杂度与扩展性（当角色从 3 个增加到 8 个时）
2. 死循环风险与熔断可控性
3. 权限审计与全链路可观测性
4. 适用场景边界

### 参考答案：
| 对比维度 | Supervisor 模式（集中式编排） | Peer-to-Peer 模式（去中心化网状协作） |
| :--- | :--- | :--- |
| **路由复杂度与扩展性** | 路由逻辑集中于 `SupervisorOrchestrator`，每个 Worker 仅需关注自身专长；新增 Worker 时只需向 Supervisor 注册并更新路由策略，复杂度呈 $O(N)$ 线性增长。 | 每个 Agent 都要在 Prompt 中维护其余所有 Agent 的能力描述并自行决定交接目标，角色增多时交互边呈 $O(N^2)$ 膨胀，提示词极易失控。 |
| **死循环风险与熔断** | 由 Supervisor 统一维护 `rounds_used` 与 `max_rounds`，可在单一控制点精准执行熔断与降级交付。 | 缺乏全局视角，A -> B -> C -> A 的隐蔽环路难以在局部察觉，全局状态同步成本高。 |
| **权限审计与可观测性** | 所有任务交接均经由 Supervisor 转发，天然形成完整的 `agent_handoffs` 审计轨迹，便于计费、限流与合规追踪。 | 消息在节点间点对点跳跃，需要额外的分布式追踪总线才能还原完整执行链路。 |
| **适用场景** | 企业级强流程、高合规要求、需要确定性交付的任务（如研报生成、工单审批、代码评审流水线）。 | 高度开放的头脑风暴、多角色自由辩论或博弈仿真场景。 |

**选型结论**：企业级研报与业务自动化场景应优先采用 **Supervisor 模式**，以换取可控的路由成本、确定性的终止保障与完整的审计可观测性。

---

## 作业二：Handoff 死循环防护——验证 `max_rounds` 熔断与交接轨迹审计
**题目**：在多智能体协作中，如果 `ResearcherAgent` 与 `AnalystAgent` 互相认为对方产出不够充分而反复退回重做，系统就会陷入“乒乓死循环”。请你使用 `SupervisorOrchestrator` 编写一段可运行的验证代码：
1. 定义一个自定义 `router_fn`，故意在 `"researcher"` 与 `"analyst"` 之间交替路由，永不返回 `"FINISH"`。
2. 设置 `max_rounds=4` 运行 `orchestrator.run("高并发架构复盘")`。
3. 断言返回结果的 `status == "max_rounds_reached"`、`rounds_used == 4`，并打印出完整的 `agent_handoffs` 轨迹与降级生成的阶段性报告标题。

### 参考答案：
```python
from zhishu_agent import SupervisorOrchestrator

def ping_pong_router(context, handoffs, available_workers):
    # 故意在 researcher 和 analyst 之间无限来回切换
    target = "analyst" if len(handoffs) % 2 == 1 else "researcher"
    return target, f"第 {len(handoffs) + 1} 轮补充调研/分析"

orchestrator = SupervisorOrchestrator(max_rounds=4, router_fn=ping_pong_router)
result = orchestrator.run("高并发架构复盘")

assert result.status == "max_rounds_reached"
assert result.rounds_used == 4
assert len(result.agent_handoffs) == 4
assert [h.to_agent for h in result.agent_handoffs] == [
    "researcher", "analyst", "researcher", "analyst"
]

print("熔断状态:", result.status)
print("交接轨迹:", [(h.round_num, h.to_agent) for h in result.agent_handoffs])
print("报告首行:", result.final_report.splitlines()[0])
```

---

## 作业三：横向扩展——新增 `ReviewerAgent` 实现四阶段质量门禁
**题目**：为了确保最终交付的研报符合企业发布标准，我们需要在 `WriterAgent` 之后增加一个 `ReviewerAgent`（质量审核员）。请你：
1. 继承 `AgentWorker` 实现 `ReviewerAgent`，检查 `context["report"]` 是否同时包含 `"核心事实"` 与 `"风险评估"` 两个章节；若通过则在 `artifacts` 中写入 `{"review_approved": True}`，否则写入 `{"review_approved": False}`。
2. 编写一个支持四阶段（`researcher -> analyst -> writer -> reviewer -> FINISH`）的 `router_fn`。
3. 使用 `SupervisorOrchestrator` 运行一次完整任务，断言 `rounds_used == 4` 且 `shared_context["review_approved"] is True`。

### 参考答案：
```python
from zhishu_agent import (
    FINISH,
    AgentWorker,
    AnalystAgent,
    ResearcherAgent,
    SupervisorOrchestrator,
    WorkerResult,
    WriterAgent,
)

class ReviewerAgent(AgentWorker):
    def __init__(self) -> None:
        super().__init__(
            name="reviewer",
            role="Quality Reviewer",
            description="校验研报是否包含核心事实与风险评估章节",
        )

    def execute(self, task: str, context: dict) -> WorkerResult:
        report = str(context.get("report", ""))
        approved = ("核心事实" in report) and ("风险评估" in report)
        return WorkerResult(
            agent_name=self.name,
            role=self.role,
            output=f"质量门禁校验结果: {'通过' if approved else '驳回'}",
            artifacts={"review_approved": approved},
        )

def quality_gated_router(context, handoffs, available_workers):
    if "findings" not in context:
        return "researcher", "检索主题背景与事实"
    if "insights" not in context:
        return "analyst", "提炼分析洞察与风险"
    if "report" not in context:
        return "writer", "撰写结构化研报"
    if "review_approved" not in context:
        return "reviewer", "执行终稿质量门禁审核"
    return FINISH, "审核通过，准予发布"

orchestrator = SupervisorOrchestrator(
    workers=[ResearcherAgent(), AnalystAgent(), WriterAgent(), ReviewerAgent()],
    max_rounds=6,
    router_fn=quality_gated_router,
)
result = orchestrator.run("企业级 AI 网关选型评估")

assert result.status == "completed"
assert result.rounds_used == 4
assert result.shared_context["review_approved"] is True
assert [h.to_agent for h in result.agent_handoffs] == [
    "researcher", "analyst", "writer", "reviewer"
]
print("四阶段审核流校验通过！最终状态:", result.status)
```
