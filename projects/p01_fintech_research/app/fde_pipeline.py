"""FDE Production Pipeline: Ontology + LLM Wiki + Financial Ratio Tool + Guardrails + HITL + Audit Trail."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional
import uuid

from app.llm_wiki import FinTechLLMWiki
from app.ontology import (
    ActionStatus,
    ComplianceAction,
    FinancialMetric,
    Issuer,
    OntologyRegistry,
    RiskSignal,
    SEVERITY_RANK,
    SeverityLevel,
)


_CN_ID_RE = re.compile(r"\b\d{17}[\dXx]\b")
_BANK_CARD_RE = re.compile(r"\b\d{16,19}\b")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_COMPLIANCE_BLOCK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("mnpi_insider_trading", re.compile(r"(insider\s+trading|mnpi|内幕消息|内幕交易|未公开重大信息)", re.I)),
    ("bypass_compliance", re.compile(r"(bypass\s+compliance|绕过风控|规避合规|伪造财报)", re.I)),
]


class FinTechFDEPipeline:
    """Forward Deployed Engineering (FDE) Production Pipeline for FinTech Research & Compliance."""

    def __init__(
        self,
        wiki: FinTechLLMWiki,
        ontology: Optional[OntologyRegistry] = None,
        audit_log_path: Optional[Path | str] = None,
    ) -> None:
        self.wiki = wiki
        self.ontology = ontology or OntologyRegistry()
        self.audit_log_path = Path(audit_log_path) if audit_log_path else (wiki.wiki_dir / "audit_trail.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.approval_queue: dict[str, ComplianceAction] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _write_audit(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "event_id": str(uuid.uuid4()),
            "timestamp": self._now_iso(),
            "event_type": event_type,
            **payload,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read_audit_trail(self) -> list[dict[str, Any]]:
        if not self.audit_log_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.audit_log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    @staticmethod
    def scan_guardrails(text: str) -> dict[str, Any]:
        findings: list[str] = []
        redacted = text

        if _CN_ID_RE.search(redacted):
            findings.append("pii_cn_id_redacted")
            redacted = _CN_ID_RE.sub("[REDACTED_CN_ID]", redacted)
        if _BANK_CARD_RE.search(redacted):
            findings.append("pii_bank_card_redacted")
            redacted = _BANK_CARD_RE.sub("[REDACTED_CARD]", redacted)
        if _PHONE_RE.search(redacted):
            findings.append("pii_phone_redacted")
            redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
        if _EMAIL_RE.search(redacted):
            findings.append("pii_email_redacted")
            redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)

        blocked = False
        for code, pattern in _COMPLIANCE_BLOCK_PATTERNS:
            if pattern.search(text):
                findings.append(f"compliance_block:{code}")
                blocked = True

        return {
            "passed": not blocked,
            "blocked": blocked,
            "redacted_text": redacted,
            "findings": findings,
        }

    def compute_financial_ratios(
        self,
        issuer_id: str,
        period: str,
        financials: dict[str, float],
        register_in_ontology: bool = True,
    ) -> dict[str, Any]:
        """Deterministic Financial Ratio Tool + Risk Threshold Evaluator."""
        total_debt = float(financials.get("total_debt", 0.0))
        equity = float(financials.get("shareholders_equity", 0.0))
        curr_assets = float(financials.get("current_assets", 0.0))
        curr_liab = float(financials.get("current_liabilities", 0.0))
        ebit = float(financials.get("ebit", 0.0))
        interest = float(financials.get("interest_expense", 0.0))
        net_income = float(financials.get("net_income", 0.0))

        ratios: dict[str, float] = {}
        if equity > 0:
            ratios["debt_to_equity"] = round(total_debt / equity, 4)
            ratios["roe"] = round(net_income / equity, 4)
        if curr_liab > 0:
            ratios["current_ratio"] = round(curr_assets / curr_liab, 4)
        if interest > 0:
            ratios["interest_coverage"] = round(ebit / interest, 4)

        triggered_risks: list[dict[str, Any]] = []
        if "debt_to_equity" in ratios and ratios["debt_to_equity"] > 2.0:
            triggered_risks.append(
                {
                    "category": "leverage",
                    "severity": SeverityLevel.HIGH,
                    "metric": "debt_to_equity",
                    "description": f"High leverage: debt_to_equity={ratios['debt_to_equity']} > 2.0",
                }
            )
        if "current_ratio" in ratios and ratios["current_ratio"] < 1.0:
            triggered_risks.append(
                {
                    "category": "liquidity",
                    "severity": SeverityLevel.HIGH,
                    "metric": "current_ratio",
                    "description": f"Liquidity stress: current_ratio={ratios['current_ratio']} < 1.0",
                }
            )
        if "interest_coverage" in ratios and ratios["interest_coverage"] < 1.5:
            triggered_risks.append(
                {
                    "category": "credit",
                    "severity": SeverityLevel.CRITICAL,
                    "metric": "interest_coverage",
                    "description": f"Severe coverage shortfall: interest_coverage={ratios['interest_coverage']} < 1.5",
                }
            )

        if register_in_ontology and issuer_id in self.ontology.issuers:
            for r_name, r_val in ratios.items():
                m_id = f"metric_{issuer_id}_{r_name}_{period}"
                self.ontology.register_metric(
                    FinancialMetric(
                        metric_id=m_id,
                        issuer_id=issuer_id,
                        name=r_name,
                        value=r_val,
                        period=period,
                    )
                )
            for idx, r_info in enumerate(triggered_risks, start=1):
                m_id = f"metric_{issuer_id}_{r_info['metric']}_{period}"
                s_id = f"sig_{issuer_id}_{r_info['category']}_{period}_{idx}"
                self.ontology.register_risk_signal(
                    RiskSignal(
                        signal_id=s_id,
                        issuer_id=issuer_id,
                        category=r_info["category"],
                        severity=r_info["severity"],
                        description=r_info["description"],
                        triggered_by_metric=m_id if m_id in self.ontology.metrics else None,
                    )
                )

        return {
            "issuer_id": issuer_id,
            "period": period,
            "ratios": ratios,
            "triggered_risks": [
                {**r, "severity": r["severity"].value} for r in triggered_risks
            ],
        }

    def ingest_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        entities: Optional[list[dict[str, Any]]] = None,
        timestamp: Optional[str] = None,
    ) -> dict[str, Any]:
        guard = self.scan_guardrails(content)
        if guard["blocked"]:
            self._write_audit(
                "INGEST_BLOCKED",
                {"doc_id": doc_id, "findings": guard["findings"]},
            )
            raise PermissionError(f"Document '{doc_id}' blocked by compliance guardrail: {guard['findings']}")

        entities = entities or []
        for ent in entities:
            eid = str(ent["id"])
            if ent.get("type", "Issuer") == "Issuer" and eid not in self.ontology.issuers:
                self.ontology.register_issuer(
                    Issuer(
                        issuer_id=eid,
                        name=ent.get("name", eid),
                        ticker=ent.get("ticker", eid.upper()[:8]),
                        sector=ent.get("sector", "FinTech"),
                        country=ent.get("country", "CN"),
                        credit_rating=ent.get("credit_rating", "A"),
                    )
                )
            period = str(ent.get("period", "2025-Q4"))
            for m_name, m_val in ent.get("metrics", {}).items():
                if eid in self.ontology.issuers:
                    m_id = f"metric_{eid}_{m_name}_{period}"
                    self.ontology.register_metric(
                        FinancialMetric(
                            metric_id=m_id,
                            issuer_id=eid,
                            name=m_name,
                            value=float(m_val),
                            period=period,
                            source_doc_id=doc_id,
                        )
                    )

        wiki_res = self.wiki.ingest(
            doc_id=doc_id,
            title=title,
            content=guard["redacted_text"],
            entities=entities,
            timestamp=timestamp,
        )
        self._write_audit(
            "INGEST_SUCCESS",
            {
                "doc_id": doc_id,
                "pages_updated": wiki_res["pages_updated"],
                "guardrail_findings": guard["findings"],
            },
        )
        return wiki_res

    def _maybe_enqueue_hitl_action(self, issuer_id: str) -> Optional[ComplianceAction]:
        signals = [s for s in self.ontology.risk_signals.values() if s.issuer_id == issuer_id]
        high_signals = [
            s for s in signals if SEVERITY_RANK[s.severity] >= SEVERITY_RANK[SeverityLevel.HIGH]
        ]
        if not high_signals:
            return None

        existing = [
            a
            for a in self.ontology.actions.values()
            if a.issuer_id == issuer_id and a.status == ActionStatus.PENDING
        ]
        if existing:
            self.approval_queue[existing[0].action_id] = existing[0]
            return existing[0]

        top_sig = max(high_signals, key=lambda s: SEVERITY_RANK[s.severity])
        action_type = (
            "FREEZE_LIMIT" if top_sig.severity == SeverityLevel.CRITICAL else "ESCALATE_REVIEW"
        )
        action = ComplianceAction(
            action_id=f"act_{issuer_id}_{len(self.ontology.actions) + 1}",
            issuer_id=issuer_id,
            action_type=action_type,
            required_role="compliance_officer",
            min_severity=SeverityLevel.HIGH,
            status=ActionStatus.PENDING,
            rationale=f"Auto-enqueued due to {top_sig.severity.value} risk: {top_sig.description}",
        )
        self.ontology.register_action(action)
        self.approval_queue[action.action_id] = action
        return action

    def run_research(
        self,
        question: str,
        issuer_id: Optional[str] = None,
        actor_role: str = "analyst",
        financials: Optional[dict[str, float]] = None,
        period: str = "2025-Q4",
    ) -> dict[str, Any]:
        guard = self.scan_guardrails(question)
        if guard["blocked"]:
            audit = self._write_audit(
                "RESEARCH_BLOCKED",
                {
                    "actor_role": actor_role,
                    "question_redacted": guard["redacted_text"],
                    "findings": guard["findings"],
                },
            )
            return {
                "status": "blocked",
                "reason": "Query blocked by compliance guardrail (MNPI / policy violation).",
                "guardrail": guard,
                "audit_event_id": audit["event_id"],
            }

        ratio_result = None
        if issuer_id and financials:
            ratio_result = self.compute_financial_ratios(
                issuer_id=issuer_id,
                period=period,
                financials=financials,
                register_in_ontology=True,
            )

        wiki_result = self.wiki.query(guard["redacted_text"])

        target_issuer = issuer_id
        if not target_issuer and wiki_result["citations"]:
            first_eid = wiki_result["citations"][0]["entity_id"]
            if first_eid in self.ontology.issuers:
                target_issuer = first_eid

        ontology_context: dict[str, Any] = {}
        enqueued_action: Optional[dict[str, Any]] = None
        if target_issuer and target_issuer in self.ontology.issuers:
            ontology_context = self.ontology.traverse_graph(target_issuer, max_depth=2)
            act = self._maybe_enqueue_hitl_action(target_issuer)
            if act is not None:
                enqueued_action = act.model_dump()

        audit = self._write_audit(
            "RESEARCH_COMPLETED",
            {
                "actor_role": actor_role,
                "issuer_id": target_issuer,
                "question_redacted": guard["redacted_text"],
                "guardrail_findings": guard["findings"],
                "citations_count": len(wiki_result["citations"]),
                "enqueued_action_id": enqueued_action["action_id"] if enqueued_action else None,
            },
        )

        return {
            "status": "completed",
            "question": guard["redacted_text"],
            "guardrail": guard,
            "wiki": wiki_result,
            "ratios": ratio_result,
            "ontology_graph": ontology_context,
            "hitl_pending_action": enqueued_action,
            "audit_event_id": audit["event_id"],
        }

    def approve_action(
        self,
        action_id: str,
        decision: str,
        actor_role: str,
        approver: str,
        comment: str = "",
    ) -> dict[str, Any]:
        decision_norm = decision.lower().strip()
        if decision_norm not in ("approve", "reject"):
            raise ValueError(f"Invalid decision '{decision}'. Must be 'approve' or 'reject'.")

        if action_id not in self.ontology.actions:
            raise KeyError(f"ComplianceAction '{action_id}' not found.")

        ok, msg = self.ontology.check_action_preconditions(action_id, actor_role)
        if not ok:
            self._write_audit(
                "HITL_PRECONDITION_FAILED",
                {
                    "action_id": action_id,
                    "actor_role": actor_role,
                    "approver": approver,
                    "reason": msg,
                },
            )
            raise PermissionError(msg)

        action = self.ontology.actions[action_id]
        action.status = ActionStatus.APPROVED if decision_norm == "approve" else ActionStatus.REJECTED
        action.approved_by = approver
        self.approval_queue[action_id] = action

        audit = self._write_audit(
            "HITL_DECISION",
            {
                "action_id": action_id,
                "decision": decision_norm,
                "status": action.status.value,
                "actor_role": actor_role,
                "approver": approver,
                "comment": comment,
            },
        )
        return {
            "action": action.model_dump(),
            "message": f"Action '{action_id}' {action.status.value.lower()} by {approver}.",
            "audit_event_id": audit["event_id"],
        }
