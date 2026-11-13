"""Day 01 单元测试：验证环境信息与数字名片生成逻辑"""
import sys
from pathlib import Path

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.profile import build_employee_card, get_environment_info


def test_get_environment_info():
    """测试环境信息返回结构完整且非空"""
    env = get_environment_info()
    assert "python_version" in env
    assert "os_info" in env
    assert "executable" in env
    assert len(env["python_version"]) > 0


def test_build_employee_card_enabled():
    """测试已开通大模型权限的员工名片渲染"""
    card = build_employee_card(
        name="陈默",
        role="AI 应用开发工程师",
        years_exp=2,
        hourly_cost=12.5,
        llm_enabled=True,
    )
    assert "陈默" in card
    assert "AI 应用开发工程师" in card
    assert "2 年" in card
    assert "¥12.50 / 小时" in card
    assert "已开通 [OK]" in card


def test_build_employee_card_disabled():
    """测试未开通大模型权限的员工名片渲染"""
    card = build_employee_card(
        name="实习生小王",
        role="转行学员",
        years_exp=0,
        hourly_cost=0.0,
        llm_enabled=False,
    )
    assert "实习生小王" in card
    assert "未开通 [LOCKED]" in card
