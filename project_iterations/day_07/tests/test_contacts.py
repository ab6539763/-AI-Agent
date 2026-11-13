"""Day 07 单元测试：全面验证企业通讯录 / Agent 联系人管理系统 (CRUD + JSON 持久化)"""
import json
import sys
from pathlib import Path

import pytest

# 确保可以导入当前迭代目录下的 zhishu_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zhishu_agent.contacts import (
    add_contact,
    delete_contact,
    find_contact,
    format_contacts_table,
    list_contacts,
    load_contacts,
    save_contacts,
    update_contact,
)


def _sample_contacts() -> list[dict]:
    contacts: list[dict] = []
    add_contact(
        contacts,
        name="张工",
        role="Tech Lead",
        department="AI 研发部",
        email="zhang@xingchen.ai",
        phone="13800001001",
        agent_type="human",
        skills=["Python", "架构设计"],
    )
    add_contact(
        contacts,
        name="陈默",
        role="AI 应用开发工程师",
        department="AI 研发部",
        email="chenmo@xingchen.ai",
        phone="13800001002",
        agent_type="human",
        skills=["Python", "JSON"],
    )
    add_contact(
        contacts,
        name="ZhiShu-QA-Bot",
        role="自动化测试 Agent",
        department="质量保障部",
        email="qa-bot@xingchen.ai",
        agent_type="agent",
        skills=["pytest", "CI"],
    )
    return contacts


def test_add_contact_success():
    """测试正常新增真人与 Agent 联系人"""
    contacts: list[dict] = []
    c1 = add_contact(
        contacts,
        name="  林晓  ",
        role="产品经理",
        department="产品部",
        email="linxiao@xingchen.ai",
        skills=["PRD", " 需求分析 "],
    )
    assert len(contacts) == 1
    assert c1["name"] == "林晓"
    assert c1["agent_type"] == "human"
    assert c1["skills"] == ["PRD", "需求分析"]

    c2 = add_contact(
        contacts,
        name="RagBot",
        role="知识库检索助手",
        agent_type="AGENT",
    )
    assert len(contacts) == 2
    assert c2["agent_type"] == "agent"


def test_add_contact_validation_errors():
    """测试空姓名、空岗位、重复联系人及非法类型时抛出 ValueError"""
    contacts = _sample_contacts()

    with pytest.raises(ValueError, match="姓名"):
        add_contact(contacts, name="   ", role="工程师")

    with pytest.raises(ValueError, match="岗位"):
        add_contact(contacts, name="新同事", role="")

    with pytest.raises(ValueError, match="已存在"):
        add_contact(contacts, name="zhishu-qa-bot", role="测试")

    with pytest.raises(ValueError, match="联系人类型"):
        add_contact(contacts, name="赵磊", role="运维", agent_type="robot")


def test_find_contact_fuzzy_and_case_insensitive():
    """测试按姓名、岗位、部门、技能模糊搜索（忽略大小写）"""
    contacts = _sample_contacts()

    assert len(find_contact(contacts, "AI 研发部")) == 2
    assert len(find_contact(contacts, "pytest")) == 1
    assert find_contact(contacts, "qa-bot")[0]["name"] == "ZhiShu-QA-Bot"
    assert find_contact(contacts, "不存在的关键词") == []
    assert find_contact(contacts, "   ") == []


def test_update_contact_success_and_errors():
    """测试更新联系人字段、重命名冲突与异常校验"""
    contacts = _sample_contacts()

    updated = update_contact(
        contacts,
        "陈默",
        role="高级 AI 工程师",
        phone="13900009999",
        skills=["Python", "JSON", "Agent"],
    )
    assert updated["role"] == "高级 AI 工程师"
    assert updated["phone"] == "13900009999"
    assert updated["skills"] == ["Python", "JSON", "Agent"]

    with pytest.raises(ValueError, match="未找到"):
        update_contact(contacts, "路人甲", role="实习生")

    with pytest.raises(ValueError, match="不支持更新"):
        update_contact(contacts, "陈默", salary=99999)

    with pytest.raises(ValueError, match="已存在"):
        update_contact(contacts, "陈默", name="张工")

    with pytest.raises(ValueError, match="skills"):
        update_contact(contacts, "陈默", skills="Python")


def test_delete_contact_success_and_not_found():
    """测试删除联系人及重复删除抛出 ValueError"""
    contacts = _sample_contacts()
    removed = delete_contact(contacts, "ZhiShu-QA-Bot")
    assert removed["name"] == "ZhiShu-QA-Bot"
    assert len(contacts) == 2

    with pytest.raises(ValueError, match="未找到"):
        delete_contact(contacts, "ZhiShu-QA-Bot")


def test_list_contacts_with_filters():
    """测试按 agent_type 与 department 组合筛选"""
    contacts = _sample_contacts()

    assert len(list_contacts(contacts)) == 3
    assert len(list_contacts(contacts, agent_type="human")) == 2
    assert len(list_contacts(contacts, agent_type="agent")) == 1
    assert len(list_contacts(contacts, department="质量保障部")) == 1
    assert len(list_contacts(contacts, agent_type="human", department="AI 研发部")) == 2

    with pytest.raises(ValueError, match="联系人类型"):
        list_contacts(contacts, agent_type="invalid")


def test_save_and_load_contacts_roundtrip(tmp_path: Path):
    """测试使用 tmp_path 进行 JSON 持久化，验证中文不转义与数据完整还原"""
    contacts = _sample_contacts()
    db_file = tmp_path / "data" / "contacts.json"

    save_contacts(db_file, contacts)
    assert db_file.exists()

    raw_text = db_file.read_text(encoding="utf-8")
    assert "AI 研发部" in raw_text
    assert "\\u" not in raw_text
    assert "\n  {" in raw_text

    loaded = load_contacts(db_file)
    assert loaded == contacts


def test_load_contacts_error_cases(tmp_path: Path):
    """测试加载不存在文件、损坏 JSON 与非 list[dict] 结构时的异常处理"""
    with pytest.raises(FileNotFoundError):
        load_contacts(tmp_path / "missing.json")

    bad_json = tmp_path / "corrupt.json"
    bad_json.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="解析失败"):
        load_contacts(bad_json)

    wrong_root = tmp_path / "dict_root.json"
    wrong_root.write_text(json.dumps({"name": "张工"}), encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        load_contacts(wrong_root)


def test_format_contacts_table():
    """测试终端表格格式化输出"""
    assert format_contacts_table([]) == "[通讯录为空]"
    table = format_contacts_table(_sample_contacts())
    assert "ZhiShu-QA-Bot" in table
    assert "张工" in table
