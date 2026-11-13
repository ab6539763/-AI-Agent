"""Day 38 单元测试：AST 代码审查与静态质量审计模块验证 (v0.3.0-day38)."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import audit_project_dir, audit_python_file


def test_clean_file_passes_audit(tmp_path: Path) -> None:
    """合规的 Python 文件应实现 100% Docstring 与 Type Hint 覆盖且无任何告警或错误."""
    clean_file = tmp_path / "clean_module.py"
    clean_file.write_text(
        '''"""合规模块文档."""


class AgentHelper:
    """智能体辅助类."""

    def greet(self, name: str) -> str:
        """返回问候语."""
        return f"Hello, {name}"


def add(a: int, b: int) -> int:
    """两数相加."""
    return a + b
''',
        encoding="utf-8",
    )

    report = audit_python_file(clean_file)
    assert report.passed is True
    assert report.docstring_coverage == 1.0
    assert report.type_hint_coverage == 1.0
    assert report.error_count == 0
    assert report.warning_count == 0


def test_missing_docstrings_and_type_hints(tmp_path: Path) -> None:
    """缺少文档字符串或类型注解时应准确统计覆盖率并生成 warning 告警."""
    target = tmp_path / "incomplete.py"
    target.write_text(
        """class BareClass:
    def compute(self, x):
        return x * 2
""",
        encoding="utf-8",
    )

    report = audit_python_file(target)
    assert report.passed is True  # warning 不阻断安全门禁
    assert report.docstring_coverage == 0.0
    assert report.type_hint_coverage == 0.0
    rules = {issue.rule for issue in report.issues}
    assert "missing-module-docstring" in rules
    assert "missing-class-docstring" in rules
    assert "missing-function-docstring" in rules
    assert "missing-type-hints" in rules


def test_detects_eval_exec_and_hardcoded_api_key(tmp_path: Path) -> None:
    """检测到 eval()/exec() 或硬编码 sk-... 密钥时必须触发 error 阻断."""
    unsafe_file = tmp_path / "unsafe.py"
    unsafe_file.write_text(
        '''"""存在安全风险的示例模块."""

OPENAI_KEY = "sk-proj-1234567890abcdef1234"


def run_expr(expr: str) -> object:
    """危险动态执行."""
    return eval(expr)


def run_stmt(code: str) -> None:
    """危险语句执行."""
    exec(code)
''',
        encoding="utf-8",
    )

    report = audit_python_file(unsafe_file)
    assert report.passed is False
    assert report.error_count == 3
    rules = [issue.rule for issue in report.issues]
    assert rules.count("forbidden-dynamic-exec") == 2
    assert rules.count("hardcoded-api-key") == 1


def test_syntax_error_is_handled_gracefully(tmp_path: Path) -> None:
    """遇到语法错误文件时应记录 syntax-error 而不崩溃."""
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = audit_python_file(broken)
    assert report.passed is False
    assert report.syntax_error is not None
    assert report.error_count == 1
    assert report.issues[0].rule == "syntax-error"


def test_audit_project_dir_aggregates_and_ignores_pycache(tmp_path: Path) -> None:
    """audit_project_dir 应递归聚合子目录结果并自动跳过 __pycache__."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""包初始化."""\n', encoding="utf-8")
    (pkg / "service.py").write_text(
        '''"""服务模块."""


def ping() -> str:
    """健康检查."""
    return "pong"
''',
        encoding="utf-8",
    )

    cache_dir = pkg / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "bad_cached.py").write_text("eval('1+1')\n", encoding="utf-8")

    proj_report = audit_project_dir(tmp_path)
    assert proj_report.total_files == 2
    assert proj_report.passed is True
    assert proj_report.total_errors == 0
    assert proj_report.docstring_coverage == 1.0
    assert proj_report.type_hint_coverage == 1.0
    summary = proj_report.format_summary()
    assert "PASS" in summary


def test_missing_file_or_dir_raises(tmp_path: Path) -> None:
    """传入不存在的文件或目录应抛出明确的异常."""
    with pytest.raises(FileNotFoundError):
        audit_python_file(tmp_path / "not_exists.py")
    with pytest.raises(NotADirectoryError):
        audit_project_dir(tmp_path / "missing_dir")
