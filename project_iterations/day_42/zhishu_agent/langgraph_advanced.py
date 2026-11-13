"""智枢平台 Day 42 核心模块：高级 LangGraph 状态图引擎与多章节写作智能体 (v0.4.0-day42).

核心能力：
1. SQLiteCheckpointer：基于 SQLite 按 thread_id 持久化图执行快照，支持断点恢复与历史回溯。
2. interrupt_before & resume(thread_id, updated_state)：Human-in-the-loop 人工审批拦截与状态注入恢复。
3. ParallelSectionRunner：基于 ThreadPoolExecutor 的并发章节撰写器，支持有序聚合与单节重试。
4. RetryPolicy：节点级可配置重试策略（最大重试次数、指数退避、异常白名单）。
5. Writing Agent：完整“大纲生成 -> 人工审批 -> 并发写章 -> 终稿润色”企业级长文写作工作流。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type


END = "__END__"
START = "__START__"

NodeFunc = Callable[[Dict[str, Any]], Dict[str, Any]]
ConditionFunc = Callable[[Dict[str, Any]], str]


@dataclass(frozen=True)
class RetryPolicy:
    """节点级或任务级重试策略配置."""

    max_retries: int = 2
    initial_delay_s: float = 0.01
    backoff_factor: float = 2.0
    retry_on: Tuple[Type[BaseException], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries 不能为负数")
        if self.initial_delay_s < 0:
            raise ValueError("initial_delay_s 不能为负数")
        if self.backoff_factor < 1.0:
            raise ValueError("backoff_factor 必须 >= 1.0")


@dataclass
class CheckpointRecord:
    """单次图执行检查点记录."""

    checkpoint_id: str
    thread_id: str
    step: int
    next_node: str
    state: Dict[str, Any]
    status: str
    created_at: str


@dataclass
class GraphExecutionResult:
    """图执行或恢复后的结构化返回结果."""

    thread_id: str
    status: str  # "completed" | "interrupted"
    state: Dict[str, Any]
    next_node: Optional[str] = None
    interrupted_at: Optional[str] = None
    checkpoint_id: Optional[str] = None
    execution_trace: List[str] = field(default_factory=list)


class SQLiteCheckpointer:
    """基于 SQLite 的持久化状态检查点存储，按 thread_id 隔离会话状态."""

    def __init__(self, db_path: str | Path) -> None:
        """初始化 SQLite 检查点表结构."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """创建数据库连接."""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        """创建 checkpoints 表与 thread_id 索引."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkpoint_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    next_node TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_step
                ON checkpoints (thread_id, id DESC)
                """
            )
            conn.commit()

    def save_checkpoint(
        self,
        thread_id: str,
        step: int,
        next_node: str,
        state: Dict[str, Any],
        status: str,
    ) -> CheckpointRecord:
        """保存指定 thread_id 的当前状态快照."""
        checkpoint_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(timezone.utc).isoformat()
        state_json = json.dumps(state, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (
                    checkpoint_id, thread_id, step, next_node, state_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, thread_id, step, next_node, state_json, status, created_at),
            )
            conn.commit()
        return CheckpointRecord(
            checkpoint_id=checkpoint_id,
            thread_id=thread_id,
            step=step,
            next_node=next_node,
            state=json.loads(state_json),
            status=status,
            created_at=created_at,
        )

    def get_latest(self, thread_id: str) -> Optional[CheckpointRecord]:
        """读取指定 thread_id 最新一条检查点."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT checkpoint_id, thread_id, step, next_node, state_json, status, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return CheckpointRecord(
            checkpoint_id=row[0],
            thread_id=row[1],
            step=row[2],
            next_node=row[3],
            state=json.loads(row[4]),
            status=row[5],
            created_at=row[6],
        )

    def get_history(self, thread_id: str) -> List[CheckpointRecord]:
        """按执行顺序返回指定 thread_id 的全部历史检查点."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT checkpoint_id, thread_id, step, next_node, state_json, status, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY id ASC
                """,
                (thread_id,),
            ).fetchall()
        return [
            CheckpointRecord(
                checkpoint_id=r[0],
                thread_id=r[1],
                step=r[2],
                next_node=r[3],
                state=json.loads(r[4]),
                status=r[5],
                created_at=r[6],
            )
            for r in rows
        ]

    def list_threads(self) -> List[str]:
        """列出当前存储的所有不重复 thread_id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id ASC"
            ).fetchall()
        return [r[0] for r in rows]

    def delete_thread(self, thread_id: str) -> int:
        """删除指定 thread_id 的全部检查点，返回删除行数."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = ?",
                (thread_id,),
            )
            conn.commit()
            return int(cur.rowcount)


