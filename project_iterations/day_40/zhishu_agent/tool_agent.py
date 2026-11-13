"""Day 40 核心模块：LangChain `@tool` 装饰器、`StructuredTool`、`ToolCallingAgent` 与 `AgentExecutor`.

本模块以零外部大模型密钥依赖的方式，完整复现并工程化实现了 LangChain Tool-Calling Agent 生态：
1. `@tool` 装饰器：自动提取函数名、Docstring 与类型注解生成 JSON Schema。
2. `StructuredTool`：统一工具封装、参数校验与 OpenAI Function Calling Schema 导出。
3. `ToolCallingAgent` & `AgentExecutor`：标准 `AgentAction` / `AgentFinish` 编排循环，
   返回 `{"output": ..., "intermediate_steps": [...]}`。
4. 企业级安全沙箱工具集：Mock Tavily 联网搜索、基于 `ast` 的安全数学求值器、
   以及防路径穿越（Path Traversal）的沙箱文件读写工具。
"""

from __future__ import annotations

import ast
import inspect
import math
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Literal,
    Sequence,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """将 Python 类型注解转换为标准 JSON Schema 描述."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Union:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_schema(non_none[0])
        return {"anyOf": [_python_type_to_json_schema(a) for a in non_none]}

    if origin is Literal:
        values = list(args)
        inferred_type = "string"
        if values and isinstance(values[0], bool):
            inferred_type = "boolean"
        elif values and isinstance(values[0], int):
            inferred_type = "integer"
        elif values and isinstance(values[0], float):
            inferred_type = "number"
        return {"type": inferred_type, "enum": values}

    if origin in (list, tuple, set):
        item_schema = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    if origin is dict:
        return {"type": "object"}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is list:
        return {"type": "array"}
    if annotation is dict:
        return {"type": "object"}

    return {"type": "string"}


def _parse_arg_descriptions(docstring: str) -> dict[str, str]:
    """从 Google 风格 Docstring 的 Args 段落提取参数说明."""
    descriptions: dict[str, str] = {}
    in_args = False
    for raw_line in docstring.splitlines():
        stripped = raw_line.strip()
        if stripped in ("Args:", "Parameters:"):
            in_args = True
            continue
        if in_args:
            if stripped.endswith(":") and not raw_line.startswith(" " * 4):
                break
            match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*(.+)$", stripped)
            if match:
                descriptions[match.group(1)] = match.group(2).strip()
    return descriptions


@dataclass
class StructuredTool:
    """结构化工具封装，支持 JSON Schema 导出、参数校验与安全调用."""

    name: str
    description: str
    func: Callable[..., Any]
    args_schema: dict[str, Any] = field(default_factory=dict)
    return_direct: bool = False

    @classmethod
    def from_function(
        cls,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        return_direct: bool = False,
    ) -> StructuredTool:
        """从普通 Python 函数自动解析名称、Docstring 与类型注解构建 StructuredTool."""
        tool_name = name or func.__name__
        doc = inspect.getdoc(func) or ""
        tool_desc = (description if description is not None else doc).strip()
        if not tool_desc:
            raise ValueError(f"工具 '{tool_name}' 必须提供非空 Docstring 或 description 描述。")

        sig = inspect.signature(func)
        try:
            type_hints = get_type_hints(func)
        except Exception:
            type_hints = {}

        arg_docs = _parse_arg_descriptions(doc)
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            annotation = type_hints.get(param_name, param.annotation)
            prop_schema = _python_type_to_json_schema(annotation)
            if param_name in arg_docs:
                prop_schema["description"] = arg_docs[param_name]

            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                if isinstance(param.default, (str, int, float, bool)) or param.default is None:
                    prop_schema["default"] = param.default

            properties[param_name] = prop_schema

        args_schema = {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        return cls(
            name=tool_name,
            description=tool_desc,
            func=func,
            args_schema=args_schema,
            return_direct=return_direct,
        )

    def to_openai_tool(self) -> dict[str, Any]:
        """导出为标准 OpenAI / LangChain Function Calling 工具定义."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema,
            },
        }

    def invoke(self, tool_input: dict[str, Any] | str) -> Any:
        """执行工具调用，支持字典参数或单字符串快捷参数."""
        if isinstance(tool_input, str):
            required_fields = self.args_schema.get("required", [])
            props = list(self.args_schema.get("properties", {}).keys())
            target_key = required_fields[0] if required_fields else (props[0] if props else None)
            if target_key is None:
                return self.func()
            return self.func(**{target_key: tool_input})

        if not isinstance(tool_input, dict):
            raise TypeError(f"工具 '{self.name}' 期望 dict 或 str 输入，实际收到 {type(tool_input).__name__}")

        required_fields = self.args_schema.get("required", [])
        missing = [field_name for field_name in required_fields if field_name not in tool_input]
        if missing:
            raise ValueError(f"工具 '{self.name}' 缺少必填参数: {', '.join(missing)}")

        return self.func(**tool_input)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """允许被装饰函数继续像普通函数一样直接调用."""
        return self.func(*args, **kwargs)


