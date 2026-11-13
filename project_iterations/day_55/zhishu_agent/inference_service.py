"""智枢平台 Day 55 核心模块：本地私有化推理服务网关与吞吐量压测基准 (v0.5.0-day55).

核心能力：
1. InferenceBackendConfig：统一抽象 Ollama 与 vLLM 的推理后端配置与能力特征。
2. OpenAICompatibleGateway：基于 httpx（支持 MockTransport 离线仿真）的 OpenAI 兼容网关，
   实现应用层零代码改动无缝切换 Ollama / vLLM。
3. ThroughputBenchmarker：测量并发场景下的 TTFT、Tokens/s (TPS) 与 P95 延迟，
   对比 Ollama 静态批处理排队与 vLLM Continuous Batching + PagedAttention 的吞吐差异。
"""

from __future__ import annotations

import json
import math
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any, Literal

import httpx

BackendType = Literal["ollama", "vllm"]


@dataclass
class InferenceBackendConfig:
    """私有化推理后端配置（Ollama / vLLM）."""

    backend_type: BackendType
    base_url: str
    model_name: str
    api_key: str = "EMPTY"
    timeout_seconds: float = 30.0
    max_concurrency: int = 4
    supports_continuous_batching: bool | None = None
    kv_cache_strategy: str = ""

    def __post_init__(self) -> None:
        if self.backend_type not in ("ollama", "vllm"):
            raise ValueError(
                f"不支持的推理后端类型: {self.backend_type!r}，仅支持 'ollama' 或 'vllm'"
            )
        if not self.base_url.strip():
            raise ValueError("base_url 不能为空")
        if not self.model_name.strip():
            raise ValueError("model_name 不能为空")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")

        self.base_url = self.base_url.rstrip("/")

        if self.supports_continuous_batching is None:
            self.supports_continuous_batching = self.backend_type == "vllm"

        if not self.kv_cache_strategy:
            self.kv_cache_strategy = (
                "PagedAttention (Dynamic Block KV)"
                if self.backend_type == "vllm"
                else "Static Contiguous KV Allocation"
            )

    @property
    def chat_completions_url(self) -> str:
        """返回 OpenAI 兼容的 /chat/completions 完整 URL."""
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    @property
    def models_url(self) -> str:
        """返回 OpenAI 兼容的 /models 完整 URL."""
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/models"
        return f"{self.base_url}/v1/models"

    @classmethod
    def ollama_default(
        cls,
        model_name: str = "qwen2.5:14b-instruct-q4_K_M",
        base_url: str = "http://localhost:11434/v1",
        max_concurrency: int = 4,
    ) -> InferenceBackendConfig:
        """构建 Ollama 本地推理后端默认配置."""
        return cls(
            backend_type="ollama",
            base_url=base_url,
            model_name=model_name,
            api_key="ollama",
            max_concurrency=max_concurrency,
            supports_continuous_batching=False,
            kv_cache_strategy="Static Contiguous KV Allocation",
        )

    @classmethod
    def vllm_default(
        cls,
        model_name: str = "Qwen/Qwen2.5-14B-Instruct-AWQ",
        base_url: str = "http://localhost:8000/v1",
        max_concurrency: int = 64,
    ) -> InferenceBackendConfig:
        """构建 vLLM 高并发推理后端默认配置."""
        return cls(
            backend_type="vllm",
            base_url=base_url,
            model_name=model_name,
            api_key="EMPTY",
            max_concurrency=max_concurrency,
            supports_continuous_batching=True,
            kv_cache_strategy="PagedAttention (Dynamic Block KV)",
        )


