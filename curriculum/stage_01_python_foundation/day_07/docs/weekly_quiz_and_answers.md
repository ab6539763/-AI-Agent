# Day 07 第 1 周综合测评（10 道选择题 + 2 道编程实战题）与参考解析

> **测评说明**：本测评覆盖第 1 周（Day 01 - Day 07）核心知识点：Python 基础类型、字符串处理、流程控制、列表/字典数据结构、函数参数与作用域、JSON 序列化、`pathlib` 文件 I/O、异常处理以及 `pytest` 单元测试。

---

## 第一部分：单项选择题（共 10 题，每题 6 分，满分 60 分）

### 第 1 题
在智枢平台环境自检中，若要判断 Python 版本是否为 3.10 及以上，以下哪种数据类型最适合用于表示版本号中的主次版本号（如 `(3, 11)`）并进行大小比较？
- A. `str`（如 `"3.11"`）
- B. `tuple[int, int]`（如 `(3, 11)`）
- C. `set[int]`（如 `{3, 11}`）
- D. `dict`（如 `{"major": 3, "minor": 11}`）

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：字符串比较 `"3.9" > "3.11"` 会按字典序得出错误结论；集合无序且不支持大小比较；整数元组 `(3, 11) >= (3, 10)` 按元素逐位数值比较，是 Python `sys.version_info` 的标准做法。

</details>

---

### 第 2 题
在清洗用户输入或联系人姓名时，表达式 `"  陈默 \n\t ".strip()` 的返回值是？
- A. `"陈默 \n\t"`
- B. `"陈 默"`
- C. `"陈默"`
- D. `"陈默\n"`

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**C**
- **解析**：`str.strip()` 默认去除字符串首尾两端的全部空白字符（包括空格、`\n`、`\t` 等），不会修改字符串中间的字符。

</details>

---

### 第 3 题
关于 Python 字典（`dict`）的键查找，下列说法**错误**的是？
- A. 直接使用 `d["missing_key"]` 访问不存在的键会抛出 `KeyError`
- B. 使用 `d.get("missing_key", [])` 在键不存在时会返回默认值 `[]`
- C. 字典的键可以是 `list`（列表）类型，方便用多字段组合做索引
- D. `in` 运算符（如 `"name" in d`）默认检查的是键是否存在，时间复杂度为 $O(1)$

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**C**
- **解析**：字典的键必须是可哈希（hashable）的不可变类型（如 `str`、`int`、`tuple`），`list` 是可变且不可哈希的，不能作为字典的键。

</details>

---

### 第 4 题
在 `zhishu_agent/contacts.py` 中，为什么 `save_contacts` 使用 `json.dump(contacts, f, ensure_ascii=False, indent=2)`？
- A. `ensure_ascii=False` 可以让 JSON 文件体积缩小 10 倍
- B. `ensure_ascii=False` 避免中文字符被转义成 `\uXXXX`，`indent=2` 提供可读的缩进排版
- C. 不加 `ensure_ascii=False` 会导致 `json.load()` 无法读回中文
- D. `indent=2` 是 JSON 语法强制要求的格式

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：`json.dump` 默认 `ensure_ascii=True`，会把中文转义为 `\u4e2d\u6587` 形式（虽然 `json.load` 仍能还原，但人工排查和 Git diff 极不友好）。加上 `ensure_ascii=False` 与 `encoding="utf-8"` 可直接输出可读中文。

</details>

---

### 第 5 题
观察以下代码，函数的返回值是什么？
```python
def filter_agents(items):
    return [x["name"] for x in items if x.get("agent_type") == "agent"]

data = [{"name": "张工", "agent_type": "human"}, {"name": "QA-Bot", "agent_type": "agent"}]
print(filter_agents(data))
```
- A. `[{"name": "QA-Bot", "agent_type": "agent"}]`
- B. `["QA-Bot"]`
- C. `["张工", "QA-Bot"]`
- D. `("QA-Bot",)`

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：列表推导式筛选出 `agent_type == "agent"` 的元素后，收集的是 `x["name"]`，因此结果为 `["QA-Bot"]`。

</details>

---

### 第 6 题
在 `update_contact(contacts, target_name, /, **updates)` 函数签名中，斜杠 `/` 的作用是什么？
- A. 表示函数必须返回 `None`
- B. 表示 `contacts` 和 `target_name` 是仅限位置参数（Positional-Only），从而允许 `**updates` 中传入 `name="新名字"` 而不会与形参名冲突
- C. 表示 `**updates` 可以接收整数作为键
- D. 表示除法运算优先级

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：Python 3.8+ 支持 `/` 语法声明仅限位置参数。如果不加 `/`，且第二参数也叫 `name`，调用 `update_contact(contacts, "陈默", name="张工")` 会报 `TypeError: got multiple values for argument 'name'`。

</details>

---

### 第 7 题
使用 `pathlib.Path` 保存文件到可能尚不存在的子目录时，最规范的做法是？
- A. `target.mkdir()`
- B. `target.parent.mkdir(parents=True, exist_ok=True)`
- C. `os.system("mkdir " + str(target))`
- D. 直接 `open(target, "w")`，Python 会自动创建所有缺失目录

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：`open(..., "w")` 不会自动创建不存在的父目录，会抛出 `FileNotFoundError`；`target.parent.mkdir(parents=True, exist_ok=True)` 能安全地递归创建父目录且在目录已存在时不报错。

