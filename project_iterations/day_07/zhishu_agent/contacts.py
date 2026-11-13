"""
智枢企业级智能体平台 (ZhiShu-Agent) - Day 07 第 1 周综合实战模块
功能：企业通讯录 / Agent 联系人管理系统（完整 CRUD + JSON 持久化）

业务背景：
经过第 1 周（Day 01 - Day 06）的积累，我们已经掌握了变量、字符串清洗、条件与循环、
列表/字典数据结构、JSON 序列化以及文件持久化。
现在星辰数科需要一套统一管理“研发团队成员”与“企业 AI Agent 节点”的通讯录系统，
支持增删改查（CRUD）、按部门/类型筛选以及本地 JSON 文件持久化存储。
"""

import json
from pathlib import Path
from typing import Any

VALID_AGENT_TYPES = {"human", "agent"}
UPDATABLE_FIELDS = {"name", "role", "department", "email", "phone", "agent_type", "skills"}


def add_contact(
    contacts: list[dict[str, Any]],
    name: str,
    role: str,
    department: str = "AI 研发部",
    email: str = "",
    phone: str = "",
    agent_type: str = "human",
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """
    向通讯录中新增一条企业成员或 AI Agent 联系人记录。

    参数:
        contacts: 联系人列表（原地追加）
        name: 姓名或 Agent 名称（非空且不可重复）
        role: 岗位或 Agent 职责描述（非空）
        department: 所属部门，默认 "AI 研发部"
        email: 企业邮箱
        phone: 联系电话或内部短号
        agent_type: 联系人类型，"human" 或 "agent"
        skills: 技能或能力标签列表

    返回:
        dict[str, Any]: 新建的联系人字典

    异常:
        ValueError: 当姓名/岗位为空、联系人已存在或 agent_type 非法时抛出
    """
    clean_name = name.strip()
    clean_role = role.strip()
    if not clean_name:
        raise ValueError("联系人姓名/标识不能为空")
    if not clean_role:
        raise ValueError("联系人岗位/职责不能为空")

    clean_type = agent_type.strip().lower()
    if clean_type not in VALID_AGENT_TYPES:
        raise ValueError(f"非法的联系人类型 '{agent_type}'，仅支持: {sorted(VALID_AGENT_TYPES)}")

    for existing in contacts:
        if existing.get("name", "").strip().lower() == clean_name.lower():
            raise ValueError(f"联系人已存在: {clean_name}")

    contact = {
        "name": clean_name,
        "role": clean_role,
        "department": department.strip() or "AI 研发部",
        "email": email.strip(),
        "phone": phone.strip(),
        "agent_type": clean_type,
        "skills": [s.strip() for s in (skills or []) if s.strip()],
    }
    contacts.append(contact)
    return contact


def find_contact(contacts: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
    """
    根据关键词模糊检索联系人（匹配姓名、岗位、部门、邮箱或技能标签，忽略大小写）。

    参数:
        contacts: 联系人列表
        keyword: 检索关键词

    返回:
        list[dict[str, Any]]: 匹配的联系人字典列表
    """
    clean_kw = keyword.strip().lower()
    if not clean_kw:
        return []

    matched: list[dict[str, Any]] = []
    for item in contacts:
        searchable_fields = [
            str(item.get("name", "")),
            str(item.get("role", "")),
            str(item.get("department", "")),
            str(item.get("email", "")),
            " ".join(str(s) for s in item.get("skills", [])),
        ]
        if any(clean_kw in field.lower() for field in searchable_fields):
            matched.append(item)
    return matched


def update_contact(
    contacts: list[dict[str, Any]],
    target_name: str,
    /,
    **updates: Any,
) -> dict[str, Any]:
    """
    根据精确姓名更新联系人信息。

    参数:
        contacts: 联系人列表
        target_name: 目标联系人姓名
        **updates: 待更新字段（支持 name, role, department, email, phone, agent_type, skills）

    返回:
        dict[str, Any]: 更新后的联系人字典

    异常:
        ValueError: 联系人不存在、更新字段非法或字段值不合法时抛出
    """
    clean_target = target_name.strip()
    target_item: dict[str, Any] | None = None
    for item in contacts:
        if item.get("name", "").strip().lower() == clean_target.lower():
            target_item = item
            break

    if target_item is None:
        raise ValueError(f"未找到联系人: {clean_target}")

    invalid_keys = set(updates.keys()) - UPDATABLE_FIELDS
    if invalid_keys:
        raise ValueError(f"包含不支持更新的字段: {sorted(invalid_keys)}")

    if "name" in updates:
        new_name = str(updates["name"]).strip()
        if not new_name:
            raise ValueError("联系人姓名/标识不能为空")
        for other in contacts:
            if other is not target_item and other.get("name", "").strip().lower() == new_name.lower():
                raise ValueError(f"联系人已存在: {new_name}")
        target_item["name"] = new_name

    if "role" in updates:
        new_role = str(updates["role"]).strip()
        if not new_role:
            raise ValueError("联系人岗位/职责不能为空")
        target_item["role"] = new_role

    if "agent_type" in updates:
        new_type = str(updates["agent_type"]).strip().lower()
        if new_type not in VALID_AGENT_TYPES:
            raise ValueError(f"非法的联系人类型 '{updates['agent_type']}'")
        target_item["agent_type"] = new_type

    for str_field in ("department", "email", "phone"):
        if str_field in updates:
            target_item[str_field] = str(updates[str_field]).strip()

    if "skills" in updates:
        raw_skills = updates["skills"]
        if not isinstance(raw_skills, list):
            raise ValueError("skills 字段必须为列表 (list)")
        target_item["skills"] = [str(s).strip() for s in raw_skills if str(s).strip()]

    return target_item


def delete_contact(contacts: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """
    根据精确姓名从通讯录中删除联系人。

    参数:
        contacts: 联系人列表（原地删除）
        name: 目标联系人姓名

    返回:
        dict[str, Any]: 被删除的联系人字典

    异常:
        ValueError: 未找到对应联系人时抛出
    """
    clean_target = name.strip()
    for idx, item in enumerate(contacts):
        if item.get("name", "").strip().lower() == clean_target.lower():
            return contacts.pop(idx)

    raise ValueError(f"未找到联系人: {clean_target}")


def list_contacts(
    contacts: list[dict[str, Any]],
    agent_type: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    列出通讯录联系人，支持按类型 (human/agent) 与部门进行组合筛选。

    参数:
        contacts: 联系人列表
        agent_type: 可选类型过滤 ("human" 或 "agent")
        department: 可选部门过滤（精确匹配，忽略大小写）

    返回:
        list[dict[str, Any]]: 符合条件的联系人列表副本
    """
    result = list(contacts)
    if agent_type is not None:
        clean_type = agent_type.strip().lower()
        if clean_type not in VALID_AGENT_TYPES:
            raise ValueError(f"非法的联系人类型 '{agent_type}'，仅支持: {sorted(VALID_AGENT_TYPES)}")
        result = [c for c in result if c.get("agent_type", "").lower() == clean_type]

    if department is not None:
        clean_dept = department.strip().lower()
        result = [c for c in result if c.get("department", "").strip().lower() == clean_dept]

    return result


def save_contacts(filepath: Path | str, contacts: list[dict[str, Any]]) -> None:
    """
    将通讯录列表持久化到本地 JSON 文件（UTF-8 编码，保留中文，indent=2）。
    """
    target = Path(filepath)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)


def load_contacts(filepath: Path | str) -> list[dict[str, Any]]:
    """
    从本地 JSON 文件加载通讯录列表。

    异常:
        FileNotFoundError: 文件不存在时抛出
        ValueError: JSON 格式非法或根节点不是联系人字典列表时抛出
    """
    target = Path(filepath)
    if not target.exists():
        raise FileNotFoundError(f"通讯录文件不存在: {target}")

    try:
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"通讯录 JSON 解析失败: {exc}") from exc

    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("通讯录 JSON 文件必须为由联系人字典组成的数组 (list[dict])")

    return data


def format_contacts_table(contacts: list[dict[str, Any]]) -> str:
    """将联系人列表格式化为适合终端输出的对齐文本表格。"""
    if not contacts:
        return "[通讯录为空]"

    lines = [
        f"{'姓名/标识':<16} | {'类型':<6} | {'部门':<12} | {'岗位/职责':<20} | {'技能标签'}",
        "-" * 82,
    ]
    for c in contacts:
        skills_str = ", ".join(c.get("skills", [])) or "-"
        lines.append(
            f"{c.get('name', ''):<16} | "
            f"{c.get('agent_type', 'human'):<6} | "
            f"{c.get('department', ''):<12} | "
            f"{c.get('role', ''):<20} | "
            f"{skills_str}"
        )
    return "\n".join(lines)
