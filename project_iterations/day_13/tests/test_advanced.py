"""Day 13 单元测试：覆盖装饰器 (@retry_on_error, @log_latency)、生成器 (stream_tokens)、异步并发 (async_batch_ask) 与 .env 配置加载"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.config import (
    AgentConfig,
    get_env_var,
    load_agent_config,
    load_env_file,
    mask_secret,
)
from zhishu_agent.decorators import log_latency, retry_on_error
from zhishu_agent.streaming import async_batch_ask, stream_tokens


class TestDecorators:
    """测试 @retry_on_error 与 @log_latency 装饰器。"""

    def test_retry_succeeds_after_transient_failures(self) -> None:
        state = {"calls": 0}

        @retry_on_error(max_retries=3, delay=0.01)
        def unstable_api(x: int) -> int:
            """模拟前两次失败、第三次成功的接口。"""
            state["calls"] += 1
            if state["calls"] < 3:
                raise RuntimeError("temporary network error")
            return x * 2

        result = unstable_api(21)
        assert result == 42
        assert state["calls"] == 3
        assert unstable_api.__name__ == "unstable_api"
        assert "模拟前两次失败" in (unstable_api.__doc__ or "")

    def test_retry_exhausted_raises_last_exception(self) -> None:
        state = {"calls": 0}

        @retry_on_error(max_retries=3, delay=0.01)
        def always_fail() -> None:
            state["calls"] += 1
            raise ValueError(f"failed at attempt {state['calls']}")

        with pytest.raises(ValueError, match="failed at attempt 3"):
            always_fail()
        assert state["calls"] == 3

    def test_retry_invalid_params_raise(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            retry_on_error(max_retries=0)
        with pytest.raises(ValueError, match="delay"):
            retry_on_error(delay=-0.1)

    def test_log_latency_returns_value_and_prints_ms(self, capsys: pytest.CaptureFixture[str]) -> None:
        @log_latency
        def compute(a: int, b: int) -> int:
            return a + b

        assert compute(10, 20) == 30
        assert compute.__name__ == "compute"
        captured = capsys.readouterr()
        assert "[Latency] compute 耗时" in captured.out
        assert "ms" in captured.out


class TestStreamingAndAsync:
    """测试 stream_tokens 生成器与 async_batch_ask 异步并发。"""

    def test_stream_tokens_is_generator_and_yields_chunks(self) -> None:
        assert inspect.isgeneratorfunction(stream_tokens)

        gen = stream_tokens("智枢AI平台", chunk_size=2)
        assert iter(gen) is gen
        chunks = list(gen)
        assert chunks == ["智枢", "AI", "平台"]
        assert "".join(chunks) == "智枢AI平台"

    def test_stream_tokens_default_char_by_char_and_empty(self) -> None:
        assert list(stream_tokens("ABC")) == ["A", "B", "C"]
        assert list(stream_tokens("")) == []

    def test_stream_tokens_invalid_args(self) -> None:
        with pytest.raises(TypeError, match="str"):
            list(stream_tokens(123))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="chunk_size"):
            list(stream_tokens("abc", chunk_size=0))

    def test_async_batch_ask_with_asyncio_run(self) -> None:
        prompts = ["问题1", "问题2", "问题3"]
        results = asyncio.run(async_batch_ask(prompts, model_name="qwen-plus", delay=0.01))
        assert len(results) == 3
        assert results == [
            "[qwen-plus] 已异步处理: 问题1",
            "[qwen-plus] 已异步处理: 问题2",
            "[qwen-plus] 已异步处理: 问题3",
        ]

    def test_async_batch_ask_empty_list(self) -> None:
        assert asyncio.run(async_batch_ask([])) == []


class TestEnvConfig:
    """测试纯标准库 .env 解析与安全配置加载。"""

    def test_load_env_file_parses_and_respects_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ZHISHU_EXISTING", "from_os")
        monkeypatch.delenv("ZHISHU_NEW_VAR", raising=False)
        monkeypatch.delenv("ZHISHU_QUOTED", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "# 注释行\n"
            "\n"
            "ZHISHU_EXISTING=from_file\n"
            'ZHISHU_NEW_VAR="hello-world"\n'
            "export ZHISHU_QUOTED='single-quoted'\n",
            encoding="utf-8",
        )

        parsed = load_env_file(env_file, override=False)
        assert parsed == {
            "ZHISHU_EXISTING": "from_file",
            "ZHISHU_NEW_VAR": "hello-world",
            "ZHISHU_QUOTED": "single-quoted",
        }
        # override=False 时保留宿主机环境变量
        assert os.environ["ZHISHU_EXISTING"] == "from_os"
        assert os.environ["ZHISHU_NEW_VAR"] == "hello-world"
        assert os.environ["ZHISHU_QUOTED"] == "single-quoted"

        # override=True 时允许覆盖
        load_env_file(env_file, override=True)
        assert os.environ["ZHISHU_EXISTING"] == "from_file"

    def test_get_env_var_required_and_mask_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ZHISHU_MISSING_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="ZHISHU_MISSING_KEY"):
            get_env_var("ZHISHU_MISSING_KEY", required=True)

        assert mask_secret("sk-1234567890abcd") == "****...abcd"
        assert mask_secret("") == "<EMPTY>"

    def test_load_agent_config_masks_api_key_in_repr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in (
            "ZHISHU_MODEL_NAME",
            "ZHISHU_API_KEY",
            "ZHISHU_API_BASE",
            "ZHISHU_MAX_RETRIES",
            "ZHISHU_TIMEOUT",
        ):
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "ZHISHU_MODEL_NAME=gpt-4o-mini\n"
            "ZHISHU_API_KEY=sk-secret-token-8899\n"
            "ZHISHU_MAX_RETRIES=5\n"
            "ZHISHU_TIMEOUT=15.5\n",
            encoding="utf-8",
        )

        cfg = load_agent_config(env_path=env_file, override=True)
        assert isinstance(cfg, AgentConfig)
        assert cfg.model_name == "gpt-4o-mini"
        assert cfg.api_key == "sk-secret-token-8899"
        assert cfg.max_retries == 5
        assert cfg.request_timeout == 15.5
        # repr 中不能暴露完整密钥
        assert "sk-secret-token-8899" not in repr(cfg)
        assert "****...8899" in repr(cfg)
