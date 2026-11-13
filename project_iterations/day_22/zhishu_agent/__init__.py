"""智枢平台 Day 22 包初始化文件 (v0.2.0-day22 · 第二阶段：Frontend Crash Course 静态对话台)"""

from zhishu_agent.ui_validator import (
    REQUIRED_DOM_IDS,
    UIValidationResult,
    describe_static_serving,
    get_day_dir,
    get_frontend_dir,
    get_index_html_path,
    validate_frontend_file,
    validate_html_content,
)

__all__ = [
    "REQUIRED_DOM_IDS",
    "UIValidationResult",
    "describe_static_serving",
    "get_day_dir",
    "get_frontend_dir",
    "get_index_html_path",
    "validate_frontend_file",
    "validate_html_content",
]
