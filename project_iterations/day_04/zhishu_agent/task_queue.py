"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 04 核心迭代模块
功能：Agent 任务队列管理 (list)、不可变系统模型配置 (tuple) 与知识库标签去重合并 (set)

业务背景：
随着平台进入任务调度阶段，Agent 需要：
1. 使用可变列表 `list` 维护待办任务队列，支持增删、完成标记、列表推导式筛选与切片取 Top-K。
2. 使用不可变元组 `tuple` 锁定受支持的大模型白名单，防止运行期被意外篡改。
3. 使用集合 `set` 对多路 RAG 检索召回的文档标签进行去重合并与交集分析。
"""

from typing import Any

# 不可变元组：系统全局受支持的大模型白名单配置（运行期禁止修改）
SUPPORTED_MODELS: tuple[str, ...] = (
    "deepseek-chat",
    "deepseek-reasoner",
    "qwen-max",
    "qwen-plus",
    "glm-4-plus",
)


def is_model_supported(model_name: str) -> bool:
    """检查指定模型名称是否在系统不可变白名单中。"""
    return model_name.strip() in SUPPORTED_MODELS


def merge_unique_tags(tags_a: list[str], tags_b: list[str]) -> set[str]:
    """
    合并两组标签列表并自动去重（演示 set 并集操作 `|`）。

    参数:
        tags_a (list[str]): 第一组标签（如向量检索召回标签）
        tags_b (list[str]): 第二组标签（如关键词检索召回标签）

    返回:
        set[str]: 去重且清洗空白后的标签集合
    """
    set_a = {tag.strip() for tag in tags_a if tag.strip()}
    set_b = {tag.strip() for tag in tags_b if tag.strip()}
    return set_a | set_b


def find_common_tags(tags_a: list[str], tags_b: list[str]) -> set[str]:
    """查找两组标签的共同部分（演示 set 交集操作 `&`）。"""
    set_a = {tag.strip() for tag in tags_a if tag.strip()}
    set_b = {tag.strip() for tag in tags_b if tag.strip()}
    return set_a & set_b


def add_task(
    tasks: list[dict[str, Any]],
    title: str,
    priority: str = "normal",
) -> list[dict[str, Any]]:
    """
    向任务列表尾部追加一个新任务（演示 list.append）。

    参数:
        tasks (list[dict[str, Any]]): 任务队列列表
        title (str): 任务标题
        priority (str): 优先级（high / normal / low）

    返回:
        list[dict[str, Any]]: 更新后的任务列表
    """
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("任务标题不能为空")

    tasks.append(
        {
            "title": clean_title,
            "priority": priority,
            "done": False,
        }
    )
    return tasks


def remove_task(tasks: list[dict[str, Any]], title: str) -> list[dict[str, Any]]:
    """
    根据任务标题从队列中移除匹配任务（演示列表过滤与原地更新）。

    参数:
        tasks (list[dict[str, Any]]): 任务队列列表
        title (str): 要移除的任务标题

    返回:
        list[dict[str, Any]]: 移除后的任务列表
    """
    target = title.strip()
    tasks[:] = [task for task in tasks if task["title"] != target]
    return tasks


def complete_task(tasks: list[dict[str, Any]], title: str) -> bool:
    """
    将指定标题的任务标记为已完成。

    返回:
        bool: 找到并成功标记返回 True，否则返回 False
    """
    target = title.strip()
    for task in tasks:
        if task["title"] == target:
            task["done"] = True
            return True
    return False


def get_pending_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    使用列表推导式筛选所有尚未完成的任务。

    返回:
        list[dict[str, Any]]: 状态为 done=False 的待办任务列表
    """
    return [task for task in tasks if not task["done"]]


def top_k_tasks(tasks: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """
    使用列表切片获取前 k 个任务。

    参数:
        tasks (list[dict[str, Any]]): 任务列表
        k (int): 需要提取的任务数量

    返回:
        list[dict[str, Any]]: 前 k 个任务切片；当 k <= 0 时返回空列表
    """
    if k <= 0:
        return []
    return tasks[:k]


class TodoManager:
    """面向智枢 Agent 的任务队列管理器，封装 list 增删改查、筛选与切片操作。"""

    def __init__(self) -> None:
        self._tasks: list[dict[str, Any]] = []

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """返回当前任务列表的浅拷贝，避免外部直接破坏内部状态。"""
        return list(self._tasks)

    def add_task(self, title: str, priority: str = "normal") -> dict[str, Any]:
        """添加新任务并返回该任务对象。"""
        add_task(self._tasks, title=title, priority=priority)
        return self._tasks[-1]

    def remove_task(self, title: str) -> bool:
        """按标题移除任务，若有任务被移除则返回 True。"""
        before_count = len(self._tasks)
        remove_task(self._tasks, title=title)
        return len(self._tasks) < before_count

    def complete_task(self, title: str) -> bool:
        """将指定标题的任务标记为已完成。"""
        return complete_task(self._tasks, title=title)

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        """使用列表推导式返回所有未完成任务。"""
        return get_pending_tasks(self._tasks)

    def top_k_tasks(self, k: int) -> list[dict[str, Any]]:
        """使用列表切片返回前 k 个任务。"""
        return top_k_tasks(self._tasks, k=k)