</details>

---

### 第 8 题
在 `load_contacts(filepath)` 中，以下哪种异常处理策略最符合工程规范？
- A. 捕获所有 `Exception` 并静默返回 `[]`
- B. 文件不存在时抛出 `FileNotFoundError`，JSON 语法损坏或根节点非 `list[dict]` 时抛出 `ValueError`
- C. 遇到错误直接调用 `exit(0)` 退出整个进程
- D. 用 `print("出错了")` 代替抛出异常

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：库函数应当显式抛出语义清晰的异常（`FileNotFoundError`、`ValueError`），把“如何处理或展示错误”的决策权交给上层调用方，切忌静默吞掉异常或直接退出进程。

</details>

---

### 第 9 题
在 `pytest` 单元测试中，为什么测试文件读写持久化时推荐使用内置夹具 `tmp_path`？
- A. `tmp_path` 会把文件写入数据库，比磁盘更快
- B. `tmp_path` 为每个测试用例提供独立的临时 `Path` 目录，测试互不干扰且不污染项目仓库
- C. `tmp_path` 可以自动修复 JSON 语法错误
- D. 不使用 `tmp_path` 就无法导入 `json` 模块

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：`tmp_path` 是 `pytest` 提供的标准 `pathlib.Path` 临时目录夹具，保证测试幂等、隔离、不残留垃圾文件。

</details>

---

### 第 10 题
在 `pytest` 中，如何断言调用 `delete_contact(contacts, "不存在")` 一定会抛出 `ValueError`？
- A. `assert delete_contact(contacts, "不存在") == ValueError`
- B. `with pytest.raises(ValueError): delete_contact(contacts, "不存在")`
- C. `try: delete_contact(...) except ValueError: assert False`
- D. `pytest.skip(ValueError)`

<details>
<summary>点击查看答案与解析</summary>

- **正确答案**：**B**
- **解析**：`with pytest.raises(ValueError):` 是 `pytest` 断言异常的标准上下文管理器，还可以配合 `match="..."` 验证异常提示文本。

</details>

---

## 第二部分：编程实战题（共 2 题，每题 20 分，满分 40 分）

### 编程题 1：通讯录批量导入与统计（`bulk_import_contacts`）
**题目要求**：
请编写函数 `bulk_import_contacts(contacts: list[dict], records: list[dict]) -> dict[str, int]`：
1. 遍历 `records` 中的每条字典记录，尝试调用 `add_contact` 将其加入 `contacts`。
2. 若某条记录因重名、缺少姓名/岗位或 `agent_type` 非法抛出 `ValueError`，不要中断整个批量导入，而是跳过该条记录。
3. 最终返回一个统计字典：`{"added": 成功新增数, "skipped": 跳过数, "total": 导入后通讯录总数}`。

<details>
<summary>点击查看参考代码与解析</summary>

```python
from typing import Any
from zhishu_agent.contacts import add_contact


def bulk_import_contacts(
    contacts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """批量导入联系人，跳过校验失败的记录并返回导入统计。"""
    added = 0
    skipped = 0

    for rec in records:
        if not isinstance(rec, dict):
            skipped += 1
            continue
        try:
            add_contact(
                contacts,
                name=str(rec.get("name", "")),
                role=str(rec.get("role", "")),
                department=str(rec.get("department", "AI 研发部")),
                email=str(rec.get("email", "")),
                phone=str(rec.get("phone", "")),
                agent_type=str(rec.get("agent_type", "human")),
                skills=rec.get("skills") if isinstance(rec.get("skills"), list) else None,
            )
            added += 1
        except ValueError:
            skipped += 1

    return {
        "added": added,
        "skipped": skipped,
        "total": len(contacts),
    }
```

**考点解析**：结合循环遍历、`try-except` 精准捕获业务异常（`ValueError`）以及字典统计结果返回，避免单条脏数据导致整批导入崩溃。

</details>

---

### 编程题 2：按技能标签统计分布并脱敏导出（`export_skill_report`）
**题目要求**：
请编写函数 `export_skill_report(contacts: list[dict]) -> dict[str, list[str]]`：
1. 遍历 `contacts` 中的所有联系人，提取每个人的 `skills` 列表。
2. 构建一个“技能 -> 拥有该技能的联系人姓名列表”的倒排索引字典（例如 `{"Python": ["张工", "陈默"]}`）。
3. 要求技能名按字母/字典序排序，每个技能对应的姓名列表也按字典序排序且不重复。

<details>
<summary>点击查看参考代码与解析</summary>

```python
from typing import Any


def export_skill_report(contacts: list[dict[str, Any]]) -> dict[str, list[str]]:
    """构建 技能 -> 联系人姓名列表 的有序倒排索引。"""
    skill_map: dict[str, set[str]] = {}

    for contact in contacts:
        name = str(contact.get("name", "")).strip()
        if not name:
            continue
        for skill in contact.get("skills", []):
            clean_skill = str(skill).strip()
            if not clean_skill:
                continue
            skill_map.setdefault(clean_skill, set()).add(name)

    return {
        skill: sorted(names)
        for skill, names in sorted(skill_map.items(), key=lambda item: item[0])
    }
```

**考点解析**：综合考察 `dict.setdefault()`、`set` 去重、嵌套循环以及字典推导式排序，是企业级 Agent 技能路由（Skill Routing）的常见底层逻辑。

</details>
