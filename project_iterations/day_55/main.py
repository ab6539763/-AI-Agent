"""Day 55 平台启动入口：私有化推理服务网关（Ollama / vLLM）与吞吐压测演示 (v0.5.0-day55)."""

import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    InferenceBackendConfig,
    OpenAICompatibleGateway,
    ThroughputBenchmarker,
)


def main() -> None:
    """运行 Day 55 OpenAI 兼容网关无缝切换与并发吞吐基准测试演示."""
    print("=" * 72)
    print("🚀 智枢企业级智能体平台 v0.5.0-day55 · 私有化推理网关与吞吐压测")
    print("=" * 72)

    ollama_cfg = InferenceBackendConfig.ollama_default()
    vllm_cfg = InferenceBackendConfig.vllm_default()

    # 1. 统一 OpenAI 兼容网关演示：零业务代码改动从 Ollama 热切换至 vLLM
    prompt = [{"role": "user", "content": "请总结智枢平台私有化部署的显存优化核心策略。"}]
    with OpenAICompatibleGateway(ollama_cfg) as gateway:
        res_ollama = gateway.chat_completions(prompt, max_tokens=128)
        print(f"\n[1] 当前后端: {res_ollama.backend} ({res_ollama.model})")
        print(f"    TTFT={res_ollama.ttft_ms} ms | Tokens={res_ollama.completion_tokens} | 响应: {res_ollama.content}")

        gateway.switch_backend(vllm_cfg)
        res_vllm = gateway.chat_completions(prompt, max_tokens=128)
        print(f"\n[2] 热切换后端 -> {res_vllm.backend} ({res_vllm.model})")
        print(f"    TTFT={res_vllm.ttft_ms} ms | Tokens={res_vllm.completion_tokens} | 响应: {res_vllm.content}")

    # 2. 并发网关压测（MockTransport 离线全链路）
    prompts = [f"企业工单 #{i}：请生成只读 SQL 查询近 7 天异常日志。" for i in range(12)]
    with OpenAICompatibleGateway(vllm_cfg) as vllm_gw:
        report = ThroughputBenchmarker.benchmark_gateway(vllm_gw, prompts=prompts, concurrency=4, max_tokens=96)
        print("\n[3] vLLM 网关 4 并发离线压测报告")
        print(
            f"    请求={report.successful_requests}/{report.total_requests} | "
            f"系统总吞吐={report.system_tps:.1f} tok/s | "
            f"TTFT(P95)={report.ttft_ms_p95:.2f} ms | "
            f"总延迟(P95)={report.latency_ms_p95:.2f} ms"
        )

    # 3. Ollama vs vLLM 并发扩展性对比（Continuous Batching + PagedAttention）
    print("\n[4] Ollama vs vLLM 并发吞吐扩展性仿真对比 (output_tokens=128)")
    print("    并发数 | Ollama TTFT | Ollama TPS | vLLM TTFT | vLLM TPS  | 吞吐加速比")
    print("    " + "-" * 68)
    for row in ThroughputBenchmarker.simulate_concurrency_comparison([1, 4, 8, 16, 32]):
        print(
            f"    {row['concurrency']:>4d}   | {row['ollama_ttft_ms']:>8.1f} ms | "
            f"{row['ollama_system_tps']:>7.1f}/s | {row['vllm_ttft_ms']:>6.1f} ms | "
            f"{row['vllm_system_tps']:>7.1f}/s | {row['tps_speedup_vllm_vs_ollama']:>6.2f}x"
        )


if __name__ == "__main__":
    main()