def tool(
    name_or_func: str | Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    return_direct: bool = False,
) -> Any:
    """将 Python 函数转换为 `StructuredTool` 的 `@tool` 装饰器.

    支持 `@tool` 无参装饰，也支持 `@tool("custom_name", return_direct=True)` 带参装饰。
    """
    if callable(name_or_func):
        return StructuredTool.from_function(
            name_or_func,
            name=name,
            description=description,
            return_direct=return_direct,
        )

    custom_name = name_or_func if isinstance(name_or_func, str) else name

    def _decorator(func: Callable[..., Any]) -> StructuredTool:
        return StructuredTool.from_function(
            func,
            name=custom_name,
            description=description,
            return_direct=return_direct,
        )

    return _decorator


@dataclass
class AgentAction:
    """Agent 决策出的单次工具调用动作."""

    tool: str
    tool_input: dict[str, Any] | str
    log: str = ""


@dataclass
class AgentFinish:
    """Agent 完成推理并返回最终结果."""

    return_values: dict[str, Any]
    log: str = ""


# ---------------------------------------------------------------------------
# 企业级安全沙箱工具集
# ---------------------------------------------------------------------------

_MOCK_TAVILY_KB: list[dict[str, str]] = [
    {
        "title": "LangChain Tool Calling & @tool 最佳实践",
        "url": "https://docs.zhishu.ai/langchain/tool-calling",
        "content": "LangChain 通过 @tool 装饰器自动解析函数名、Docstring 与类型注解生成 JSON Schema，结合 AgentExecutor 返回 output 与 intermediate_steps。",
    },
    {
        "title": "智枢企业级智能体平台 v0.4.0 架构规范",
        "url": "https://wiki.zhishu.ai/v0.4.0/agent-sandbox",
        "content": "智枢平台要求所有工具必须经过参数 Schema 校验、AST 安全沙箱求值与工作区路径隔离，严禁直接执行 eval() 或越权读写系统目录。",
    },
    {
        "title": "Tavily Search API 智能体联网检索指南",
        "url": "https://docs.tavily.com/guides/agent-search",
        "content": "Tavily 为 AI Agent 提供低延迟、结构化的网页搜索结果（包含 title、url、content 摘要），适用于实时事实核查与外部知识补充。",
    },
]


@tool
def tavily_search(query: str, max_results: int = 3) -> list[dict[str, str]]:
    """Mock Tavily 联网搜索引擎，根据查询关键词返回结构化网页摘要列表.

    Args:
        query: 搜索关键词或自然语言问题。
        max_results: 最多返回的结果条数，默认为 3。
    """
    q_lower = query.lower()
    keywords = [tok for tok in re.split(r"[\s,，。?？]+", q_lower) if tok]
    scored: list[tuple[int, dict[str, str]]] = []
    for item in _MOCK_TAVILY_KB:
        haystack = f"{item['title']} {item['content']}".lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [item for _, item in scored[:max_results]]
    if not results:
        results = [
            {
                "title": f"Tavily Mock Result: {query}",
                "url": "https://mock.tavily.local/search",
                "content": f"关于 '{query}' 的模拟联网检索摘要：建议结合企业内部知识库与工具调用进行验证。",
            }
        ]
    return results[:max_results]


_SAFE_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_SAFE_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_FUNCS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
}

_SAFE_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


