# 智枢企业级智能体平台（ZhiShu-Agent）—— 70 天从 0 到 1 工程实战演进仓库

> **项目背景**：模拟国内互联网/AI 科技公司（星辰数科）真实研发团队，以企业真实业务需求为驱动，从零基础起步，历时 70 天（10 个迭代冲刺 Sprint），通过 **GitLab 敏捷协作流** 一天一天、一步一步完成「智枢企业级 Agent 平台」从 0 到 1 的全链路开发、测试与部署上线。

---

## 1. 团队角色设定（模拟真实国内研发团队）

| 角色 | 姓名 | 职责分工 |
|------|------|----------|
| 产品经理 (PM) | 林晓 | 拆解企业业务痛点、编写 PRD 需求文档、验收产品功能 |
| 技术负责人 (Tech Lead) | 张工 | 架构设计、技术选型、Code Review、把控代码质量与工程规范 |
| AI 应用开发工程师（主角/学员视角） | 陈默 | 核心业务代码编写、单元测试、Notebook 实验验证、提交 MR |
| 测试工程师 (QA) | 李婷 | 编写测试用例、接口与回归测试、把关上线质量 |
| 运维工程师 (DevOps) | 赵磊 | CI/CD 流水线、Docker 容器化、模型推理部署、线上监控 |

---

## 2. 仓库目录结构

```text
.
├── docs/                                  # 团队规范、GitLab 工作流与 70 天演进总图
│   ├── TEAM_GITLAB_WORKFLOW.md            # 国内研发团队 GitLab 协作规范
│   └── ROADMAP_70_DAYS.md                 # 70 天需求驱动演进与版本映射总表
├── curriculum/                            # 每日教学交付物（HTML5 课件 + Jupyter + 文档）
│   └── stage_01_python_foundation/        # 第一阶段：Python 编程基础 (Day 01 - Day 14)
│       ├── day_01/
│       │   ├── courseware.html            # HTML5 交互式课件（含旁白、流程图、架构图、作业）
│       │   ├── notebook.ipynb             # Jupyter Notebook 实操（含逐行注释与运行输出）
│       │   └── docs/                      # 当日 PRD、架构设计、GitLab MR 记录、作业答案
│       ├── day_02/ ...
├── project_iterations/                    # 企业级 Agent 平台每日可独立运行的迭代快照
│   ├── day_01/                            # v0.1.0-day01：平台环境初始化与员工数字名片 CLI
│   ├── day_02/                            # v0.1.0-day02：Prompt 模板清洗与敏感词脱敏引擎
│   ├── day_03/                            # v0.1.0-day03：多轮交互路由与企业菜单调度器
│   └── ...
└── scripts/                               # 自动化校验脚本（测试全部迭代与 Notebook）
```

---

## 3. 本地运行与测试验证

```bash
# 1. 创建并激活虚拟环境
uv venv .venv
source .venv/bin/activate

# 2. 安装依赖
uv pip install pytest nbformat jupyter_client ipykernel fastapi uvicorn httpx pydantic

# 3. 运行指定天数的单元测试（例如 Day 01）
pytest project_iterations/day_01/tests -v
```
