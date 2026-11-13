"""Day 22 单元测试：验证静态前端对话台 HTML 结构、DOM ID、JS fetch 与 UTF-8 编码。"""
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.ui_validator import (
    REQUIRED_DOM_IDS,
    describe_static_serving,
    get_frontend_dir,
    get_index_html_path,
    validate_frontend_file,
    validate_html_content,
)


def test_frontend_files_exist() -> None:
    frontend_dir = get_frontend_dir()
    index_html = get_index_html_path()
    assert frontend_dir.is_dir()
    assert index_html.is_file()
    assert index_html.name == "index.html"


def test_frontend_utf8_and_title() -> None:
    result = validate_frontend_file()
    assert result.has_utf8_meta is True
    assert result.has_viewport_meta is True
    assert "智枢企业级智能体对话台" in result.title


def test_frontend_required_dom_ids() -> None:
    result = validate_frontend_file()
    assert result.missing_ids == []
    for dom_id in REQUIRED_DOM_IDS:
        assert dom_id in result.found_ids


def test_frontend_js_fetch_and_json_payload() -> None:
    html = get_index_html_path().read_text(encoding="utf-8")
    result = validate_html_content(html)
    assert result.has_fetch_call is True
    assert result.is_valid is True
    assert "POST" in html
    assert "application/json" in html
    assert "JSON.stringify" in html


def test_frontend_chat_bubbles_and_responsive_css() -> None:
    html = get_index_html_path().read_text(encoding="utf-8")
    assert ".message.user" in html
    assert ".message.assistant" in html
    assert "@media" in html


def test_validator_detects_missing_elements() -> None:
    broken_html = """<!DOCTYPE html>
    <html>
      <head><title>Broken</title></head>
      <body>
        <div id="chat-messages"></div>
        <script>console.log("no fetch here");</script>
      </body>
    </html>
    """
    result = validate_html_content(broken_html)
    assert result.is_valid is False
    assert result.has_utf8_meta is False
    assert result.has_fetch_call is False
    assert "chat-form" in result.missing_ids
    assert "user-input" in result.missing_ids
    assert "send-btn" in result.missing_ids


def test_describe_static_serving() -> None:
    info = describe_static_serving(port=9090)
    assert Path(info["frontend_dir"]).is_dir()
    assert Path(info["index_html"]).is_file()
    assert info["preview_url"] == "http://127.0.0.1:9090/index.html"
    assert "--directory" in info["serve_command"]
