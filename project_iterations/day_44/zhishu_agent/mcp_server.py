"""Day 44 核心模块：JSON-RPC 2.0 MCP Server/Client 与双层记忆架构 (v0.4.0-day44)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# 标准 JSON-RPC 2.0 错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_jsonrpc_request(
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int | str = 1,
) -> dict[str, Any]:
    """构造标准 JSON-RPC 2.0 请求报文."""
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


def make_jsonrpc_response(
    request_id: int | str | None,
    result: Any,
) -> dict[str, Any]:
    """构造标准 JSON-RPC 2.0 成功响应报文."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def make_jsonrpc_error(
    request_id: int | str | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """构造标准 JSON-RPC 2.0 错误响应报文."""
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error_obj,
    }


@dataclass
class MCPTool:
    """MCP 工具定义."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    """MCP 资源定义."""

    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"
    content_or_reader: str | Callable[[], str] = ""

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }

    def read(self) -> str:
        if callable(self.content_or_reader):
            return str(self.content_or_reader())
        return str(self.content_or_reader)


class MCPServer:
    """基于 JSON-RPC 2.0 的轻量级 MCP Server 实现."""

    def __init__(
        self,
        name: str = "zhishu-mcp-server",
        version: str = "0.4.0-day44",
        protocol_version: str = "2024-11-05",
    ) -> None:
        self.name = name
        self.version = version
        self.protocol_version = protocol_version
        self.initialized = False
        self.client_info: dict[str, Any] = {}
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        """注册一个 MCP 工具."""
        if not name or not isinstance(name, str):
            raise ValueError("工具名称必须为非空字符串")
        self._tools[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        content_or_reader: str | Callable[[], str],
        mime_type: str = "text/plain",
    ) -> None:
        """注册一个 MCP 资源."""
        if not uri or not isinstance(uri, str):
            raise ValueError("资源 URI 必须为非空字符串")
        self._resources[uri] = MCPResource(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
            content_or_reader=content_or_reader,
        )

    def handle_message(self, message: str | dict[str, Any]) -> dict[str, Any]:
        """处理单条 JSON-RPC 2.0 请求并返回响应字典."""
        if isinstance(message, str):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError as exc:
                return make_jsonrpc_error(None, PARSE_ERROR, f"JSON 解析失败: {exc}")
        elif isinstance(message, dict):
            payload = message
        else:
            return make_jsonrpc_error(None, INVALID_REQUEST, "请求体必须为 JSON 对象或字符串")

        if not isinstance(payload, dict):
            return make_jsonrpc_error(None, INVALID_REQUEST, "JSON-RPC 请求必须为对象")

        req_id = payload.get("id")
        if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
            return make_jsonrpc_error(req_id, INVALID_REQUEST, "无效的 JSON-RPC 2.0 请求格式")

        method: str = payload["method"]
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return make_jsonrpc_error(req_id, INVALID_PARAMS, "params 必须为字典对象")

        try:
            if method == "initialize":
                return make_jsonrpc_response(req_id, self._handle_initialize(params))
            if method == "tools/list":
                return make_jsonrpc_response(req_id, self._handle_tools_list())
            if method == "tools/call":
                return make_jsonrpc_response(req_id, self._handle_tools_call(params))
            if method == "resources/list":
                return make_jsonrpc_response(req_id, self._handle_resources_list())
            if method == "resources/read":
                return make_jsonrpc_response(req_id, self._handle_resources_read(params))
            return make_jsonrpc_error(req_id, METHOD_NOT_FOUND, f"未知方法: {method}")
        except ValueError as exc:
            return make_jsonrpc_error(req_id, INVALID_PARAMS, str(exc))
        except Exception as exc:  # noqa: BLE001
            return make_jsonrpc_error(req_id, INTERNAL_ERROR, f"服务端内部错误: {exc}")

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self.initialized = True
        self.client_info = dict(params.get("clientInfo", {}))
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }

    def _handle_tools_list(self) -> dict[str, Any]:
        return {
            "tools": [tool.to_descriptor() for tool in self._tools.values()],
        }

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("tools/call 缺少有效的工具名称 'name'")
        if tool_name not in self._tools:
            raise ValueError(f"未注册的 MCP 工具: {tool_name}")

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("tools/call 的 'arguments' 必须为字典")

        tool = self._tools[tool_name]
        required_fields = tool.input_schema.get("required", [])
        for req_field in required_fields:
            if req_field not in arguments:
                raise ValueError(f"工具 '{tool_name}' 缺少必填参数: {req_field}")

        try:
            raw_result = tool.handler(arguments)
            text_output = (
                raw_result
                if isinstance(raw_result, str)
                else json.dumps(raw_result, ensure_ascii=False)
            )
            return {
                "content": [{"type": "text", "text": text_output}],
                "isError": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "content": [{"type": "text", "text": f"工具执行失败: {exc}"}],
                "isError": True,
            }

    def _handle_resources_list(self) -> dict[str, Any]:
        return {
            "resources": [res.to_descriptor() for res in self._resources.values()],
        }

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise ValueError("resources/read 缺少有效的资源 'uri'")
        if uri not in self._resources:
            raise ValueError(f"未注册的 MCP 资源: {uri}")
        resource = self._resources[uri]
        return {
            "contents": [
                {
                    "uri": resource.uri,
                    "mimeType": resource.mime_type,
                    "text": resource.read(),
                }
            ]
        }


class MCPClientError(RuntimeError):
    """MCP Client 收到的 JSON-RPC 错误."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPClient:
    """基于 JSON-RPC 2.0 的轻量级 MCP Client 实现."""

    def __init__(
        self,
        server: MCPServer | None = None,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if transport is not None:
            self._transport = transport
        elif server is not None:
            self._transport = server.handle_message
        else:
            raise ValueError("必须提供 server 或 transport 之一")
        self._next_id = 0
        self.server_capabilities: dict[str, Any] = {}
        self.server_info: dict[str, Any] = {}

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 JSON-RPC 2.0 请求并解析结果."""
        self._next_id += 1
        req = make_jsonrpc_request(method=method, params=params, request_id=self._next_id)
        resp = self._transport(req)
        if "error" in resp:
            err = resp["error"]
            raise MCPClientError(
                code=err.get("code", INTERNAL_ERROR),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )
        return dict(resp.get("result", {}))

    def initialize(
        self,
        client_name: str = "zhishu-agent-host",
        client_version: str = "0.4.0-day44",
    ) -> dict[str, Any]:
        """执行 MCP 握手初始化."""
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        self.server_capabilities = dict(result.get("capabilities", {}))
        self.server_info = dict(result.get("serverInfo", {}))
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """获取服务端注册的所有工具列表."""
        result = self.request("tools/list")
        return list(result.get("tools", []))

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用指定 MCP 工具."""
        return self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )

    def list_resources(self) -> list[dict[str, Any]]:
        """获取服务端注册的所有资源列表."""
        result = self.request("resources/list")
        return list(result.get("resources", []))

    def read_resource(self, uri: str) -> dict[str, Any]:
        """读取指定 URI 的 MCP 资源内容."""
        return self.request("resources/read", {"uri": uri})


