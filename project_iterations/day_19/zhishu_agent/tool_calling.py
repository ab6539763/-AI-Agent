"""Day 19 核心模块：Pure-API Function Calling / Tool Use 引擎（零框架依赖，纯 httpx 实现）"""
from __future__ import annotations

import ast
import json
import operator
import os
import re
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
        # 注意：在 Python 中 bool 是 int 的子类，必须显式排除
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
# 2. 企业内部工具函数实现与 OpenAI JSON Schema 定义
# ---------------------------------------------------------------------------

_MOCK_WEATHER_DB: dict[str, dict[str, Any]] = {
    "北京": {"temp_c": 18, "condition": "晴朗微风", "humidity": "35%"},
    "上海": {"temp_c": 22, "condition": "多云转晴", "humidity": "58%"},
    "深圳": {"temp_c": 27, "condition": "阵雨转阴", "humidity": "78%"},
    "杭州": {"temp_c": 20, "condition": "晴间多云", "humidity": "50%"},
}

_EMPLOYEE_DIRECTORY: dict[str, dict[str, str]] = {
    "EMP-001": {
        "employee_id": "EMP-001",
        "name": "陈默",
        "department": "AI 应用研发部",
        "role": "AI 应用开发工程师",
        "email": "chenmo@xingchen.ai",
    },
    "EMP-002": {
        "employee_id": "EMP-002",
        "name": "林晓",
        "department": "产品中心",
        "role": "高级产品经理",
        "email": "linxiao@xingchen.ai",
    },
    "EMP-003": {
        "employee_id": "EMP-003",
        "name": "张工",
        "department": "基础架构部",
        "role": "Tech Lead",
        "email": "zhanggong@xingchen.ai",
    },
    "EMP-004": {
        "employee_id": "EMP-004",
        "name": "李婷",
        "department": "质量保障部",
        "role": "高级 QA 工程师",
        "email": "liting@xingchen.ai",
    },
}


def get_weather(city: str, unit: str = "celsius") -> dict[str, Any]:
    """查询指定城市的实时天气信息。"""
    normalized_city = city.strip()
    data = _MOCK_WEATHER_DB.get(
        normalized_city,
        {"temp_c": 21, "condition": "晴", "humidity": "45%"},
    )
    temp_c = data["temp_c"]
    if unit.lower() == "fahrenheit":
        temperature = round(temp_c * 9 / 5 + 32, 1)
        unit_label = "°F"
    else:
        temperature = temp_c
        unit_label = "°C"
    return {
        "city": normalized_city,
        "temperature": temperature,
        "unit": unit_label,
        "condition": data["condition"],
        "humidity": data["humidity"],
    }


def calculate_math(expression: str) -> dict[str, Any]:
    """使用 AST 安全求值器计算数学表达式。"""
    value = safe_calculate_math(expression)
    return {
        "expression": expression.strip(),
        "result": value,
    }


def query_employee_info(
    employee_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """根据员工工号或姓名查询星辰数科内部通讯录。"""
    if employee_id:
        record = _EMPLOYEE_DIRECTORY.get(employee_id.strip().upper())
        if record:
            return {"found": True, "employee": record}
    if name:
        target = name.strip()
        for record in _EMPLOYEE_DIRECTORY.values():
            if record["name"] == target:
                return {"found": True, "employee": record}
    return {
        "found": False,
        "error": f"未找到匹配的员工记录 (employee_id={employee_id}, name={name})",
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气情况（温度、天气状况、湿度）。",
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
            "description": "安全计算四则运算、幂运算与括号混合数学表达式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "纯算术表达式字符串，例如 '(128 + 32) * 3 / 4'。",
                    },
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_employee_info",
            "description": "查询星辰数科内部员工的工号、部门、岗位与企业邮箱。",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "员工工号，例如 'EMP-001'。",
                    },
                    "name": {
                        "type": "string",
                        "description": "员工中文姓名，例如 '陈默'。",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 3. ToolRegistry：工具注册与安全分发中心
# ---------------------------------------------------------------------------


class ToolRegistry:
    """管理 Python 工具函数与对应的 OpenAI JSON Schema，并负责安全分发执行。"""

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any],
    ) -> None:
        """注册一个工具函数及其 OpenAI Function Calling Schema。"""
        if not name or not isinstance(name, str):
            raise ValueError("工具名称必须是非空字符串")
        if not callable(func):
            raise TypeError(f"工具 {name} 必须是可调用对象")
        self._functions[name] = func
        self._schemas[name] = schema

    def has_tool(self, name: str) -> bool:
        return name in self._functions

    def list_tools(self) -> list[str]:
        return list(self._functions.keys())

    def get_schemas(self) -> list[dict[str, Any]]:
        return list(self._schemas.values())

    def dispatch(self, name: str, arguments: str | dict[str, Any]) -> str:
        """
        安全分发并执行指定工具，返回 JSON 字符串供 role='tool' 消息回传给模型。
        对未知工具、非法 JSON 参数或工具内部异常进行结构化捕获，避免主循环崩溃。
        """
        if name not in self._functions:
            return json.dumps(
                {"error": f"未知工具: {name}", "available_tools": self.list_tools()},
                ensure_ascii=False,
            )

        if isinstance(arguments, str):
            raw = arguments.strip() or "{}"
            try:
                parsed_args = json.loads(raw)
            except json.JSONDecodeError as exc:
                return json.dumps(
                    {"error": f"工具参数 JSON 解析失败: {exc.msg}", "raw_arguments": arguments},
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
                {"error": "工具参数反序列化后必须是 JSON 对象 (dict)"},
                ensure_ascii=False,
            )

        try:
            result = self._functions[name](**parsed_args)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps(
                {"error": f"工具 {name} 执行失败: {exc}"},
                ensure_ascii=False,
            )