def execute_with_retry(
    fn: Callable[[], Any],
    policy: Optional[RetryPolicy] = None,
) -> Tuple[Any, int]:
    """按给定 RetryPolicy 执行无参可调用对象，返回 (结果, 实际尝试次数)."""
    if policy is None:
        return fn(), 1

    attempt = 0
    delay = policy.initial_delay_s
    while True:
        attempt += 1
        try:
            return fn(), attempt
        except policy.retry_on:
            if attempt > policy.max_retries:
                raise
            if delay > 0:
                time.sleep(delay)
            delay *= policy.backoff_factor


@dataclass
class _NodeSpec:
    """内部节点定义."""

    name: str
    func: NodeFunc
    retry_policy: Optional[RetryPolicy] = None


class AdvancedStateGraph:
    """支持 Checkpointer、Interrupt/Resume 与节点级重试的状态图构建器."""

    def __init__(self) -> None:
        """初始化节点、边与入口点注册表."""
        self._nodes: Dict[str, _NodeSpec] = {}
        self._edges: Dict[str, str] = {}
        self._conditional_edges: Dict[str, Tuple[ConditionFunc, Dict[str, str]]] = {}
        self._entry_point: Optional[str] = None

    def add_node(
        self,
        name: str,
        func: NodeFunc,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> "AdvancedStateGraph":
        """注册图节点及可选的节点级 RetryPolicy."""
        if not name or name in (START, END):
            raise ValueError(f"非法节点名称: {name!r}")
        self._nodes[name] = _NodeSpec(name=name, func=func, retry_policy=retry_policy)
        return self

    def set_entry_point(self, node_name: str) -> "AdvancedStateGraph":
        """设置状态图的起始节点."""
        if node_name not in self._nodes:
            raise ValueError(f"入口节点未注册: {node_name}")
        self._entry_point = node_name
        return self

    def add_edge(self, source: str, target: str) -> "AdvancedStateGraph":
        """添加有向确定性边."""
        if source == START:
            return self.set_entry_point(target)
        if source not in self._nodes:
            raise ValueError(f"源节点未注册: {source}")
        if target != END and target not in self._nodes:
            raise ValueError(f"目标节点未注册: {target}")
        self._edges[source] = target
        return self

    def add_conditional_edges(
        self,
        source: str,
        condition: ConditionFunc,
        mapping: Dict[str, str],
    ) -> "AdvancedStateGraph":
        """添加基于状态的条件路由边."""
        if source not in self._nodes:
            raise ValueError(f"源节点未注册: {source}")
        for target in mapping.values():
            if target != END and target not in self._nodes:
                raise ValueError(f"条件目标节点未注册: {target}")
        self._conditional_edges[source] = (condition, dict(mapping))
        return self

    def compile(
        self,
        checkpointer: Optional[SQLiteCheckpointer] = None,
        interrupt_before: Optional[Sequence[str]] = None,
    ) -> "CompiledAdvancedGraph":
        """编译状态图为可执行运行时对象."""
        if self._entry_point is None:
            raise ValueError("必须先通过 set_entry_point() 或 add_edge(START, ...) 设置入口节点")
        interrupt_set = set(interrupt_before or [])
        for node_name in interrupt_set:
            if node_name not in self._nodes:
                raise ValueError(f"interrupt_before 中的节点未注册: {node_name}")
        return CompiledAdvancedGraph(
            nodes=dict(self._nodes),
            edges=dict(self._edges),
            conditional_edges=dict(self._conditional_edges),
            entry_point=self._entry_point,
            checkpointer=checkpointer,
            interrupt_before=interrupt_set,
        )


class CompiledAdvancedGraph:
    """已编译的可执行状态图，支持 invoke() 与 resume()."""

    def __init__(
        self,
        nodes: Dict[str, _NodeSpec],
        edges: Dict[str, str],
        conditional_edges: Dict[str, Tuple[ConditionFunc, Dict[str, str]]],
        entry_point: str,
        checkpointer: Optional[SQLiteCheckpointer],
        interrupt_before: set[str],
    ) -> None:
        """初始化编译后的图运行时."""
        self._nodes = nodes
        self._edges = edges
        self._conditional_edges = conditional_edges
        self._entry_point = entry_point
        self._checkpointer = checkpointer
        self._interrupt_before = interrupt_before

    def _resolve_next_node(self, current_node: str, state: Dict[str, Any]) -> str:
        """根据确定性边或条件边计算下一跳节点."""
        if current_node in self._conditional_edges:
            condition, mapping = self._conditional_edges[current_node]
            branch_key = condition(state)
            if branch_key not in mapping:
                raise KeyError(
                    f"节点 '{current_node}' 条件路由返回值 {branch_key!r} 未在映射中定义: {list(mapping)}"
                )
            return mapping[branch_key]
        return self._edges.get(current_node, END)

    def _run_loop(
        self,
        thread_id: str,
        state: Dict[str, Any],
        start_node: str,
        start_step: int,
        skip_interrupt_on_first: bool = False,
        max_steps: int = 50,
    ) -> GraphExecutionResult:
        """执行主循环，遇到 interrupt_before 节点时持久化状态并暂停."""
        current_node = start_node
        step = start_step
        trace: List[str] = []
        last_checkpoint_id: Optional[str] = None
        first_iteration = True

        while current_node != END:
            if step >= max_steps:
                raise RuntimeError(f"图执行超过最大步数限制 ({max_steps})，可能存在死循环")

            if current_node in self._interrupt_before and not (
                first_iteration and skip_interrupt_on_first
            ):
                if self._checkpointer is not None:
                    ckpt = self._checkpointer.save_checkpoint(
                        thread_id=thread_id,
                        step=step,
                        next_node=current_node,
                        state=state,
                        status="interrupted",
                    )
                    last_checkpoint_id = ckpt.checkpoint_id
                return GraphExecutionResult(
                    thread_id=thread_id,
                    status="interrupted",
                    state=dict(state),
                    next_node=current_node,
                    interrupted_at=current_node,
                    checkpoint_id=last_checkpoint_id,
                    execution_trace=trace,
                )

            first_iteration = False
            spec = self._nodes[current_node]
            update, attempts = execute_with_retry(
                lambda s=spec, st=dict(state): s.func(st),
                spec.retry_policy,
            )
            if isinstance(update, dict):
                state = {**state, **update}
            trace.append(f"{current_node}(attempts={attempts})")
            step += 1

            next_node = self._resolve_next_node(current_node, state)
            if self._checkpointer is not None:
                ckpt = self._checkpointer.save_checkpoint(
                    thread_id=thread_id,
                    step=step,
                    next_node=next_node,
                    state=state,
                    status="completed" if next_node == END else "running",
                )
                last_checkpoint_id = ckpt.checkpoint_id
            current_node = next_node

        return GraphExecutionResult(
            thread_id=thread_id,
            status="completed",
            state=dict(state),
            next_node=None,
            interrupted_at=None,
            checkpoint_id=last_checkpoint_id,
            execution_trace=trace,
        )

    def invoke(
        self,
        initial_state: Dict[str, Any],
        thread_id: Optional[str] = None,
        max_steps: int = 50,
    ) -> GraphExecutionResult:
        """从入口节点启动图执行，若配置 checkpointer 则自动持久化快照."""
        resolved_thread_id = thread_id or f"thread-{uuid.uuid4().hex[:8]}"
        return self._run_loop(
            thread_id=resolved_thread_id,
            state=dict(initial_state),
            start_node=self._entry_point,
            start_step=0,
            skip_interrupt_on_first=False,
            max_steps=max_steps,
        )

    def resume(
        self,
        thread_id: str,
        updated_state: Optional[Dict[str, Any]] = None,
        max_steps: int = 50,
    ) -> GraphExecutionResult:
        """从 SQLiteCheckpointer 加载被中断的线程状态，注入人工修改后继续执行."""
        if self._checkpointer is None:
            raise RuntimeError("未配置 SQLiteCheckpointer，无法执行 resume()")

        latest = self._checkpointer.get_latest(thread_id)
        if latest is None:
            raise KeyError(f"未找到 thread_id={thread_id!r} 的检查点记录")
        if latest.status != "interrupted":
            raise ValueError(
                f"thread_id={thread_id!r} 当前状态为 {latest.status!r}，仅 'interrupted' 状态可恢复"
            )

        merged_state = dict(latest.state)
        if updated_state:
            merged_state.update(updated_state)

        return self._run_loop(
            thread_id=thread_id,
            state=merged_state,
            start_node=latest.next_node,
            start_step=latest.step,
            skip_interrupt_on_first=True,
            max_steps=max_steps,
        )


@dataclass
class SectionDraftResult:
    """单章节并发生成结果与重试遥测信息."""

    index: int
    title: str
    content: str
    attempts: int


class ParallelSectionRunner:
    """基于 ThreadPoolExecutor 的并发章节撰写器，保持章节输出顺序确定性."""

    def __init__(
        self,
        max_workers: int = 4,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        """初始化线程池并发度与单章节重试策略."""
        if max_workers < 1:
            raise ValueError("max_workers 必须 >= 1")
        self.max_workers = max_workers
        self.retry_policy = retry_policy

    def run(
        self,
        sections: Sequence[str],
        draft_fn: Callable[[int, str], str],
    ) -> List[SectionDraftResult]:
        """并发撰写所有章节，并按原始大纲索引顺序返回结果列表."""
        if not sections:
            return []

        results: Dict[int, SectionDraftResult] = {}

        def _worker(idx: int, title: str) -> SectionDraftResult:
            content, attempts = execute_with_retry(
                lambda i=idx, t=title: draft_fn(i, t),
                self.retry_policy,
            )
            return SectionDraftResult(
                index=idx,
                title=title,
                content=str(content),
                attempts=attempts,
            )

        worker_count = min(self.max_workers, len(sections))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(_worker, idx, title): idx
                for idx, title in enumerate(sections)
            }
            for future in as_completed(future_map):
                res = future.result()
                results[res.index] = res

        return [results[i] for i in range(len(sections))]


def _default_outline_generator(topic: str) -> List[str]:
    """确定性默认大纲生成器（无外部 LLM 依赖时使用）."""
    return [
        f"第一章：{topic} 的背景与核心痛点",
        f"第二章：{topic} 的系统架构与关键技术选型",
        f"第三章：{topic} 的工程落地与未来演进",
    ]


def _default_section_drafter(topic: str, index: int, title: str) -> str:
    """确定性默认章节撰写器."""
    return (
        f"### {title}\n"
        f"本节围绕“{topic}”第 {index + 1} 部分展开：结合企业级智能体平台实践，"
        f"明确状态持久化、人工审批门禁与并发执行在生产稳定性中的核心价值。"
    )


def build_writing_agent_graph(
    checkpointer: SQLiteCheckpointer,
    outline_fn: Optional[Callable[[str], List[str]]] = None,
    section_draft_fn: Optional[Callable[[str, int, str], str]] = None,
    max_workers: int = 4,
    node_retry_policy: Optional[RetryPolicy] = None,
) -> CompiledAdvancedGraph:
    """构建完整写作智能体图：Outline -> Human Approval -> Parallel Chapters -> Final Polish."""
    make_outline = outline_fn or _default_outline_generator
    draft_section = section_draft_fn or _default_section_drafter
    section_runner = ParallelSectionRunner(
        max_workers=max_workers,
        retry_policy=node_retry_policy,
    )

    def generate_outline(state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 1：根据主题生成结构化写作大纲."""
        topic = str(state.get("topic", "未命名主题"))
        outline = make_outline(topic)
        return {
            "outline": list(outline),
            "approved": False,
            "revision_count": int(state.get("revision_count", 0)) + 1,
        }

    def human_approval(state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 2：人工审批校验节点（配合 interrupt_before 在执行前暂停）."""
        approved = bool(state.get("approved", False))
        feedback = str(state.get("human_feedback", ""))
        return {
            "approved": approved,
            "human_feedback": feedback,
        }

    def route_after_approval(state: Dict[str, Any]) -> str:
        """条件路由：审批通过进入并发写章，否则打回重新生成大纲."""
        return "approved" if state.get("approved") else "revise"

    def parallel_chapters(state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 3：使用 ParallelSectionRunner 并发撰写全部章节."""
        topic = str(state.get("topic", "未命名主题"))
        outline: Iterable[str] = state.get("outline", [])
        section_results = section_runner.run(
            list(outline),
            lambda idx, title: draft_section(topic, idx, title),
        )
        return {
            "chapters": [
                {
                    "index": r.index,
                    "title": r.title,
                    "content": r.content,
                    "attempts": r.attempts,
                }
                for r in section_results
            ]
        }

    def final_polish(state: Dict[str, Any]) -> Dict[str, Any]:
        """节点 4：汇总所有章节并执行统一格式润色，输出终稿."""
        topic = str(state.get("topic", "未命名主题"))
        chapters = state.get("chapters", [])
        feedback = str(state.get("human_feedback", "")).strip()
        header = f"# {topic}\n"
        if feedback:
            header += f"> 审稿批注：{feedback}\n"
        body = "\n\n".join(str(ch["content"]) for ch in chapters)
        footer = f"\n\n---\n共完成 {len(chapters)} 个章节的并发撰写与终稿润色。"
        return {
            "final_article": f"{header}\n{body}{footer}".strip(),
        }

    graph = AdvancedStateGraph()
    graph.add_node("generate_outline", generate_outline, retry_policy=node_retry_policy)
    graph.add_node("human_approval", human_approval)
    graph.add_node("parallel_chapters", parallel_chapters, retry_policy=node_retry_policy)
    graph.add_node("final_polish", final_polish)

    graph.set_entry_point("generate_outline")
    graph.add_edge("generate_outline", "human_approval")
    graph.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "approved": "parallel_chapters",
            "revise": "generate_outline",
        },
    )
    graph.add_edge("parallel_chapters", "final_polish")
    graph.add_edge("final_polish", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval"],
    )
