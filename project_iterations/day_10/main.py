"""Day 10 平台启动入口：演示模块化包导入、自定义异常体系与 try/except/else/finally 完整链路"""
from zhishu_agent import (
    APIResponseError,
    BaseLLMModel,
    ChatMessage,
    InvalidRoleError,
    ModelConfigError,
    OpenAIModel,
    QwenModel,
    ZhiShuError,
)


def safe_invoke(model: BaseLLMModel, role: str, prompt: str) -> str:
    """
    安全调用大模型演示函数：
    展示 try / except / else / finally 四段式异常处理最佳实践。
    """
    result_text = ""
    try:
        msg = ChatMessage(role=role, content=prompt)
        reply = model.generate([msg])
    except InvalidRoleError as exc:
        print(f"  [拦截-角色异常] {exc}")
        result_text = f"FALLBACK(role): {exc.error_code}"
    except ModelConfigError as exc:
        print(f"  [拦截-配置异常] {exc}")
        result_text = f"FALLBACK(config): {exc.error_code}"
    except APIResponseError as exc:
        print(f"  [拦截-接口异常] {exc} (HTTP {exc.status_code})")
        result_text = f"FALLBACK(api): {exc.error_code}"
    except ZhiShuError as exc:
        print(f"  [拦截-通用平台异常] {exc}")
        result_text = f"FALLBACK(zhishu): {exc.error_code}"
    else:
        # 只有 try 块完全没有抛出异常时才会执行
        print(f"  [成功-else分支] 推理完成，回复长度 {len(reply.content)} 字符")
        result_text = reply.content
    finally:
        # 无论成功还是异常，都会执行资源释放与审计收尾
        print(f"  [收尾-finally分支] 已记录调用审计日志 (model={model.model_name})")

    return result_text


def run_demo() -> None:
    """运行 Day 10 核心功能演示。"""
    print("=== 智枢平台 v0.1.0-day10：模块化包管理与自定义异常体系演示 ===\n")

    openai_llm = OpenAIModel(model_name="gpt-4o-mini", temperature=0.3)
    qwen_llm = QwenModel(model_name="qwen-plus", temperature=0.8, enable_search=True)

    print("1) 正常调用场景（触发 try -> else -> finally）：")
    out1 = safe_invoke(openai_llm, role="user", prompt="请说明 try/except/else/finally 的执行顺序。")
    print(f"   返回结果: {out1}\n")

    print("2) 非法角色场景（触发 InvalidRoleError -> finally）：")
    out2 = safe_invoke(qwen_llm, role="superadmin", prompt="你好")
    print(f"   返回结果: {out2}\n")

    print("3) 模型配置非法场景（触发 ModelConfigError）：")
    try:
        openai_llm.temperature = 3.2
    except ModelConfigError as exc:
        print(f"  [拦截-温度配置异常] {exc}\n")

    print("4) 上游 API 异常场景（触发 APIResponseError -> finally）：")
    out4 = safe_invoke(qwen_llm, role="user", prompt="[SIMULATE_ERROR] 测试上游超时")
    print(f"   返回结果: {out4}\n")


if __name__ == "__main__":
    run_demo()
