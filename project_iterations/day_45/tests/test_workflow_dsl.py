"""Day 45 Workflow DSL 引擎单元测试 (v0.4.0-day45)."""

import json
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    WorkflowEngine,
    WorkflowExecutionError,
    WorkflowValidationError,
    build_default_rag_workflow_dsl,
    parse_workflow_dsl,
    render_template,
    resolve_variable,
)


def test_variable_interpolation_and_strict_mode() -> None:
    """测试 {{sys.query}} 与嵌套变量插值及缺失变量报错."""
    pool = {
        "sys": {"query": "MCP 协议怎么接入？", "user": {"role": "admin"}},
        "kb_1": {"hit_count": 2, "context": "[1] MCP 指南"},
    }
    assert resolve_variable("sys.user.role", pool) == "admin"
    rendered = render_template("问题={{ sys.query }} | 命中={{kb_1.hit_count}}", pool)
    assert rendered == "问题=MCP 协议怎么接入？ | 命中=2"

    with pytest.raises(WorkflowExecutionError, match="变量未定义"):
        render_template("{{sys.missing_key}}", pool, strict=True)

    assert render_template("{{sys.missing_key}}", pool, strict=False) == ""


def test_parse_dsl_validation_and_cycle_detection() -> None:
    """测试 DSL 解析、缺少 Start/End 校验与 DAG 环检测."""
    valid_dsl = build_default_rag_workflow_dsl()
    parsed = parse_workflow_dsl(json.dumps(valid_dsl, ensure_ascii=False))
    assert parsed.start_node_id == "start"
    assert "end_hit" in parsed.end_node_ids

    # 制造环：llm_rag -> kb_1
    cyclic_dsl = build_default_rag_workflow_dsl()
    cyclic_dsl["edges"].append({"source": "llm_rag", "target": "kb_1"})
    with pytest.raises(WorkflowValidationError, match="循环依赖"):
        parse_workflow_dsl(cyclic_dsl)

    # 缺少 StartNode
    no_start_dsl = {
        "id": "bad",
        "nodes": [{"id": "end", "type": "end", "config": {"outputs": {}}}],
        "edges": [],
    }
    with pytest.raises(WorkflowValidationError, match="StartNode"):
        parse_workflow_dsl(no_start_dsl)


def test_workflow_engine_hit_and_miss_branches() -> None:
    """测试 RAG 条件分支路由：命中知识库走 llm_rag，未命中走 llm_fallback."""
    dsl = build_default_rag_workflow_dsl()
    engine = WorkflowEngine()

    hit_res = engine.run(dsl, inputs={"query": "请假和报销怎么审批？"})
    assert hit_res.status == "succeeded"
    assert hit_res.outputs["route"] == "knowledge_rag"
    assert hit_res.outputs["hit_count"] >= 1
    assert [r.node_id for r in hit_res.execution_trace] == [
        "start",
        "kb_1",
        "cond_1",
        "llm_rag",
        "end_hit",
    ]

    miss_res = engine.run(dsl, inputs={"query": "火星殖民地天气如何？"})
    assert miss_res.status == "succeeded"
    assert miss_res.outputs["route"] == "fallback"
    assert miss_res.outputs["hit_count"] == 0
    assert [r.node_id for r in miss_res.execution_trace] == [
        "start",
        "kb_1",
        "cond_1",
        "llm_fallback",
        "end_miss",
    ]


def test_custom_retriever_llm_and_required_input() -> None:
    """测试自定义 retriever_fn/llm_fn 注入及 StartNode 必填参数校验."""
    dsl = build_default_rag_workflow_dsl()

    def custom_retriever(query: str, dataset_id: str, top_k: int) -> list[dict]:
        return [{"title": "自定义文档", "content": f"针对 {query} 的专属答案", "score": 0.99}]

    def custom_llm(model: str, system_prompt: str, user_prompt: str, options: dict) -> str:
        return f"CUSTOM({model}): {user_prompt}"

    engine = WorkflowEngine(retriever_fn=custom_retriever, llm_fn=custom_llm)
    res = engine.run(dsl, inputs={"query": "LangGraph 状态机"})
    assert "CUSTOM(deepseek-chat):" in res.outputs["answer"]
    assert "专属答案" in res.outputs["answer"]

    with pytest.raises(WorkflowExecutionError, match="缺少必填输入变量"):
        engine.run(dsl, inputs={})


def test_condition_node_logical_operators() -> None:
    """测试 ConditionNode 的 or 逻辑组合与 contains / is_empty 算子."""
    dsl = {
        "id": "cond-test",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "config": {"variables": [{"variable": "query", "required": True}]},
            },
            {
                "id": "cond",
                "type": "condition",
                "config": {
                    "cases": [
                        {
                            "case_id": "vip",
                            "logical_operator": "or",
                            "conditions": [
                                {
                                    "variable": "{{sys.query}}",
                                    "comparison_operator": "contains",
                                    "value": "紧急",
                                },
                                {
                                    "variable": "sys.query",
                                    "comparison_operator": "equals",
                                    "value": "VIP",
                                },
                            ],
                        }
                    ],
                    "default_branch": "normal",
                },
            },
            {
                "id": "end_vip",
                "type": "end",
                "config": {"outputs": {"priority": "P0", "q": "{{sys.query}}"}},
            },
            {
                "id": "end_normal",
                "type": "end",
                "config": {"outputs": {"priority": "P2", "q": "{{sys.query}}"}},
            },
        ],
        "edges": [
            {"source": "start", "target": "cond"},
            {"source": "cond", "target": "end_vip", "sourceHandle": "vip"},
            {"source": "cond", "target": "end_normal", "sourceHandle": "normal"},
        ],
    }

    engine = WorkflowEngine()
    assert engine.run(dsl, inputs={"query": "紧急故障处理"}).outputs["priority"] == "P0"
    assert engine.run(dsl, inputs={"query": "VIP"}).outputs["priority"] == "P0"
    assert engine.run(dsl, inputs={"query": "普通咨询"}).outputs["priority"] == "P2"
