# Day 64 完整部署运维指南与 15 分钟毕业答辩演示脚本

> **适用版本**：`v1.0.0-day64` · 星辰数科《智枢企业级智能体平台 (ZhiShu-Agent)》  
> **维护团队**：DevOps 赵磊 · 全栈工程师 陈默 · QA 李婷

---

## 第一部分：生产级 Docker 部署运维指南

### 1. 环境准备与密钥配置

在目标服务器（Linux x86_64 / ARM64，已安装 Docker 24+ 与 Docker Compose v2）进入 `project_iterations/day_64/` 目录：

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，务必将 APP_ENV 设为 production，并替换为真实高强度密钥
#    APP_ENV=production
#    JWT_SECRET=<openssl rand -hex 32 生成的随机串>
#    LLM_API_KEY=<企业网关分配的真实 API Key>
```

> **⚠️ 安全红线**：`release_packager.py` 中的 `check_env_vars()` 会在 `APP_ENV=production` 时自动拦截 `change-me-in-production` 等占位符密钥，切勿跳过预检直接上线。

### 2. 发布前自动化预检（Preflight Checks）

在构建镜像前，先执行发布前校验与 5 步自测：

```bash
.venv/bin/python project_iterations/day_64/main.py
```

预期输出包含：
- `[1/3] 发布前预检 (Preflight): PASS ✅`
- `[2/3] 发布清单 (Release Manifest): 共登记 6 个核心交付物`
- `[3/3] 5 步全流程上线演示 (5-Step Live Demo): Step 1 ~ Step 5 全部 ✅`

### 3. 构建镜像与启动容器集群

```bash
cd project_iterations/day_64

# 1. 构建多阶段生产镜像
docker compose build --no-cache

# 2. 后台启动服务并等待健康检查就绪
docker compose up -d

# 3. 查看容器状态与实时日志
docker compose ps
docker compose logs -f zhishu-agent
```

### 4. 线上健康检查与平滑升级

```bash
# 验证健康探针
curl -s http://127.0.0.1:8000/api/v1/health | jq .

# 平滑升级与回滚
docker compose pull && docker compose up -d --remove-orphans
```

---

## 第二部分：15 分钟毕业答辩现场演示脚本（Live Demo Script）

> **🎙️ 演示角色分配**：主讲人（陈默，全栈工程视角），评委提问辅助（张工 / 林晓）。

| 时间段 | 演示环节 | 核心动作与台词要点 | 对应接口 / 工具 |
| :--- | :--- | :--- | :--- |
| **00:00 – 02:00** | **1. 项目背景与架构总览** | 展示企业痛点（财报检索幻觉、高风险操作失控、上线难观测），亮出智枢平台五层架构与 `v1.0.0-day64` 容器化方案。 | `PRD_and_Architecture.md` |
| **02:00 – 04:00** | **2. 发布预检与容器安全** | 运行 `main.py` 展示 `validate_dockerfile`（多阶段 + 非 root `appuser` + `HEALTHCHECK`）与 SHA-256 制品清单。 | `run_preflight_checks()` |
| **04:00 – 06:30** | **3. Step 1 & 2：健康检查与混合 RAG** | 调用 `/api/v1/health` 确认服务就绪；提问“星辰数科 2025 Q4 营收与内控红线”，展示带 `citations` 证据溯源的精准回答。 | `GET /api/v1/health`<br/>`POST /api/v1/rag/query` |
| **06:30 – 09:00** | **4. Step 3：财务比率工具调用** | 传入 Q4 财务指标，调用工具精准计算净利率（16.41%）、ROE（20.0%）与资产负债率（38.0%），消除大模型算术幻觉。 | `POST /api/v1/tools/financial-ratio` |
| **09:00 – 11:30** | **5. Step 4：HITL 人工审批闭环** | 提交 85 万元“研发 GPU 集群扩容资金划拨”高风险动作，触发 `pending` 挂起；由审批人批准后状态流转为 `approved`，并演示重复审批返回 `409 Conflict`。 | `POST /api/v1/hitl/submit`<br/>`POST /api/v1/hitl/approve` |
| **11:30 – 13:30** | **6. Step 5：全链路审计日志导出** | 导出本次会话完整 JSON 审计日志，证明所有健康检查、检索、工具计算与审批决策 100% 可追溯。 | `GET /api/v1/audit/export` |
| **13:30 – 15:00** | **7. 质量总结与 Q&A** | 展示 `pytest` 全绿测试报告与 `verify_day.py` 自动化校验结果，回答评委关于高并发、幻觉抑制与私有化部署的提问。 | `pytest` / `verify_day.py` |
