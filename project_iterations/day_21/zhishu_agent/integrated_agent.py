"""Day 21 核心模块：Week 3 综合迷你项目 —— 多轮记忆 + 工具调用 + 流式输出集成智能体 (v0.2.0-day21)"""
from __future__ import annotations

import ast
import json
import operator
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

# ---------------------------------------------------------------------------
# 1. 安全数学表达式求值器（基于 AST 白名单，严禁 eval()）
# ---------------------------------------------------------------------------

_BINARY_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_ast_node(node: ast.AST) -> int | float:
    """递归求值受限 AST 数学节点，仅允许数字常量与基础算术运算符。"""
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"不允许的常量类型: {type(node.value).__name__}")
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BINARY_OPS:
            raise ValueError(f"不支持的二元运算符: {op_type.__name__}")
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if op_type is ast.Pow and abs(right) > 1000:
            raise ValueError("幂运算指数过大（绝对值不能超过 1000）")
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ValueError("除数不能为 0")
        return _BINARY_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        operand = _eval_ast_node(node.operand)
        return _UNARY_OPS[op_type](operand)
    raise ValueError(f"检测到不安全的表达式语法节点: {type(node).__name__}")


def safe_calculate_math(expression: str) -> int | float:
    """安全计算纯算术表达式（仅支持 +, -, *, /, //, %, ** 与括号）。"""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("数学表达式不能为空")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"数学表达式语法错误: {exc.msg}") from exc
    result = _eval_ast_node(tree)
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return round(result, 6) if isinstance(result, float) else result


# ---------------------------------------------------------------------------
# 2. 企业工具实现与 OpenAI Function Calling JSON Schema
# ---------------------------------------------------------------------------

_MOCK_WEATHER_DB: dict[str, dict[str, Any]] = {
    "北京": {"temp_c": 18, "condition": "晴朗微风", "humidity": "35%"},
    "上海": {"temp_c": 22, "condition": "多云转晴", "humidity": "58%"},
    "深圳": {"temp_c": 27, "condition": "阵雨转阴", "humidity": "78%"},
    "杭州": {"temp_c": 20, "condition": "晴间多云", "humidity": "50%"},
}


def get_weather(city: str, unit: str = "celsius") -> dict[str, Any]:
    """查询指定城市的实时天气信息。"""
    normalized = city.strip()
    record = _MOCK_WEATHER_DB.get(
        normalized,
        {"temp_c": 21, "condition": "多云", "humidity": "45%"},
    )
    temp_c = record["temp_c"]
    if unit == "fahrenheit":
        temp = round(temp_c * 9 / 5 + 32, 1)
        unit_label = "°F"
    else:
        temp = temp_c
        unit_label = "°C"
    return {
        "city": normalized,
        "temperature": temp,
        "unit": unit_label,
        "condition": record["condition"],
        "humidity": record["humidity"],
    }


def calculate_math(expression: str) -> dict[str, Any]:
    """安全计算数学表达式并返回结构化结果。"""
    value = safe_calculate_math(expression)
    return {"expression": expression.strip(), "result": value}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气（温度、天气状况与湿度）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如：北京、上海、深圳、杭州。",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，默认为 celsius（摄氏度）。",
                    },
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_math",
            "description": "安全计算算术数学表达式，支持加减乘除、取余、幂运算与括号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "纯算术表达式，例如 '(120 + 80) * 3 / 4'。",
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
]


