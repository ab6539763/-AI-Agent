"""Day 05 继承测试：验证环境信息与数字名片生成逻辑"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.profile import build_employee_card, get_environment_info


def test_get_environment_info():
    """测试环境信息返回结构完整且非空"""
    env = get_environment_info()
    assert "python_version" in env
    assert "os_info" in env
    assert "executable" in env
    assert len(env["python_version"]) > 0


def test_build_employee_card():
    """测试员工名片渲染"""
    card = build_employee_card(
        name="陈默",
        role="AI 应用开发工程师",
        years_exp=2,
        hourly_cost=12.5,
        llm_enabled=True,
    )
    assert "陈默" in card
    assert "v0.1.0-day05" in card
    assert "已开通 [OK]" in card
