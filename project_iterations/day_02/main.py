"""Day 02 平台启动入口：演示环境自检与 Prompt 清洗脱敏流水线"""
from zhishu_agent.profile import get_environment_info
from zhishu_agent.sanitizer import (
    clean_text,
    estimate_cost_and_check_budget,
    mask_sensitive_words,
    render_prompt_template,
)


def run_sanitizer_pipeline() -> None:
    """运行 Day 02 Prompt 清洗、脱敏、模板渲染与预算校验流水线。"""
    raw_query = "   请帮我总结   Project-Apollo  的进度，顺便检查 sk-secret-9988 是否有效。  \n"
    sensitive = ("Project-Apollo", "sk-secret-9988")

    cleaned = clean_text(raw_query)
    safe_text = mask_sensitive_words(cleaned, sensitive)
    prompt = render_prompt_template(
        role="星辰数科企业研发助手",
        task="对用户提交的项目问题进行安全合规审查并给出简明答复",
        user_input=safe_text,
    )
    allowed = estimate_cost_and_check_budget(char_count=len(prompt), budget=0.05)

    print("=== Day 02 Prompt 安全预处理流水线 ===")
    print(f"原始输入 : {raw_query!r}")
    print(f"清洗结果 : {cleaned}")
    print(f"脱敏结果 : {safe_text}")
    print("\n--- 渲染后的标准 Prompt ---")
    print(prompt)
    print(f"\n[预算校验] 字符数={len(prompt)} | 预算=¥0.05 | 是否放行={allowed}")


if __name__ == "__main__":
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day02 | Python {env['python_version']}")
    run_sanitizer_pipeline()