def create_default_registry() -> ToolRegistry:
    """创建并预注册智枢平台 Day 19 默认工具集。"""
    registry = ToolRegistry()
    func_map: dict[str, Callable[..., Any]] = {
        "get_weather": get_weather,
        "calculate_math": calculate_math,
        "query_employee_info": query_employee_info,
    }
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        registry.register(name=name, func=func_map[name], schema=schema)
    return registry


# ---------------------------------------------------------------------------
# 4. MockTransport：离线模拟 OpenAI Function Calling 多轮协议
# ---------------------------------------------------------------------------


def _extract_last_user_index(messages: list[dict[str, Any]]) -> int:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "user":
            return idx
    return -1


def create_mock_tool_calling_transport() -> httpx.MockTransport:
    """
    构造支持完整 Function Calling 两轮/多轮闭环的 httpx.MockTransport。
    Round 1: 根据用户问题返回标准 assistant tool_calls 载荷。
    Round 2: 读取 role='tool' 回传结果，生成最终自然语言回复。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            payload = json.loads(request.content.decode("utf-8"))
            messages: list[dict[str, Any]] = payload.get("messages", [])
            last_user_idx = _extract_last_user_index(messages)
            user_text = messages[last_user_idx].get("content", "") if last_user_idx >= 0 else ""

            # 检查当前 userTurn 之后是否已经执行过 tool
            tool_messages = [
                m for m in messages[last_user_idx + 1 :] if m.get("role") == "tool"
            ]

            if tool_messages:
                # Round 2：汇总所有 role="tool" 的真实执行结果并生成最终回复
                summaries: list[str] = []
                for tm in tool_messages:
                    tool_name = tm.get("name", "unknown")
                    data = json.loads(tm.get("content", "{}"))
                    if "error" in data:
                        summaries.append(f"[{tool_name} 异常] {data['error']}")
                    elif tool_name == "get_weather":
                        summaries.append(
                            f"{data['city']}当前天气{data['condition']}，气温 {data['temperature']}{data['unit']}，湿度 {data['humidity']}"
                        )
                    elif tool_name == "calculate_math":
                        summaries.append(
                            f"算式 `{data['expression']}` 的计算结果为 {data['result']}"
                        )
                    elif tool_name == "query_employee_info":
                        if data.get("found"):
                            emp = data["employee"]
                            summaries.append(
                                f"{emp['name']}（{emp['employee_id']}）隶属{emp['department']}，担任{emp['role']}，邮箱 {emp['email']}"
                            )
                        else:
                            summaries.append(data.get("error", "未找到员工信息"))
                    else:
                        summaries.append(f"{tool_name}: {json.dumps(data, ensure_ascii=False)}")

                final_answer = "已为您调用工具完成查询：" + "；".join(summaries) + "。"
                return httpx.Response(
                    200,
                    json={
                        "id": "chatcmpl-mock-round2",
                        "model": payload.get("model", "gpt-4o-mini"),
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": final_answer},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
                    },
                )

            # Round 1：识别意图并构造标准 OpenAI tool_calls
            tool_calls: list[dict[str, Any]] = []
            call_seq = 1

            # 1) 天气意图
            for city in ("北京", "上海", "深圳", "杭州"):
                if city in user_text:
                    unit = "fahrenheit" if "华氏" in user_text else "celsius"
                    tool_calls.append(
                        {
                            "id": f"call_mock_{call_seq}",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": json.dumps({"city": city, "unit": unit}, ensure_ascii=False),
                            },
                        }
                    )
                    call_seq += 1
                    break

            # 2) 数学计算意图
            math_match = re.search(r"([0-9]+(?:\.[0-9]+)?(?:\s*[\+\-\*/%]\s*[0-9]+(?:\.[0-9]+)?|\s*\*\*?\s*[0-9]+)+|\([0-9\+\-\*/\.\s]+\)\s*[\+\-\*/]\s*[0-9\+\-\*/\.\(\)\s]+)", user_text)
            if math_match:
                expr = math_match.group(0).strip()
                tool_calls.append(
                    {
                        "id": f"call_mock_{call_seq}",
                        "type": "function",
                        "function": {
                            "name": "calculate_math",
                            "arguments": json.dumps({"expression": expr}, ensure_ascii=False),
                        },
                    }
                )
                call_seq += 1

            # 3) 员工查询意图
            emp_id_match = re.search(r"EMP-\d{3}", user_text, re.IGNORECASE)
            if emp_id_match:
                tool_calls.append(
                    {
                        "id": f"call_mock_{call_seq}",
                        "type": "function",
                        "function": {
                            "name": "query_employee_info",
                            "arguments": json.dumps({"employee_id": emp_id_match.group(0).upper()}, ensure_ascii=False),
                        },
                    }
                )
                call_seq += 1
            else:
                for name in ("陈默", "林晓", "张工", "李婷"):
                    if name in user_text:
                        tool_calls.append(
                            {
                                "id": f"call_mock_{call_seq}",
                                "type": "function",
                                "function": {
                                    "name": "query_employee_info",
                                    "arguments": json.dumps({"name": name}, ensure_ascii=False),
                                },
                            }
                        )
                        call_seq += 1
                        break

            if tool_calls:
                return httpx.Response(
                    200,
                    json={
                        "id": "chatcmpl-mock-round1",
                        "model": payload.get("model", "gpt-4o-mini"),
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
                        "usage": {"prompt_tokens": 90, "completion_tokens": 25, "total_tokens": 115},
                    },
                )

            # 无需工具的普通问答
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-mock-direct",
                    "model": payload.get("model", "gpt-4o-mini"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"收到您的消息：「{user_text}」。当前问题无需调用外部工具，我可以直接为您解答。",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80},
                },
            )

        return httpx.Response(404, json={"error": {"message": "Not Found"}})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 5. ToolCallingAgentLoop：Pure-API Function Calling 核心循环
# ---------------------------------------------------------------------------


@dataclass
class AgentRunResult:
    """单次 Agent Function Calling 运行的完整结构化结果。"""

    answer: str
    rounds: int
    executed_tools: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0


class ToolCallingAgentLoop:
    """
    Pure-API Function Calling 引擎（无 LangChain / 无 OpenAI SDK 依赖）。
    严格实现：user -> assistant(tool_calls) -> 本地工具执行 -> role='tool' -> 最终 assistant 回复。
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        transport: httpx.BaseTransport | None = None,
        max_iterations: int = 5,
        system_prompt: str = "你是智枢企业级智能体平台的 AI 助手，擅长按需调用工具解决用户问题。",
    ) -> None:
        self.registry = registry or create_default_registry()
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt

        if transport is not None:
            self._transport = transport
            self.is_mock = True
        elif not self.api_key:
            self._transport = create_mock_tool_calling_transport()
            self.is_mock = True
        else:
            self._transport = None
            self.is_mock = False

    def _call_chat_completions(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        schemas = self.registry.get_schemas()
        if schemas:
            payload["tools"] = schemas
            payload["tool_choice"] = "auto"

        client_kwargs: dict[str, Any] = {"timeout": 30.0}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        with httpx.Client(**client_kwargs) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    def run(self, user_query: str) -> AgentRunResult:
        """执行完整的 Function Calling 多轮循环直到模型产出最终文本回复。"""
        if not user_query or not user_query.strip():
            raise ValueError("用户输入不能为空")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_query.strip()},
        ]
        executed_tools: list[dict[str, Any]] = []
        total_tokens = 0

        for round_idx in range(1, self.max_iterations + 1):
            data = self._call_chat_completions(messages)
            total_tokens += data.get("usage", {}).get("total_tokens", 0)

            assistant_msg = data["choices"][0]["message"]
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                return AgentRunResult(
                    answer=assistant_msg.get("content") or "",
                    rounds=round_idx,
                    executed_tools=executed_tools,
                    messages=messages,
                    total_tokens=total_tokens,
                )

            for tc in tool_calls:
                call_id = tc["id"]
                fn_info = tc["function"]
                fn_name = fn_info["name"]
                fn_args = fn_info.get("arguments", "{}")

                tool_output = self.registry.dispatch(fn_name, fn_args)
                executed_tools.append(
                    {
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "arguments": fn_args,
                        "output": tool_output,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": tool_output,
                    }
                )

        raise RuntimeError(f"超过最大工具调用轮数限制 ({self.max_iterations})")