class ToolRegistry:
    """工具注册与安全分发中心：管理 Schema 与本地 Python 执行器。"""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any],
    ) -> None:
        """注册工具函数及其 OpenAI JSON Schema。"""
        self._tools[name] = func
        self._schemas[name] = schema

    def list_tools(self) -> list[str]:
        """返回已注册工具名称列表。"""
        return list(self._tools.keys())

    def get_schemas(self) -> list[dict[str, Any]]:
        """导出全部工具的 OpenAI `tools` 参数列表。"""
        return list(self._schemas.values())

    def dispatch(self, name: str, arguments: str | dict[str, Any]) -> str:
        """解析参数并安全执行目标工具，始终返回 JSON 字符串作为 role='tool' 内容。"""
        if name not in self._tools:
            return json.dumps(
                {
                    "error": f"未知工具: {name}",
                    "available_tools": self.list_tools(),
                },
                ensure_ascii=False,
            )

        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                return json.dumps(
                    {"error": f"工具参数 JSON 解析失败: {exc.msg}"},
                    ensure_ascii=False,
                )
        elif isinstance(arguments, dict):
            parsed_args = arguments
        else:
            return json.dumps(
                {"error": f"不支持的参数类型: {type(arguments).__name__}"},
                ensure_ascii=False,
            )

        if not isinstance(parsed_args, dict):
            return json.dumps(
                {"error": "工具参数必须为 JSON 对象"},
                ensure_ascii=False,
            )

        try:
            result = self._tools[name](**parsed_args)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps(
                {"error": f"工具 {name} 执行失败: {exc}"},
                ensure_ascii=False,
            )


def create_default_registry() -> ToolRegistry:
    """创建并注册 Day 21 默认工具集（get_weather, calculate_math）。"""
    registry = ToolRegistry()
    schema_map = {item["function"]["name"]: item for item in TOOL_SCHEMAS}
    registry.register("get_weather", get_weather, schema_map["get_weather"])
    registry.register("calculate_math", calculate_math, schema_map["calculate_math"])
    return registry


# ---------------------------------------------------------------------------
# 3. SSE 流式解析与离线 MockTransport 协议引擎
# ---------------------------------------------------------------------------


def parse_sse_line(line: str) -> str | None:
    """解析单行 SSE 文本并提取 `choices[0].delta.content` 增量文本片段。"""
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None

    payload = stripped[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    delta = first_choice.get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) else None


