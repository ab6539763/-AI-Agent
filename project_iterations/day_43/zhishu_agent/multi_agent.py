"""智枢平台 Day 43：多智能体协作系统 (Supervisor Pattern: Researcher + Analyst + Writer).

实现标准 Supervisor-Worker 多智能体编排架构：
- `AgentWorker`: 所有专职智能体的抽象基类
- `ResearcherAgent`: 信息调研员，负责检索事实与背景资料
- `AnalystAgent`: 数据与策略分析师，负责提炼洞察、指标与风险
- `WriterAgent`: 技术报告撰稿人，负责整合调研与分析生成结构化研报
- `SupervisorOrchestrator`: 中央调度器，负责任务路由、追踪 `agent_handoffs`、
  强制执行 `max_rounds` 防死循环上限，并输出最终合成研报。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

FINISH = "FINISH"


@dataclass
class HandoffRecord:
    """记录一次智能体间的任务交接（Handoff）."""

    round_num: int
    from_agent: str
    to_agent: str
    instruction: str
    summary: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class WorkerResult:
    """专职智能体单次执行的结构化返回结果."""

    agent_name: str
    role: str
    output: str
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationResult:
    """Supervisor 编排全流程的最终输出."""

    topic: str
    status: str  # "completed" | "max_rounds_reached"
    rounds_used: int
    max_rounds: int
    agent_handoffs: list[HandoffRecord]
    worker_outputs: dict[str, str]
    final_report: str
    shared_context: dict[str, Any]


class AgentWorker(ABC):
    """专职智能体基类，所有 Worker 必须实现 `execute` 方法."""

    name: str
    role: str
    description: str

    def __init__(self, name: str, role: str, description: str) -> None:
        self.name = name
        self.role = role
        self.description = description

    @abstractmethod
    def execute(self, task: str, context: dict[str, Any]) -> WorkerResult:
        """根据 Supervisor 下发的任务指令与共享上下文执行工作."""


class ResearcherAgent(AgentWorker):
    """信息调研智能体：收集主题相关的核心事实、技术趋势与参考依据."""

    def __init__(
        self,
        name: str = "researcher",
        search_fn: Callable[[str, dict[str, Any]], list[str]] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            role="Information Researcher",
            description="围绕目标主题检索行业背景、关键事实与技术动态。",
        )
        self._search_fn = search_fn

    def execute(self, task: str, context: dict[str, Any]) -> WorkerResult:
        topic = str(context.get("topic") or task)
        if self._search_fn is not None:
            findings = list(self._search_fn(topic, context))
        else:
            findings = [
                f"[事实 1] {topic} 在企业生产环境中通常面临任务拆解、工具调用可靠性与上下文隔离三大挑战。",
                f"[事实 2] 采用 Supervisor 集中式路由模式可将单 Agent 提示词复杂度降低约 40%，并支持专职能力独立演进。",
                f"[事实 3] 生产级多智能体系统必须设置 max_rounds 熔断阈值与 handoff 审计日志以防止死循环。",
            ]

        output = "【调研结论】\n" + "\n".join(f"- {item}" for item in findings)
        return WorkerResult(
            agent_name=self.name,
            role=self.role,
            output=output,
            artifacts={"findings": findings},
        )


class AnalystAgent(AgentWorker):
    """数据分析与策略智能体：对调研事实进行结构化对比、量化评估与风险识别."""

    def __init__(
        self,
        name: str = "analyst",
        analyze_fn: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            role="Data & Strategy Analyst",
            description="基于调研事实提炼核心洞察、评估关键指标与潜在风险。",
        )
        self._analyze_fn = analyze_fn

    def execute(self, task: str, context: dict[str, Any]) -> WorkerResult:
        topic = str(context.get("topic") or task)
        findings: list[str] = list(context.get("findings", []))

        if self._analyze_fn is not None:
            analysis = dict(self._analyze_fn(topic, context))
            insights = list(analysis.get("insights", []))
            risks = list(analysis.get("risks", []))
            metrics = dict(analysis.get("metrics", {}))
        else:
            insights = [
                f"针对「{topic}」，共汇总 {len(findings)} 条一手调研事实，角色专业化分工收益显著。",
                "集中式 Supervisor 相比网状 Peer-to-Peer 通信更易实现权限审计与确定性终止。",
            ]
            risks = [
                "若路由策略缺少完成态判定或 max_rounds 上限，Worker 间可能发生乒乓式循环交接。",
                "长链路上下文透传需控制信息冗余，避免干扰下游撰稿质量。",
            ]
            metrics = {
                "findings_count": len(findings),
                "recommended_max_rounds": 6,
                "architecture_pattern": "Supervisor-Worker",
            }

        lines = ["【分析洞察】"]
        lines.extend(f"- {ins}" for ins in insights)
        lines.append("【风险提示】")
        lines.extend(f"- {r}" for r in risks)
        output = "\n".join(lines)

        return WorkerResult(
            agent_name=self.name,
            role=self.role,
            output=output,
            artifacts={
                "insights": insights,
                "risks": risks,
                "metrics": metrics,
            },
        )


class WriterAgent(AgentWorker):
    """技术报告撰稿智能体：汇总调研事实与分析洞察，输出最终结构化研报."""

    def __init__(
        self,
        name: str = "writer",
        write_fn: Callable[[str, dict[str, Any]], str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            role="Technical Report Writer",
            description="综合调研与分析成果，撰写逻辑清晰、可直接交付的专题研究报告。",
        )
        self._write_fn = write_fn

    def execute(self, task: str, context: dict[str, Any]) -> WorkerResult:
        topic = str(context.get("topic") or task)
        if self._write_fn is not None:
            report = self._write_fn(topic, context)
        else:
            findings: list[str] = list(context.get("findings", []))
            insights: list[str] = list(context.get("insights", []))
            risks: list[str] = list(context.get("risks", []))
            metrics: dict[str, Any] = dict(context.get("metrics", {}))

            findings_md = "\n".join(f"{i}. {f}" for i, f in enumerate(findings, 1)) or "- 暂无调研事实"
            insights_md = "\n".join(f"- {ins}" for ins in insights) or "- 暂无分析洞察"
            risks_md = "\n".join(f"- {r}" for r in risks) or "- 暂无风险提示"

            report = (
                f"# {topic} — 多智能体联合研究报告\n\n"
                f"## 1. 背景与核心事实（Researcher）\n{findings_md}\n\n"
                f"## 2. 深度分析与关键洞察（Analyst）\n{insights_md}\n\n"
                f"## 3. 风险评估与治理建议\n{risks_md}\n\n"
                f"## 4. 关键指标摘要\n"
                f"- 调研事实数: {metrics.get('findings_count', len(findings))}\n"
                f"- 编排模式: {metrics.get('architecture_pattern', 'Supervisor-Worker')}\n"
            )

        return WorkerResult(
            agent_name=self.name,
            role=self.role,
            output=report,
            artifacts={"report": report},
        )


RouterFn = Callable[[dict[str, Any], list[HandoffRecord], Sequence[str]], tuple[str, str]]


class SupervisorOrchestrator:
    """Supervisor 中央编排器：负责多智能体任务路由、交接追踪与最大轮次熔断."""

    def __init__(
        self,
        workers: Sequence[AgentWorker] | None = None,
        max_rounds: int = 6,
        router_fn: RouterFn | None = None,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds 必须大于或等于 1")

        self.max_rounds = max_rounds
        self._router_fn = router_fn
        default_workers: Sequence[AgentWorker] = (
            workers
            if workers is not None
            else (ResearcherAgent(), AnalystAgent(), WriterAgent())
        )
        self.workers: dict[str, AgentWorker] = {}
        for w in default_workers:
            self.register_worker(w)

    def register_worker(self, worker: AgentWorker) -> None:
        """注册或替换一个专职 Worker 智能体."""
        self.workers[worker.name] = worker

    def _default_route(
        self,
        context: dict[str, Any],
        handoffs: list[HandoffRecord],
    ) -> tuple[str, str]:
        """默认确定性路由策略：Researcher -> Analyst -> Writer -> FINISH."""
        topic = str(context.get("topic", ""))
        if "researcher" in self.workers and "findings" not in context:
            return "researcher", f"请围绕「{topic}」检索并整理关键事实与背景资料。"
        if "analyst" in self.workers and "insights" not in context:
            return "analyst", f"请基于已有调研事实，对「{topic}」进行深入分析与风险评估。"
        if "writer" in self.workers and "report" not in context:
            return "writer", f"请综合调研与分析结果，撰写「{topic}」最终研究报告。"
        return FINISH, "所有专职智能体任务已完成，汇总交付最终报告。"

    def _decide_next(
        self,
        context: dict[str, Any],
        handoffs: list[HandoffRecord],
    ) -> tuple[str, str]:
        if self._router_fn is not None:
            return self._router_fn(context, handoffs, list(self.workers.keys()))
        return self._default_route(context, handoffs)

    def run(
        self,
        topic: str,
        initial_context: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """执行多智能体协作闭环，直到 FINISH 或触发 max_rounds 熔断."""
        context: dict[str, Any] = dict(initial_context or {})
        context["topic"] = topic

        agent_handoffs: list[HandoffRecord] = []
        worker_outputs: dict[str, str] = {}
        status = "max_rounds_reached"
        rounds_used = 0

        for round_num in range(1, self.max_rounds + 1):
            next_agent, instruction = self._decide_next(context, agent_handoffs)
            if next_agent == FINISH:
                status = "completed"
                break

            if next_agent not in self.workers:
                raise KeyError(f"未注册的智能体角色: {next_agent!r}")

            rounds_used = round_num
            worker = self.workers[next_agent]
            result = worker.execute(instruction, context)

            # 更新共享上下文与节点输出
            context.update(result.artifacts)
            worker_outputs[next_agent] = result.output

            preview = result.output.splitlines()[0][:80] if result.output else ""
            agent_handoffs.append(
                HandoffRecord(
                    round_num=round_num,
                    from_agent="supervisor",
                    to_agent=next_agent,
                    instruction=instruction,
                    summary=preview,
                )
            )
        else:
            # 用满 max_rounds 后再检查一次是否恰好达到完成条件
            next_agent, _ = self._decide_next(context, agent_handoffs)
            if next_agent == FINISH:
                status = "completed"

        final_report = str(context.get("report") or "")
        if not final_report:
            sections = [
                f"# {topic} — 阶段性汇总报告（status={status}）",
                *[f"## {name}\n{out}" for name, out in worker_outputs.items()],
            ]
            final_report = "\n\n".join(sections)

        return OrchestrationResult(
            topic=topic,
            status=status,
            rounds_used=rounds_used,
            max_rounds=self.max_rounds,
            agent_handoffs=agent_handoffs,
            worker_outputs=worker_outputs,
            final_report=final_report,
            shared_context=context,
        )
