"""智枢企业级 Prompt 模板库与少样本构造器 (v0.2.0-day17)

核心能力：
1. PromptTemplate：基于四要素（instruction / context / user_input / output_format）与分隔符（XML 标签 / 三反引号）构建结构化 Prompt。
2. FewShotPromptBuilder：支持 Zero-shot（0 示例）、One-shot（1 示例）、Few-shot（多示例）动态切换。
3. JSON 输出约束与解析：extract_json_payload() 自动剥离 Markdown 代码围栏并校验 JSON 合法性。
4. 企业级预设模板：翻译（translation）、摘要（summarization）、改写（rewriting）、分类（classification）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

DelimiterStyle = Literal["xml", "backtick"]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _wrap_section(tag: str, content: str, style: DelimiterStyle) -> str:
    """使用 XML 标签或三反引号分隔符包裹单个 Prompt 区块。"""
    cleaned = content.strip()
    if style == "xml":
        return f"<{tag}>\n{cleaned}\n</{tag}>"
    if style == "backtick":
        return f"### {tag.upper()}\n```\n{cleaned}\n```"
    raise ValueError(f"不支持的分隔符风格: {style!r}，仅支持 'xml' 或 'backtick'")


def _sanitize_xml_input(text: str) -> str:
    """对用户输入中的潜在闭合标签做轻量转义，降低 Prompt 注入破坏分隔符边界的风险。"""
    return text.replace("</user_input>", "&lt;/user_input&gt;").replace(
        "<user_input>", "&lt;user_input&gt;"
    )


def extract_json_payload(raw_response: str) -> dict[str, Any] | list[Any]:
    """从大模型原始输出中提取并解析 JSON 载荷。

    支持：
    - 纯 JSON 字符串
    - 包裹在 ```json ... ``` 或 ``` ... ``` 中的 JSON 代码块
    """
    text = raw_response.strip()
    if not text:
        raise ValueError("模型输出为空，无法解析 JSON")

    match = _JSON_FENCE_RE.search(text)
    candidate = match.group(1).strip() if match else text

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: {exc.msg}") from exc

    if not isinstance(parsed, (dict, list)):
        raise ValueError(f"期望 JSON 对象或数组，实际得到 {type(parsed).__name__}")
    return parsed


def _safe_format(template: str, variables: dict[str, Any]) -> str:
    """仅替换 variables 中存在的 {identifier} 占位符，避免 JSON 花括号触发 KeyError。"""
    if not template or not variables:
        return template
    return re.sub(
        r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}",
        lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0),
        template,
    )


@dataclass
class PromptTemplate:
    """结构化四要素 Prompt 模板。

    Attributes:
        instruction: 核心任务指令（必须非空）。
        context: 背景知识、业务规则或参考资料（可选）。
        user_input: 待处理的终端用户输入模板或占位符，如 ``"{text}"``。
        output_format: 输出格式与 JSON Schema 约束说明（可选）。
        delimiter_style: 分隔符风格，支持 ``"xml"`` 与 ``"backtick"``。
        require_json: 是否在输出格式区块附加严格 JSON 约束声明。
    """

    instruction: str
    context: str = ""
    user_input: str = "{text}"
    output_format: str = ""
    delimiter_style: DelimiterStyle = "xml"
    require_json: bool = False

    def __post_init__(self) -> None:
        if not self.instruction or not self.instruction.strip():
            raise ValueError("instruction 不能为空")
        if self.delimiter_style not in ("xml", "backtick"):
            raise ValueError(
                f"不支持的分隔符风格: {self.delimiter_style!r}，仅支持 'xml' 或 'backtick'"
            )

    def render(self, **variables: Any) -> str:
        """渲染四要素结构化 Prompt。

        Args:
            **variables: 用于格式化 ``instruction`` / ``context`` / ``user_input`` / ``output_format`` 的变量。

        Returns:
            使用指定分隔符清晰隔离四要素的完整 Prompt 字符串。
        """
        rendered_instruction = _safe_format(self.instruction, variables)
        rendered_context = _safe_format(self.context, variables) if self.context else ""
        rendered_user_input = _safe_format(self.user_input, variables) if self.user_input else ""
        rendered_output_format = (
            _safe_format(self.output_format, variables) if self.output_format else ""
        )

        if self.delimiter_style == "xml" and rendered_user_input:
            rendered_user_input = _sanitize_xml_input(rendered_user_input)

        if self.require_json:
            json_rule = "请严格仅输出合法的 JSON，不要包含 Markdown 解释或额外前后缀。"
            rendered_output_format = (
                f"{rendered_output_format.strip()}\n{json_rule}".strip()
                if rendered_output_format.strip()
                else json_rule
            )

        sections: list[str] = [
            _wrap_section("instruction", rendered_instruction, self.delimiter_style)
        ]
        if rendered_context.strip():
            sections.append(_wrap_section("context", rendered_context, self.delimiter_style))
        if rendered_user_input.strip():
            sections.append(
                _wrap_section("user_input", rendered_user_input, self.delimiter_style)
            )
        if rendered_output_format.strip():
            sections.append(
                _wrap_section("output_format", rendered_output_format, self.delimiter_style)
            )

        return "\n\n".join(sections)


@dataclass
class FewShotPromptBuilder:
    """Zero-shot / One-shot / Few-shot 少样本 Prompt 构造器。

    - 0 条示例 -> ``zero-shot``
    - 1 条示例 -> ``one-shot``
    - >=2 条示例 -> ``few-shot``
    """

    instruction: str
    examples: list[tuple[str, str]] = field(default_factory=list)
    context: str = ""
    output_format: str = ""
    delimiter_style: DelimiterStyle = "xml"
    require_json: bool = False

    def __post_init__(self) -> None:
        if not self.instruction or not self.instruction.strip():
            raise ValueError("instruction 不能为空")
        if self.delimiter_style not in ("xml", "backtick"):
            raise ValueError(
                f"不支持的分隔符风格: {self.delimiter_style!r}，仅支持 'xml' 或 'backtick'"
            )
        for idx, pair in enumerate(self.examples):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(f"第 {idx} 条示例必须是 (input, output) 二元组")

    @property
    def shot_mode(self) -> str:
        """返回当前少样本模式：zero-shot / one-shot / few-shot。"""
        count = len(self.examples)
        if count == 0:
            return "zero-shot"
        if count == 1:
            return "one-shot"
        return "few-shot"

    def add_example(self, example_input: str, example_output: str) -> FewShotPromptBuilder:
        """追加一条 (输入, 期望输出) 示例，支持链式调用。"""
        self.examples.append((example_input, example_output))
        return self

    def build(self, user_input: str) -> str:
        """结合系统指令、背景、少样本示例与当前用户输入生成最终 Prompt。"""
        if not user_input or not user_input.strip():
            raise ValueError("user_input 不能为空")

        examples_block = ""
        if self.examples:
            lines: list[str] = []
            for idx, (ex_in, ex_out) in enumerate(self.examples, start=1):
                if self.delimiter_style == "xml":
                    lines.append(
                        f"<example index=\"{idx}\">\n"
                        f"  <input>{ex_in.strip()}</input>\n"
                        f"  <output>{ex_out.strip()}</output>\n"
                        f"</example>"
                    )
                else:
                    lines.append(
                        f"示例 {idx} 输入:\n```\n{ex_in.strip()}\n```\n"
                        f"示例 {idx} 输出:\n```\n{ex_out.strip()}\n```"
                    )
            examples_block = "\n".join(lines)

        merged_context_parts = [p.strip() for p in (self.context, examples_block) if p and p.strip()]
        merged_context = "\n\n".join(merged_context_parts)

        template = PromptTemplate(
            instruction=self.instruction,
            context=merged_context,
            user_input="{user_input}",
            output_format=self.output_format,
            delimiter_style=self.delimiter_style,
            require_json=self.require_json,
        )
        return template.render(user_input=user_input)


# ==============================================================================
# 企业级预设 Prompt 模板（翻译、摘要、改写、分类）
# ==============================================================================

TRANSLATION_TEMPLATE = PromptTemplate(
    instruction=(
        "你是一位资深企业技术本地化专家。请将用户输入精准翻译为{target_language}，"
        "保持专业术语准确、语义忠实且符合目标语言商务表达习惯。"
    ),
    context="领域规范：{domain}。专有名词（如 ZhiShu-Agent、API、RAG、SDK）保持英文原样。",
    user_input="{text}",
    output_format=(
        '输出 JSON 对象，包含字段：{"source_language": str, "target_language": str, "translation": str}。'
    ),
    delimiter_style="xml",
    require_json=True,
)

SUMMARIZATION_TEMPLATE = PromptTemplate(
    instruction=(
        "你是一位企业级信息提炼助手。请阅读用户输入文本，提取核心事实与关键结论，"
        "生成不超过 {max_words} 字的高密度摘要。"
    ),
    context="受众角色：{audience}。严禁编造原文未提及的数据或结论。",
    user_input="{text}",
    output_format=(
        '输出 JSON 对象，包含字段：{"summary": str, "key_points": list[str], "word_count": int}。'
    ),
    delimiter_style="xml",
    require_json=True,
)

REWRITING_TEMPLATE = PromptTemplate(
    instruction=(
        "你是一位企业公文与沟通润色专家。请将用户输入文本改写为「{tone}」风格，"
        "修正语病并提升表达清晰度，但不得改变核心事实。"
    ),
    context="使用场景：{scenario}。",
    user_input="{text}",
    output_format=(
        '输出 JSON 对象，包含字段：{"tone": str, "rewritten_text": str, "changes_summary": str}。'
    ),
    delimiter_style="xml",
    require_json=True,
)

CLASSIFICATION_TEMPLATE = PromptTemplate(
    instruction=(
        "你是一位企业智能工单与意图路由分类器。请根据候选标签集合对用户输入进行精确单标签分类，"
        "并给出置信度（0~1）与简短判断依据。"
    ),
    context="候选标签集合：{labels}。若无法归入任何业务标签，请归类为「其他」。",
    user_input="{text}",
    output_format=(
        '输出 JSON 对象，包含字段：{"label": str, "confidence": float, "reason": str}。'
    ),
    delimiter_style="xml",
    require_json=True,
)

ENTERPRISE_PRESETS: dict[str, PromptTemplate] = {
    "translation": TRANSLATION_TEMPLATE,
    "summarization": SUMMARIZATION_TEMPLATE,
    "rewriting": REWRITING_TEMPLATE,
    "classification": CLASSIFICATION_TEMPLATE,
}


def get_preset_template(name: str) -> PromptTemplate:
    """按名称获取企业级预设 PromptTemplate。"""
    key = name.strip().lower()
    if key not in ENTERPRISE_PRESETS:
        available = ", ".join(sorted(ENTERPRISE_PRESETS.keys()))
        raise KeyError(f"未知的预设模板: {name!r}，可用模板: {available}")
    return ENTERPRISE_PRESETS[key]