def _eval_ast_node(node: ast.AST) -> float | int:
    """递归求值受限白名单 AST 节点，彻底阻断代码注入."""
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"安全拦截：不允许的常量类型 {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_BIN_OPS:
            raise ValueError(f"安全拦截：不支持的二元运算符 {op_type.__name__}")
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if op_type is ast.Pow and abs(right) > 1000:
            raise ValueError("安全拦截：幂指数绝对值过大（上限 1000）")
        return _SAFE_BIN_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_UNARY_OPS:
            raise ValueError(f"安全拦截：不支持的一元运算符 {op_type.__name__}")
        return _SAFE_UNARY_OPS[op_type](_eval_ast_node(node.operand))

    if isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[node.id]
        raise ValueError(f"安全拦截：禁止访问未授权标识符 '{node.id}'")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
            raise ValueError("安全拦截：仅允许调用白名单数学函数 (abs, round, min, max, pow, sqrt)")
        if node.keywords:
            raise ValueError("安全拦截：数学函数调用不支持关键字参数")
        args = [_eval_ast_node(arg) for arg in node.args]
        return _SAFE_FUNCS[node.func.id](*args)

    raise ValueError(f"安全拦截：禁止的 AST 语法节点 {type(node).__name__}")


@tool
def safe_math_eval(expression: str) -> float | int:
    """使用 AST 白名单安全计算数学表达式，彻底替代危险的 eval().

    Args:
        expression: 待计算的数学表达式，例如 "(12 + 8) * 3 / 2" 或 "sqrt(16) + pi"。
    """
    if not expression or not expression.strip():
        raise ValueError("数学表达式不能为空")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"数学表达式语法错误: {exc}") from exc
    return _eval_ast_node(tree)


def create_sandbox_file_tools(sandbox_root: Path) -> tuple[StructuredTool, StructuredTool]:
    """创建绑定到指定沙箱目录的安全文件读写工具 `(read_file, write_file)`.

    任何试图通过 `../` 或绝对路径访问 `sandbox_root` 之外的文件都会触发 `PermissionError`。
    """
    root_resolved = Path(sandbox_root).resolve()
    root_resolved.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise ValueError("文件路径不能为空")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise PermissionError(f"安全拦截：禁止使用绝对路径 '{relative_path}' 越权访问沙箱外目录")
        target = (root_resolved / candidate).resolve()
        if not target.is_relative_to(root_resolved):
            raise PermissionError(f"安全拦截：检测到路径穿越攻击 '{relative_path}'，已拒绝访问")
        return target

    @tool
    def read_file(file_path: str) -> str:
        """从安全沙箱工作区读取 UTF-8 文本文件内容.

        Args:
            file_path: 相对于沙箱根目录的文件路径。
        """
        target = _resolve_safe_path(file_path)
        if not target.exists():
            raise FileNotFoundError(f"沙箱中不存在文件: {file_path}")
        return target.read_text(encoding="utf-8")

    @tool
    def write_file(file_path: str, content: str) -> str:
        """将 UTF-8 文本内容安全写入沙箱工作区指定文件.

        Args:
            file_path: 相对于沙箱根目录的文件路径。
            content: 要写入的文本内容。
        """
        target = _resolve_safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已安全写入 {len(content)} 字符至沙箱文件: {file_path}"

    return read_file, write_file


# ---------------------------------------------------------------------------
# ToolCallingAgent & AgentExecutor
# ---------------------------------------------------------------------------


