"""Day 62 Capstone 全栈 FastAPI 应用：SSE 流式输出 + 混合 RAG + HITL 人工审批 + SQLite 持久化。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

DEFAULT_DAY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND_DIR = DEFAULT_DAY_DIR / "frontend"
DEFAULT_DB_PATH = DEFAULT_DAY_DIR / "data" / "zhishu_capstone.db"


class SessionNotFoundError(KeyError):
    """会话 ID 不存在时抛出。"""


class ApprovalNotFoundError(KeyError):
    """审批单 ID 不存在时抛出。"""


class InvalidApprovalStateError(ValueError):
    """审批单已处理，禁止重复审批时抛出。"""


class CitationItem(BaseModel):
    """混合检索命中引用条目。"""

    index: int
    doc_id: str
    title: str
    source: str
    snippet: str
    score: float


class ChatStreamRequest(BaseModel):
    """SSE 流式对话请求体。"""

    query: str = Field(..., description="用户输入的问题或业务指令")
    session_id: str | None = Field(default=None, description="可选会话 ID，不传则自动生成")
    top_k: int = Field(default=3, ge=1, le=8, description="混合 RAG 召回文档条数")


class ApprovalRequest(BaseModel):
    """HITL 高风险动作审批请求体。"""

    approval_id: str = Field(..., description="待审批单据 ID")
    approved: bool = Field(..., description="True 表示批准执行，False 表示拒绝拦截")
    reviewer: str = Field(default="合规总监", description="审批人姓名或角色")
    comment: str = Field(default="", description="审批意见或拒绝理由")


class ApprovalResponse(BaseModel):
    """HITL 审批结果响应体。"""

    approval_id: str
    session_id: str
    action_type: str
    risk_level: str
    status: str
    reviewer: str
    comment: str
    final_message: str
    resolved_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_sse(event: str, data: dict[str, Any]) -> str:
    """将数据编码为标准 Server-Sent Events (SSE) 帧。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _mask_pii(text: str) -> str:
    """对输入文本中的身份证、银行卡、手机号、邮箱执行无冲突脱敏。"""
    masked = re.sub(
        r"(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)",
        r"\1********\2",
        text,
    )
    masked = re.sub(
        r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)",
        lambda m: f"{m.group(1)}{'*' * (len(m.group(0)) - 8)}{m.group(2)}",
        masked,
    )
    masked = re.sub(
        r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)",
        r"\1****\2",
        masked,
    )
    masked = re.sub(
        r"([A-Za-z0-9._%+-]{1,2})[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        r"\1***@\2",
        masked,
    )
    return masked


def _tokenize_mixed(text: str) -> list[str]:
    """中英混合分词：英文按词切分，中文按单字与二元组（bigram）切分。"""
    lowered = text.lower()
    en_tokens = re.findall(r"[a-z0-9_]+", lowered)
    zh_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    zh_bigrams = [zh_chars[i] + zh_chars[i + 1] for i in range(len(zh_chars) - 1)]
    return en_tokens + zh_chars + zh_bigrams


