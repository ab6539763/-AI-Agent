"""GovTech FDE (Forward-Deployed Engineering) Pipeline:
- Citizen / Enterprise PII masking
- Policy eligibility matching with exact clause citation
- Deterministic refusal on unsupported claims
- HITL case-officer sign-off
- Immutable audit trail
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .llm_wiki import GovTechLLMWiki, WikiQueryHit
from .ontology import (
    CitizenProfile,
    EligibilityEvaluation,
    GovAction,
    GovOntologyRegistry,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Regex patterns for Chinese citizen & enterprise PII
_ID_CARD_RE = re.compile(
    r"(?<!\d)(\d{6})(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}([\dXx])(?!\d)"
)
_USCC_RE = re.compile(
    r"(?<![0-9A-Za-z])([0-9A-HJ-NPQRTUWXY]{2}\d{6})[0-9A-Za-z]{8}([0-9A-Za-z]{2})(?![0-9A-Za-z])"
)
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_BANK_CARD_RE = re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)")
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])"
)


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Mask citizen and enterprise PII in free text.

    Returns (masked_text, list_of_masked_field_types).
    """
    masked_types: list[str] = []
    result = text

    if _ID_CARD_RE.search(result):
        result = _ID_CARD_RE.sub(lambda m: f"{m.group(1)}*********{m.group(5)}", result)
        masked_types.append("id_card")

    if _USCC_RE.search(result):
        result = _USCC_RE.sub(lambda m: f"{m.group(1)}************{m.group(2)}", result)
        masked_types.append("uscc")

    if _PHONE_RE.search(result):
        result = _PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", result)
        masked_types.append("phone")

    if _BANK_CARD_RE.search(result):
        result = _BANK_CARD_RE.sub(lambda m: f"{m.group(1)}********{m.group(2)}", result)
        masked_types.append("bank_card")

    if _EMAIL_RE.search(result):
        result = _EMAIL_RE.sub("[MASKED_EMAIL]", result)
        masked_types.append("email")

    return result, masked_types


def mask_identifier(identifier: str) -> str:
    """Mask a standalone Citizen ID or Enterprise USCC."""
    if len(identifier) <= 6:
        return "***"
    return f"{identifier[:4]}{'*' * (len(identifier) - 6)}{identifier[-2:]}"


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"AUD-{uuid4().hex[:10].upper()}")
    timestamp: str = Field(default_factory=_utc_now_iso)
    stage: str
    actor: str
    masked_pii_types: list[str] = Field(default_factory=list)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyAskResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: f"REQ-{uuid4().hex[:10].upper()}")
    status: Literal["answered", "refused"]
    masked_question: str
    masked_pii_types: list[str] = Field(default_factory=list)
    department: str
    answer: str
    clause_citations: list[str] = Field(default_factory=list)
    wiki_hits: list[WikiQueryHit] = Field(default_factory=list)
    eligibility_evaluations: list[EligibilityEvaluation] = Field(default_factory=list)
    pending_action: GovAction | None = None
    refusal_reason: str | None = None