class ToolCallingAgent:
    """支持工具 Schema 绑定与 ReAct/Tool-Calling 决策循环的智能体."""

    def __init__(
        self,
        tools: Sequence[StructuredTool],
        llm: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]] | None = None,
        system_prompt: str = "你是智枢企业级智能体，请合理调用工具解决用户问题。",
    ) -> None:
        self.tools = list(tools)
        self.tool_schemas = [t.to_openai_tool() for t in self.tools]
        self.llm = llm
        self.system_prompt = system_prompt

    def _build_messages(
        self,
        user_input: str,
        intermediate_steps: list[tuple[AgentAction, Any]],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        for action, observation in intermediate_steps:
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [{"name": action.tool, "arguments": action.tool_input}],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "name": action.tool,
                    "content": str(observation),
                }
            )
        return messages

    def _mock_plan(
        self,
        user_input: str,
        intermediate_steps: list[tuple[AgentAction, Any]],
    ) -> AgentAction | AgentFinish:
        """内置确定性 Mock 规划器，无需真实 API Key 即可完整演示多步 Tool Calling."""
        available = {t.name for t in self.tools}

        if intermediate_steps:
            last_action, last_obs = intermediate_steps[-1]
            # 若用户要求保存/写入文件且尚未写文件
            if (
                ("写入" in user_input or "保存" in user_input)
                and "write_file" in available
                and last_action.tool != "write_file"
            ):
                match_file = re.search(r"([a-zA-Z0-9_.-]+\.(?:txt|md|json))", user_input)
                filename = match_file.group(1) if match_file else "agent_output.txt"
                return AgentAction(
                    tool="write_file",
                    tool_input={"file_path": filename, "content": str(last_obs)},
                    log=f"将工具 {last_action.tool} 的结果写入沙箱文件 {filename}",
                )
            return AgentFinish(
                return_values={"output": f"已完成工具 [{last_action.tool}] 调用，结果：{last_obs}"},
                log="基于工具观察结果生成最终回答",
            )

        # 第一步意图路由
        math_match = re.search(r"([0-9+\-*/().%\s]{3,}|sqrt\([^)]+\))", user_input)
        if ("计算" in user_input or math_match) and "safe_math_eval" in available:
            expr = math_match.group(1).strip() if math_match else user_input
            return AgentAction(
                tool="safe_math_eval",
                tool_input={"expression": expr},
                log=f"调用 safe_math_eval 计算表达式: {expr}",
            )

        if ("读取" in user_input or "查看文件" in user_input) and "read_file" in available:
            match_file = re.search(r"([^\s\"']+\.(?:txt|md|json|py))", user_input)
            target = match_file.group(1) if match_file else "note.txt"
            return AgentAction(
                tool="read_file",
                tool_input={"file_path": target},
                log=f"调用 read_file 读取沙箱文件: {target}",
            )

        if ("搜索" in user_input or "查询" in user_input or "tavily" in user_input.lower()) and "tavily_search" in available:
            return AgentAction(
                tool="tavily_search",
                tool_input={"query": user_input, "max_results": 2},
                log="调用 tavily_search 执行联网检索",
            )

        return AgentFinish(
            return_values={"output": f"直接回答：{user_input}"},
            log="无需调用工具，直接回复",
        )

    def plan(
        self,
        intermediate_steps: list[tuple[AgentAction, Any]],
        user_input: str,
    ) -> AgentAction | AgentFinish:
        """根据用户输入与历史执行步骤，规划下一步工具调用或最终输出."""
        if self.llm is None:
            return self._mock_plan(user_input, intermediate_steps)

        messages = self._build_messages(user_input, intermediate_steps)
        response = self.llm(messages, self.tool_schemas)
        tool_calls = response.get("tool_calls") or []
        if tool_calls:
            call = tool_calls[0]
            return AgentAction(
                tool=call["name"],
                tool_input=call.get("arguments", {}),
                log=response.get("content", "") or f"LLM 请求调用工具 {call['name']}",
            )
        return AgentFinish(
            return_values={"output": response.get("content", "")},
            log="LLM 返回最终回答",
        )


class AgentExecutor:
    """负责驱动 `ToolCallingAgent` 执行 `Plan -> Act -> Observe` 循环的执行器."""

    def __init__(
        self,
        agent: ToolCallingAgent,
        tools: Sequence[StructuredTool],
        max_iterations: int = 5,
        return_intermediate_steps: bool = True,
    ) -> None:
        self.agent = agent
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.return_intermediate_steps = return_intermediate_steps

    def invoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行智能体任务并返回 `{"output": ..., "intermediate_steps": [...]}`."""
        user_input = str(inputs.get("input", ""))
        intermediate_steps: list[tuple[AgentAction, Any]] = []

        for _ in range(self.max_iterations):
            decision = self.agent.plan(intermediate_steps, user_input)
            if isinstance(decision, AgentFinish):
                result: dict[str, Any] = {"output": decision.return_values.get("output", "")}
                if self.return_intermediate_steps:
                    result["intermediate_steps"] = intermediate_steps
                return result

            tool_obj = self.tools.get(decision.tool)
            if tool_obj is None:
                observation: Any = f"Error: 未注册的工具 '{decision.tool}'"
            else:
                try:
                    observation = tool_obj.invoke(decision.tool_input)
                except Exception as exc:
                    observation = f"Error: {type(exc).__name__}: {exc}"

            intermediate_steps.append((decision, observation))

            if tool_obj is not None and tool_obj.return_direct:
                result = {"output": observation}
                if self.return_intermediate_steps:
                    result["intermediate_steps"] = intermediate_steps
                return result

        timeout_result: dict[str, Any] = {
            "output": f"达到最大迭代次数 ({self.max_iterations})，任务提前终止。"
        }
        if self.return_intermediate_steps:
            timeout_result["intermediate_steps"] = intermediate_steps
        return timeout_result
