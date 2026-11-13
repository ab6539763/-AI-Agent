"""智枢企业级智能体平台 Day 64 发布打包与部署就绪包 (v1.0.0-day64)。"""

from zhishu_agent.release_packager import (
    DemoRunner,
    DeploymentConfig,
    ValidationResult,
    check_env_vars,
    create_demo_app,
    generate_release_manifest,
    run_preflight_checks,
    validate_compose,
    validate_dockerfile,
)

__version__ = "v1.0.0-day64"

__all__ = [
    "__version__",
    "DeploymentConfig",
    "ValidationResult",
    "validate_dockerfile",
    "validate_compose",
    "check_env_vars",
    "run_preflight_checks",
    "generate_release_manifest",
    "create_demo_app",
    "DemoRunner",
]