class GovTechFDEPipeline:
    """End-to-end deterministic FDE pipeline for GovTech policy Q&A and benefit sign-off."""

    def __init__(
        self,
        registry: GovOntologyRegistry,
        wiki: GovTechLLMWiki,
        audit_log_path: Path | str | None = None,
        min_relevance_score: float = 0.2,
    ) -> None:
        self.registry = registry
        self.wiki = wiki
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None
        self.min_relevance_score = min_relevance_score
        self.audit_trail: list[AuditEvent] = []

    def _record_audit(
        self,
        stage: str,
        actor: str,
        summary: str,
        masked_pii_types: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            stage=stage,
            actor=actor,
            masked_pii_types=masked_pii_types or [],
            summary=summary,
            metadata=metadata or {},
        )
        self.audit_trail.append(event)
        if self.audit_log_path is not None:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        return event

    def ask(
        self,
        question: str,
        profile: CitizenProfile | None = None,
        program_id: str | None = None,
        create_hitl_action: bool = True,
    ) -> PolicyAskResponse:
        # 1. PII Masking
        masked_q, pii_types = mask_pii(question)
        actor = profile.applicant_id if profile else "anonymous"
        if profile is not None:
            masked_id = mask_identifier(profile.identifier)
            self._record_audit(
                stage="pii_masking",
                actor=actor,
                summary=f"Masked query & applicant identifier ({masked_id})",
                masked_pii_types=pii_types + ["applicant_identifier"],
            )
        else:
            self._record_audit(
                stage="pii_masking",
                actor=actor,
                summary="Masked query text",
                masked_pii_types=pii_types,
            )

        # 2. Wiki Retrieval
        raw_hits = self.wiki.query(masked_q, top_k=3)
        relevant_hits = [h for h in raw_hits if h.score >= self.min_relevance_score]

        # 3. Ontology Eligibility Evaluation
        evaluations: list[EligibilityEvaluation] = []
        if profile is not None:
            self.registry.register_profile(profile)
            evaluations = self.registry.evaluate_eligibility(profile, program_id=program_id)

        eligible_evals = [e for e in evaluations if e.eligible]

        # 4. Refusal on unsupported claims
        if not relevant_hits and not eligible_evals:
            reason = "未检索到现行有效政策依据，且申请人未满足已登记补贴项目条件，系统拒绝无依据答复或承诺。"
            self._record_audit(
                stage="refusal",
                actor=actor,
                summary=reason,
                metadata={"question": masked_q},
            )
            return PolicyAskResponse(
                status="refused",
                masked_question=masked_q,
                masked_pii_types=pii_types,
                department=self.registry.route_department(masked_q),
                answer="抱歉，知识库与政策本体中未找到支持该诉求的现行有效政策条款，无法给出肯定答复。",
                clause_citations=[],
                wiki_hits=[],
                eligibility_evaluations=evaluations,
                pending_action=None,
                refusal_reason=reason,
            )

        # 5. Collect exact clause citations & department routing
        citations: list[str] = []
        for ev in eligible_evals:
            for c in ev.exact_clauses:
                if c not in citations:
                    citations.append(c)

        for hit in relevant_hits:
            for ref in hit.clauses:
                cite = f"{hit.doc_id} {ref}"
                if cite not in citations:
                    citations.append(cite)

        department = (
            eligible_evals[0].department
            if eligible_evals
            else relevant_hits[0].department
        )

        # 6. Build deterministic grounded answer
        answer_parts: list[str] = []
        if eligible_evals:
            for ev in eligible_evals:
                answer_parts.append(
                    f"经本体规则核验，申请人符合【{ev.program_name}】（责任部门：{ev.department}），"
                    f"预计最高补贴 {ev.estimated_subsidy:.0f} 元。"
                )
        elif evaluations:
            answer_parts.append("经本体规则核验，当前申请人暂未完全满足已登记补贴项目的全部条件。")

        if relevant_hits:
            top_hit = relevant_hits[0]
            answer_parts.append(
                f"相关政策依据：《{top_hit.title}》（{top_hit.doc_id}，责任部门：{top_hit.department}）。"
            )

        if citations:
            answer_parts.append(f"引用条款：{'; '.join(citations)}。")

        # 7. HITL Case-Officer Sign-off Action Creation
        pending_action: GovAction | None = None
        if create_hitl_action and eligible_evals and profile is not None:
            best_eval = max(eligible_evals, key=lambda e: e.estimated_subsidy)
            program = self.registry.programs[best_eval.program_id]
            requires_hitl = (
                program.requires_hitl
                or best_eval.estimated_subsidy >= program.hitl_threshold_amount
            )
            action = GovAction(
                applicant_id=profile.applicant_id,
                program_id=best_eval.program_id,
                department=best_eval.department,
                action_type="subsidy_grant",
                amount=best_eval.estimated_subsidy,
                status="pending_approval" if requires_hitl else "approved",
                requires_hitl=requires_hitl,
                clause_citations=best_eval.exact_clauses,
            )
            self.registry.record_action(action)
            pending_action = action
            self._record_audit(
                stage="hitl_created",
                actor=actor,
                summary=f"Created GovAction {action.action_id} ({action.status}) for {best_eval.program_id}",
                metadata={"action_id": action.action_id, "amount": action.amount},
            )

        self._record_audit(
            stage="policy_answer",
            actor=actor,
            summary=f"Answered policy query with {len(citations)} clause citations",
            metadata={"department": department, "citations": citations},
        )

        return PolicyAskResponse(
            status="answered",
            masked_question=masked_q,
            masked_pii_types=pii_types,
            department=department,
            answer=" ".join(answer_parts),
            clause_citations=citations,
            wiki_hits=relevant_hits,
            eligibility_evaluations=evaluations,
            pending_action=pending_action,
            refusal_reason=None,
        )

    def approve_action(
        self,
        action_id: str,
        officer_id: str,
        approved: bool,
        note: str = "",
    ) -> GovAction:
        """HITL case-officer sign-off for a pending GovAction."""
        if action_id not in self.registry.actions:
            raise KeyError(f"Unknown action_id: {action_id}")
        action = self.registry.actions[action_id]
        action.status = "approved" if approved else "rejected"
        action.approved_by = officer_id
        action.decision_note = note
        action.decided_at = _utc_now_iso()

        self._record_audit(
            stage="hitl_signoff",
            actor=officer_id,
            summary=f"Case officer {officer_id} {action.status} action {action_id}",
            metadata={
                "action_id": action_id,
                "status": action.status,
                "note": note,
            },
        )
        return action

    def get_audit_trail(self) -> list[AuditEvent]:
        return list(self.audit_trail)
