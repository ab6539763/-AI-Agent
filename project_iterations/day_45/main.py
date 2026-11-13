"""Day 45 平台启动入口：低代码 Workflow DSL 解析与 DAG 执行引擎演示 (v0.4.0-day45)."""

import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    WorkflowEngine,
    build_default_rag_workflow_dsl,
)


def main() -> None:
    """运行 Day 45 Dify/Coze 风格 Workflow DSL 端到端演示."""
    print("=" * 68)
    print("🧩 智枢企业级智能体平台 v0.4.0-day45 · 低代码 Workflow DSL 引擎")
    print("=" * 68)

    dsl = build_default_rag_workflow_dsl()
    engine = WorkflowEngine()

    print("\n[场景 1] 命中知识库分支：query='公司年假和报销流程是什么？'")
    res_hit = engine.run(dsl, inputs={"query": "公司年假和报销流程是什么？"})
    print("执行路径:", " -> ".join(r.node_id for r in res_hit.execution_trace))
    print("路由结果:", res_hit.outputs["route"], "| 命中数:", res_hit.outputs["hit_count"])
    print("输出预览:\n" + res_hit.outputs["answer"])

    print("\n" + "-" * 68)
    print("[场景 2] 未命中兜底分支：query='今天食堂午餐有什么？'")
    dsl_json = json.dumps(dsl, ensure_ascii=False)
    res_miss = engine.run(dsl_json, inputs={"query": "今天食堂午餐有什么？"})
    print("执行路径:", " -> ".join(r.node_id for r in res_miss.execution_trace))
    print("路由结果:", res_miss.outputs["route"], "| 命中数:", res_miss.outputs["hit_count"])
    print("输出预览:\n" + res_miss.outputs["answer"])


if __name__ == "__main__":
    main()
