"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 05 迭代模块
功能：大模型 API JSON 响应解析、多轮对话持久化与 Token 用量统计

业务背景：
无论是 OpenAI、DeepSeek 还是 Qwen，所有大模型 API 的请求与响应本质上都是 JSON 数据。
在正式接入网络请求前，智枢平台需要先构建可靠的 JSON 解析层与本地会话持久化层，
确保能够准确提取模型回复、记录中文对话历史，并汇总各次调用的 Token 消耗。
"""

import json
from pathlib import Path
from typing import Any


def extract_llm_response(raw_json: str) -> dict[str, Any]:
    """
    解析模拟的 OpenAI / DeepSeek Chat Completions API 响应 JSON 字符串，
    提取核心字段并拍平为标准字典。

    参数:
        raw_json (str): 大模型 API 返回的原始 JSON 字符串

    返回:
        dict[str, Any]: 包含 id, model, content, prompt_tokens,
                        completion_tokens, total_tokens 的字典

    异常:
        ValueError: 当 JSON 格式非法、根结构不是字典或缺少 choices 时抛出
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 响应 JSON 解析失败: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("LLM 响应根节点必须为 JSON 对象 (dict)")

    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise ValueError("LLM 响应缺少有效的 choices 列表")

    first_choice = choices[0]
    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    content = message.get("content", "")

    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}

    return {
        "id": str(data.get("id", "")),
        "model": str(data.get("model", "")),
        "content": str(content),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }


def save_session_json(filepath: Path, messages: list[dict[str, Any]]) -> None:
    """
    将多轮对话消息列表保存为本地 JSON 文件（保留中文字符并格式化缩进）。

    参数:
        filepath (Path): 目标 JSON 文件路径
        messages (list[dict[str, Any]]): 对话消息列表，例如 [{"role": "user", "content": "你好"}]
    """
    target = Path(filepath)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def load_session_json(filepath: Path) -> list[dict[str, Any]]:
    """
    从本地 JSON 文件加载多轮对话消息列表。

    参数:
        filepath (Path): 会话 JSON 文件路径

    返回:
        list[dict[str, Any]]: 解析后的对话消息列表

    异常:
        FileNotFoundError: 文件不存在时抛出
        ValueError: 文件内容不是 JSON 列表时抛出
    """
    target = Path(filepath)
    if not target.exists():
        raise FileNotFoundError(f"会话文件不存在: {target}")

    with target.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("会话 JSON 文件根节点必须为数组 (list)")

    return data


def summarize_usage(responses: list[dict[str, Any]]) -> dict[str, int]:
    """
    遍历多次大模型 API 原始响应字典，聚合统计 Token 消耗总量。

    参数:
        responses (list[dict[str, Any]]): 原始 API 响应字典列表

    返回:
        dict[str, int]: 包含 request_count, prompt_tokens,
                        completion_tokens, total_tokens 的统计字典
    """
    total_prompt = 0
    total_completion = 0
    total_all = 0

    for resp in responses:
        if not isinstance(resp, dict):
            continue
        usage = resp.get("usage", {})
        if not isinstance(usage, dict):
            continue
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        # 若响应中未显式提供 total_tokens，则由 prompt + completion 自动补全
        total = int(usage.get("total_tokens", prompt + completion))

        total_prompt += prompt
        total_completion += completion
        total_all += total

    return {
        "request_count": len(responses),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_all,
    }