class HybridFinancialRAG:
    """企业财报与合规知识库混合检索器（BM25 关键词 + TF-IDF 余弦向量 + RRF 融合）。"""

    DEFAULT_DOCS: list[dict[str, str]] = [
        {
            "doc_id": "FIN-2026-Q1",
            "title": "智枢科技 2026 年第一季度财报核心摘要",
            "source": "财务部/2026Q1_财报.pdf#P3",
            "content": (
                "2026 年 Q1 智枢科技实现营业收入 4.86 亿元，同比增长 31.4%；"
                "综合毛利率提升至 64.2%，其中企业级 AI 智能体订阅收入占比达 58%。"
                "研发费用投入 1.12 亿元，研发费用率 23.0%，经营性现金流净额为 9,400 万元。"
            ),
        },
        {
            "doc_id": "FIN-2025-AR",
            "title": "2025 年度应收账款与现金流健康度报告",
            "source": "财务部/2025年度审计报告.pdf#P18",
            "content": (
                "截至 2025 年末，公司应收账款周转天数为 46 天，较上年缩短 8 天；"
                "账龄 1 年以上应收账款坏账准备计提比例严格维持在 15% 以上，流动性风险可控。"
            ),
        },
        {
            "doc_id": "COMP-AI-001",
            "title": "企业生成式 AI 合规与双备案管理规范",
            "source": "法务合规部/AI_合规手册_v3.md#S2",
            "content": (
                "依据《生成式人工智能服务管理暂行办法》，对外发布的金融与财报分析服务必须完成"
                "算法备案与大模型上线双备案（备案号 BeiAn-ZhiShu-2026-001）。"
                "所有输入输出日志均需经过 PII 脱敏，严禁明文留存身份证、银行卡与手机号。"
            ),
        },
        {
            "doc_id": "COMP-HITL-002",
            "title": "高风险财务操作 Human-in-the-Loop 审批制度",
            "source": "内控审计部/资金与披露内控红线.md#S4",
            "content": (
                "涉及大额资金划拨（单笔超过 5 万元）、对外发布财报公告、或批量导出未脱敏财务明细时，"
                "AI 智能体必须自动挂起任务并触发 HITL 人工审批流程，经合规总监或 CFO 批准后方可执行。"
            ),
        },
        {
            "doc_id": "SEC-DATA-003",
            "title": "数据安全与提示词注入防御基线",
            "source": "安全运维中心/LLM_网关基线.md#S1",
            "content": (
                "网关层对 Ignore previous instructions、导出系统提示词、越权查询数据库等"
                "提示词注入行为实施毫秒级拦截，并记录请求 SHA-256 摘要用于安全审计追溯。"
            ),
        },
    ]

    def __init__(self, docs: list[dict[str, str]] | None = None) -> None:
        self.docs: list[dict[str, str]] = list(docs) if docs is not None else list(self.DEFAULT_DOCS)
        self._doc_tokens: list[list[str]] = []
        self._doc_tfs: list[Counter[str]] = []
        self._idf: dict[str, float] = {}
        self._rebuild_index()

    def add_document(self, doc_id: str, title: str, source: str, content: str) -> None:
        """向混合检索索引动态追加企业文档。"""
        self.docs.append(
            {"doc_id": doc_id, "title": title, "source": source, "content": content}
        )
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._doc_tokens = [
            _tokenize_mixed(f"{d['title']} {d['content']}") for d in self.docs
        ]
        self._doc_tfs = [Counter(tokens) for tokens in self._doc_tokens]
        n_docs = max(len(self.docs), 1)
        df: Counter[str] = Counter()
        for tf in self._doc_tfs:
            for term in tf.keys():
                df[term] += 1
        self._idf = {
            term: math.log((n_docs + 1.0) / (freq + 0.5)) + 1.0
            for term, freq in df.items()
        }

    def _bm25_scores(self, query_tokens: list[str]) -> list[float]:
        avg_len = sum(len(t) for t in self._doc_tokens) / max(len(self._doc_tokens), 1)
        k1, b = 1.5, 0.75
        scores: list[float] = []
        for tokens, tf in zip(self._doc_tokens, self._doc_tfs):
            doc_len = max(len(tokens), 1)
            s = 0.0
            for qt in query_tokens:
                if qt not in tf:
                    continue
                f = tf[qt]
                idf = self._idf.get(qt, 1.0)
                s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / max(avg_len, 1.0)))
            scores.append(s)
        return scores

    def _vector_cosine_scores(self, query_tokens: list[str]) -> list[float]:
        q_tf = Counter(query_tokens)
        q_vec = {t: c * self._idf.get(t, 1.0) for t, c in q_tf.items()}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1e-9
        scores: list[float] = []
        for tf in self._doc_tfs:
            d_vec = {t: c * self._idf.get(t, 1.0) for t, c in tf.items()}
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1e-9
            dot = sum(q_vec[t] * d_vec[t] for t in q_vec if t in d_vec)
            scores.append(dot / (q_norm * d_norm))
        return scores

    def search(self, query: str, top_k: int = 3) -> list[CitationItem]:
        """执行 BM25 + 向量余弦双路召回，并使用 RRF (k=60) 融合排序。"""
        q_tokens = _tokenize_mixed(query)
        if not q_tokens or not self.docs:
            return []

        bm25 = self._bm25_scores(q_tokens)
        vec = self._vector_cosine_scores(q_tokens)

        bm25_rank = sorted(range(len(self.docs)), key=lambda i: bm25[i], reverse=True)
        vec_rank = sorted(range(len(self.docs)), key=lambda i: vec[i], reverse=True)

        rrf_scores: dict[int, float] = {i: 0.0 for i in range(len(self.docs))}
        for rank, idx in enumerate(bm25_rank, start=1):
            rrf_scores[idx] += 1.0 / (60 + rank)
        for rank, idx in enumerate(vec_rank, start=1):
            rrf_scores[idx] += 1.0 / (60 + rank)

        ranked_indices = sorted(
            range(len(self.docs)),
            key=lambda i: (rrf_scores[i], bm25[i] + vec[i]),
            reverse=True,
        )[:top_k]

        results: list[CitationItem] = []
        for display_idx, doc_idx in enumerate(ranked_indices, start=1):
            doc = self.docs[doc_idx]
            results.append(
                CitationItem(
                    index=display_idx,
                    doc_id=doc["doc_id"],
                    title=doc["title"],
                    source=doc["source"],
                    snippet=doc["content"],
                    score=round(rrf_scores[doc_idx] * 100, 2),
                )
            )
        return results


