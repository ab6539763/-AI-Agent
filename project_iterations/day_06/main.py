"""Day 06 平台启动入口：演示函数式 Prompt 清洗流水线、动态 API Payload 构造与递归 Token 统计"""
import json

from zhishu_agent.pipeline_fn import (
    apply_pipeline,
    build_api_payload,
    count_nested_tokens,
)
from zhishu_agent.profile import get_environment_info


def run_demo() -> None:
    """运行 Day 06 函数式管道核心功能演示"""
    env = get_environment_info()
    print(f"[系统启动] 智枢平台 v0.1.0-day06 | Python {env['python_version']}")

    # 1. 高阶函数 + lambda 清洗用户输入 Prompt
    raw_prompt = "   请帮我总结   【机密】星辰数科 Q3 营收报告   的关键结论！  "
    cleaned_prompt = apply_pipeline(
        raw_prompt,
        str.strip,
        lambda s: " ".join(s.split()),
        lambda s: s.replace("【机密】", "[已脱敏]"),
    )
    print(f"\n[Prompt 清洗前] {raw_prompt!r}")
    print(f"[Prompt 清洗后] {cleaned_prompt!r}")

    # 2. 使用位置参数 + *args + 默认关键字参数 + **kwargs 构造 API Payload
    sys_msg = {"role": "system", "content": "你是星辰数科智枢平台企业级 AI 助手。"}
    user_msg = {"role": "user", "content": cleaned_prompt}

    payload = build_api_payload(
        "deepseek-chat",
        sys_msg,
        user_msg,
        temperature=0.3,
        max_tokens=2048,
        stream=True,
    )
    print("\n[API 请求体 Payload]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # 3. 递归统计嵌套 JSON 树中的文本字符数（估算 Token）
    total_chars = count_nested_tokens(payload)
    print(f"\n[递归统计] Payload 嵌套树总文本字符数（估算 Token）: {total_chars}")


if __name__ == "__main__":
    run_demo()
