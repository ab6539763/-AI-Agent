"""Day 26：LCEL 表达式语言与链式编排核心实现 (v0.3.0-day26)。

实现与 LangChain LCEL 核心语义一致的可组合管道引擎：
- Runnable 抽象基类（支持 `|` 运算符重载：`__or__` / `__ror__`、`invoke`、`batch`、`stream`）
- RunnableSequence：顺序组合多个 Runnable
- RunnableLambda：将普通函数 / lambda 包装为 Runnable
- RunnablePassthrough：原样透传输入，支持 `.assign(...)` 动态追加字段
- RunnableParallel：并行分支映射（支持字典自动强制转换）
- PromptTemplate & MockChatModel：离线可运行的 Prompt 与大模型模拟节点
- OutputParsers：StrOutputParser、JsonOutputParser、PydanticOutputParser
- 3 阶段「翻译 -> 润色 -> 摘要」LCEL 链工厂函数
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel, Field

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ModelT = TypeVar("ModelT", bound=BaseModel)


def coerce_to_runnable(thing: Union[Runnable[Any, Any], Callable[[Any], Any], Mapping[str, Any]]) -> Runnable[Any, Any]:
    """将普通可调用对象或字典自动转换为 Runnable，支撑 LCEL 的隐式组合能力。"""
    if isinstance(thing, Runnable):
        return thing
    if isinstance(thing, Mapping):
        return RunnableParallel(thing)
    if callable(thing):
        return RunnableLambda(thing)
    raise TypeError(f"无法将类型 {type(thing).__name__} 转换为 Runnable")


class Runnable(ABC, Generic[InputT, OutputT]):
    """LCEL 可运行组件抽象基类，支持 `|` 管道符拼接与 invoke/batch/stream 调用。"""

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def invoke(self, input_data: InputT, config: Optional[Dict[str, Any]] = None) -> OutputT:
        """同步执行单条输入。"""

    def batch(
        self,
        inputs: Sequence[InputT],
        config: Optional[Dict[str, Any]] = None,
    ) -> List[OutputT]:
        """批量执行多条输入。"""
        return [self.invoke(item, config=config) for item in inputs]

    def stream(
        self,
        input_data: InputT,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[OutputT]:
        """流式执行单条输入（默认逐项产出 invoke 结果，子类可覆盖为增量产出）。"""
        yield self.invoke(input_data, config=config)

    def __or__(
        self,
        other: Union[Runnable[OutputT, Any], Callable[[OutputT], Any], Mapping[str, Any]],
    ) -> RunnableSequence:
        """重载 `|` 运算符：self | other -> RunnableSequence。"""
        return RunnableSequence(self, coerce_to_runnable(other))

    def __ror__(
        self,
        other: Union[Runnable[Any, InputT], Callable[[Any], InputT], Mapping[str, Any]],
    ) -> RunnableSequence:
        """重载反向 `|` 运算符：callable_or_dict | self -> RunnableSequence。"""
        return RunnableSequence(coerce_to_runnable(other), self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


class RunnableSequence(Runnable[Any, Any]):
    """顺序组合多个 Runnable 的管道序列（A | B | C）。"""

    def __init__(self, *steps: Runnable[Any, Any], name: Optional[str] = None) -> None:
        flattened: List[Runnable[Any, Any]] = []
        for step in steps:
            runnable_step = coerce_to_runnable(step)
            if isinstance(runnable_step, RunnableSequence):
                flattened.extend(runnable_step.steps)
            else:
                flattened.append(runnable_step)
        if len(flattened) < 1:
            raise ValueError("RunnableSequence 至少需要包含一个 Runnable 步骤")
        self.steps: List[Runnable[Any, Any]] = flattened
        super().__init__(name=name or " | ".join(s.name for s in self.steps))

    def invoke(self, input_data: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        current = input_data
        for step in self.steps:
            current = step.invoke(current, config=config)
        return current

    def stream(self, input_data: Any, config: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        """将前序步骤的输出依次送入最后一个步骤的 stream()。"""
        current = input_data
        for step in self.steps[:-1]:
            current = step.invoke(current, config=config)
        yield from self.steps[-1].stream(current, config=config)


class RunnableLambda(Runnable[InputT, OutputT]):
    """将任意 Python 函数或 lambda 表达式封装为标准 Runnable。"""

    def __init__(self, func: Callable[[InputT], OutputT], name: Optional[str] = None) -> None:
        if not callable(func):
            raise TypeError("RunnableLambda 必须接收一个可调用对象")
        self.func = func
        func_name = getattr(func, "__name__", "lambda")
        super().__init__(name=name or f"RunnableLambda({func_name})")

    def invoke(self, input_data: InputT, config: Optional[Dict[str, Any]] = None) -> OutputT:
        return self.func(input_data)


class RunnableParallel(Runnable[Any, Dict[str, Any]]):
    """并行执行多个分支 Runnable，并将各分支输出按字典键名聚合返回。"""

    def __init__(
        self,
        steps: Optional[Mapping[str, Union[Runnable[Any, Any], Callable[[Any], Any], Mapping[str, Any]]]] = None,
        name: Optional[str] = None,
        **kwargs: Union[Runnable[Any, Any], Callable[[Any], Any], Mapping[str, Any]],
    ) -> None:
        merged: Dict[str, Any] = {}
        if steps:
            merged.update(steps)
        if kwargs:
            merged.update(kwargs)
        if not merged:
            raise ValueError("RunnableParallel 至少需要一个分支")
        self.branches: Dict[str, Runnable[Any, Any]] = {
            key: coerce_to_runnable(val) for key, val in merged.items()
        }
        super().__init__(name=name or f"RunnableParallel({list(self.branches.keys())})")

    def invoke(self, input_data: Any, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if len(self.branches) == 1:
            key, branch = next(iter(self.branches.items()))
            return {key: branch.invoke(input_data, config=config)}

        results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(self.branches)) as executor:
            futures = {
                key: executor.submit(branch.invoke, input_data, config)
                for key, branch in self.branches.items()
            }
            for key, future in futures.items():
                results[key] = future.result()
        return results


class RunnablePassthrough(Runnable[Any, Any]):
    """原样透传输入数据；亦可通过 `.assign(**kwargs)` 在保留原字典的基础上追加派生字段。"""

    def __init__(self, name: Optional[str] = None) -> None:
        super().__init__(name=name or "RunnablePassthrough")

    def invoke(self, input_data: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        return input_data

    @classmethod
    def assign(
        cls,
        **kwargs: Union[Runnable[Any, Any], Callable[[Any], Any], Mapping[str, Any]],
    ) -> RunnableAssign:
        """返回一个在字典输入上保留原字段并追加计算字段的 RunnableAssign。"""
        return RunnableAssign(RunnableParallel(kwargs))


class RunnableAssign(Runnable[Dict[str, Any], Dict[str, Any]]):
    """配合 RunnablePassthrough.assign 使用：合并输入字典与并行分支输出。"""

    def __init__(self, mapper: RunnableParallel, name: Optional[str] = None) -> None:
        self.mapper = mapper
        super().__init__(name=name or f"RunnableAssign({list(mapper.branches.keys())})")

    def invoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(input_data, Mapping):
            raise TypeError("RunnablePassthrough.assign 要求输入必须为字典（Mapping）")
        merged = dict(input_data)
        merged.update(self.mapper.invoke(input_data, config=config))
        return merged


class PromptTemplate(Runnable[Dict[str, Any], str]):
    """轻量级提示词模板 Runnable，接收字典变量并格式化为字符串 Prompt。"""

    def __init__(self, template: str, name: Optional[str] = None) -> None:
        self.template = template
        super().__init__(name=name or "PromptTemplate")

    def invoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> str:
        if not isinstance(input_data, Mapping):
            raise TypeError("PromptTemplate 输入必须为字典")
        return self.template.format(**input_data)


class AIMessage(BaseModel):
    """模拟大模型返回的消息对象，与 LangChain AIMessage 接口对齐。"""

    content: str
    model: str = "zhishu-mock-llm"


class MockChatModel(Runnable[str, AIMessage]):
    """离线可运行的确定性模拟大模型，用于教学演示与自动化单元测试。

    可根据输入 Prompt 中的指令关键字（如翻译、润色、摘要、JSON）生成结构化响应，
    亦支持注入自定义响应函数 `responder`。
    """

    def __init__(
        self,
        responder: Optional[Callable[[str], str]] = None,
        model_name: str = "zhishu-mock-llm",
        name: Optional[str] = None,
    ) -> None:
        self.responder = responder
        self.model_name = model_name
        super().__init__(name=name or f"MockChatModel({model_name})")

    def invoke(self, input_data: str, config: Optional[Dict[str, Any]] = None) -> AIMessage:
        prompt_text = str(input_data)
        if self.responder is not None:
            reply = self.responder(prompt_text)
        else:
            reply = self._default_respond(prompt_text)
        return AIMessage(content=reply, model=self.model_name)

    def stream(self, input_data: str, config: Optional[Dict[str, Any]] = None) -> Iterator[AIMessage]:
        full = self.invoke(input_data, config=config)
        chunk_size = 6
        for i in range(0, len(full.content), chunk_size):
            yield AIMessage(content=full.content[i : i + chunk_size], model=self.model_name)

    @staticmethod
    def _default_respond(prompt_text: str) -> str:
        """基于任务标识的确定性规则响应。"""
        if "[TASK:TRANSLATE]" in prompt_text:
            body = prompt_text.split("[INPUT]", 1)[-1].strip()
            return f"智枢企业级智能体平台支持可组合管道、自动化运维以及安全的数据分析。（译自：{body}）"
        if "[TASK:POLISH]" in prompt_text:
            body = prompt_text.split("[INPUT]", 1)[-1].strip()
            clean = re.sub(r"（译自：.*?）$", "", body).strip()
            return f"【专业润色版】{clean} 凭借标准化组件编排，助力企业实现高效、可靠的智能化升级。"
        if "[TASK:SUMMARY_JSON]" in prompt_text:
            body = prompt_text.split("[INPUT]", 1)[-1].strip()
            payload = {
                "title": "智枢平台核心能力简报",
                "summary": body[:48] + ("..." if len(body) > 48 else ""),
                "keywords": ["智枢平台", "可组合管道", "企业级智能体"],
                "word_count": len(body),
            }
            return f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
        return f"已收到指令：{prompt_text}"


def _extract_text(output: Union[str, AIMessage, Mapping[str, Any]]) -> str:
    """从模型输出（str / AIMessage / dict）中统一提取文本内容。"""
    if isinstance(output, str):
        return output
    if isinstance(output, AIMessage):
        return output.content
    if isinstance(output, Mapping) and "content" in output:
        return str(output["content"])
    return str(output)


def _strip_markdown_code_fence(text: str) -> str:
    """去除大模型常见的 ```json ... ``` 代码块包裹。"""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


class StrOutputParser(Runnable[Union[str, AIMessage, Mapping[str, Any]], str]):
    """将模型输出（AIMessage / dict / str）解析为纯字符串。"""

    def invoke(
        self,
        input_data: Union[str, AIMessage, Mapping[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        return _extract_text(input_data)


class JsonOutputParser(Runnable[Union[str, AIMessage, Mapping[str, Any]], Any]):
    """从模型输出中提取并反序列化 JSON（自动兼容 ```json 代码块）。"""

    def invoke(
        self,
        input_data: Union[str, AIMessage, Mapping[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> Any:
        raw_text = _extract_text(input_data)
        cleaned = _strip_markdown_code_fence(raw_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JsonOutputParser 解析失败，非法 JSON 内容: {cleaned!r}") from exc


class PydanticOutputParser(Runnable[Union[str, AIMessage, Mapping[str, Any]], ModelT], Generic[ModelT]):
    """将模型输出解析并校验为指定的 Pydantic BaseModel 实例。"""

    def __init__(self, pydantic_object: Type[ModelT], name: Optional[str] = None) -> None:
        if not (isinstance(pydantic_object, type) and issubclass(pydantic_object, BaseModel)):
            raise TypeError("pydantic_object 必须是 pydantic.BaseModel 的子类")
        self.pydantic_object = pydantic_object
        super().__init__(name=name or f"PydanticOutputParser({pydantic_object.__name__})")

    def get_format_instructions(self) -> str:
        """生成可嵌入 Prompt 的 JSON Schema 格式约束指令。"""
        schema = json.dumps(self.pydantic_object.model_json_schema(), ensure_ascii=False, indent=2)
        return (
            f"请严格按照以下 JSON Schema 输出纯 JSON 对象（不要包含多余解释）：\n"
            f"```json\n{schema}\n```"
        )

    def invoke(
        self,
        input_data: Union[str, AIMessage, Mapping[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> ModelT:
        raw_text = _extract_text(input_data)
        cleaned = _strip_markdown_code_fence(raw_text)
        try:
            return self.pydantic_object.model_validate_json(cleaned)
        except Exception as exc:
            raise ValueError(
                f"PydanticOutputParser 校验 {self.pydantic_object.__name__} 失败: {exc}"
            ) from exc


class ArticleSummary(BaseModel):
    """3 阶段「翻译 -> 润色 -> 摘要」LCEL 链的结构化最终输出模型。"""

    title: str = Field(description="摘要标题")
    summary: str = Field(description="核心内容摘要")
    keywords: List[str] = Field(description="提取的关键词列表")
    word_count: int = Field(ge=0, description="润色后正文字符数")


def build_translate_polish_summary_chain(
    llm: Optional[Runnable[str, Any]] = None,
) -> RunnableSequence:
    """构建 3 阶段「翻译 -> 润色 -> 摘要」LCEL 管道链。

    数据流：
    `{"source_text": ...}`
      -> 阶段1（翻译）：`PromptTemplate | llm | StrOutputParser`
      -> 阶段2（润色）：`PromptTemplate | llm | StrOutputParser`
      -> 阶段3（摘要）：`PromptTemplate | llm | PydanticOutputParser(ArticleSummary)`
    同时使用 `RunnablePassthrough.assign` 保留中间各阶段产物，方便观测与审计。
    """
    model = llm or MockChatModel()
    str_parser = StrOutputParser()
    summary_parser = PydanticOutputParser(ArticleSummary)

    translate_prompt = PromptTemplate(
        "[TASK:TRANSLATE] 请将以下英文技术文本精准翻译为中文：\n[INPUT] {source_text}"
    )
    polish_prompt = PromptTemplate(
        "[TASK:POLISH] 请对以下中文译文进行企业级专业润色：\n[INPUT] {translated_text}"
    )
    summary_prompt = PromptTemplate(
        "[TASK:SUMMARY_JSON] 请基于以下润色文本生成结构化摘要。\n"
        "{format_instructions}\n[INPUT] {polished_text}"
    )

    translate_chain = (lambda x: {"source_text": x["source_text"]}) | translate_prompt | model | str_parser
    polish_chain = (lambda x: {"translated_text": x["translated_text"]}) | polish_prompt | model | str_parser
    summary_chain = (
        (lambda x: {
            "polished_text": x["polished_text"],
            "format_instructions": summary_parser.get_format_instructions(),
        })
        | summary_prompt
        | model
        | summary_parser
    )

    full_chain = (
        RunnablePassthrough.assign(translated_text=translate_chain)
        | RunnablePassthrough.assign(polished_text=polish_chain)
        | RunnablePassthrough.assign(final_summary=summary_chain)
    )
    return full_chain
