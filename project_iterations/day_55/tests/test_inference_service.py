"""Day 55 单元测试：InferenceBackendConfig、OpenAICompatibleGateway 与 ThroughputBenchmarker."""

import sys
from pathlib import Path

import httpx
import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.inference_service import (
    InferenceBackendConfig,
    OpenAICompatibleGateway,
    ThroughputBenchmarker,
    create_mock_inference_transport,
)


def test_inference_backend_config_defaults_and_validation() -> None:
    ollama = InferenceBackendConfig.ollama_default()
    assert ollama.backend_type == "ollama"
    assert ollama.supports_continuous_batching is False
    assert ollama.chat_completions_url == "http://localhost:11434/v1/chat/completions"
    assert ollama.models_url == "http://localhost:11434/v1/models"

    vllm = InferenceBackendConfig.vllm_default()
    assert vllm.backend_type == "vllm"
    assert vllm.supports_continuous_batching is True
    assert "PagedAttention" in vllm.kv_cache_strategy
    assert vllm.chat_completions_url == "http://localhost:8000/v1/chat/completions"

    with pytest.raises(ValueError, match="不支持的推理后端类型"):
        InferenceBackendConfig(
            backend_type="unknown",  # type: ignore[arg-type]
            base_url="http://localhost:8000/v1",
            model_name="qwen",
        )

    with pytest.raises(ValueError, match="max_concurrency"):
        InferenceBackendConfig(
            backend_type="vllm",
            base_url="http://localhost:8000/v1",
            model_name="qwen",
            max_concurrency=0,
        )


def test_openai_compatible_gateway_and_backend_switching() -> None:
    ollama_cfg = InferenceBackendConfig.ollama_default()
    vllm_cfg = InferenceBackendConfig.vllm_default()

    with OpenAICompatibleGateway(ollama_cfg, simulated_delay_s=0.0) as gw:
        models_ollama = gw.list_models()
        assert models_ollama == [ollama_cfg.model_name]

        res1 = gw.chat_completions(
            messages=[{"role": "user", "content": "查询今日订单汇总"}],
            max_tokens=64,
        )
        assert res1.backend == "ollama"
        assert res1.model == ollama_cfg.model_name
        assert res1.completion_tokens > 0
        assert res1.ttft_ms > 0
        assert "OLLAMA" in res1.content

        # 业务调用签名完全不变，热切换至 vLLM
        gw.switch_backend(vllm_cfg)
        models_vllm = gw.list_models()
        assert models_vllm == [vllm_cfg.model_name]

        res2 = gw.chat_completions(
            messages=[{"role": "user", "content": "查询今日订单汇总"}],
            max_tokens=64,
        )
        assert res2.backend == "vllm"
        assert res2.model == vllm_cfg.model_name
        assert "VLLM" in res2.content
        assert res2.ttft_ms < res1.ttft_ms


def test_gateway_validation_and_custom_mock_transport_errors() -> None:
    cfg = InferenceBackendConfig.vllm_default()
    transport = create_mock_inference_transport(cfg, simulated_delay_s=0.0)

    with OpenAICompatibleGateway(cfg, transport=transport, use_mock=False) as gw:
        with pytest.raises(ValueError, match="messages 不能为空"):
            gw.chat_completions(messages=[])

    # 验证底层 MockTransport 对未知路由返回 404
    client = httpx.Client(transport=transport)
    resp = client.get("http://localhost:8000/v1/unknown")
    assert resp.status_code == 404
    client.close()


def test_throughput_benchmarker_gateway_and_concurrency_comparison() -> None:
    vllm_cfg = InferenceBackendConfig.vllm_default()
    prompts = [f"工单分析任务 #{i}" for i in range(10)]

    with OpenAICompatibleGateway(vllm_cfg, simulated_delay_s=0.001) as gw:
        report = ThroughputBenchmarker.benchmark_gateway(
            gw, prompts=prompts, concurrency=5, max_tokens=64
        )

    assert report.backend == "vllm"
    assert report.continuous_batching is True
    assert report.total_requests == 10
    assert report.successful_requests == 10
    assert report.failed_requests == 0
    assert report.total_completion_tokens > 0
    assert report.system_tps > 0
    assert report.latency_ms_p95 >= report.latency_ms_avg or report.latency_ms_p95 > 0

    rows = ThroughputBenchmarker.simulate_concurrency_comparison([1, 4, 8, 16, 32])
    assert len(rows) == 5
    # 高并发（32）下 vLLM Continuous Batching 总吞吐显著高于 Ollama 静态槽位排队
    high_conc = rows[-1]
    assert high_conc["concurrency"] == 32
    assert high_conc["vllm_system_tps"] > high_conc["ollama_system_tps"]
    assert high_conc["vllm_ttft_ms"] < high_conc["ollama_ttft_ms"]
    assert high_conc["tps_speedup_vllm_vs_ollama"] > 2.0