class CapstoneStore:
    """基于 SQLite 的全栈会话历史与 HITL 审批持久化存储。"""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    compliance_status TEXT NOT NULL DEFAULT 'PASS',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewer TEXT NOT NULL DEFAULT '',
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def ensure_session(self, session_id: str, title: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, title[:60], now, now),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (now, session_id),
                )

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        compliance_status: str = "PASS",
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, citations_json, compliance_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    json.dumps(citations or [], ensure_ascii=False),
                    compliance_status,
                    now,
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def create_approval(
        self,
        session_id: str,
        action_type: str,
        risk_level: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        approval_id = f"apr-{uuid.uuid4().hex[:10]}"
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, session_id, action_type, risk_level, summary,
                    payload_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    approval_id,
                    session_id,
                    action_type,
                    risk_level,
                    summary,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
        return {
            "approval_id": approval_id,
            "session_id": session_id,
            "action_type": action_type,
            "risk_level": risk_level,
            "summary": summary,
            "payload": payload,
            "status": "pending",
            "created_at": now,
        }

    def resolve_approval(
        self,
        approval_id: str,
        approved: bool,
        reviewer: str,
        comment: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        new_status = "approved" if approved else "rejected"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ApprovalNotFoundError(f"Approval '{approval_id}' not found")
            if row["status"] != "pending":
                raise InvalidApprovalStateError(
                    f"Approval '{approval_id}' is already '{row['status']}'"
                )
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, reviewer = ?, comment = ?, resolved_at = ?
                WHERE approval_id = ?
                """,
                (new_status, reviewer, comment, now, approval_id),
            )
            return {
                "approval_id": approval_id,
                "session_id": row["session_id"],
                "action_type": row["action_type"],
                "risk_level": row["risk_level"],
                "summary": row["summary"],
                "status": new_status,
                "reviewer": reviewer,
                "comment": comment,
                "resolved_at": now,
            }

    def get_history(self, session_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            sess = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if sess is None:
                raise SessionNotFoundError(f"Session '{session_id}' not found")

            msg_rows = conn.execute(
                "SELECT id, role, content, citations_json, compliance_status, created_at "
                "FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            apr_rows = conn.execute(
                "SELECT approval_id, action_type, risk_level, summary, payload_json, "
                "status, reviewer, comment, created_at, resolved_at "
                "FROM approvals WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()

        return {
            "session_id": sess["session_id"],
            "title": sess["title"],
            "created_at": sess["created_at"],
            "updated_at": sess["updated_at"],
            "messages": [
                {
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "citations": json.loads(r["citations_json"]),
                    "compliance_status": r["compliance_status"],
                    "created_at": r["created_at"],
                }
                for r in msg_rows
            ],
            "approvals": [
                {
                    "approval_id": r["approval_id"],
                    "action_type": r["action_type"],
                    "risk_level": r["risk_level"],
                    "summary": r["summary"],
                    "payload": json.loads(r["payload_json"]),
                    "status": r["status"],
                    "reviewer": r["reviewer"],
                    "comment": r["comment"],
                    "created_at": r["created_at"],
                    "resolved_at": r["resolved_at"],
                }
                for r in apr_rows
            ],
        }


class CapstoneAgent:
    """智枢企业财报与合规分析智能体：串联安全过滤、混合 RAG、SSE 流式输出与 HITL 审批。"""

    INJECTION_PATTERNS = (
        "ignore previous instructions",
        "system prompt",
        "drop table",
        "绕过合规",
        "关闭脱敏",
    )

    HITL_RULES: list[tuple[str, tuple[str, ...], str]] = [
        ("fund_transfer", ("划拨", "转账", "付款", "打款"), "高风险资金划拨操作需经内控人工审批"),
        ("public_disclosure", ("对外披露", "发布财报", "发布公告", "对外公告"), "对外财报披露需经合规总监复核批准"),
        ("data_export", ("批量导出", "导出明文", "下载全量"), "敏感财务/客户数据导出需经数据安全官审批"),
    ]

    def __init__(self, store: CapstoneStore, rag: HybridFinancialRAG | None = None) -> None:
        self.store = store
        self.rag = rag or HybridFinancialRAG()

    def _check_injection(self, query: str) -> bool:
        lowered = query.lower()
        return any(pat in lowered for pat in self.INJECTION_PATTERNS)

    def _detect_hitl(self, query: str) -> tuple[str, str] | None:
        for action_type, keywords, summary in self.HITL_RULES:
            if any(kw in query for kw in keywords):
                return action_type, summary
        return None

    def stream_chat(
        self,
        query: str,
        session_id: str | None = None,
        top_k: int = 3,
    ) -> Generator[str, None, None]:
        """执行完整智能体分析并以 SSE 帧格式流式输出。"""
        sid = session_id or f"sess-{uuid.uuid4().hex[:10]}"
        masked_query = _mask_pii(query.strip())
        self.store.ensure_session(sid, title=masked_query)
        self.store.add_message(sid, role="user", content=masked_query)

        # 1. 合规网关安全预检
        yield _format_sse(
            "status",
            {"stage": "compliance_check", "message": "正在执行 PII 脱敏与安全合规预检..."},
        )
        if self._check_injection(masked_query):
            blocked_msg = (
                "【安全网关拦截】检测到高危提示词注入或越权指令，请求已被合规网关阻断并记入审计日志。"
            )
            self.store.add_message(
                sid,
                role="assistant",
                content=blocked_msg,
                compliance_status="BLOCKED",
            )
            yield _format_sse("token", {"token": blocked_msg})
            yield _format_sse(
                "done",
                {"session_id": sid, "status": "blocked", "approval_id": None},
            )
            return

        # 2. 混合 RAG 双路检索
        yield _format_sse(
            "status",
            {"stage": "hybrid_rag", "message": "正在执行 BM25 + 向量双路混合检索与 RRF 重排..."},
        )
        citations = self.rag.search(masked_query, top_k=top_k)
        citations_dicts = [c.model_dump() for c in citations]
        yield _format_sse("citations", {"citations": citations_dicts})

        # 3. 构造基于引用证据的回答并流式输出
        yield _format_sse(
            "status",
            {"stage": "generating", "message": "正在生成可追溯财报合规分析结论..."},
        )
        if citations:
            evidence_lines = [
                f"[{c.index}] 依据《{c.title}》（{c.source}）：{c.snippet}"
                for c in citations[:2]
            ]
            answer = (
                f"针对您的分析请求「{masked_query}」，智枢智能体已完成混合检索与合规核验：\n\n"
                + "\n".join(evidence_lines)
                + "\n\n综合研判：上述指标与制度条款均已通过企业知识库交叉校验。"
            )
        else:
            answer = f"已完成对「{masked_query}」的合规核验，暂未检索到高相关度历史财报片段。"

        hitl_match = self._detect_hitl(masked_query)
        approval_record: dict[str, Any] | None = None
        if hitl_match is not None:
            action_type, summary = hitl_match
            approval_record = self.store.create_approval(
                session_id=sid,
                action_type=action_type,
                risk_level="HIGH",
                summary=summary,
                payload={"masked_query": masked_query, "citations_count": len(citations)},
            )
            answer += (
                f"\n\n⚠️ 【HITL 人工审批挂起】该请求触发高风险操作（{action_type}），"
                f"审批单号 `{approval_record['approval_id']}` 已生成，请人工确认批准或拒绝。"
            )

        # 按固定粒度流式推送 token 事件
        chunk_size = 18
        for i in range(0, len(answer), chunk_size):
            yield _format_sse("token", {"token": answer[i : i + chunk_size]})

        self.store.add_message(
            sid,
            role="assistant",
            content=answer,
            citations=citations_dicts,
            compliance_status="AWAITING_APPROVAL" if approval_record else "PASS",
        )

        if approval_record is not None:
            yield _format_sse("hitl_required", approval_record)
            yield _format_sse(
                "done",
                {
                    "session_id": sid,
                    "status": "awaiting_approval",
                    "approval_id": approval_record["approval_id"],
                },
            )
        else:
            yield _format_sse(
                "done",
                {"session_id": sid, "status": "completed", "approval_id": None},
            )

    def resolve_hitl(self, req: ApprovalRequest) -> ApprovalResponse:
        """处理 HITL 人工审批决定并持久化恢复结果。"""
        resolved = self.store.resolve_approval(
            approval_id=req.approval_id,
            approved=req.approved,
            reviewer=req.reviewer,
            comment=req.comment,
        )
        if req.approved:
            final_msg = (
                f"✅ 【审批已通过】审批人「{req.reviewer}」已批准操作 `{resolved['action_type']}`"
                f"（单号 {req.approval_id}）。备注：{req.comment or '准予执行'}。任务已恢复并完成闭环。"
            )
        else:
            final_msg = (
                f"🛑 【审批已拒绝】审批人「{req.reviewer}」已拦截操作 `{resolved['action_type']}`"
                f"（单号 {req.approval_id}）。理由：{req.comment or '不符合内控要求'}。操作已安全终止。"
            )

        self.store.add_message(
            resolved["session_id"],
            role="system",
            content=final_msg,
            compliance_status="APPROVED" if req.approved else "REJECTED",
        )
        return ApprovalResponse(
            approval_id=resolved["approval_id"],
            session_id=resolved["session_id"],
            action_type=resolved["action_type"],
            risk_level=resolved["risk_level"],
            status=resolved["status"],
            reviewer=resolved["reviewer"],
            comment=resolved["comment"],
            final_message=final_msg,
            resolved_at=resolved["resolved_at"],
        )


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    frontend_dir: str | Path = DEFAULT_FRONTEND_DIR,
) -> FastAPI:
    """构建隔离配置的 Day 62 Capstone FastAPI 应用实例。"""
    application = FastAPI(
        title="智枢企业财报与合规智能分析台",
        version="v1.0.0-day62",
        description="Capstone Dev Day 4: Full-Stack UI + FastAPI SSE + Hybrid RAG + HITL + SQLite",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    store = CapstoneStore(db_path=db_path)
    agent = CapstoneAgent(store=store)
    frontend_path = Path(frontend_dir)

    @application.get("/", response_class=HTMLResponse)
    def serve_frontend() -> HTMLResponse:
        index_file = frontend_path / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Frontend index.html not found")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": "v1.0.0-day62",
            "service": "zhishu-capstone",
        }

    @application.post("/api/v1/capstone/chat/stream")
    def chat_stream(req: ChatStreamRequest) -> StreamingResponse:
        if not req.query or not req.query.strip():
            raise HTTPException(status_code=400, detail="query must not be empty")
        return StreamingResponse(
            agent.stream_chat(
                query=req.query,
                session_id=req.session_id,
                top_k=req.top_k,
            ),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @application.post("/api/v1/capstone/approve", response_model=ApprovalResponse)
    def approve_action(req: ApprovalRequest) -> ApprovalResponse:
        try:
            return agent.resolve_hitl(req)
        except ApprovalNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidApprovalStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/v1/capstone/history/{session_id}")
    def get_history(session_id: str) -> dict[str, Any]:
        try:
            return store.get_history(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return application


app = create_app()
