"""Day 07 平台启动入口：演示第 1 周综合实战 —— 企业通讯录 / Agent 联系人管理系统"""
import tempfile
from pathlib import Path

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
from zhishu_agent.profile import build_employee_card, get_environment_info


def run_demo() -> None:
    """运行 Day 07 第 1 周综合实战演示"""
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day07 | Python {env['python_version']}")
    print(build_employee_card("陈默", "AI 应用开发工程师", 2, 18.5, True))

    contacts: list[dict] = []

    # 1. Create：录入真人研发团队成员与 AI Agent 节点
    add_contact(
        contacts,
        name="张工",
        role="Tech Lead / 架构师",
        department="AI 研发部",
        email="zhang@xingchen.ai",
        phone="13800001001",
        agent_type="human",
        skills=["Python", "架构设计", "Code Review"],
    )
    add_contact(
        contacts,
        name="陈默",
        role="AI 应用开发工程师",
        department="AI 研发部",
        email="chenmo@xingchen.ai",
        phone="13800001002",
        agent_type="human",
        skills=["Python", "JSON", "Prompt"],
    )
    add_contact(
        contacts,
        name="ZhiShu-QA-Bot",
        role="自动化测试 Agent",
        department="质量保障部",
        email="qa-bot@xingchen.ai",
        agent_type="agent",
        skills=["pytest", "回归测试"],
    )
    print("\n[1. 初始化通讯录]")
    print(format_contacts_table(list_contacts(contacts)))

    # 2. Read：按关键词检索 & 按类型筛选
    print("\n[2. 检索关键词 'JSON']")
    print(format_contacts_table(find_contact(contacts, "JSON")))

    print("\n[3. 仅查看 AI Agent 节点]")
    print(format_contacts_table(list_contacts(contacts, agent_type="agent")))

    # 3. Update：更新联系人岗位与技能
    update_contact(contacts, "陈默", role="高级 AI 应用开发工程师", skills=["Python", "JSON", "Agent"])
    print("\n[4. 更新 '陈默' 信息后]")
    print(format_contacts_table(find_contact(contacts, "陈默")))

    # 4. Persistence：持久化到 JSON 并重新加载
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "zhishu_contacts.json"
        save_contacts(db_path, contacts)
        reloaded = load_contacts(db_path)
        print(f"\n[5. JSON 持久化验证] 成功保存并重新加载 {len(reloaded)} 条记录。")

        # 5. Delete：删除节点后再次保存
        removed = delete_contact(reloaded, "ZhiShu-QA-Bot")
        save_contacts(db_path, reloaded)
        print(f"[6. 删除联系人] 已移除: {removed['name']}，当前剩余 {len(reloaded)} 条记录。")


if __name__ == "__main__":
    run_demo()
