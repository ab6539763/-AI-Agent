"""Day 03 单元测试：验证权限路由、批量 Prompt 清洗、菜单调度与乘法口诀表"""
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.router import (
    batch_clean_prompts,
    check_access_level,
    generate_multiplication_table,
    run_menu_dispatch,
)


class TestCheckAccessLevel:
    """测试嵌套 if/elif/else 权限等级判定"""

    def test_vip_access(self):
        assert check_access_level(years_exp=3, llm_enabled=True, budget=50.0) == "VIP"
        assert check_access_level(years_exp=5, llm_enabled=True, budget=120.0) == "VIP"

    def test_standard_access(self):
        # 工龄不足 3 年但预算充足
        assert check_access_level(years_exp=1, llm_enabled=True, budget=20.0) == "STANDARD"
        # 工龄 0 年但预算 >= 10.0
        assert check_access_level(years_exp=0, llm_enabled=True, budget=10.0) == "STANDARD"
        # 工龄 >= 3 年但预算未达 VIP 门槛 (50.0)
        assert check_access_level(years_exp=4, llm_enabled=True, budget=30.0) == "STANDARD"

    def test_denied_access(self):
        # 未开通大模型权限
        assert check_access_level(years_exp=5, llm_enabled=False, budget=100.0) == "DENIED"
        # 预算 <= 0
        assert check_access_level(years_exp=3, llm_enabled=True, budget=0.0) == "DENIED"
        assert check_access_level(years_exp=2, llm_enabled=True, budget=-5.0) == "DENIED"
        # 新手且预算低于 10.0
        assert check_access_level(years_exp=0, llm_enabled=True, budget=5.0) == "DENIED"


class TestBatchCleanPrompts:
    """测试 for 循环 + continue + break 批量清洗"""

    def test_skip_empty_and_stop_on_keyword(self):
        raw = [
            "  你好，智枢  ",
            "",
            "   \t  ",
            "请帮我生成   周报",
            "STOP",
            "这条消息在 STOP 之后不应被处理",
        ]
        result = batch_clean_prompts(raw)
        assert result == ["你好，智枢", "请帮我生成 周报"]

    def test_sensitive_word_masking(self):
        raw = ["我的 API_KEY 是 12345", "不要泄露密码"]
        result = batch_clean_prompts(raw)
        assert result == ["我的 *** 是 12345", "不要泄露***"]

    def test_custom_stop_keyword(self):
        raw = ["第一条", "END", "第二条"]
        result = batch_clean_prompts(raw, stop_keyword="END")
        assert result == ["第一条"]

    def test_empty_input_list(self):
        assert batch_clean_prompts([]) == []


class TestMultiplicationTable:
    """测试嵌套 for 循环生成的乘法口诀表"""

    def test_default_9x9_table(self):
        table = generate_multiplication_table()
        lines = table.splitlines()
        assert len(lines) == 9
        assert lines[0] == "1×1=1"
        assert "3×3=9" in lines[2]
        assert "9×9=81" in lines[8]

    def test_custom_size(self):
        table = generate_multiplication_table(n=3)
        lines = table.splitlines()
        assert len(lines) == 3
        assert lines[1] == "1×2=2   2×2=4"

    def test_invalid_size_raises(self):
        with pytest.raises(ValueError):
            generate_multiplication_table(n=0)


class TestRunMenuDispatch:
    """测试 CLI 菜单路由分发逻辑"""

    def test_choice_1_profile_and_access(self):
        ctx = {
            "name": "陈默",
            "role": "AI 工程师",
            "years_exp": 3,
            "budget": 80.0,
            "llm_enabled": True,
        }
        out = run_menu_dispatch("1", ctx)
        assert "陈默" in out
        assert "当前平台权限等级: VIP" in out

    def test_choice_2_batch_clean(self):
        ctx = {"prompts": ["  测试文本  ", "", "STOP", "忽略"]}
        out = run_menu_dispatch("2", ctx)
        assert "共处理 1 条有效 Prompt" in out
        assert "1. 测试文本" in out

    def test_choice_2_empty(self):
        out = run_menu_dispatch("2", {"prompts": ["", "STOP"]})
        assert "未收集到有效 Prompt" in out

    def test_choice_3_multiplication(self):
        out = run_menu_dispatch("3", {"n": 4})
        assert "4×4=16" in out

    def test_choice_4_environment(self):
        out = run_menu_dispatch("4", {})
        assert "[环境自检] Python" in out

    def test_choice_0_exit(self):
        out = run_menu_dispatch("0", {})
        assert "再见" in out

    def test_invalid_choice(self):
        out = run_menu_dispatch("99", {})
        assert "无效的菜单选项" in out
