"""Day 13 环境变量与安全配置加载模块（纯标准库实现，不依赖 python-dotenv）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _strip_quotes(value: str) -> str:
    """去除环境变量值首尾成对的单引号或双引号。"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def load_env_file(env_path: str | Path = ".env", override: bool = False) -> dict[str, str]:
    """安全解析 .env 文件并注入 os.environ（纯标准库实现）。

    规则：
    - 忽略空行与 `#` 开头的注释行；
    - 支持可选的 `export KEY=VALUE` 前缀；
    - 自动去除值首尾成对引号；
    - 默认 `override=False`，不覆盖宿主机/CI 中已存在的环境变量。

    Args:
        env_path: `.env` 文件路径。
        override: 是否覆盖 `os.environ` 中已有的同名变量。

    Returns:
        本次成功解析的键值对字典。
    """
    path = Path(env_path)
    if not path.exists():
        return {}

    parsed: dict[str, str] = {}
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ValueError(f".env 第 {line_no} 行格式非法（缺少 '='）: {raw_line!r}")

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f".env 第 {line_no} 行缺少变量名: {raw_line!r}")

        value = _strip_quotes(raw_value.strip())
        parsed[key] = value
        if override or key not in os.environ:
            os.environ[key] = value

    return parsed


def get_env_var(
    key: str,
    default: str | None = None,
    required: bool = False,
) -> str:
    """安全读取环境变量，支持默认值与必填校验。"""
    value = os.getenv(key)
    if value is None or not value.strip():
        if required and default is None:
            raise EnvironmentError(f"缺少必要的环境变量: {key}")
        return "" if default is None else default
    return value.strip()


def mask_secret(secret: str, visible_tail: int = 4) -> str:
    """对敏感密钥进行脱敏展示，防止 API Key 泄露到日志中。"""
    if not secret:
        return "<EMPTY>"
    if len(secret) <= visible_tail:
        return "*" * len(secret)
    return f"{'*' * 4}...{secret[-visible_tail:]}"


@dataclass(frozen=True)
class AgentConfig:
    """智枢平台运行时配置对象。"""

    model_name: str
    api_key: str
    api_base: str
    max_retries: int
    request_timeout: float

    def __repr__(self) -> str:
        # 覆盖默认 repr，确保打印配置对象时不会暴露明文 api_key
        return (
            f"AgentConfig(model_name={self.model_name!r}, "
            f"api_key={mask_secret(self.api_key)!r}, "
            f"api_base={self.api_base!r}, "
            f"max_retries={self.max_retries}, "
            f"request_timeout={self.request_timeout})"
        )


def load_agent_config(env_path: str | Path | None = None, override: bool = False) -> AgentConfig:
    """从 .env 文件（可选）与 os.environ 加载 AgentConfig。"""
    if env_path is not None:
        load_env_file(env_path=env_path, override=override)

    return AgentConfig(
        model_name=get_env_var("ZHISHU_MODEL_NAME", default="deepseek-chat"),
        api_key=get_env_var("ZHISHU_API_KEY", default="sk-demo-offline-0000"),
        api_base=get_env_var("ZHISHU_API_BASE", default="https://api.deepseek.com/v1"),
        max_retries=int(get_env_var("ZHISHU_MAX_RETRIES", default="3")),
        request_timeout=float(get_env_var("ZHISHU_TIMEOUT", default="30.0")),
    )
