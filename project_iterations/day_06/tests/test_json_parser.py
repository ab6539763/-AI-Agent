"""Day 05 单元测试：验证 LLM JSON 解析、会话持久化与 Token 用量汇总"""
import json
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.json_parser import (
    extract_llm_response,
    load_session_json,
    save_session_json,
    summarize_usage,
)

VALID_LLM_JSON = json.dumps(
    {
        "id": "chatcmpl-998877",
        "object": "chat.completion",
        "created": 1731456000,
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "智枢平台已成功解析 JSON 数据！",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 18,
            "total_tokens": 60,
        },
    },
    ensure_ascii=False,
)


def test_extract_llm_response_success():
    """测试正常解析 OpenAI/DeepSeek 格式的 JSON 响应"""
    result = extract_llm_response(VALID_LLM_JSON)
    assert result["id"] == "chatcmpl-998877"
    assert result["model"] == "deepseek-chat"
    assert result["content"] == "智枢平台已成功解析 JSON 数据！"
    assert result["prompt_tokens"] == 42
    assert result["completion_tokens"] == 18
    assert result["total_tokens"] == 60


def test_extract_llm_response_invalid_json():
    """测试传入非法 JSON 字符串时抛出 ValueError"""
    with pytest.raises(ValueError, match="JSON 解析失败"):
        extract_llm_response("{not valid json")


def test_extract_llm_response_missing_choices():
    """测试缺少 choices 或 choices 为空时抛出 ValueError"""
    empty_choices = json.dumps({"id": "1", "model": "qwen", "choices": []})
    with pytest.raises(ValueError, match="choices"):
        extract_llm_response(empty_choices)


def test_save_and_load_session_json(tmp_path: Path):
    """测试使用 tmp_path 保存和加载含中文的对话历史，并验证 ensure_ascii=False 与缩进"""
    session_file = tmp_path / "nested_dir" / "chat_history.json"
    messages = [
        {"role": "system", "content": "你是星辰数科智能助手"},
        {"role": "user", "content": "你好，请问如何学习 Python JSON？"},
        {"role": "assistant", "content": "建议先掌握 json.loads 与 json.dump。"},
    ]

    save_session_json(session_file, messages)

    assert session_file.exists()
    raw_text = session_file.read_text(encoding="utf-8")
    # 确保中文未被转义为 \uXXXX，且带有 indent=2 换行缩进
    assert "你是星辰数科智能助手" in raw_text
    assert "\\u" not in raw_text
    assert "\n  {" in raw_text

    loaded = load_session_json(session_file)
    assert loaded == messages


def test_load_session_json_file_not_found(tmp_path: Path):
    """测试加载不存在的会话文件时抛出 FileNotFoundError"""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_session_json(missing)


def test_load_session_json_invalid_root_type(tmp_path: Path):
    """测试会话文件根节点不是 list 时抛出 ValueError"""
    bad_file = tmp_path / "bad_session.json"
    bad_file.write_text('{"role": "user"}', encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        load_session_json(bad_file)


def test_summarize_usage_multiple_responses():
    """测试遍历多个嵌套 API 响应字典并汇总 Token 消耗"""
    responses = [
        {
            "id": "resp-1",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
        {
            "id": "resp-2",
            "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
        },
        {
            "id": "resp-3",
            # 模拟缺少 total_tokens 时自动计算 prompt + completion
            "usage": {"prompt_tokens": 30, "completion_tokens": 20},
        },
    ]

    summary = summarize_usage(responses)
    assert summary == {
        "request_count": 3,
        "prompt_tokens": 330,
        "completion_tokens": 150,
        "total_tokens": 480,
    }


def test_summarize_usage_empty_list():
    """测试空响应列表的汇总结果"""
    summary = summarize_usage([])
    assert summary == {
        "request_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