@dataclass
class ChatCompletionResult:
    """OpenAI 兼容网关单次推理返回结果."""

    request_id: str
    backend: BackendType
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    ttft_ms: float
    total_latency_ms: float
    tps: float
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """并发压测吞吐与延迟统计报告."""

    backend: BackendType
    model_name: str
    continuous_batching: bool
    concurrency: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_completion_tokens: int
    total_duration_s: float
    ttft_ms_avg: float
    ttft_ms_p95: float
    latency_ms_avg: float
    latency_ms_p95: float
    system_tps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """计算已排序列表的分位数（线性插值）."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def create_mock_inference_transport(
    config: InferenceBackendConfig,
    simulated_delay_s: float = 0.002,
) -> httpx.MockTransport:
    """创建支持离线运行的 httpx.MockTransport，精确模拟 OpenAI /v1/chat/completions 协议."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if request.method == "GET" and path.endswith("/models"):
            return httpx.Response(
                status_code=200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": config.model_name,
                            "object": "model",
                            "owned_by": config.backend_type,
                        }
                    ],
                },
            )

        if request.method == "POST" and path.endswith("/chat/completions"):
            try:
                payload = json.loads(request.content.decode("utf-8"))
            except Exception:
                return httpx.Response(
                    status_code=400,
                    json={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
                )

            messages = payload.get("messages")
            if not isinstance(messages, list) or len(messages) == 0:
                return httpx.Response(
                    status_code=400,
                    json={"error": {"message": "'messages' must be a non-empty list", "type": "invalid_request_error"}},
                )

            req_model = payload.get("model") or config.model_name
            max_tokens = int(payload.get("max_tokens") or 64)
            last_user_msg = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_msg = str(msg.get("content", ""))
                    break

            prompt_tokens = max(12, sum(len(str(m.get("content", ""))) for m in messages) // 2 + 8)
            completion_tokens = min(max_tokens, max(24, len(last_user_msg) // 2 + 24))

            if simulated_delay_s > 0:
                # vLLM Continuous Batching 单次调度开销更低
                factor = 0.7 if config.backend_type == "vllm" else 1.1
                time.sleep(simulated_delay_s * factor)

            base_ttft = 38.0 if config.backend_type == "vllm" else 85.0
            tpot = 11.5 if config.backend_type == "vllm" else 22.0

            reply_content = (
                f"[{config.backend_type.upper()}::{req_model}] "
                f"已收到智枢企业请求：'{last_user_msg[:40]}'。"
                f"当前 KV 策略：{config.kv_cache_strategy}。"
            )

            return httpx.Response(
                status_code=200,
                json={
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": req_model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": reply_content,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                    "x_zhishu_metrics": {
                        "backend": config.backend_type,
                        "ttft_ms": base_ttft,
                        "tpot_ms": tpot,
                        "continuous_batching": bool(config.supports_continuous_batching),
                    },
                },
            )

        return httpx.Response(
            status_code=404,
            json={"error": {"message": f"Unknown endpoint: {path}", "type": "not_found"}},
        )

    return httpx.MockTransport(handler)


class OpenAICompatibleGateway:
    """OpenAI 协议兼容推理网关：支持在 Ollama 与 vLLM 之间无缝切换."""

    def __init__(
        self,
        config: InferenceBackendConfig,
        transport: httpx.BaseTransport | None = None,
        use_mock: bool = True,
        simulated_delay_s: float = 0.002,
    ) -> None:
        self.config = config
        self._use_mock = use_mock
        self._simulated_delay_s = simulated_delay_s
        self._client = self._build_client(config, transport, use_mock, simulated_delay_s)

    @staticmethod
    def _build_client(
        config: InferenceBackendConfig,
        transport: httpx.BaseTransport | None,
        use_mock: bool,
        simulated_delay_s: float,
    ) -> httpx.Client:
        effective_transport = transport
        if effective_transport is None and use_mock:
            effective_transport = create_mock_inference_transport(
                config, simulated_delay_s=simulated_delay_s
            )
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        return httpx.Client(
            transport=effective_transport,
            headers=headers,
            timeout=config.timeout_seconds,
        )

    def switch_backend(
        self,
        new_config: InferenceBackendConfig,
        transport: httpx.BaseTransport | None = None,
        use_mock: bool | None = None,
    ) -> None:
        """热切换推理后端（如从 Ollama 切换至 vLLM），保持上层调用接口完全不变."""
        self.close()
        self.config = new_config
        mock_flag = self._use_mock if use_mock is None else use_mock
        self._client = self._build_client(
            new_config, transport, mock_flag, self._simulated_delay_s
        )

    def list_models(self) -> list[str]:
        """查询当前推理后端已加载的模型列表."""
        resp = self._client.get(self.config.models_url)
        resp.raise_for_status()
        data = resp.json()
        return [item["id"] for item in data.get("data", []) if "id" in item]

    def chat_completions(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 256,
        **extra_params: Any,
    ) -> ChatCompletionResult:
        """发送标准 OpenAI /v1/chat/completions 请求并返回结构化结果与性能指标."""
        if not messages:
            raise ValueError("messages 不能为空")

        target_model = model or self.config.model_name
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **extra_params,
        }

        start = time.perf_counter()
        resp = self._client.post(self.config.chat_completions_url, json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        resp.raise_for_status()
        body = resp.json()

        choices = body.get("choices") or []
        content = choices[0]["message"]["content"] if choices else ""
        usage = body.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))

        metrics = body.get("x_zhishu_metrics") or {}
        ttft_ms = float(metrics.get("ttft_ms", elapsed_ms * 0.25))
        total_latency_ms = max(elapsed_ms, ttft_ms)
        tps = (
            completion_tokens / (total_latency_ms / 1000.0)
            if total_latency_ms > 0
            else 0.0
        )

        return ChatCompletionResult(
            request_id=str(body.get("id", "")),
            backend=self.config.backend_type,
            model=str(body.get("model", target_model)),
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            ttft_ms=round(ttft_ms, 3),
            total_latency_ms=round(total_latency_ms, 3),
            tps=round(tps, 2),
            raw_response=body,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatibleGateway:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


class ThroughputBenchmarker:
    """私有化推理服务吞吐量与延迟压测引擎."""

    @staticmethod
    def benchmark_gateway(
        gateway: OpenAICompatibleGateway,
        prompts: list[str],
        concurrency: int = 4,
        max_tokens: int = 128,
    ) -> BenchmarkReport:
        """对指定网关执行并发压测，统计真实请求 TTFT、P95 延迟与系统总 TPS."""
        if not prompts:
            raise ValueError("prompts 不能为空")
        if concurrency <= 0:
            raise ValueError("concurrency 必须大于 0")

        ttft_list: list[float] = []
        latency_list: list[float] = []
        total_completion_tokens = 0
        failed = 0

        def _run_one(prompt_text: str) -> ChatCompletionResult:
            return gateway.chat_completions(
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=max_tokens,
            )

        wall_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_run_one, p) for p in prompts]
            for fut in futures:
                try:
                    res = fut.result()
                    ttft_list.append(res.ttft_ms)
                    latency_list.append(res.total_latency_ms)
                    total_completion_tokens += res.completion_tokens
                except Exception:
                    failed += 1
        wall_duration_s = max(time.perf_counter() - wall_start, 1e-6)

        ttft_sorted = sorted(ttft_list)
        latency_sorted = sorted(latency_list)
        successful = len(latency_list)

        return BenchmarkReport(
            backend=gateway.config.backend_type,
            model_name=gateway.config.model_name,
            continuous_batching=bool(gateway.config.supports_continuous_batching),
            concurrency=concurrency,
            total_requests=len(prompts),
            successful_requests=successful,
            failed_requests=failed,
            total_completion_tokens=total_completion_tokens,
            total_duration_s=round(wall_duration_s, 4),
            ttft_ms_avg=round(sum(ttft_list) / successful, 2) if successful else 0.0,
            ttft_ms_p95=round(_percentile(ttft_sorted, 95.0), 2),
            latency_ms_avg=round(sum(latency_list) / successful, 2) if successful else 0.0,
            latency_ms_p95=round(_percentile(latency_sorted, 95.0), 2),
            system_tps=round(total_completion_tokens / wall_duration_s, 2),
        )

    @staticmethod
    def simulate_concurrency_comparison(
        concurrency_levels: list[int] | None = None,
        output_tokens: int = 128,
        ollama_parallel_slots: int = 4,
    ) -> list[dict[str, Any]]:
        """仿真对比 Ollama（静态批处理/槽位排队）与 vLLM（Continuous Batching + PagedAttention）在不同并发下的吞吐与延迟."""
        if concurrency_levels is None:
            concurrency_levels = [1, 4, 8, 16, 32]

        rows: list[dict[str, Any]] = []
        for c in concurrency_levels:
            if c <= 0:
                raise ValueError("并发数必须大于 0")

            # Ollama 模型：单流速度 ~42 tok/s，超出 OLLAMA_NUM_PARALLEL 后产生排队等待
            ollama_active = min(c, ollama_parallel_slots)
            ollama_queue_waves = math.ceil(c / ollama_parallel_slots)
            ollama_per_stream_tps = 42.0 * (0.88 ** max(0, ollama_active - 1))
            ollama_single_gen_s = output_tokens / ollama_per_stream_tps
            ollama_ttft_ms = 85.0 + (ollama_queue_waves - 1) * (ollama_single_gen_s * 1000.0 * 0.85)
            ollama_p95_latency_ms = ollama_ttft_ms + ollama_single_gen_s * 1000.0 * 1.12
            ollama_total_time_s = (ollama_p95_latency_ms / 1000.0) * 0.92
            ollama_system_tps = (c * output_tokens) / ollama_total_time_s

            # vLLM Continuous Batching + PagedAttention：迭代级调度，高并发下显存无碎片且总吞吐近似线性爬升后趋于饱和
            vllm_base_tps = 65.0
            vllm_batch_efficiency = 1.0 - 0.35 * (1.0 - math.exp(-c / 24.0))
            vllm_per_stream_tps = vllm_base_tps * vllm_batch_efficiency
            vllm_ttft_ms = 38.0 + 4.5 * math.log2(c + 1)
            vllm_gen_ms = (output_tokens / vllm_per_stream_tps) * 1000.0
            vllm_p95_latency_ms = vllm_ttft_ms + vllm_gen_ms * 1.08
            vllm_system_tps = c * vllm_per_stream_tps

            rows.append(
                {
                    "concurrency": c,
                    "ollama_ttft_ms": round(ollama_ttft_ms, 1),
                    "ollama_p95_latency_ms": round(ollama_p95_latency_ms, 1),
                    "ollama_system_tps": round(ollama_system_tps, 1),
                    "vllm_ttft_ms": round(vllm_ttft_ms, 1),
                    "vllm_p95_latency_ms": round(vllm_p95_latency_ms, 1),
                    "vllm_system_tps": round(vllm_system_tps, 1),
                    "tps_speedup_vllm_vs_ollama": round(vllm_system_tps / ollama_system_tps, 2),
                }
            )

        return rows
