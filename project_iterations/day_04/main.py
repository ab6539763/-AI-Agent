"""Day 04 平台启动入口：演示数字名片、Prompt 脱敏、功能路由与容器数据结构"""

from zhishu_agent.profile import build_employee_card, get_environment_info
from zhishu_agent.router import format_menu, route_command
from zhishu_agent.sanitizer import clean_and_mask
from zhishu_agent.task_queue import (
    SUPPORTED_MODELS,
    TodoManager,
    merge_unique_tags,
)


def run_demo() -> None:
    """运行 Day 04 非阻塞全链路演示。"""
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day04 | Python {env['python_version']}")
    print(build_employee_card("陈默", "AI 应用开发工程师", 2, 12.5, True))

    # 1. 演示 Day 02 脱敏模块
    raw_prompt = "  帮我联系 13812345678，我的密钥是 sk-proj-abc12345  "
    print("\n[Prompt 清洗脱敏]", clean_and_mask(raw_prompt))

    # 2. 演示 Day 03 路由模块
    print("\n" + format_menu())
    print("[路由测试] 选项 '3' ->", route_command("3"))

    # 3. 演示 Day 04 tuple 不可变模型配置
    print("\n[受支持模型配置 (tuple)]", SUPPORTED_MODELS)

    # 4. 演示 Day 04 list 任务队列与切片/推导式
    manager = TodoManager()
    manager.add_task("配置企业知识库索引", priority="high")
    manager.add_task("清洗历史工单 Prompt", priority="normal")
    manager.add_task("生成周报摘要", priority="low")
    manager.complete_task("清洗历史工单 Prompt")

    print("[全部任务数]", len(manager.tasks))
    print("[待办任务 (列表推导式)]", [t["title"] for t in manager.get_pending_tasks()])
    print("[Top-2 任务 (切片)]", [t["title"] for t in manager.top_k_tasks(2)])

    # 5. 演示 Day 04 set 标签去重合并
    rag_tags = ["Python", "RAG", "Agent", "Python"]
    sql_tags = ["Agent", "LangGraph", "SQL"]
    print("[去重合并标签 (set)]", sorted(merge_unique_tags(rag_tags, sql_tags)))


if __name__ == "__main__":
    run_demo()
