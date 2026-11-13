"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 06 迭代模块
功能：函数式 Prompt 清洗流水线、动态 API Payload 构造器与嵌套结构递归 Token 统计

业务背景：
在之前的迭代中，我们把字典组装、文本清洗逻辑散落在脚本各处，复用性差。
Day 06 引入 Python 函数体系（位置/关键字/默认参数、*args/**kwargs、高阶函数与 lambda、递归），
将智枢平台的数据预处理与请求构造重构为可组合的函数式流水线。
"""

from collections.abc import Callable
from typing import Any


def build_api_payload(
    model: str,
    *messages: dict[str, Any],
    temperature: float = 0.7,
    **extra_params: Any,
) -> dict[str, Any]:
    """
    动态构造 OpenAI / DeepSeek Chat Completions API 请求体字典。

    参数:
        model (str): 必选模型名称（位置或关键字参数），如 "deepseek-chat"
        *messages (dict[str, Any]): 可变位置参数，接收任意多条对话消息字典
        temperature (float): 关键字默认参数，采样温度，默认 0.7（范围 0.0 ~ 2.0）
        **extra_params (Any): 可变关键字参数，透传 max_tokens、stream、top_p 等扩展配置

    返回:
        dict[str, Any]: 符合大模型 API 规范的请求体字典

    异常:
        ValueError: 当 model 为空字符串或 temperature 超出 [0.0, 2.0] 时抛出
        TypeError: 当 messages 中包含非 dict 元素时抛出
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model 必须是非空字符串")

    if not (0.0 <= temperature <= 2.0):
        raise ValueError(f"temperature 必须在 [0.0, 2.0] 范围内，当前为: {temperature}")

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise TypeError(f"messages 第 {idx} 项必须是 dict 类型，当前为: {type(msg).__name__}")

    payload: dict[str, Any] = {
        "model": model.strip(),
        "messages": list(messages),
        "temperature": temperature,
    }
    payload.update(extra_params)
    return payload


def apply_pipeline(text: str, *transforms: Callable[[str], str]) -> str:
    """
    高阶函数：按顺序将任意多个文本变换函数（含 lambda 匿名函数）串联应用到输入文本上。

    参数:
        text (str): 原始输入文本（如用户原始 Prompt）
        *transforms (Callable[[str], str]): 可变位置参数，接收任意个 str -> str 的处理函数

    返回:
        str: 经过所有变换函数依次处理后的清洗文本

    异常:
        TypeError: 当 text 不是 str 或 transforms 中存在不可调用对象时抛出
    """
    if not isinstance(text, str):
        raise TypeError(f"text 必须是 str 类型，当前为: {type(text).__name__}")

    result = text
    for idx, fn in enumerate(transforms):
        if not callable(fn):
            raise TypeError(f"transforms 第 {idx} 项不可调用: {fn!r}")
        result = fn(result)

    return result


def count_nested_tokens(node: dict[str, Any] | list[Any] | str | Any) -> int:
    """
    递归遍历嵌套的 JSON / 对话消息树，统计所有文本节点的字符级估算 Token 总数。

    说明:
        采用简化估算策略（中文/混合文本场景下以字符串长度 len(s) 作为 Token 估算基数）。
        对 int / float / bool / None 等非文本标量返回 0。

    参数:
        node: 任意嵌套的 dict、list、str 或标量节点

    返回:
        int: 嵌套结构中所有字符串节点的总长度
    """
    # 递归基准条件（Base Case）：遇到字符串直接返回长度
    if isinstance(node, str):
        return len(node)

    # 递归分支 1：列表节点，累加每个子元素的统计结果
    if isinstance(node, list):
        return sum(count_nested_tokens(item) for item in node)

    # 递归分支 2：字典节点，遍历所有 value 递归求和
    if isinstance(node, dict):
        return sum(count_nested_tokens(value) for value in node.values())

    # 其他标量（如 int, float, bool, None）不计入文本 Token
    return 0
