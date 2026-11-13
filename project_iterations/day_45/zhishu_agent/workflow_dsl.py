"""Day 45: Dify/Coze 风格低代码 Workflow DSL 解析与 DAG 执行引擎 (v0.4.0-day45).

支持声明式 JSON/dict 工作流定义、变量插值 (`{{sys.query}}` / `{{node_id.field}}`)、
DAG 拓扑校验（环检测、孤立边检测）与条件分支路由：
- StartNode: 入口参数校验与 sys 上下文注入
- KnowledgeRetrievalNode: 知识库检索（支持自定义 retriever_fn 与内置 Mock 知识库）
- ConditionNode: 多条件分支路由（支持 equals / contains / gt / lt / is_empty 等算子与 and/or 组合）
- LLMNode: 提示词模板渲染与大模型调用（支持自定义 llm_fn 与确定性 Mock 推理）
- EndNode: 终态输出变量映射与汇总
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*\}\}")


class WorkflowDSLError(Exception):
    """Workflow DSL 引擎基础异常."""


class WorkflowValidationError(WorkflowDSLError):
    """DSL 结构解析、DAG 环检测或节点配置校验失败异常."""


class WorkflowExecutionError(WorkflowDSLError):
    """Workflow 运行期变量解析或节点执行失败异常."""


def resolve_variable(path: str, variables: dict[str, Any], *, strict: bool = True) -> Any:
    """按点分路径（如 `sys.query` 或 `kb_1.hit_count`）从变量池中取值."""
    parts = [p for p in path.strip().split(".") if p]
    if not parts:
        raise WorkflowExecutionError(f"非法变量路径: {path!r}")

    current: Any = variables
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            if strict:
                raise WorkflowExecutionError(f"变量未定义: {{{{{path}}}}}")
            return ""
    return current


def render_template(
    template: str,
    variables: dict[str, Any],
    *,
    strict: bool = True,
) -> str:
    """将模板字符串中的 `{{namespace.key}}` 占位符替换为变量池中的实际值."""
    if not isinstance(template, str):
        return str(template)

    def _replace(match: re.Match[str]) -> str:
        var_path = match.group(1)
        val = resolve_variable(var_path, variables, strict=strict)
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return "" if val is None else str(val)

    return _VAR_PATTERN.sub(_replace, template)


def resolve_value(expr: Any, variables: dict[str, Any], *, strict: bool = True) -> Any:
    """若表达式为单一 `{{var}}` 占位符，返回原始类型值；否则按字符串模板渲染."""
    if not isinstance(expr, str):
        return expr
    stripped = expr.strip()
    full_match = _VAR_PATTERN.fullmatch(stripped)
    if full_match:
        return resolve_variable(full_match.group(1), variables, strict=strict)
    return render_template(expr, variables, strict=strict)


@dataclass
class NodeExecutionRecord:
    """单个节点的执行轨迹记录."""

    node_id: str
    node_type: str
    title: str
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    selected_branch: str | None = None
    duration_ms: float = 0.0


@dataclass
class WorkflowEdge:
    """DAG 有向边定义."""

    source: str
    target: str
    source_handle: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WorkflowEdge:
        source = raw.get("source")
        target = raw.get("target")
        if not source or not target:
            raise WorkflowValidationError(f"边定义缺少 source 或 target: {raw}")
        handle = raw.get("sourceHandle") or raw.get("source_handle") or raw.get("branch")
        return cls(source=str(source), target=str(target), source_handle=handle)


@dataclass
class ExecutionContext:
    """工作流运行期共享上下文."""

    variables: dict[str, Any]
    retriever_fn: Callable[[str, str, int], list[dict[str, Any]]]
    llm_fn: Callable[[str, str, str, dict[str, Any]], str]
    strict_variables: bool = True


class BaseNode:
    """所有 DSL 节点的抽象基类."""

    node_type: str = "base"

    def __init__(
        self,
        node_id: str,
        title: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.id = node_id
        self.title = title or node_id
        self.config = dict(config or {})

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        raise NotImplementedError


class StartNode(BaseNode):
    """工作流入口节点：校验输入参数并写入 `sys` 与自身节点命名空间."""

    node_type = "start"

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        declared_vars = self.config.get("variables", [])
        sys_vars = ctx.variables.setdefault("sys", {})
        node_outputs: dict[str, Any] = {}

        for var_spec in declared_vars:
            if isinstance(var_spec, str):
                name, required, default = var_spec, False, None
            elif isinstance(var_spec, dict):
                name = str(var_spec.get("variable") or var_spec.get("name") or "")
                required = bool(var_spec.get("required", False))
                default = var_spec.get("default")
            else:
                raise WorkflowValidationError(f"StartNode 变量声明格式非法: {var_spec}")

            if not name:
                raise WorkflowValidationError("StartNode 变量名不能为空")

            if name in sys_vars and sys_vars[name] is not None:
                val = sys_vars[name]
            elif default is not None:
                val = default
                sys_vars[name] = val
            elif required:
                raise WorkflowExecutionError(f"StartNode 缺少必填输入变量: sys.{name}")
            else:
                val = ""
                sys_vars[name] = val

            node_outputs[name] = val

        # 透传所有 sys 变量到 start 节点输出，方便 {{start.query}} 引用
        for k, v in sys_vars.items():
            node_outputs.setdefault(k, v)
        return node_outputs


class KnowledgeRetrievalNode(BaseNode):
    """知识库检索节点：渲染查询模板并调用检索器返回文档列表与上下文."""

    node_type = "knowledge-retrieval"

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        query_tpl = self.config.get("query_template") or self.config.get("query") or "{{sys.query}}"
        dataset_id = str(self.config.get("dataset_id", "default_kb"))
        top_k = int(self.config.get("top_k", 3))
        score_threshold = float(self.config.get("score_threshold", 0.0))

        query_text = render_template(str(query_tpl), ctx.variables, strict=ctx.strict_variables)
        raw_docs = ctx.retriever_fn(query_text, dataset_id, top_k)

        filtered_docs = [
            doc for doc in raw_docs if float(doc.get("score", 1.0)) >= score_threshold
        ][:top_k]

        context_chunks = [
            f"[{i + 1}] {doc.get('title', 'doc')}: {doc.get('content', '')}"
            for i, doc in enumerate(filtered_docs)
        ]
        return {
            "query": query_text,
            "dataset_id": dataset_id,
            "documents": filtered_docs,
            "hit_count": len(filtered_docs),
            "context": "\n".join(context_chunks),
        }


class ConditionNode(BaseNode):
    """条件分支节点：支持多分支规则与 and/or 逻辑组合，返回命中的分支标识."""

    node_type = "condition"

    @staticmethod
    def _eval_single(actual: Any, op: str, expected: Any) -> bool:
        if op in ("equals", "eq", "=="):
            return actual == expected
        if op in ("not_equals", "ne", "!="):
            return actual != expected
        if op == "contains":
            if actual is None:
                return False
            return str(expected) in str(actual)
        if op == "not_contains":
            if actual is None:
                return True
            return str(expected) not in str(actual)
        if op in ("gt", ">"):
            return float(actual) > float(expected)
        if op in ("gte", ">="):
            return float(actual) >= float(expected)
        if op in ("lt", "<"):
            return float(actual) < float(expected)
        if op in ("lte", "<="):
            return float(actual) <= float(expected)
        if op == "is_empty":
            return actual is None or actual == "" or actual == [] or actual == {}
        if op == "is_not_empty":
            return not (actual is None or actual == "" or actual == [] or actual == {})
        raise WorkflowValidationError(f"不支持的条件比较算子: {op!r}")

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        cases = self.config.get("cases", [])
        default_branch = str(self.config.get("default_branch", "else"))

        for case in cases:
            case_id = str(case.get("case_id") or case.get("id") or "")
            if not case_id:
                raise WorkflowValidationError(f"ConditionNode 分支缺少 case_id: {case}")
            logical_op = str(case.get("logical_operator", "and")).lower()
            conditions = case.get("conditions", [])
            if not conditions:
                continue

            results: list[bool] = []
            for cond in conditions:
                var_path = str(cond.get("variable") or cond.get("variable_selector") or "")
                # 兼容 {{kb_1.hit_count}} 或 kb_1.hit_count 两种写法
                match = _VAR_PATTERN.fullmatch(var_path.strip())
                if match:
                    var_path = match.group(1)
                actual = resolve_variable(var_path, ctx.variables, strict=ctx.strict_variables)
                op = str(cond.get("comparison_operator") or cond.get("operator") or "equals")
                expected = cond.get("value")
                results.append(self._eval_single(actual, op, expected))

            matched = all(results) if logical_op == "and" else any(results)
            if matched:
                return {"selected_branch": case_id, "matched": True}

        return {"selected_branch": default_branch, "matched": False}


class LLMNode(BaseNode):
    """大模型推理节点：渲染 system_prompt 与 prompt，调用 llm_fn 生成文本."""

    node_type = "llm"

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        model = str(self.config.get("model", "zhishu-llm-mock"))
        system_tpl = str(self.config.get("system_prompt", "你是智枢企业级智能体助手。"))
        user_tpl = str(self.config.get("prompt") or self.config.get("user_prompt") or "{{sys.query}}")
        temperature = float(self.config.get("temperature", 0.2))

        system_prompt = render_template(system_tpl, ctx.variables, strict=ctx.strict_variables)
        user_prompt = render_template(user_tpl, ctx.variables, strict=ctx.strict_variables)

        text = ctx.llm_fn(
            model,
            system_prompt,
            user_prompt,
            {"temperature": temperature, "node_id": self.id},
        )
        return {
            "text": text,
            "model": model,
            "rendered_system_prompt": system_prompt,
            "rendered_user_prompt": user_prompt,
        }


class EndNode(BaseNode):
    """工作流终态节点：按声明映射最终输出字段."""

    node_type = "end"

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        outputs_cfg = self.config.get("outputs", {})
        final_outputs: dict[str, Any] = {}

        if isinstance(outputs_cfg, dict):
            for key, expr in outputs_cfg.items():
                final_outputs[str(key)] = resolve_value(
                    expr, ctx.variables, strict=ctx.strict_variables
                )
        elif isinstance(outputs_cfg, list):
            for item in outputs_cfg:
                key = str(item.get("variable") or "")
                expr = item.get("value_selector") or item.get("value") or ""
                if not key:
                    raise WorkflowValidationError(f"EndNode 输出配置缺少 variable: {item}")
                final_outputs[key] = resolve_value(
                    expr, ctx.variables, strict=ctx.strict_variables
                )
        else:
            raise WorkflowValidationError(f"EndNode outputs 配置格式非法: {type(outputs_cfg)}")

        return final_outputs


NODE_TYPE_MAP: dict[str, type[BaseNode]] = {
    "start": StartNode,
    "knowledge-retrieval": KnowledgeRetrievalNode,
    "knowledge_retrieval": KnowledgeRetrievalNode,
    "condition": ConditionNode,
    "if-else": ConditionNode,
    "llm": LLMNode,
    "end": EndNode,
}


@dataclass
class WorkflowDefinition:
    """解析并校验通过的 DAG 工作流定义."""

    workflow_id: str
    name: str
    version: str
    nodes: dict[str, BaseNode]
    edges: list[WorkflowEdge]
    start_node_id: str
    end_node_ids: set[str]
    outgoing: dict[str, list[WorkflowEdge]]


@dataclass
class WorkflowRunResult:
    """工作流单次执行的完整结果与可观测轨迹."""

    workflow_id: str
    status: str
    outputs: dict[str, Any]
    variables: dict[str, Any]
    execution_trace: list[NodeExecutionRecord]


def parse_workflow_dsl(dsl: dict[str, Any] | str) -> WorkflowDefinition:
    """解析 JSON/dict 形式的 Workflow DSL，并执行 DAG 结构与环检测校验."""
    if isinstance(dsl, str):
        try:
            raw = json.loads(dsl)
        except json.JSONDecodeError as exc:
            raise WorkflowValidationError(f"DSL JSON 解析失败: {exc}") from exc
    elif isinstance(dsl, dict):
        raw = dsl
    else:
        raise WorkflowValidationError(f"DSL 必须为 dict 或 JSON 字符串，收到: {type(dsl)}")

    workflow_id = str(raw.get("id") or "workflow-untitled")
    name = str(raw.get("name") or workflow_id)
    version = str(raw.get("version") or "0.4.0-day45")

    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges", [])
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowValidationError("DSL 必须包含非空的 nodes 列表")
    if not isinstance(raw_edges, list):
        raise WorkflowValidationError("DSL edges 必须为列表")

    nodes: dict[str, BaseNode] = {}
    start_ids: list[str] = []
    end_ids: set[str] = set()

    for item in raw_nodes:
        if not isinstance(item, dict):
            raise WorkflowValidationError(f"节点定义必须为 dict: {item}")
        node_id = str(item.get("id") or "").strip()
        node_type = str(item.get("type") or "").strip()
        if not node_id or not node_type:
            raise WorkflowValidationError(f"节点缺少 id 或 type: {item}")
        if node_id in nodes:
            raise WorkflowValidationError(f"存在重复节点 ID: {node_id!r}")

        node_cls = NODE_TYPE_MAP.get(node_type)
        if node_cls is None:
            raise WorkflowValidationError(f"不支持的节点类型: {node_type!r}")

        title = str(item.get("title") or node_id)
        config = item.get("config") or item.get("data") or {}
        node = node_cls(node_id=node_id, title=title, config=config)
        nodes[node_id] = node

        if isinstance(node, StartNode):
            start_ids.append(node_id)
        elif isinstance(node, EndNode):
            end_ids.add(node_id)

    if len(start_ids) != 1:
        raise WorkflowValidationError(
            f"工作流必须有且仅有一个 StartNode，当前数量: {len(start_ids)}"
        )
    if not end_ids:
        raise WorkflowValidationError("工作流必须至少包含一个 EndNode")

    edges: list[WorkflowEdge] = []
    outgoing: dict[str, list[WorkflowEdge]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in nodes}

    for raw_edge in raw_edges:
        edge = WorkflowEdge.from_dict(raw_edge)
        if edge.source not in nodes:
            raise WorkflowValidationError(f"边引用了不存在的源节点: {edge.source!r}")
        if edge.target not in nodes:
            raise WorkflowValidationError(f"边引用了不存在的目标节点: {edge.target!r}")
        if edge.source == edge.target:
            raise WorkflowValidationError(f"检测到自环边: {edge.source!r}")
        edges.append(edge)
        outgoing[edge.source].append(edge)
        in_degree[edge.target] += 1

    # Kahn 算法进行 DAG 环检测
    queue: deque[str] = deque([nid for nid, deg in in_degree.items() if deg == 0])
    visited_count = 0
    while queue:
        curr = queue.popleft()
        visited_count += 1
        for edge in outgoing.get(curr, []):
            in_degree[edge.target] -= 1
            if in_degree[edge.target] == 0:
                queue.append(edge.target)

    if visited_count != len(nodes):
        raise WorkflowValidationError("DSL 工作流存在循环依赖（非合法 DAG）")

    return WorkflowDefinition(
        workflow_id=workflow_id,
        name=name,
        version=version,
        nodes=nodes,
        edges=edges,
        start_node_id=start_ids[0],
        end_node_ids=end_ids,
        outgoing=dict(outgoing),
    )


def default_mock_retriever(query: str, dataset_id: str, top_k: int) -> list[dict[str, Any]]:
    """内置默认知识库检索器（无外部依赖，便于离线演示与单测）."""
    kb = [
        {
            "title": "智枢平台请假与报销制度",
            "content": "员工年假需提前 3 个工作日在 OA 提交申请；差旅报销需附发票与审批单。",
            "keywords": ["请假", "年假", "报销", "差旅", "OA"],
            "score": 0.92,
        },
        {
            "title": "低代码与高代码边界规范",
            "content": "简单 RAG 编排与运营活动页推荐 Dify/Coze 低代码；复杂状态机与高并发风控推荐 LangGraph 高代码。",
            "keywords": ["低代码", "高代码", "Dify", "Coze", "LangGraph", "RAG"],
            "score": 0.95,
        },
        {
            "title": "MCP 协议接入指南",
            "content": "所有外部工具统一通过 Model Context Protocol (MCP) 暴露标准 Schema 与鉴权。",
            "keywords": ["MCP", "工具", "协议", "鉴权"],
            "score": 0.88,
        },
    ]
    q_lower = query.lower()
    hits = []
    for item in kb:
        if any(kw.lower() in q_lower for kw in item["keywords"]):
            hits.append(
                {
                    "dataset_id": dataset_id,
                    "title": item["title"],
                    "content": item["content"],
                    "score": item["score"],
                }
            )
    return hits[:top_k]


def default_mock_llm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    options: dict[str, Any],
) -> str:
    """内置默认确定性 Mock LLM."""
    return f"[{model}] 基于提示词完成推理:\n{user_prompt}"


class WorkflowEngine:
    """Dify/Coze 风格低代码 Workflow DSL 执行引擎."""

    def __init__(
        self,
        *,
        retriever_fn: Callable[[str, str, int], list[dict[str, Any]]] | None = None,
        llm_fn: Callable[[str, str, str, dict[str, Any]], str] | None = None,
        strict_variables: bool = True,
    ) -> None:
        self.retriever_fn = retriever_fn or default_mock_retriever
        self.llm_fn = llm_fn or default_mock_llm
        self.strict_variables = strict_variables

    def run(
        self,
        dsl: dict[str, Any] | str,
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowRunResult:
        """解析并从 StartNode 开始沿激活边执行 DAG，直至 EndNode."""
        definition = parse_workflow_dsl(dsl)
        variables: dict[str, Any] = {"sys": dict(inputs or {})}
        ctx = ExecutionContext(
            variables=variables,
            retriever_fn=self.retriever_fn,
            llm_fn=self.llm_fn,
            strict_variables=self.strict_variables,
        )

        trace: list[NodeExecutionRecord] = []
        final_outputs: dict[str, Any] = {}

        # 使用可达激活队列：仅当节点被激活（或所有激活前驱完成）时执行
        queue: deque[str] = deque([definition.start_node_id])
        executed: set[str] = set()

        while queue:
            node_id = queue.popleft()
            if node_id in executed:
                continue

            node = definition.nodes[node_id]
            t0 = time.perf_counter()
            outputs = node.execute(ctx)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)

            ctx.variables[node_id] = outputs
            executed.add(node_id)

            selected_branch = (
                outputs.get("selected_branch") if isinstance(node, ConditionNode) else None
            )
            trace.append(
                NodeExecutionRecord(
                    node_id=node.id,
                    node_type=node.node_type,
                    title=node.title,
                    status="succeeded",
                    outputs=outputs,
                    selected_branch=selected_branch,
                    duration_ms=elapsed_ms,
                )
            )

            if isinstance(node, EndNode):
                final_outputs = outputs
                break

            outgoing_edges = definition.outgoing.get(node_id, [])
            for edge in outgoing_edges:
                if isinstance(node, ConditionNode):
                    if edge.source_handle is None or edge.source_handle == selected_branch:
                        queue.append(edge.target)
                else:
                    queue.append(edge.target)

        return WorkflowRunResult(
            workflow_id=definition.workflow_id,
            status="succeeded",
            outputs=final_outputs,
            variables=ctx.variables,
            execution_trace=trace,
        )


def build_default_rag_workflow_dsl() -> dict[str, Any]:
    """构建标准 Dify/Coze 风格 RAG 条件路由工作流 DSL 示例."""
    return {
        "id": "zhishu-rag-assistant-v1",
        "name": "智枢企业知识库问答工作流",
        "version": "0.4.0-day45",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "title": "用户输入",
                "config": {
                    "variables": [
                        {"variable": "query", "required": True},
                        {"variable": "channel", "required": False, "default": "web"},
                    ]
                },
            },
            {
                "id": "kb_1",
                "type": "knowledge-retrieval",
                "title": "企业知识库检索",
                "config": {
                    "dataset_id": "zhishu_policy_kb",
                    "query_template": "{{sys.query}}",
                    "top_k": 3,
                },
            },
            {
                "id": "cond_1",
                "type": "condition",
                "title": "命中判定分支",
                "config": {
                    "cases": [
                        {
                            "case_id": "hit",
                            "logical_operator": "and",
                            "conditions": [
                                {
                                    "variable": "kb_1.hit_count",
                                    "comparison_operator": "gt",
                                    "value": 0,
                                }
                            ],
                        }
                    ],
                    "default_branch": "miss",
                },
            },
            {
                "id": "llm_rag",
                "type": "llm",
                "title": "基于知识库生成回答",
                "config": {
                    "model": "deepseek-chat",
                    "system_prompt": "你是智枢企业知识助手，请严格依据参考资料回答。",
                    "prompt": "用户问题：{{sys.query}}\n参考资料：\n{{kb_1.context}}",
                },
            },
            {
                "id": "llm_fallback",
                "type": "llm",
                "title": "未命中兜底回答",
                "config": {
                    "model": "deepseek-chat",
                    "system_prompt": "你是智枢企业知识助手。",
                    "prompt": "知识库未检索到“{{sys.query}}”相关规范，请给出通用引导并建议联系人工客服。",
                },
            },
            {
                "id": "end_hit",
                "type": "end",
                "title": "命中输出",
                "config": {
                    "outputs": {
                        "answer": "{{llm_rag.text}}",
                        "route": "knowledge_rag",
                        "hit_count": "{{kb_1.hit_count}}",
                    }
                },
            },
            {
                "id": "end_miss",
                "type": "end",
                "title": "兜底输出",
                "config": {
                    "outputs": {
                        "answer": "{{llm_fallback.text}}",
                        "route": "fallback",
                        "hit_count": "{{kb_1.hit_count}}",
                    }
                },
            },
        ],
        "edges": [
            {"source": "start", "target": "kb_1"},
            {"source": "kb_1", "target": "cond_1"},
            {"source": "cond_1", "target": "llm_rag", "sourceHandle": "hit"},
            {"source": "cond_1", "target": "llm_fallback", "sourceHandle": "miss"},
            {"source": "llm_rag", "target": "end_hit"},
            {"source": "llm_fallback", "target": "end_miss"},
        ],
    }
