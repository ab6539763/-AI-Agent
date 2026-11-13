"""Day 04 单元测试：验证任务队列 (list)、模型配置 (tuple) 与标签去重 (set)"""
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.router import route_command
from zhishu_agent.sanitizer import clean_and_mask
from zhishu_agent.task_queue import (
    SUPPORTED_MODELS,
    TodoManager,
    add_task,
    complete_task,
    find_common_tags,
    get_pending_tasks,
    is_model_supported,
    merge_unique_tags,
    remove_task,
    top_k_tasks,
)


def test_supported_models_is_immutable_tuple():
    """验证 SUPPORTED_MODELS 是不可变元组且包含核心模型"""
    assert isinstance(SUPPORTED_MODELS, tuple)
    assert "deepseek-chat" in SUPPORTED_MODELS
    assert is_model_supported("qwen-max") is True
    assert is_model_supported("unknown-model") is False

    with pytest.raises(TypeError):
        # 元组不支持原地修改元素
        SUPPORTED_MODELS[0] = "hacked-model"  # type: ignore[index]


def test_merge_unique_tags_and_common_tags():
    """验证 set 标签并集去重与交集计算"""
    tags_a = ["RAG", "Python", "RAG", "  Agent "]
    tags_b = ["Agent", "FastAPI", ""]

    merged = merge_unique_tags(tags_a, tags_b)
    assert isinstance(merged, set)
    assert merged == {"RAG", "Python", "Agent", "FastAPI"}

    common = find_common_tags(tags_a, tags_b)
    assert common == {"Agent"}


def test_list_task_queue_functions():
    """验证列表版任务队列的增删、完成、列表推导式筛选与切片"""
    tasks: list[dict] = []
    add_task(tasks, "任务A", priority="high")
    add_task(tasks, "任务B", priority="normal")
    add_task(tasks, "任务C", priority="low")

    assert len(tasks) == 3
    assert complete_task(tasks, "任务B") is True
    assert complete_task(tasks, "不存在的任务") is False

    pending = get_pending_tasks(tasks)
    assert [t["title"] for t in pending] == ["任务A", "任务C"]

    top2 = top_k_tasks(tasks, 2)
    assert [t["title"] for t in top2] == ["任务A", "任务B"]
    assert top_k_tasks(tasks, 0) == []

    remove_task(tasks, "任务A")
    assert [t["title"] for t in tasks] == ["任务B", "任务C"]


def test_add_empty_task_raises():
    """验证空任务标题抛出 ValueError"""
    with pytest.raises(ValueError):
        add_task([], "   ")


def test_todo_manager_lifecycle():
    """验证 TodoManager 类的完整生命周期操作"""
    manager = TodoManager()
    t1 = manager.add_task("构建向量库", priority="high")
    manager.add_task("编写单元测试", priority="normal")
    manager.add_task("输出日报", priority="low")

    assert t1["done"] is False
    assert manager.complete_task("编写单元测试") is True
    assert len(manager.get_pending_tasks()) == 2
    assert [t["title"] for t in manager.top_k_tasks(2)] == ["构建向量库", "编写单元测试"]

    assert manager.remove_task("构建向量库") is True
    assert manager.remove_task("不存在") is False
    assert len(manager.tasks) == 2


def test_inherited_modules_smoke():
    """回归验证 Day 02 脱敏与 Day 03 路由模块工作正常"""
    cleaned = clean_and_mask("  联系 13812345678 key=sk-test1234  ")
    assert "138****5678" in cleaned
    assert "sk-***" in cleaned
    assert route_command("3") == "tasks"
    assert route_command("invalid") == "unknown"
