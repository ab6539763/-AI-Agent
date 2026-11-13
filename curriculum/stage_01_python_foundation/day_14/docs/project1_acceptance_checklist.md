# 项目一（v0.1.0-day14）QA 验收报告与 Code Review 检查清单

**项目名称**：智枢企业级智能体平台 · 项目一《命令行多轮对话 AI 助手》  
**验收版本**：`v0.1.0-day14`（第一阶段里程碑交付物）  
**验收团队**：Tech Lead 张工（Code Review）、QA 工程师 李婷（质量验收）  

---

## 1. 功能验收清单（Functional Acceptance Checklist）

| 编号 | 验收项 | 验收标准 | 测试方式 | 验收结果 |
|------|--------|----------|----------|----------|
| AC-01 | 多轮上下文记忆 | 连续提问时，`LLMClient` 发送的 `messages` 列表包含完整的 `system` + 历史 `user`/`assistant` 对话 | `pytest` + Notebook 实操 | ✅ PASS |
| AC-02 | 离线 Mock 回退 | 未设置 `OPENAI_API_KEY` 时自动启用 `httpx.MockTransport`，不依赖外网即可端到端运行 | `monkeypatch.delenv` 单测 | ✅ PASS |
| AC-03 | `/clear` 指令 | 清空历史对话并重置轮数与 Token 统计，同时**保留**初始 `System Prompt` | `test_clear_keeps_system_prompt_and_resets_stats` | ✅ PASS |
| AC-04 | `/save` 与 `/load` | 支持将完整消息与统计导出为 UTF-8 JSON，并支持从 JSON 无损恢复会话；缺失文件/坏 JSON 抛出 `CommandError` | `test_save_and_load_roundtrip` & `error_handling` | ✅ PASS |
| AC-05 | `/stats` 指令 | 准确展示当前模型名称、运行模式（Mock/Live）、对话轮数、上下文消息条数与三项 Token 统计 | `test_stats_and_exit_and_unknown_command` | ✅ PASS |
| AC-06 | `/exit` 与 `/help` | `/help` 打印指令清单；`/exit` 返回终止标志 `(False, ...)` 优雅退出 CLI 循环 | `test_stats_and_exit_and_unknown_command` | ✅ PASS |
| AC-07 | 瞬时异常重试 | 遇到 HTTP 429 / 503 / 超时时，按 `@retry_on_error` 自动重试并在恢复后正常返回 | `test_retry_succeeds_after_transient_429_and_503` | ✅ PASS |
| AC-08 | 不可重试错误与回滚 | 遇到 HTTP 401 时不浪费重试次数（仅请求 1 次），且 `MultiTurnAssistant.ask()` 自动回滚未提交的 `user` 消息 | `test_non_retryable_401_fails_fast_and_rolls_back_user_message` | ✅ PASS |

---

## 2. 工程规范与 Code Review 检查清单（MR !014）

- [x] **PEP 8 与类型标注**：所有公开类、方法与函数均具备完整 Python 3.10+ 类型注解（`list[ChatMessage]`、`str | None` 等）。
- [x] **中文注释与 Docstring**：核心模块、类、关键异常处理与回滚逻辑均附带清晰中文 Docstring 与行内说明。
- [x] **密钥安全合规**：严禁硬编码 API Key；所有鉴权凭据统一通过 `os.environ.get("OPENAI_API_KEY")` 读取。
- [x] **无交互阻塞风险**：核心逻辑与 CLI `input()` 解耦，`MultiTurnAssistant.process_input()` 可被 `pytest` 与 Notebook 无阻塞直接调用。
- [x] **自动化校验通过**：`scripts/verify_day.py` Notebook 执行与 `pytest` 单元测试 100% 通过。

---

## 3. QA 验收结论

> **QA 李婷 签字结论**：`v0.1.0-day14` 各项功能指标、异常容错能力与自动化测试覆盖度均达到第一阶段里程碑上线标准，**准予发布**，正式进入第二阶段（`v0.2.0` 大模型原理与 Web 对话系统）研发！
