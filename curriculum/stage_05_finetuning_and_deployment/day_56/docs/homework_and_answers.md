# Day 56 课后作业与参考答案

## 作业一：多阶段 Dockerfile 优化与非 root 安全加固
**题目**：某初级工程师编写了如下单阶段 `Dockerfile`，存在镜像臃肿、安全漏洞与健康状态不可观测等问题：
```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
ENV OPENAI_API_KEY=sk-live-1234567890abcdef1234567890
CMD ["uvicorn", "zhishu_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
```
请指出该 `Dockerfile` 存在的 **4 项以上生产级缺陷**，并说明如何使用 `zhishu_agent.validate_dockerfile` 自动拦截此类问题。

### 参考答案：
1. **存在的核心生产级缺陷**：
   - **未使用多阶段构建与 slim 镜像**：直接基于完整版 `python:3.11`（约 1GB+），且未分离构建期与运行期，镜像体积过大且包含不必要的编译器与系统工具，扩大了 CVE 攻击面。应拆分为 `builder` 与 `runtime` 两阶段，并统一采用 `python:3.11-slim`。
   - **以默认 `root` 用户运行**：未创建低权限用户并执行 `USER <non-root>`，一旦 FastAPI 应用存在命令注入或路径穿越漏洞，攻击者将直接获得宿主机容器内 `root` 权限。
   - **硬编码真实密钥**：通过 `ENV OPENAI_API_KEY=sk-live-...` 将密钥打入镜像层（`docker history` 可直接明文查看），造成严重的凭据泄漏风险。
   - **缺少 `HEALTHCHECK` 与 `EXPOSE`**：编排引擎与负载均衡器无法感知进程假死（如死锁或 OOM 卡死）状态。
2. **使用 `validate_dockerfile` 自动拦截**：
   ```python
   from zhishu_agent import validate_dockerfile

   res = validate_dockerfile(bad_dockerfile_text)
   assert not res.passed
   print(res.errors)
   # 将输出：缺少多阶段构建、非 python:3.11-slim、缺少 USER、缺少 HEALTHCHECK、ENV 硬编码密钥
   ```

---

## 作业二：Docker Compose `depends_on` 与 `healthcheck` 编排实践
**题目**：在微服务容器化启动时，为什么仅写 `depends_on: [qdrant, redis]` 仍然会导致 `zhishu-api` 启动报错？请写出正确的 `depends_on` + `healthcheck` 编排写法，并说明 `start_period` 参数的工程意义。

### 参考答案：
1. **原因分析**：
   不带条件的 `depends_on` 仅控制容器的**创建与启动顺序**（PID 1 进程拉起即视为满足），而 Qdrant 索引加载、Redis AOF 回放与密码初始化往往需要数秒。此时端口尚未监听，`zhishu-api` 立即连接会触发 `ConnectionRefusedError` 并退出重启。
2. **正确编排写法**：
   ```yaml
   services:
     zhishu-api:
       depends_on:
         qdrant:
           condition: service_healthy
         redis:
           condition: service_healthy
       healthcheck:
         test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
         interval: 30s
         timeout: 5s
         retries: 3
         start_period: 15s
   ```
3. **`start_period` 的工程意义**：
   `start_period` 为容器冷启动宽限期（如 Python FastAPI 加载 Embedding 模型或连接池初始化耗时）。在宽限期内探测失败**不计入 `retries` 失败次数**，避免应用尚未完成冷启动就被 Docker 误判为 `unhealthy` 并反复重启。

---

## 作业三：`.env` 密钥注入规范与 CI 防泄漏校验
**题目**：团队成员在提交代码时误将包含真实 `REDIS_PASSWORD` 与 `OPENAI_API_KEY` 的配置文件推入 GitLab 仓库。请设计一套完整的 `.env` 密钥注入规范，并使用 `check_env_secrets_safety` 对 `.env.example` 与真实泄漏样本进行对比验证。

### 参考答案：
1. **`.env` 密钥注入规范**：
   - `.gitignore` 必须强制忽略 `.env`、`*.pem`、`*.key`，仅允许提交不含真实凭据的 `.env.example` 模板。
   - `docker-compose.yml` 通过 `env_file: [.env]` 与 `${VAR}` 变量插值动态注入密钥，不在 YAML 中写死明文。
   - 生产环境通过 CI/CD Secret（如 GitLab CI Variables / Vault / K8s Secret）在部署阶段动态渲染 `.env`。
2. **Python 校验示例**：
   ```python
   from zhishu_agent import check_env_secrets_safety, generate_env_example

   # 1. 安全模板应通过校验
   safe_res = check_env_secrets_safety(generate_env_example())
   assert safe_res.passed is True

   # 2. 真实密钥或明文口令应被立即拦截
   leaked = "OPENAI_API_KEY=sk-prod-998877665544332211\nREDIS_PASSWORD=ProdPass!2026"
   bad_res = check_env_secrets_safety(leaked)
   assert bad_res.passed is False
   print("拦截到的泄漏风险:", bad_res.errors)
   ```
