"""Day 26 自动化单元测试：覆盖 Runnable、`|` 管道运算符、并行/透传组合器、OutputParsers 与 3 阶段 LCEL 链。"""
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.lcel import (
    AIMessage,
    ArticleSummary,
    JsonOutputParser,
    MockChatModel,
    PromptTemplate,
    PydanticOutputParser,
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
    RunnableSequence,
    StrOutputParser,
    build_translate_polish_summary_chain,
)


class CustomMultiplier(Runnable[int, int]):
    """自定义 Runnable 子类，用于测试继承与 `|` 组合。"""

    def __init__(self, factor: int) -> None:
        super().__init__(name=f"Multiply({factor})")
        self.factor = factor

    def invoke(self, input_data: int, config=None) -> int:
        return input_data * self.factor


def test_runnable_sequence_and_pipe_operator() -> None:
    """验证 `|` (__or__ / __ror__) 构造 RunnableSequence 及 invoke/batch/stream。"""
    add_one = RunnableLambda(lambda x: x + 1)
    times_two = CustomMultiplier(2)

    # 支持 Runnable | Runnable 以及 plain callable | Runnable | plain callable
    chain = (lambda x: x - 3) | add_one | times_two | (lambda x: f"result={x}")
    assert isinstance(chain, RunnableSequence)
    assert len(chain.steps) == 4

    assert chain.invoke(10) == "result=16"
    assert chain.batch([5, 10]) == ["result=6", "result=16"]
    assert list(chain.stream(10)) == ["result=16"]


def test_runnable_passthrough_and_assign() -> None:
    """验证 RunnablePassthrough 原样透传与 `.assign(...)` 动态追加字段。"""
    passthrough = RunnablePassthrough()
    assert passthrough.invoke({"a": 1}) == {"a": 1}

    enrich_chain = RunnablePassthrough.assign(
        upper_name=lambda x: x["name"].upper(),
        name_len=RunnableLambda(lambda x: len(x["name"])),
    )
    out = enrich_chain.invoke({"name": "zhishu", "version": "0.3.0"})
    assert out == {
        "name": "zhishu",
        "version": "0.3.0",
        "upper_name": "ZHISHU",
        "name_len": 6,
    }


def test_runnable_parallel_and_dict_coercion() -> None:
    """验证 RunnableParallel 与字典在 `|` 中的自动强制转换。"""
    chain = (
        {"raw": RunnablePassthrough(), "doubled": lambda x: x * 2, "squared": lambda x: x**2}
        | RunnableLambda(lambda d: f"{d['raw']}->{d['doubled']}->{d['squared']}")
    )
    assert isinstance(chain, RunnableSequence)
    assert isinstance(chain.steps[0], RunnableParallel)
    assert chain.invoke(4) == "4->8->16"


def test_output_parsers() -> None:
    """验证 StrOutputParser、JsonOutputParser 与 PydanticOutputParser。"""
    str_parser = StrOutputParser()
    assert str_parser.invoke(AIMessage(content="hello")) == "hello"
    assert str_parser.invoke({"content": "world"}) == "world"

    json_parser = JsonOutputParser()
    fenced_json = '```json\n{"status": "ok", "count": 3}\n```'
    assert json_parser.invoke(AIMessage(content=fenced_json)) == {"status": "ok", "count": 3}

    with pytest.raises(ValueError, match="JsonOutputParser 解析失败"):
        json_parser.invoke("not-valid-json")

    class TaskInfo(BaseModel):
        task: str
        priority: int = Field(ge=1, le=5)

    pydantic_parser = PydanticOutputParser(TaskInfo)
    instructions = pydantic_parser.get_format_instructions()
    assert "TaskInfo" in instructions and "priority" in instructions

    parsed = pydantic_parser.invoke('```json\n{"task": "deploy", "priority": 2}\n```')
    assert isinstance(parsed, TaskInfo)
    assert parsed.task == "deploy" and parsed.priority == 2

    with pytest.raises(ValueError, match="PydanticOutputParser 校验 TaskInfo 失败"):
        pydantic_parser.invoke('{"task": "deploy", "priority": 99}')


def test_prompt_model_parser_and_three_stage_chain() -> None:
    """验证 Prompt | Model | Parser 以及 3 阶段「翻译 -> 润色 -> 摘要」LCEL 链。"""
    simple_chain = PromptTemplate("主题：{topic}") | MockChatModel() | StrOutputParser()
    assert "主题：RAG" in simple_chain.invoke({"topic": "RAG"})

    # 流式调用最终节点
    chunks = list(simple_chain.stream({"topic": "LCEL"}))
    assert "".join(chunks) == simple_chain.invoke({"topic": "LCEL"})

    # 3 阶段链端到端测试
    pipeline = build_translate_polish_summary_chain()
    result = pipeline.invoke(
        {"source_text": "ZhiShu Agent supports composable pipelines."}
    )
    assert "智枢企业级智能体平台" in result["translated_text"]
    assert result["polished_text"].startswith("【专业润色版】")
    summary = result["final_summary"]
    assert isinstance(summary, ArticleSummary)
    assert summary.title == "智枢平台核心能力简报"
    assert len(summary.keywords) >= 1
    assert summary.word_count == len(result["polished_text"])