def _tokenize_for_similarity(text: str) -> Counter[str]:
    """轻量级中英文混合分词与字符二元组统计，用于离线语义/词法相似度计算."""
    normalized = text.lower().strip()
    if not normalized:
        return Counter()
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
    bigrams = [
        normalized[i : i + 2]
        for i in range(len(normalized) - 1)
        if not normalized[i].isspace() and not normalized[i + 1].isspace()
    ]
    return Counter(words + bigrams)


def _cosine_similarity(c1: Counter[str], c2: Counter[str]) -> float:
    if not c1 or not c2:
        return 0.0
    common = set(c1.keys()) & set(c2.keys())
    dot = sum(c1[k] * c2[k] for k in common)
    norm1 = math.sqrt(sum(v * v for v in c1.values()))
    norm2 = math.sqrt(sum(v * v for v in c2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


@dataclass
class MemoryTurn:
    """短期滑动窗口中的单轮对话记录."""

    role: str
    content: str
    timestamp: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class DualMemoryManager:
    """智枢双层记忆管理器：短期滑动窗口 + SQLite 长期键值/语义记忆."""

    def __init__(self, db_path: str | Path, window_size: int = 6) -> None:
        if window_size < 1:
            raise ValueError("window_size 必须 >= 1")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.window_size = window_size
        self._short_term: dict[str, deque[MemoryTurn]] = {}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    mem_key TEXT NOT NULL,
                    mem_value TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(namespace, mem_key)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ltm_namespace
                ON long_term_memory (namespace)
                """
            )

    # ---- 短期记忆（滑动窗口） ----

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """向指定会话的短期滑动窗口追加一轮消息."""
        if session_id not in self._short_term:
            self._short_term[session_id] = deque(maxlen=self.window_size)
        self._short_term[session_id].append(
            MemoryTurn(role=role, content=content, metadata=metadata or {})
        )

    def get_short_term(self, session_id: str) -> list[dict[str, Any]]:
        """获取指定会话当前窗口内的全部短期记忆."""
        if session_id not in self._short_term:
            return []
        return [turn.to_dict() for turn in self._short_term[session_id]]

    def clear_short_term(self, session_id: str) -> None:
        """清空指定会话的短期记忆."""
        self._short_term.pop(session_id, None)

    # ---- 长期记忆（SQLite 键值 + 语义相似度检索） ----

    def remember(
        self,
        key: str,
        value: str,
        *,
        namespace: str = "default",
        tags: list[str] | None = None,
    ) -> None:
        """写入或更新一条长期记忆."""
        if not key:
            raise ValueError("长期记忆 key 不能为空")
        now = _utc_now_iso()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memory (namespace, mem_key, mem_value, tags_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, mem_key) DO UPDATE SET
                    mem_value = excluded.mem_value,
                    tags_json = excluded.tags_json,
                    updated_at = excluded.updated_at
                """,
                (namespace, key, value, tags_json, now, now),
            )

    def recall_key(
        self,
        key: str,
        *,
        namespace: str = "default",
    ) -> dict[str, Any] | None:
        """按键精确检索长期记忆."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT namespace, mem_key, mem_value, tags_json, created_at, updated_at
                FROM long_term_memory
                WHERE namespace = ? AND mem_key = ?
                """,
                (namespace, key),
            ).fetchone()
        if row is None:
            return None
        return {
            "namespace": row["namespace"],
            "key": row["mem_key"],
            "value": row["mem_value"],
            "tags": json.loads(row["tags_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def search_long_term(
        self,
        query: str,
        *,
        namespace: str = "default",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """基于词法/二元组余弦相似度检索最相关的长期记忆."""
        if top_k < 1:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT namespace, mem_key, mem_value, tags_json, created_at, updated_at
                FROM long_term_memory
                WHERE namespace = ?
                """,
                (namespace,),
            ).fetchall()

        query_vec = _tokenize_for_similarity(query)
        scored: list[dict[str, Any]] = []
        for row in rows:
            tags = json.loads(row["tags_json"])
            doc_text = f"{row['mem_key']} {row['mem_value']} {' '.join(tags)}"
            score = _cosine_similarity(query_vec, _tokenize_for_similarity(doc_text))
            scored.append(
                {
                    "namespace": row["namespace"],
                    "key": row["mem_key"],
                    "value": row["mem_value"],
                    "tags": tags,
                    "score": round(score, 4),
                    "updated_at": row["updated_at"],
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def forget(self, key: str, *, namespace: str = "default") -> bool:
        """删除指定 key 的长期记忆."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM long_term_memory WHERE namespace = ? AND mem_key = ?",
                (namespace, key),
            )
            return cursor.rowcount > 0

    def count_long_term(self, *, namespace: str | None = None) -> int:
        """统计长期记忆条数."""
        with self._connect() as conn:
            if namespace is None:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM long_term_memory").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM long_term_memory WHERE namespace = ?",
                    (namespace,),
                ).fetchone()
        return int(row["cnt"])

    def build_context(
        self,
        session_id: str,
        query: str,
        *,
        namespace: str = "default",
        top_k: int = 3,
    ) -> dict[str, Any]:
        """融合短期滑动窗口与长期语义记忆，生成 Agent 上下文."""
        return {
            "session_id": session_id,
            "namespace": namespace,
            "short_term": self.get_short_term(session_id),
            "long_term": self.search_long_term(query, namespace=namespace, top_k=top_k),
        }


def create_memory_enabled_mcp_server(
    db_path: str | Path,
    window_size: int = 6,
) -> tuple[MCPServer, DualMemoryManager]:
    """创建预装记忆工具与企业配置资源的 MCPServer 与 DualMemoryManager."""
    memory = DualMemoryManager(db_path=db_path, window_size=window_size)
    server = MCPServer(name="zhishu-memory-mcp", version="0.4.0-day44")

    server.register_tool(
        name="memory_store",
        description="向智枢长期记忆库写入或更新一条键值对记忆",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆唯一键"},
                "value": {"type": "string", "description": "记忆内容"},
                "namespace": {"type": "string", "description": "租户或用户命名空间"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["key", "value"],
        },
        handler=lambda args: (
            memory.remember(
                key=args["key"],
                value=args["value"],
                namespace=args.get("namespace", "default"),
                tags=args.get("tags", []),
            )
            or {"status": "stored", "key": args["key"]}
        ),
    )

    server.register_tool(
        name="memory_recall",
        description="按精确键名从长期记忆库检索记忆",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "namespace": {"type": "string", "description": "命名空间"},
            },
            "required": ["key"],
        },
        handler=lambda args: memory.recall_key(
            key=args["key"],
            namespace=args.get("namespace", "default"),
        )
        or {"found": False, "key": args["key"]},
    )

    server.register_tool(
        name="memory_search",
        description="按自然语言查询语义检索最相关的长期记忆",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题或关键词"},
                "namespace": {"type": "string", "description": "命名空间"},
                "top_k": {"type": "integer", "description": "返回条数"},
            },
            "required": ["query"],
        },
        handler=lambda args: memory.search_long_term(
            query=args["query"],
            namespace=args.get("namespace", "default"),
            top_k=int(args.get("top_k", 3)),
        ),
    )

    server.register_resource(
        uri="memory://stats",
        name="记忆库运行统计",
        description="实时返回长期记忆条目数与短期窗口配置",
        mime_type="application/json",
        content_or_reader=lambda: json.dumps(
            {
                "long_term_count": memory.count_long_term(),
                "window_size": memory.window_size,
            },
            ensure_ascii=False,
        ),
    )

    server.register_resource(
        uri="config://zhishu/agent",
        name="智枢智能体协议配置",
        description="智枢平台 MCP 协议与记忆治理策略",
        mime_type="application/json",
        content_or_reader=json.dumps(
            {
                "platform": "ZhiShu-Agent",
                "version": "0.4.0-day44",
                "protocol": "MCP/JSON-RPC-2.0",
                "memory_architecture": "DualMemory(SlidingWindow + SQLite)",
            },
            ensure_ascii=False,
        ),
    )

    return server, memory
