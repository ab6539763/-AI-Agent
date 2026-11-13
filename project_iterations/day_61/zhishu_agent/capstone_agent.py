"""Day 61 核心模块：毕业设计开发日 3 —— 多工具协同、SQLite 持久化记忆、合规脱敏与 HITL 审批编排器."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _utc_now_iso() -> str:
    """返回 UTC ISO-8601 时间戳."""
    return datetime.now(timezone.utc).isoformat()


class ApprovalStatus(str, Enum):
    """HITL 人工审批状态枚举."""

    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class FinancialMetricsInput:
    """企业财务指标输入结构体（单位：万元，百分比由工具自动计算）."""

    company_name: str
    period: str
    revenue: float
    net_profit: float
    total_assets: float
    total_liabilities: float
    shareholders_equity: float
    current_assets: float
    current_liabilities: float
    gross_profit: Optional[float] = None


@dataclass
class FinancialRatioResult:
    """财务比率计算与风险评估结果."""

    company_name: str
    period: str
    roe_pct: float
    net_profit_margin_pct: float
    gross_margin_pct: Optional[float]
    debt_to_asset_ratio_pct: float
    current_ratio: float
    asset_turnover: float
    risk_level: str
    risk_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FinancialRatioTool:
    """企业财务比率计算器工具：计算盈利能力、偿债能力、运营效率并识别高风险信号."""

    name: str = "financial_ratio_calculator"
    description: str = "计算企业 ROE、净利率、资产负债率、流动比率与资产周转率，并输出风险预警标签。"

    def calculate(self, metrics: FinancialMetricsInput) -> FinancialRatioResult:
        """执行财务比率计算，拦截非法零值/负资产输入."""
        if metrics.revenue <= 0:
            raise ValueError("营业收入 (revenue) 必须大于 0")
        if metrics.total_assets <= 0:
            raise ValueError("总资产 (total_assets) 必须大于 0")
        if metrics.shareholders_equity <= 0:
            raise ValueError("所有者权益 (shareholders_equity) 必须大于 0")
        if metrics.current_liabilities <= 0:
            raise ValueError("流动负债 (current_liabilities) 必须大于 0")
        if metrics.total_liabilities < 0 or metrics.current_assets < 0:
            raise ValueError("负债与流动资产不能为负数")

        roe_pct = round((metrics.net_profit / metrics.shareholders_equity) * 100.0, 2)
        net_margin_pct = round((metrics.net_profit / metrics.revenue) * 100.0, 2)
        gross_margin_pct = (
            round((metrics.gross_profit / metrics.revenue) * 100.0, 2)
            if metrics.gross_profit is not None
            else None
        )
        debt_to_asset_pct = round((metrics.total_liabilities / metrics.total_assets) * 100.0, 2)
        current_ratio = round(metrics.current_assets / metrics.current_liabilities, 2)
        asset_turnover = round(metrics.revenue / metrics.total_assets, 2)

        risk_flags: List[str] = []
        if debt_to_asset_pct >= 70.0:
            risk_flags.append(f"高杠杆预警：资产负债率 {debt_to_asset_pct}% >= 70%")
        if current_ratio < 1.2:
            risk_flags.append(f"短期偿债压力：流动比率 {current_ratio} < 1.2")
        if roe_pct < 5.0:
            risk_flags.append(f"盈利能力偏弱：ROE {roe_pct}% < 5%")
        if metrics.net_profit < 0:
            risk_flags.append("净利润为负：存在持续亏损风险")

        if len(risk_flags) >= 2 or metrics.net_profit < 0 or debt_to_asset_pct >= 80.0:
            risk_level = "HIGH"
        elif len(risk_flags) == 1:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return FinancialRatioResult(
            company_name=metrics.company_name,
            period=metrics.period,
            roe_pct=roe_pct,
            net_profit_margin_pct=net_margin_pct,
            gross_margin_pct=gross_margin_pct,
            debt_to_asset_ratio_pct=debt_to_asset_pct,
            current_ratio=current_ratio,
            asset_turnover=asset_turnover,
            risk_level=risk_level,
            risk_flags=risk_flags,
        )


@dataclass
class RAGDocument:
    """企业知识库文档条目."""

    doc_id: str
    title: str
    category: str
    content: str


@dataclass
class RAGSearchResult:
    """RAG 检索命中结果."""

    doc_id: str
    title: str
    category: str
    snippet: str
    score: float


def _tokenize(text: str) -> List[str]:
    """中英文混合分词：英文/数字按词切分，中文按单字与二元词组切分."""
    lower = text.lower()
    en_tokens = re.findall(r"[a-z0-9_]+", lower)
    zh_chars = re.findall(r"[\u4e00-\u9fff]", lower)
    zh_bigrams = [zh_chars[i] + zh_chars[i + 1] for i in range(len(zh_chars) - 1)]
    return en_tokens + zh_chars + zh_bigrams


class RAGSearchTool:
    """企业风控与合规知识库 RAG 检索工具（基于 TF-IDF 余弦相似度）."""

    name: str = "enterprise_rag_search"
    description: str = "从星辰数科企业风控、财税合规与高管报告规范知识库中检索最相关的政策与案例片段。"

    DEFAULT_DOCUMENTS: List[RAGDocument] = [
        RAGDocument(
            doc_id="DOC-RISK-001",
            title="企业高杠杆与流动性风控指引（2026修订版）",
            category="风险管理",
            content=(
                "资产负债率超过 70% 属于高杠杆警戒区间，超过 80% 应触发红色预警。"
                "流动比率低于 1.2 表示短期偿债能力承压，需在经营分析报告中给出债务展期或现金流回笼预案。"
            ),
        ),
        RAGDocument(
            doc_id="DOC-FIN-002",
            title="高管经营分析与 ROE 盈利质量评估标准",
            category="财务分析",
            content=(
                "净资产收益率（ROE）低于 5% 或净利率持续下滑时，需结合资产周转率拆解杜邦因子，"
                "区分行业周期性波动与核心业务盈利能力恶化。"
            ),
        ),
        RAGDocument(
            doc_id="DOC-COMP-003",
            title="智能体输出合规与 PII 个人敏感信息脱敏规范",
            category="安全合规",
            content=(
                "所有面向高管或外部发布的风险报告，必须经过 PII 脱敏网关处理，"
                "严禁明文出现手机号、身份证号、银行卡号、个人邮箱及内部 API 密钥。"
            ),
        ),
        RAGDocument(
            doc_id="DOC-HITL-004",
            title="高管风险报告发布人工审批（HITL）SOP",
            category="治理流程",
            content=(
                "任何自动生成的正式高管风险评估报告，在对外发布或归档前必须进入 HITL 人工复核节点，"
                "由风控负责人或财务总监确认数据口径并签署审批意见后方可正式发布。"
            ),
        ),
    ]

    def __init__(self, documents: Optional[List[RAGDocument]] = None) -> None:
        self.documents: List[RAGDocument] = (
            list(documents) if documents is not None else list(self.DEFAULT_DOCUMENTS)
        )

    def add_document(self, doc: RAGDocument) -> None:
        """向内存知识库追加文档."""
        self.documents.append(doc)

    def search(self, query: str, top_k: int = 3) -> List[RAGSearchResult]:
        """基于 TF-IDF 余弦相似度检索 top_k 相关知识片段."""
        query_tokens = _tokenize(query)
        if not query_tokens or not self.documents or top_k <= 0:
            return []

        doc_tokens_list = [_tokenize(f"{d.title} {d.category} {d.content}") for d in self.documents]
        num_docs = len(self.documents)

        # 计算 IDF
        df: Dict[str, int] = {}
        for tokens in doc_tokens_list:
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1

        def _tfidf_vec(tokens: List[str]) -> Dict[str, float]:
            tf: Dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            vec: Dict[str, float] = {}
            total = len(tokens) or 1
            for tok, cnt in tf.items():
                idf = math.log((num_docs + 1) / (df.get(tok, 0) + 1)) + 1.0
                vec[tok] = (cnt / total) * idf
            return vec

        q_vec = _tfidf_vec(query_tokens)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scored: List[Tuple[float, RAGDocument]] = []
        for doc, d_tokens in zip(self.documents, doc_tokens_list):
            d_vec = _tfidf_vec(d_tokens)
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
            dot = sum(q_vec.get(t, 0.0) * d_vec.get(t, 0.0) for t in q_vec)
            score = round(dot / (q_norm * d_norm), 4)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RAGSearchResult(
                doc_id=doc.doc_id,
                title=doc.title,
                category=doc.category,
                snippet=doc.content,
                score=score,
            )
            for score, doc in scored[:top_k]
        ]


class ComplianceGuard:
    """合规脱敏网关：在记忆落库与报告生成前自动识别并脱敏 PII 与密钥信息."""

    _PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
        ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[REDACTED_API_KEY]"),
        ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[REDACTED_ID_CARD]"),
        ("bank_card", re.compile(r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4,7}(?!\d)"), "[REDACTED_BANK_CARD]"),
        ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
        (
            "email",
            re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
            "[REDACTED_EMAIL]",
        ),
    ]

    def redact(self, text: str) -> Tuple[str, Dict[str, int]]:
        """对输入文本执行多类型 PII 脱敏，返回 (脱敏后文本, 各类命中计数)."""
        sanitized = text
        counts: Dict[str, int] = {}
        for label, pattern, replacement in self._PATTERNS:
            sanitized, n = pattern.subn(replacement, sanitized)
            if n > 0:
                counts[label] = n
        return sanitized, counts


@dataclass
class HITLCheckpoint:
    """HITL 人工审批检查点记录."""

    approval_id: str
    session_id: str
    status: ApprovalStatus
    report_title: str
    draft_report: str
    risk_level: str
    created_at: str
    updated_at: str
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None


@dataclass
class ExecutiveReport:
    """正式发布的高管风险评估报告."""

    report_id: str
    approval_id: str
    session_id: str
    title: str
    content: str
    risk_level: str
    published_by: str
    published_at: str


@dataclass
class OrchestratorResponse:
    """编排器单次运行/恢复返回结构."""

    session_id: str
    status: ApprovalStatus
    reply: str
    approval_id: Optional[str] = None
    financial_result: Optional[FinancialRatioResult] = None
    rag_references: List[RAGSearchResult] = field(default_factory=list)
    redaction_counts: Dict[str, int] = field(default_factory=dict)
    published_report: Optional[ExecutiveReport] = None


class SQLiteMemoryStore:
    """基于 SQLite 的多轮对话记忆、HITL 审批检查点与已发布报告持久化存储."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON conversation_messages(session_id, id);

                CREATE TABLE IF NOT EXISTS hitl_checkpoints (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_title TEXT NOT NULL,
                    draft_report TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    reviewer TEXT,
                    review_comment TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS published_reports (
                    report_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    published_by TEXT NOT NULL,
                    published_at TEXT NOT NULL
                );
                """
            )

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """写入一条脱敏后的会话消息."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages (session_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    _utc_now_iso(),
                ),
            )

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按时间顺序读取指定会话的最近 limit 条消息."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, metadata_json, created_at
                FROM conversation_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        ordered = list(reversed(rows))
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in ordered
        ]

    def save_checkpoint(self, cp: HITLCheckpoint) -> None:
        """保存新的 HITL 审批检查点."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hitl_checkpoints (
                    approval_id, session_id, status, report_title, draft_report,
                    risk_level, reviewer, review_comment, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cp.approval_id,
                    cp.session_id,
                    cp.status.value,
                    cp.report_title,
                    cp.draft_report,
                    cp.risk_level,
                    cp.reviewer,
                    cp.review_comment,
                    cp.created_at,
                    cp.updated_at,
                ),
            )

    def get_checkpoint(self, approval_id: str) -> Optional[HITLCheckpoint]:
        """根据 approval_id 查询 HITL 检查点."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hitl_checkpoints WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return HITLCheckpoint(
            approval_id=row["approval_id"],
            session_id=row["session_id"],
            status=ApprovalStatus(row["status"]),
            report_title=row["report_title"],
            draft_report=row["draft_report"],
            risk_level=row["risk_level"],
            reviewer=row["reviewer"],
            review_comment=row["review_comment"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_checkpoint_decision(
        self,
        approval_id: str,
        status: ApprovalStatus,
        reviewer: str,
        review_comment: str,
    ) -> None:
        """更新 HITL 检查点审批状态."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE hitl_checkpoints
                SET status = ?, reviewer = ?, review_comment = ?, updated_at = ?
                WHERE approval_id = ?
                """,
                (status.value, reviewer, review_comment, _utc_now_iso(), approval_id),
            )

    def save_published_report(self, report: ExecutiveReport) -> None:
        """将审批通过的高管报告正式归档发布."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO published_reports (
                    report_id, approval_id, session_id, title, content,
                    risk_level, published_by, published_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.approval_id,
                    report.session_id,
                    report.title,
                    report.content,
                    report.risk_level,
                    report.published_by,
                    report.published_at,
                ),
            )

    def list_published_reports(self, session_id: Optional[str] = None) -> List[ExecutiveReport]:
        """查询已正式发布的高管报告."""
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM published_reports WHERE session_id = ? ORDER BY published_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM published_reports ORDER BY published_at DESC"
                ).fetchall()
        return [
            ExecutiveReport(
                report_id=row["report_id"],
                approval_id=row["approval_id"],
                session_id=row["session_id"],
                title=row["title"],
                content=row["content"],
                risk_level=row["risk_level"],
                published_by=row["published_by"],
                published_at=row["published_at"],
            )
            for row in rows
        ]


class CapstoneAgentOrchestrator:
    """智枢毕业设计核心编排器：整合多工具协同、SQLite 多轮记忆、PII 合规脱敏与 HITL 审批中断/恢复."""

    def __init__(
        self,
        db_path: str | Path,
        financial_tool: Optional[FinancialRatioTool] = None,
        rag_tool: Optional[RAGSearchTool] = None,
        compliance_guard: Optional[ComplianceGuard] = None,
    ) -> None:
        self.memory = SQLiteMemoryStore(db_path)
        self.financial_tool = financial_tool or FinancialRatioTool()
        self.rag_tool = rag_tool or RAGSearchTool()
        self.compliance_guard = compliance_guard or ComplianceGuard()

    def _build_draft_report(
        self,
        sanitized_query: str,
        fin_result: Optional[FinancialRatioResult],
        rag_hits: List[RAGSearchResult],
        history_len: int,
    ) -> Tuple[str, str, str]:
        """整合财务工具与 RAG 检索结果生成高管风险评估报告草稿."""
        if fin_result is not None:
            title = f"{fin_result.company_name}（{fin_result.period}）高管风险评估报告"
            risk_level = fin_result.risk_level
            flags_text = (
                "\n".join(f"  - ⚠️ {flag}" for flag in fin_result.risk_flags)
                if fin_result.risk_flags
                else "  - ✅ 暂未触发核心财务红线"
            )
            fin_section = (
                f"### 1. 财务健康度量化指标\n"
                f"- **ROE（净资产收益率）**：{fin_result.roe_pct}%\n"
                f"- **净利率**：{fin_result.net_profit_margin_pct}%\n"
                f"- **资产负债率**：{fin_result.debt_to_asset_ratio_pct}%\n"
                f"- **流动比率**：{fin_result.current_ratio}\n"
                f"- **总资产周转率**：{fin_result.asset_turnover}\n"
                f"- **综合风险等级**：`{fin_result.risk_level}`\n"
                f"- **预警信号**：\n{flags_text}\n"
            )
        else:
            title = "企业综合风控与合规高管评估报告"
            risk_level = "MEDIUM"
            fin_section = "### 1. 财务健康度量化指标\n- 本次未提供结构化财报数据，已结合历史会话与知识库制度生成定性评估。\n"

        if rag_hits:
            rag_lines = "\n".join(
                f"- **[{hit.doc_id}] {hit.title}**（相关度 {hit.score}）：{hit.snippet}"
                for hit in rag_hits
            )
        else:
            rag_lines = "- 未检索到直接匹配的企业制度文档。"

        draft = (
            f"# {title}\n\n"
            f"- **脱敏后请求摘要**：{sanitized_query}\n"
            f"- **关联历史上下文轮次**：{history_len} 条消息\n\n"
            f"{fin_section}\n"
            f"### 2. 企业知识库合规与风控依据（RAG）\n"
            f"{rag_lines}\n\n"
            f"### 3. 治理结论\n"
            f"本报告草稿已完成 PII 合规脱敏，正在等待人工审批（HITL）后正式发布。"
        )
        sanitized_draft, _ = self.compliance_guard.redact(draft)
        return title, sanitized_draft, risk_level

    def run(
        self,
        session_id: str,
        user_query: str,
        financial_metrics: Optional[FinancialMetricsInput] = None,
        require_report_publish: bool = False,
        rag_top_k: int = 2,
    ) -> OrchestratorResponse:
        """执行一轮多工具协同编排；若涉及发布高管风险报告，则触发 HITL 中断等待审批."""
        sanitized_query, redaction_counts = self.compliance_guard.redact(user_query)
        prior_history = self.memory.get_history(session_id)
        self.memory.append_message(
            session_id=session_id,
            role="user",
            content=sanitized_query,
            metadata={"redaction_counts": redaction_counts},
        )

        fin_result: Optional[FinancialRatioResult] = None
        if financial_metrics is not None:
            fin_result = self.financial_tool.calculate(financial_metrics)

        rag_query = sanitized_query
        if fin_result is not None and fin_result.risk_flags:
            rag_query = f"{sanitized_query} {' '.join(fin_result.risk_flags)}"
        rag_hits = self.rag_tool.search(rag_query, top_k=rag_top_k)

        if require_report_publish:
            title, draft_report, risk_level = self._build_draft_report(
                sanitized_query=sanitized_query,
                fin_result=fin_result,
                rag_hits=rag_hits,
                history_len=len(prior_history),
            )
            approval_id = f"hitl-{uuid.uuid4().hex[:10]}"
            now = _utc_now_iso()
            checkpoint = HITLCheckpoint(
                approval_id=approval_id,
                session_id=session_id,
                status=ApprovalStatus.PENDING_APPROVAL,
                report_title=title,
                draft_report=draft_report,
                risk_level=risk_level,
                created_at=now,
                updated_at=now,
            )
            self.memory.save_checkpoint(checkpoint)

            pause_reply = (
                f"[HITL 中断] 已生成《{title}》草稿（风险等级：{risk_level}），"
                f"请人工复核并调用 resume(approval_id='{approval_id}', approved=True/False) 完成审批。"
            )
            self.memory.append_message(
                session_id=session_id,
                role="assistant",
                content=pause_reply,
                metadata={"approval_id": approval_id, "status": ApprovalStatus.PENDING_APPROVAL.value},
            )
            return OrchestratorResponse(
                session_id=session_id,
                status=ApprovalStatus.PENDING_APPROVAL,
                reply=pause_reply,
                approval_id=approval_id,
                financial_result=fin_result,
                rag_references=rag_hits,
                redaction_counts=redaction_counts,
            )

        # 普通多轮问答模式：直接汇总工具结果与历史上下文并返回
        parts: List[str] = [f"已结合 {len(prior_history)} 条历史上下文完成分析。"]
        if fin_result is not None:
            parts.append(
                f"财务指标（{fin_result.company_name} {fin_result.period}）："
                f"ROE={fin_result.roe_pct}%，资产负债率={fin_result.debt_to_asset_ratio_pct}%，"
                f"流动比率={fin_result.current_ratio}，风险等级={fin_result.risk_level}。"
            )
        if rag_hits:
            refs = "；".join(f"[{h.doc_id}]{h.title}" for h in rag_hits)
            parts.append(f"参考企业知识库：{refs}。")

        reply, _ = self.compliance_guard.redact(" ".join(parts))
        self.memory.append_message(
            session_id=session_id,
            role="assistant",
            content=reply,
            metadata={"status": ApprovalStatus.COMPLETED.value},
        )
        return OrchestratorResponse(
            session_id=session_id,
            status=ApprovalStatus.COMPLETED,
            reply=reply,
            financial_result=fin_result,
            rag_references=rag_hits,
            redaction_counts=redaction_counts,
        )

    def resume(
        self,
        approval_id: str,
        approved: bool,
        reviewer: str,
        comment: str = "",
    ) -> OrchestratorResponse:
        """恢复被 HITL 中断的工作流：审批通过则正式发布高管报告，拒绝则终止发布."""
        checkpoint = self.memory.get_checkpoint(approval_id)
        if checkpoint is None:
            raise KeyError(f"未找到审批检查点: {approval_id}")
        if checkpoint.status != ApprovalStatus.PENDING_APPROVAL:
            raise ValueError(
                f"审批检查点 {approval_id} 当前状态为 {checkpoint.status.value}，无法重复审批"
            )

        sanitized_comment, _ = self.compliance_guard.redact(comment)
        if approved:
            self.memory.update_checkpoint_decision(
                approval_id=approval_id,
                status=ApprovalStatus.APPROVED,
                reviewer=reviewer,
                review_comment=sanitized_comment or "同意发布",
            )
            report = ExecutiveReport(
                report_id=f"rep-{uuid.uuid4().hex[:10]}",
                approval_id=approval_id,
                session_id=checkpoint.session_id,
                title=checkpoint.report_title,
                content=checkpoint.draft_report,
                risk_level=checkpoint.risk_level,
                published_by=reviewer,
                published_at=_utc_now_iso(),
            )
            self.memory.save_published_report(report)
            reply = (
                f"[审批通过] 复核人 {reviewer} 已批准发布《{report.title}》"
                f"（report_id={report.report_id}）。"
            )
            self.memory.append_message(
                session_id=checkpoint.session_id,
                role="assistant",
                content=reply,
                metadata={"approval_id": approval_id, "report_id": report.report_id},
            )
            return OrchestratorResponse(
                session_id=checkpoint.session_id,
                status=ApprovalStatus.APPROVED,
                reply=reply,
                approval_id=approval_id,
                published_report=report,
            )

        self.memory.update_checkpoint_decision(
            approval_id=approval_id,
            status=ApprovalStatus.REJECTED,
            reviewer=reviewer,
            review_comment=sanitized_comment or "驳回发布",
        )
        reply = (
            f"[审批驳回] 复核人 {reviewer} 拒绝发布《{checkpoint.report_title}》，"
            f"原因：{sanitized_comment or '未通过风控复核'}。"
        )
        self.memory.append_message(
            session_id=checkpoint.session_id,
            role="assistant",
            content=reply,
            metadata={"approval_id": approval_id, "status": ApprovalStatus.REJECTED.value},
        )
        return OrchestratorResponse(
            session_id=checkpoint.session_id,
            status=ApprovalStatus.REJECTED,
            reply=reply,
            approval_id=approval_id,
        )
