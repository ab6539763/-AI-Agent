# Day 07 需求文档（PRD）、架构设计与 GitLab 协作记录

## 1. 旁白：第 1 周里程碑复盘 —— 从“单兵脚本”到“持久化数据系统”

> **讲师旁白**：恭喜大家顺利走到第 1 周的收官日（Day 07）！回顾过去 6 天，我们从 Day 01 的环境治理与数字名片 `profile.py` 起步，一路攻克了字符串清洗、条件分支与循环路由、列表/字典数据结构、JSON 序列化（`json_parser.py`）以及 `pathlib` 文件异常处理。很多同学会问：“学完第 1 周，我到底能做出什么真实东西？”今天，我们不搞虚的，直接用本周所有核心语法，在**智枢平台（ZhiShu-Agent）**中落地第一个完整闭环的业务子系统——**企业通讯录 / Agent 联系人管理系统（`zhishu_agent/contacts.py`）**，打通 **Create / Read / Update / Delete（CRUD）+ 本地 JSON 持久化**，为下周的面向对象重构与真实大模型 API 接入打下坚实基础！

---

## 2. GitLab Issue #007：第 1 周里程碑复盘与企业通讯录/Agent联系人管理系统

- **提出人**：产品经理 林晓 / Tech Lead 张工
- **指派给**：AI 应用开发工程师 陈默
- **关联分支**：`feature/day-07-contacts-capstone`
- **目标版本**：`v0.1.0-day07`

### 2.1 第 1 周能力里程碑回顾
| 天数 | 核心主题 | 平台迭代产出 | 关键工程能力 |
|------|----------|--------------|--------------|
| Day 01 | 开发环境与第一行代码 | `zhishu_agent/profile.py` | Python 环境自检、基础类型、GitLab 协作流 |
| Day 02 | 字符串与 Prompt 清洗 | 文本清洗与脱敏模块 | `strip`/`replace`/f-string/切片 |
| Day 03 | 条件与循环控制流 | 多轮交互路由调度器 | `if-elif-else`、`while`/`for`、边界校验 |
| Day 04 | 列表与字典数据结构 | 企业工具/技能注册表 | `list`/`dict` 嵌套操作、推导式 |
| Day 05 | JSON 解析与会话持久化 | `zhishu_agent/json_parser.py` | `json.loads`/`json.dump(ensure_ascii=False)` |
| Day 06 | 文件路径与异常处理 | 健壮 I/O 与异常防御 | `pathlib.Path`、`try-except`、`pytest` `tmp_path` |
| **Day 07** | **第 1 周综合实战（Capstone）** | **`zhishu_agent/contacts.py`** | **完整 CRUD + JSON 持久化 + 单元测试闭环** |

### 2.2 业务需求描述
1. **联系人模型规范**：每条记录统一使用标准字典表示，包含 `name`（姓名/Agent 标识，唯一主键）、`role`（岗位/职责）、`department`（所属部门）、`email`、`phone`、`agent_type`（仅允许 `"human"` 或 `"agent"`）与 `skills`（技能标签列表）。
2. **完整 CRUD 接口**：
   - `add_contact`：校验非空字段、校验 `agent_type` 合法性并防止重名冲突。
   - `find_contact`：支持按姓名、岗位、部门、邮箱及技能标签进行大小写不敏感的模糊检索。
   - `update_contact`：支持按精确姓名局部更新指定字段（含重命名冲突检测与白名单字段校验）。
   - `delete_contact`：按精确姓名删除联系人并返回被删记录，不存在时抛出 `ValueError`。
   - `list_contacts`：支持按 `agent_type` 与 `department` 组合筛选，返回副本避免外部误修改。
3. **JSON 持久化接口 (`save_contacts` / `load_contacts`)**：使用 `pathlib.Path` 自动创建父目录，以 `utf-8` + `ensure_ascii=False` + `indent=2` 保存中文通讯录，并在加载时校验文件存在性与 `list[dict]` 合法性。

### 2.3 系统架构图（Week 1 演进与 Contacts CRUD 数据流）

```mermaid
flowchart TD
    subgraph W1["第 1 周基础能力沉淀"]
        D1["Day 01-02<br/>环境与字符串清洗"] --> D3["Day 03-04<br/>流程控制与列表/字典"]
        D3 --> D5["Day 05-06<br/>JSON 序列化与 Path/异常"]
    end

    D5 --> C["Day 07 核心模块: zhishu_agent/contacts.py"]

    C --> ADD["add_contact()<br/>字段校验 + 去重写入"]
    C --> FIND["find_contact() / list_contacts()<br/>模糊检索 + 条件筛选"]
    C --> UPD["update_contact()<br/>白名单局部更新"]
    C --> DEL["delete_contact()<br/>安全移除记录"]

    ADD & UPD & DEL -->|内存状态 list[dict]| SAVE["save_contacts()<br/>ensure_ascii=False, indent=2"]
    SAVE -->|持久化| DB[("本地 JSON 文件<br/>contacts.json")]
    DB -->|load_contacts()<br/>类型与异常校验| FIND
```

---

## 3. GitLab Merge Request !007 评审记录

- **提交说明**：`feat(day-07): 完成第 1 周综合实战 —— 企业通讯录与 Agent 联系人管理系统 (CRUD + JSON 持久化)`
- **Tech Lead 张工 Review 意见**：
  - `[通过]` `update_contact` 使用了仅限位置参数 `target_name, /`，巧妙避免了更新 `name="新名字"` 时与函数形参冲突的问题，非常地道。
  - `[通过]` 所有校验失败均抛出语义明确的 `ValueError` / `FileNotFoundError`，杜绝了静默失败（Silent Failure）。
  - `[通过]` `save_contacts` 保留 `ensure_ascii=False` 与 `indent=2`，中文工程可读性极佳。
- **QA 李婷 测试结果**：`pytest project_iterations/day_07/tests -v` 共 9 个测试用例（含 `tmp_path` 持久化回环与异常边界测试）100% PASS。
