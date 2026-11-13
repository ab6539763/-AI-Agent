"""智枢平台 Day 38 代码审查与静态质量审计模块 (v0.3.0-day38).

基于 Python 标准库 ``ast`` 与正则表达式，对迭代目录中的 Python 源码执行零外部依赖的静态质量审计：
1. 文档字符串检查（模块、类、函数/方法 Docstring 覆盖率）
2. 类型注解检查（函数/方法参数与返回值 Type Hints 覆盖率，自动豁免 ``self``/``cls``）
3. 危险动态执行拦截（禁止 ``eval()`` 与 ``exec()``）
4. 硬编码密钥泄漏扫描（检测 ``sk-...`` 等 API Key 模式）
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# 匹配常见 OpenAI / 兼容接口硬编码密钥模式（如 sk-proj-xxx / sk-live-xxx / sk-1234567890abcdef）
_API_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{10,}")

# 扫描项目目录时默认跳过的子目录
_IGNORED_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
    }
)

_DANGEROUS_CALLS = frozenset({"eval", "exec"})


@dataclass(frozen=True)
class AuditIssue:
    """单条静态审计发现的问题记录."""

    file_path: str
    line: int
    severity: str  # "error" | "warning"
    rule: str
    message: str


@dataclass
class FileAuditReport:
    """单个 Python 文件的静态质量审计报告."""

    file_path: str
    total_definitions: int = 0
    docstring_covered: int = 0
    total_functions: int = 0
    type_hint_covered: int = 0
    issues: list[AuditIssue] = field(default_factory=list)
    syntax_error: str | None = None

    @property
    def docstring_coverage(self) -> float:
        """返回文档字符串覆盖率（0.0 ~ 1.0）."""
        if self.total_definitions == 0:
            return 1.0
        return self.docstring_covered / self.total_definitions

    @property
    def type_hint_coverage(self) -> float:
        """返回类型注解覆盖率（0.0 ~ 1.0）."""
        if self.total_functions == 0:
            return 1.0
        return self.type_hint_covered / self.total_functions

    @property
    def error_count(self) -> int:
        """返回阻断级问题（error）数量."""
        return sum(1 for item in self.issues if item.severity == "error")

    @property
    def warning_count(self) -> int:
        """返回告警级问题（warning）数量."""
        return sum(1 for item in self.issues if item.severity == "warning")

    @property
    def passed(self) -> bool:
        """无语法错误且无阻断级（error）问题即视为安全门禁通过."""
        return self.syntax_error is None and self.error_count == 0


@dataclass
class ProjectAuditReport:
    """整个迭代目录的聚合代码审计报告."""

    project_dir: str
    file_reports: list[FileAuditReport] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """返回已扫描的 Python 文件总数."""
        return len(self.file_reports)

    @property
    def total_errors(self) -> int:
        """返回全项目阻断级（error）问题总数."""
        return sum(r.error_count for r in self.file_reports)

    @property
    def total_warnings(self) -> int:
        """返回全项目告警级（warning）问题总数."""
        return sum(r.warning_count for r in self.file_reports)

    @property
    def docstring_coverage(self) -> float:
        """返回全项目聚合文档字符串覆盖率."""
        total_defs = sum(r.total_definitions for r in self.file_reports)
        if total_defs == 0:
            return 1.0
        covered = sum(r.docstring_covered for r in self.file_reports)
        return covered / total_defs

    @property
    def type_hint_coverage(self) -> float:
        """返回全项目聚合类型注解覆盖率."""
        total_funcs = sum(r.total_functions for r in self.file_reports)
        if total_funcs == 0:
            return 1.0
        covered = sum(r.type_hint_covered for r in self.file_reports)
        return covered / total_funcs

    @property
    def passed(self) -> bool:
        """所有文件均无语法错误且无阻断级问题时返回 True."""
        return all(r.passed for r in self.file_reports)

    def format_summary(self) -> str:
        """生成可读性良好的终端/报告摘要文本."""
        status = "✅ PASS" if self.passed else "❌ FAILED"
        lines = [
            f"=== 智枢工程代码质量审计报告 ({status}) ===",
            f"目标目录       : {self.project_dir}",
            f"扫描文件数     : {self.total_files}",
            f"Docstring 覆盖率: {self.docstring_coverage:.1%}",
            f"Type Hint 覆盖率: {self.type_hint_coverage:.1%}",
            f"阻断问题 (Error) : {self.total_errors}",
            f"质量告警 (Warn)  : {self.total_warnings}",
        ]
        all_issues = [issue for r in self.file_reports for issue in r.issues]
        if all_issues:
            lines.append("--- 问题明细 ---")
            for issue in all_issues[:20]:
                lines.append(
                    f"[{issue.severity.upper()}] {issue.file_path}:{issue.line} "
                    f"({issue.rule}) {issue.message}"
                )
            if len(all_issues) > 20:
                lines.append(f"... 其余 {len(all_issues) - 20} 条问题已省略")
        return "\n".join(lines)


def _has_complete_type_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, list[str]]:
    """检查函数或方法的参数（豁免 self/cls）与返回值是否均具备类型注解."""
    missing: list[str] = []
    all_args: list[ast.arg] = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        all_args.append(node.args.vararg)
    if node.args.kwarg is not None:
        all_args.append(node.args.kwarg)

    for idx, arg in enumerate(all_args):
        if idx == 0 and arg.arg in {"self", "cls"}:
            continue
        if arg.annotation is None:
            missing.append(f"参数 '{arg.arg}'")

    if node.returns is None:
        missing.append("返回值")

    return len(missing) == 0, missing


def _iter_python_files(root: Path) -> Iterable[Path]:
    """递归遍历目录下的 Python 源文件，跳过缓存与虚拟环境目录."""
    for path in sorted(root.rglob("*.py")):
        if any(part in _IGNORED_DIRS for part in path.parts):
            continue
        yield path


def audit_python_file(file_path: str | Path) -> FileAuditReport:
    """对单个 Python 文件执行 AST 静态质量审计.

    Args:
        file_path: 目标 ``.py`` 文件路径。

    Returns:
        包含覆盖率指标与问题明细的 ``FileAuditReport``。
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"待审计文件不存在: {path}")

    source = path.read_text(encoding="utf-8")
    report = FileAuditReport(file_path=str(path))

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        err_msg = f"语法解析失败: {exc.msg} (line {exc.lineno})"
        report.syntax_error = err_msg
        report.issues.append(
            AuditIssue(
                file_path=str(path),
                line=exc.lineno or 1,
                severity="error",
                rule="syntax-error",
                message=err_msg,
            )
        )
        return report

    # 1. 模块级 Docstring 检查
    report.total_definitions += 1
    if ast.get_docstring(tree) is not None:
        report.docstring_covered += 1
    else:
        report.issues.append(
            AuditIssue(
                file_path=str(path),
                line=1,
                severity="warning",
                rule="missing-module-docstring",
                message="模块缺少顶部文档字符串 (Docstring)",
            )
        )

    # 2. 遍历 AST 检查类、函数、危险调用与硬编码密钥
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            report.total_definitions += 1
            if ast.get_docstring(node) is not None:
                report.docstring_covered += 1
            else:
                report.issues.append(
                    AuditIssue(
                        file_path=str(path),
                        line=node.lineno,
                        severity="warning",
                        rule="missing-class-docstring",
                        message=f"类 '{node.name}' 缺少文档字符串",
                    )
                )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            report.total_definitions += 1
            if ast.get_docstring(node) is not None:
                report.docstring_covered += 1
            else:
                report.issues.append(
                    AuditIssue(
                        file_path=str(path),
                        line=node.lineno,
                        severity="warning",
                        rule="missing-function-docstring",
                        message=f"函数 '{node.name}' 缺少文档字符串",
                    )
                )

            report.total_functions += 1
            has_hints, missing_parts = _has_complete_type_hints(node)
            if has_hints:
                report.type_hint_covered += 1
            else:
                report.issues.append(
                    AuditIssue(
                        file_path=str(path),
                        line=node.lineno,
                        severity="warning",
                        rule="missing-type-hints",
                        message=f"函数 '{node.name}' 缺少类型注解: {', '.join(missing_parts)}",
                    )
                )

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_CALLS:
                report.issues.append(
                    AuditIssue(
                        file_path=str(path),
                        line=node.lineno,
                        severity="error",
                        rule="forbidden-dynamic-exec",
                        message=f"禁止调用危险内置函数 '{node.func.id}()'",
                    )
                )

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = _API_KEY_PATTERN.search(node.value)
            if match:
                masked = match.group(0)[:7] + "***"
                report.issues.append(
                    AuditIssue(
                        file_path=str(path),
                        line=node.lineno,
                        severity="error",
                        rule="hardcoded-api-key",
                        message=f"检测到疑似硬编码 API Key ({masked})，请改用环境变量注入",
                    )
                )

    report.issues.sort(key=lambda item: (item.line, item.rule))
    return report


def audit_project_dir(project_dir: str | Path) -> ProjectAuditReport:
    """对整个迭代目录中的所有 Python 文件执行批量静态质量审计.

    Args:
        project_dir: 待审计的项目或迭代目录路径。

    Returns:
        聚合全项目指标与各文件明细的 ``ProjectAuditReport``。
    """
    root = Path(project_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"待审计目录不存在: {root}")

    project_report = ProjectAuditReport(project_dir=str(root))
    for py_file in _iter_python_files(root):
        project_report.file_reports.append(audit_python_file(py_file))
    return project_report
