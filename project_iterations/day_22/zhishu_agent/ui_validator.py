"""智枢平台 Day 22 前端静态页面校验与静态资源路径辅助模块 (v0.2.0-day22)"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import re

REQUIRED_DOM_IDS: tuple[str, ...] = (
    "chat-messages",
    "chat-form",
    "user-input",
    "send-btn",
)


@dataclass
class UIValidationResult:
    """前端 HTML 结构与交互脚本校验结果。"""

    is_valid: bool
    title: str
    has_utf8_meta: bool
    has_viewport_meta: bool
    has_fetch_call: bool
    found_ids: list[str] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _FrontendHTMLParser(HTMLParser):
    """基于 Python 标准库的轻量级 HTML 结构解析器。"""

    def __init__(self) -> None:
        super().__init__()
        self.has_utf8_meta: bool = False
        self.has_viewport_meta: bool = False
        self.ids: list[str] = []
        self.classes: set[str] = set()
        self.title: str = ""
        self._in_title: bool = False
        self._in_script: bool = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if "id" in attr_map and attr_map["id"]:
            self.ids.append(attr_map["id"])

        if "class" in attr_map and attr_map["class"]:
            for cls_name in attr_map["class"].split():
                self.classes.add(cls_name)

        if tag_lower == "meta":
            charset = attr_map.get("charset", "").strip().lower()
            http_equiv = attr_map.get("http-equiv", "").strip().lower()
            content = attr_map.get("content", "").strip().lower()
            name = attr_map.get("name", "").strip().lower()

            if charset == "utf-8" or (
                http_equiv == "content-type" and "utf-8" in content
            ):
                self.has_utf8_meta = True

            if name == "viewport" and content:
                self.has_viewport_meta = True

        elif tag_lower == "title":
            self._in_title = True

        elif tag_lower == "script":
            self._in_script = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_script:
            self.scripts.append(data)


def get_day_dir(base_dir: Path | None = None) -> Path:
    """获取 Day 22 迭代根目录路径。"""
    if base_dir is not None:
        return Path(base_dir).resolve()
    return Path(__file__).resolve().parent.parent


def get_frontend_dir(base_dir: Path | None = None) -> Path:
    """获取静态前端目录 `frontend/` 的绝对路径。"""
    frontend_dir = get_day_dir(base_dir) / "frontend"
    if not frontend_dir.is_dir():
        raise FileNotFoundError(f"未找到前端静态目录: {frontend_dir}")
    return frontend_dir


def get_index_html_path(base_dir: Path | None = None) -> Path:
    """获取 `frontend/index.html` 的绝对路径。"""
    index_path = get_frontend_dir(base_dir) / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"未找到前端入口页面: {index_path}")
    return index_path


def validate_html_content(
    html_content: str,
    required_ids: tuple[str, ...] = REQUIRED_DOM_IDS,
) -> UIValidationResult:
    """校验 HTML 字符串是否满足 UTF-8、核心 DOM ID 与 JS fetch() 规范。"""
    parser = _FrontendHTMLParser()
    parser.feed(html_content)
    parser.close()

    script_text = "\n".join(parser.scripts)
    has_fetch_call = bool(re.search(r"\bfetch\s*\(", script_text))

    found_id_set = set(parser.ids)
    missing_ids = [dom_id for dom_id in required_ids if dom_id not in found_id_set]

    errors: list[str] = []
    if not parser.has_utf8_meta:
        errors.append("缺少 <meta charset=\"UTF-8\"> 声明")
    if not parser.has_viewport_meta:
        errors.append("缺少响应式 <meta name=\"viewport\"> 声明")
    if missing_ids:
        errors.append(f"缺少必要 DOM ID: {', '.join(missing_ids)}")
    if not has_fetch_call:
        errors.append("脚本中未检测到 JS fetch() API 调用")

    return UIValidationResult(
        is_valid=len(errors) == 0,
        title=parser.title.strip(),
        has_utf8_meta=parser.has_utf8_meta,
        has_viewport_meta=parser.has_viewport_meta,
        has_fetch_call=has_fetch_call,
        found_ids=parser.ids,
        missing_ids=missing_ids,
        errors=errors,
    )


def validate_frontend_file(
    html_path: Path | None = None,
    required_ids: tuple[str, ...] = REQUIRED_DOM_IDS,
) -> UIValidationResult:
    """读取并校验指定前端 HTML 文件（默认为 `frontend/index.html`）。"""
    target = Path(html_path) if html_path is not None else get_index_html_path()
    content = target.read_text(encoding="utf-8")
    return validate_html_content(content, required_ids=required_ids)


def describe_static_serving(port: int = 8080, base_dir: Path | None = None) -> dict[str, str]:
    """返回静态前端目录路径与本地预览命令信息（不阻塞进程）。"""
    frontend_dir = get_frontend_dir(base_dir)
    index_path = get_index_html_path(base_dir)
    return {
        "frontend_dir": str(frontend_dir),
        "index_html": str(index_path),
        "preview_url": f"http://127.0.0.1:{port}/index.html",
        "serve_command": f"python -m http.server {port} --directory {frontend_dir}",
    }
