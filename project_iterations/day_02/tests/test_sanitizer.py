"""Day 02 单元测试：验证文本清洗、敏感词脱敏、Prompt 模板渲染与预算校验"""
import sys
from pathlib import Path

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.sanitizer import (
    clean_text,
    estimate_cost_and_check_budget,
    mask_sensitive_words,
    render_prompt_template,
)


def test_clean_text_whitespace_and_newlines():
    """测试去除首尾空白并折叠多余空格、制表符和换行符"""
    raw = "   你好，   智枢平台\t\t正在运行   \n  测试中  "
    assert clean_text(raw) == "你好， 智枢平台 正在运行 测试中"


def test_clean_text_lowercase():
    """测试开启 lowercase=True 时将英文转为小写"""
    raw = "  DeepSeek-Chat   API Key  "
    assert clean_text(raw, lowercase=False) == "DeepSeek-Chat API Key"
    assert clean_text(raw, lowercase=True) == "deepseek-chat api key"


def test_clean_text_empty():
    """测试空字符串和纯空白字符串的清洗"""
    assert clean_text("") == ""
    assert clean_text("   \n\t  ") == ""


def test_mask_sensitive_words_multiple():
    """测试多个敏感词同时脱敏"""
    text = "使用密钥 sk-abc123456 访问内部项目 Project-X 的数据库"
    result = mask_sensitive_words(text, ("sk-abc123456", "Project-X"))
    assert result == "使用密钥 *** 访问内部项目 *** 的数据库"
    assert "sk-abc123456" not in result
    assert "Project-X" not in result


def test_mask_sensitive_words_edge_cases():
    """测试无匹配、空元组以及包含空字符串的敏感词元组"""
    text = "正常业务咨询：如何申请报销？"
    assert mask_sensitive_words(text, ()) == text
    assert mask_sensitive_words(text, ("sk-999", "")) == text


def test_render_prompt_template():
    """测试 f-string Prompt 模板是否正确包含角色、任务与用户输入"""
    prompt = render_prompt_template(
        role="Python 架构师",
        task="审查代码安全性",
        user_input="请检查这段脚本是否有硬编码密钥",
    )
    assert "[系统角色]" in prompt
    assert "Python 架构师" in prompt
    assert "[核心任务]" in prompt
    assert "审查代码安全性" in prompt
    assert "[用户输入]" in prompt
    assert "请检查这段脚本是否有硬编码密钥" in prompt


def test_estimate_cost_and_check_budget_pass_and_fail():
    """测试正常预算内放行与超预算拦截"""
    # 1000 字符 -> 1500 tokens -> 0.003 元
    assert estimate_cost_and_check_budget(1000, 0.01) is True
    assert estimate_cost_and_check_budget(1000, 0.003) is True
    assert estimate_cost_and_check_budget(1000, 0.002) is False


def test_estimate_cost_and_check_budget_invalid_inputs():
    """测试非法字符数或非正预算时返回 False"""
    assert estimate_cost_and_check_budget(-10, 1.0) is False
    assert estimate_cost_and_check_budget(100, 0.0) is False
    assert estimate_cost_and_check_budget(100, -0.5) is False
    assert estimate_cost_and_check_budget(0, 0.01) is True