def _split_sse_chunks(text: str, chunk_size: int = 8) -> bytes:
    """将完整文本切分为标准 OpenAI `text/event-stream` SSE 字节流。"""
    lines: list[str] = []
    for idx in range(0, len(text), chunk_size):
        piece = text[idx : idx + chunk_size]
        payload = json.dumps(
            {
                "id": "chatcmpl-mock-day21",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
            },
            ensure_ascii=False,
        )
        lines.append(f"data: {payload}\n\n")
    finish_payload = json.dumps(
        {
            "id": "chatcmpl-mock-day21",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        ensure_ascii=False,
    )
    lines.append(f"data: {finish_payload}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _extract_latest_user_and_tools(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """提取最新一轮用户输入及该轮之后产生的 tool 观测消息。"""
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx == -1:
        return "", []
    user_text = str(messages[last_user_idx].get("content", ""))
    tool_msgs = [
        m for m in messages[last_user_idx + 1 :] if m.get("role") == "tool"
    ]
    return user_text, tool_msgs


def _detect_city(text: str) -> str | None:
    for city in ("北京", "上海", "深圳", "杭州"):
        if city in text:
            return city
    return None


def _detect_math_expr(text: str) -> str | None:
    match = re.search(r"([\(\s]*[0-9]+(?:\.[0-9]+)?(?:\s*[\+\-\*/%]\s*[\(\)\s0-9\.]+)+)", text)
    if match:
        return match.group(1).strip()
    return None


def _recall_user_name(messages: list[dict[str, Any]]) -> str | None:
    for msg in messages:
        if msg.get("role") == "user":
            content = str(msg.get("content", ""))
            m = re.search(r"我叫([^\s，。！？,.!?]+)", content)
            if m:
                return m.group(1)
    return None


def _recall_last_weather_city(messages: list[dict[str, Any]]) -> str | None:
    for msg in reversed(messages[:-1]):
        if msg.get("role") == "tool":
            try:
                data = json.loads(str(msg.get("content", "")))
                if isinstance(data, dict) and "city" in data:
                    return str(data["city"])
            except json.JSONDecodeError:
                continue
    return None


def create_integrated_mock_transport() -> httpx.MockTransport:
    """构造支持多轮记忆 + Function Calling + SSE 流式输出的离线 MockTransport。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        messages: list[dict[str, Any]] = body.get("messages", [])
        is_stream = bool(body.get("stream", False))
        user_text, tool_msgs = _extract_latest_user_and_tools(messages)

        # 场景 A：非流式工具决策阶段（尚未收到本轮 tool 结果）
        if not is_stream and not tool_msgs:
            tool_calls: list[dict[str, Any]] = []
            city = _detect_city(user_text)
            if ("天气" in user_text or "气温" in user_text) and city:
                tool_calls.append(
                    {
                        "id": "call_weather_001",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps(
                                {"city": city, "unit": "celsius"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )
            expr = _detect_math_expr(user_text)
            if expr and any(k in user_text for k in ("算", "计算", "等于", "+", "-", "*", "/")):
                tool_calls.append(
                    {
                        "id": "call_math_001",
                        "type": "function",
                        "function": {
                            "name": "calculate_math",
                            "arguments": json.dumps(
                                {"expression": expr},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )

            if tool_calls:
                return httpx.Response(
                    status_code=200,
                    json={
                        "id": "chatcmpl-mock-tool-round",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": tool_calls,
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"total_tokens": 110},
                    },
                )

        # 场景 B：生成最终自然语言回复（汇总工具结果或基于多轮记忆回答）
        if tool_msgs:
            parts: list[str] = []
            for tm in tool_msgs:
                try:
                    data = json.loads(str(tm.get("content", "")))
                except json.JSONDecodeError:
                    data = {}
                if "city" in data and "temperature" in data:
                    parts.append(
                        f"{data['city']}当前天气{data['condition']}，气温 {data['temperature']}{data['unit']}，湿度 {data['humidity']}"
                    )
                elif "expression" in data and "result" in data:
                    parts.append(f"算式 {data['expression']} 的计算结果为 {data['result']}")
                elif "error" in data:
                    parts.append(f"工具执行提示：{data['error']}")
            final_text = "已为您调用工具完成查询：" + "；".join(parts) + "。"
        else:
            remembered_name = _recall_user_name(messages)
            last_city = _recall_last_weather_city(messages)
            if "我叫什么" in user_text or "我是谁" in user_text:
                if remembered_name:
                    final_text = f"您刚才告诉我，您的名字是{remembered_name}。"
                else:
                    final_text = "您还没有告诉我您的名字哦。"
            elif "刚才" in user_text and "城市" in user_text:
                if last_city:
                    final_text = f"您上一轮查询天气的城市是{last_city}。"
                else:
                    final_text = "本轮会话中您还没有查询过城市天气。"
            elif "我叫" in user_text:
                name_match = re.search(r"我叫([^\s，。！？,.!?]+)", user_text)
                name = name_match.group(1) if name_match else "朋友"
                final_text = f"您好，{name}！我已经记住您的名字，请问有什么可以帮您？"
            else:
                final_text = f"收到您的消息：「{user_text}」。智枢集成助手已就绪，支持多轮记忆、天气查询与数学计算。"

        if is_stream:
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                content=_split_sse_chunks(final_text),
            )

        return httpx.Response(
            status_code=200,
            json={
                "id": "chatcmpl-mock-final",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": final_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 95},
            },
        )

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 4. 综合集成智能体：Multi-turn Memory + Tool Calling + Streaming
# ---------------------------------------------------------------------------


@dataclass
class IntegratedRunResult:
    """单轮综合交互的结构化运行结果。"""

    answer: str
    rounds: int
    executed_tools: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    streamed_chunks: int = 0


class IntegratedAgent:
    """智枢 Day 21 综合智能体：融合多轮上下文记忆、工具调用与生成器流式输出。"""

    DEFAULT_SYSTEM_PROMPT = (
        "你是星辰数科《智枢》企业级智能助手。"
        "当需要查询天气或进行精确数学计算时，请优先调用工具；"
        "同时请准确记住用户的多轮对话上下文。"
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
        system_prompt: str | None = None,
        registry: ToolRegistry | None = None,
        transport: httpx.BaseTransport | None = None,
        max_iterations: int = 5,
        timeout: float = 30.0,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.api_key = resolved_key or "mock-key"
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.registry = registry or create_default_registry()
        self.max_iterations = max_iterations
        self.timeout = timeout

        if transport is not None:
            self._transport: httpx.BaseTransport | None = transport
            self._is_mock = isinstance(transport, httpx.MockTransport)
        elif not resolved_key:
            self._transport = create_integrated_mock_transport()
            self._is_mock = True
        else:
            self._transport = None
            self._is_mock = False

        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.total_tokens: int = 0
        self.turn_count: int = 0
        self.last_run: IntegratedRunResult | None = None

    @property
    def is_mock(self) -> bool:
        """当前是否处于 Mock 离线模拟模式。"""
        return self._is_mock

    def clear_history(self) -> None:
        """清空多轮对话历史，保留 System Prompt 并重置统计计数。"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.total_tokens = 0
        self.turn_count = 0
        self.last_run = None

    def get_history(self) -> list[dict[str, Any]]:
        """返回当前多轮消息历史副本。"""
        return [dict(m) for m in self.messages]

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
            transport=self._transport,
        )

    def stream_reply(self, user_input: str) -> Iterator[str]:
        """执行「工具调用决策闭环 + SSE 生成器流式输出」并维护多轮记忆。

        Args:
            user_input: 本轮用户输入文本。

        Yields:
            str: 流式输出的增量文本片段。
        """
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        checkpoint = len(self.messages)
        self.messages.append({"role": "user", "content": user_input.strip()})

        executed_tools: list[dict[str, Any]] = []
        round_tokens = 0
        rounds = 0

        try:
            with self._build_client() as client:
                # 阶段一：工具调用决策循环（非流式，确保完整解析 tool_calls）
                while rounds < self.max_iterations:
                    rounds += 1
                    payload: dict[str, Any] = {
                        "model": self.model,
                        "messages": self.messages,
                        "tools": self.registry.get_schemas(),
                        "stream": False,
                    }
                    resp = client.post("/chat/completions", json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    usage = data.get("usage") or {}
                    round_tokens += int(usage.get("total_tokens", 0))

                    choice = data["choices"][0]
                    assistant_msg = choice["message"]
                    tool_calls = assistant_msg.get("tool_calls") or []

                    if not tool_calls:
                        # 无需调用工具（或工具结果已消化完毕）：进入阶段二流式输出
                        break

                    # 严格遵循 OpenAI 协议：先追加带 tool_calls 的 assistant 消息
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_msg.get("content"),
                            "tool_calls": tool_calls,
                        }
                    )
                    # 再逐个执行工具并追加 role="tool" 观测结果
                    for tc in tool_calls:
                        fn = tc["function"]
                        tool_name = fn["name"]
                        raw_args = fn.get("arguments", "{}")
                        output = self.registry.dispatch(tool_name, raw_args)
                        executed_tools.append(
                            {
                                "id": tc["id"],
                                "name": tool_name,
                                "arguments": raw_args,
                                "output": output,
                            }
                        )
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": tool_name,
                                "content": output,
                            }
                        )
                else:
                    raise RuntimeError(f"工具调用超过最大轮数限制 ({self.max_iterations})")

                # 阶段二：通过 SSE 流式接口逐块生成并 yield 最终回复
                stream_payload: dict[str, Any] = {
                    "model": self.model,
                    "messages": self.messages,
                    "stream": True,
                }
                chunks: list[str] = []
                with client.stream("POST", "/chat/completions", json=stream_payload) as stream_resp:
                    stream_resp.raise_for_status()
                    for line in stream_resp.iter_lines():
                        delta = parse_sse_line(line)
                        if delta:
                            chunks.append(delta)
                            yield delta

                full_answer = "".join(chunks)
                self.messages.append({"role": "assistant", "content": full_answer})
                self.turn_count += 1
                self.total_tokens += round_tokens
                self.last_run = IntegratedRunResult(
                    answer=full_answer,
                    rounds=rounds,
                    executed_tools=executed_tools,
                    total_tokens=round_tokens,
                    streamed_chunks=len(chunks),
                )
        except Exception:
            # 事务性回滚：若本轮任一环节失败，回滚本轮追加的 user/assistant/tool 消息
            del self.messages[checkpoint:]
            raise

    def run(self, user_input: str) -> IntegratedRunResult:
        """同步消费 `stream_reply` 并返回完整结构化结果。"""
        for _ in self.stream_reply(user_input):
            pass
        assert self.last_run is not None
        return self.last_run
