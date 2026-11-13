# Day 64 课后作业与参考答案

## 作业一：为什么生产环境 Dockerfile 必须采用多阶段构建（Multi-stage Build）与非 root 用户？
**题目**：在智枢平台的 `Dockerfile` 中，我们拆分了 `builder` 与 `runtime` 两个阶段，并在最后执行 `USER appuser`。请结合企业安全与运维规范说明这两项设计的工程价值。

### 参考答案：
1. **多阶段构建（Multi-stage Build）的价值**：
   - `builder` 阶段安装了 `build-essential` 等 C/C++ 编译工具链用于编译 Python 扩展包；
   - `runtime` 阶段仅通过 `COPY --from=builder /install /usr/local` 拷贝编译好的运行时依赖，彻底剔除了编译器与构建缓存，通常可将镜像体积缩减 50% 以上，同时大幅减少镜像中的 CVE 漏洞面。
2. **非 root 用户（`USER appuser`）的价值**：
   - 遵循最小权限原则（Principle of Least Privilege）。即使应用层出现远程代码执行（RCE）漏洞，攻击者在容器内也仅拥有受限的普通用户权限，无法修改系统关键目录或提权逃逸至宿主机。

---

## 作业二：设计生产环境密钥占位符拦截逻辑
**题目**：很多团队曾因为忘记修改 `.env.example` 中的默认密钥（如 `change-me-in-production`）就直接上线而引发安全事故。请说明 `check_env_vars(config)` 如何区分“测试/预发环境”与“生产环境”的密钥校验策略。

### 参考答案：
- 当 `APP_ENV != "production"`（例如 `staging` 或本地开发）时，允许使用示例密钥以便团队快速跑通流程，只需检查必填键是否存在且非空；
- 当 `APP_ENV == "production"` 时，除了检查非空外，还必须比对黑名单占位符集合 `{"change-me-in-production", "your-api-key-here", "changeme", "todo"}`，一旦命中立即将 `passed` 置为 `False` 并阻断发布流水线。

---

## 作业三：使用 `DemoRunner` 编写上线前冒烟测试（Smoke Test）
**题目**：在 CI/CD 发布流水线中，如何在不启动外部网络和真实 LLM API Key 的情况下，验证智枢平台核心链路（健康检查 → RAG → 工具 → HITL → 审计）可用？请写出核心验证代码。

### 参考答案：
```python
from pathlib import Path
from zhishu_agent.release_packager import DemoRunner, run_preflight_checks

day64_dir = Path("project_iterations/day_64")
preflight = run_preflight_checks(day64_dir)
assert preflight["overall_passed"] is True

runner = DemoRunner()
steps = runner.run_all()
assert len(steps) == 5
assert all(step["passed"] for step in steps)
print("v1.0.0-day64 冒烟测试 100% 通过！")
```
