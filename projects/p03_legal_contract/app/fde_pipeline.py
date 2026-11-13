"""Forward-Deployed Engineering (FDE) Pipeline for Legal Contract Review."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from typing import Any

from .llm_wiki import LegalLLMWiki
from .ontology import (
    Clause,
    Contract,
    LegalAction,
    LegalOntologyRegistry,
    Obligation,
    RiskLevel,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LegalFDEPipeline:
    """Deterministic contract review pipeline with PII masking, redlining, HITL, and audit."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})(?!\d)")
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    ACCOUNT_RE = re.compile(r"\b(?:IBAN[:\s]?[A-Z]{2}\d{2}[A-Z0-9]{8,24}|ACCT[-:\s]?\d{6,16})\b", re.IGNORECASE)

    def __init__(
        self,
        registry: LegalOntologyRegistry,
        wiki: LegalLLMWiki,
    ) -> None:
        self.registry = registry
        self.wiki = wiki
        self.audit_trail: list[dict[str, Any]] = []
        self.pii_masked_total: int = 0

    def record_audit(
        self,
        event_type: str,
        actor: str,
        target_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": _utc_now_iso(),
            "event_type": event_type,
            "actor": actor,
            "target_id": target_id,
            "details": details or {},
        }
        self.audit_trail.append(entry)
        return entry

    def mask_pii(self, text: str) -> tuple[str, int]:
        """Deterministically mask PII and sensitive account identifiers."""
        count = 0

        def _sub(pattern: re.Pattern[str], replacement: str, src: str) -> str:
            nonlocal count
            new_src, n = pattern.subn(replacement, src)
            count += n
            return new_src

        masked = _sub(self.EMAIL_RE, "[EMAIL_REDACTED]", text)
        masked = _sub(self.SSN_RE, "[ID_REDACTED]", masked)
        masked = _sub(self.ACCOUNT_RE, "[ACCOUNT_REDACTED]", masked)
        masked = _sub(self.PHONE_RE, "[PHONE_REDACTED]", masked)
        self.pii_masked_total += count
        return masked, count

    @staticmethod
    def extract_clauses(contract_id: str, masked_text: str) -> list[tuple[str, str]]:
        """Split contract text into (title, clause_text) pairs deterministically."""
        # Split on blank lines or numbered section headers like "1. " / "Section 1:"
        raw_blocks = [b.strip() for b in re.split(r"\n\s*\n+", masked_text.strip()) if b.strip()]
        if len(raw_blocks) == 1:
            # Try splitting by numbered lines if single block
            numbered = re.split(r"(?m)(?=^(?:\d+\.|Section\s+\d+[:.]))", masked_text.strip())
            candidates = [n.strip() for n in numbered if n.strip()]
            if len(candidates) > 1:
                raw_blocks = candidates

        clauses: list[tuple[str, str]] = []
        for idx, block in enumerate(raw_blocks, start=1):
            first_line = block.splitlines()[0].strip()
            title = first_line[:80] if first_line else f"Clause {idx}"
            clauses.append((title, block))
        return clauses

    @staticmethod
    def _extract_obligations(clause: Clause) -> list[Obligation]:
        obligations: list[Obligation] = []
        lower = clause.text.lower()
        if any(w in lower for w in ("shall", "must", "agrees to", "required to")):
            party: str = "mutual"
            if "vendor shall" in lower or "supplier shall" in lower or "provider shall" in lower:
                party = "vendor"
            elif "customer shall" in lower or "client shall" in lower or "buyer shall" in lower:
                party = "customer"
            due_match = re.search(r"(\d+)\s+days?", lower)
            due_days = int(due_match.group(1)) if due_match else None
            obligations.append(
                Obligation(
                    id=f"obl_{clause.id}_1",
                    clause_id=clause.id,
                    party=party,  # type: ignore[arg-type]
                    description=clause.text[:160],
                    due_days=due_days,
                    mandatory=True,
                )
            )
        return obligations

    @staticmethod
    def _overall_risk(clauses: list[Clause]) -> tuple[float, RiskLevel]:
        if not clauses:
            return 0.0, "low"
        max_score = max(c.risk_score for c in clauses)
        avg_score = sum(c.risk_score for c in clauses) / len(clauses)
        combined = round(0.7 * max_score + 0.3 * avg_score, 4)
        if max_score >= 0.85:
            level: RiskLevel = "critical"
        elif max_score >= 0.70:
            level = "high"
        elif max_score >= 0.45:
            level = "medium"
        else:
            level = "low"
        return combined, level

    def review_contract(
        self,
        contract_id: str,
        title: str,
        raw_text: str,
        counterparty: str = "Counterparty Corp.",
        jurisdiction: str = "US-NY",
        liability_cap_usd: float | None = None,
        requested_by: str = "legal_ops",
    ) -> dict[str, Any]:
        """Run full FDE contract review: PII masking -> clause extraction -> redline -> HITL."""
        masked_text, masked_count = self.mask_pii(raw_text)

        contract = Contract(
            id=contract_id,
            title=title,
            counterparty=counterparty,
            jurisdiction=jurisdiction,
            liability_cap_usd=liability_cap_usd,
            status="under_review",
        )
        self.registry.register_contract(contract)

        extracted = self.extract_clauses(contract_id, masked_text)
        reviewed_clauses: list[Clause] = []
        pending_actions: list[LegalAction] = []

        for idx, (cl_title, cl_text) in enumerate(extracted, start=1):
            cl_id = f"{contract_id}_cl_{idx}"
            clause = Clause(
                id=cl_id,
                contract_id=contract_id,
                title=cl_title,
                text=cl_text,
            )
            self.registry.register_clause(clause, auto_classify=True, auto_map=True)
            reviewed_clauses.append(clause)

            for obl in self._extract_obligations(clause):
                self.registry.register_obligation(obl)

            if clause.risk_level in ("high", "critical"):
                action = LegalAction(
                    id=f"act_{cl_id}",
                    contract_id=contract_id,
                    clause_id=cl_id,
                    action_type="GENERAL_COUNSEL_APPROVAL",
                    risk_level=clause.risk_level,
                    status="pending",
                    requested_by=requested_by,
                )
                self.registry.register_action(action)
                pending_actions.append(action)

        overall_score, overall_level = self._overall_risk(reviewed_clauses)
        requires_hitl = len(pending_actions) > 0
        contract.status = "pending_gc_approval" if requires_hitl else "approved"

        self.wiki.sync_contract(contract)
        self.wiki.append_log(
            "REVIEW",
            contract_id,
            f"clauses={len(reviewed_clauses)}, risk={overall_level}, hitl={len(pending_actions)}, pii_masked={masked_count}",
        )
        audit_entry = self.record_audit(
            event_type="CONTRACT_REVIEWED",
            actor=requested_by,
            target_id=contract_id,
            details={
                "overall_risk_score": overall_score,
                "overall_risk_level": overall_level,
                "pii_masked_count": masked_count,
                "requires_hitl": requires_hitl,
                "pending_action_ids": [a.id for a in pending_actions],
            },
        )

        return {
            "contract": contract.model_dump(),
            "masked_text": masked_text,
            "pii_masked_count": masked_count,
            "overall_risk_score": overall_score,
            "overall_risk_level": overall_level,
            "requires_hitl": requires_hitl,
            "clauses": [c.model_dump() for c in reviewed_clauses],
            "pending_actions": [a.model_dump() for a in pending_actions],
            "audit_entry": audit_entry,
        }

    def approve_action(
        self,
        action_id: str,
        decision: str,
        approver: str,
        notes: str = "",
    ) -> LegalAction:
        """Approve or reject a pending HITL General Counsel action."""
        if action_id not in self.registry.actions:
            raise KeyError(f"LegalAction '{action_id}' not found")
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")

        action = self.registry.actions[action_id]
        action.status = decision  # type: ignore[assignment]
        action.approver = approver
        action.decision_notes = notes
        action.decided_at = _utc_now_iso()

        # Update parent contract status if all actions for that contract are decided
        contract = self.registry.contracts.get(action.contract_id)
        if contract:
            contract_actions = [
                a for a in self.registry.actions.values() if a.contract_id == contract.id
            ]
            if any(a.status == "rejected" for a in contract_actions):
                contract.status = "rejected"
            elif all(a.status == "approved" for a in contract_actions):
                contract.status = "approved"
            self.wiki.sync_contract(contract)

        self.wiki.append_log(
            "HITL_DECISION",
            action_id,
            f"decision={decision}, approver={approver}",
        )
        self.record_audit(
            event_type="HITL_ACTION_DECIDED",
            actor=approver,
            target_id=action_id,
            details={
                "contract_id": action.contract_id,
                "clause_id": action.clause_id,
                "decision": decision,
                "notes": notes,
            },
        )
        return action

    def compare_contract_versions(
        self,
        contract_id: str,
        title: str,
        original_text: str,
        revised_text: str,
        requested_by: str = "legal_ops",
    ) -> dict[str, Any]:
        """Compare two contract versions and return clause risk delta + redline recommendations."""
        orig_masked, orig_pii = self.mask_pii(original_text)
        rev_masked, rev_pii = self.mask_pii(revised_text)

        def _classify_blocks(prefix: str, text: str) -> list[Clause]:
            extracted = self.extract_clauses(contract_id, text)
            items: list[Clause] = []
            for idx, (cl_title, cl_text) in enumerate(extracted, start=1):
                ctype, score, level, redline = self.registry.classify_clause_risk(cl_text)
                items.append(
                    Clause(
                        id=f"{contract_id}_{prefix}_cl_{idx}",
                        contract_id=contract_id,
                        title=cl_title,
                        clause_type=ctype,
                        text=cl_text,
                        risk_level=level,
                        risk_score=score,
                        redline_suggestion=redline,
                        extracted_cap_usd=self.registry.extract_liability_cap_usd(cl_text),
                    )
                )
            return items

        orig_clauses = _classify_blocks("v1", orig_masked)
        rev_clauses = _classify_blocks("v2", rev_masked)

        orig_score, orig_level = self._overall_risk(orig_clauses)
        rev_score, rev_level = self._overall_risk(rev_clauses)
        risk_score_delta = round(rev_score - orig_score, 4)
        if risk_score_delta < 0:
            risk_trend = "improved"
        elif risk_score_delta > 0:
            risk_trend = "worsened"
        else:
            risk_trend = "unchanged"

        max_len = max(len(orig_clauses), len(rev_clauses))
        clause_diffs: list[dict[str, Any]] = []
        redline_recommendations: list[dict[str, Any]] = []

        for idx in range(max_len):
            orig_cl = orig_clauses[idx] if idx < len(orig_clauses) else None
            rev_cl = rev_clauses[idx] if idx < len(rev_clauses) else None

            if orig_cl and not rev_cl:
                status = "removed"
                delta = round(0.0 - orig_cl.risk_score, 4)
                diff_lines: list[str] = [f"- {line}" for line in orig_cl.text.splitlines()]
                rec = "Clause removed in revised version."
            elif rev_cl and not orig_cl:
                status = "added"
                delta = round(rev_cl.risk_score - 0.0, 4)
                diff_lines = [f"+ {line}" for line in rev_cl.text.splitlines()]
                rec = rev_cl.redline_suggestion
            else:
                assert orig_cl is not None and rev_cl is not None
                status = "unchanged" if orig_cl.text == rev_cl.text else "modified"
                delta = round(rev_cl.risk_score - orig_cl.risk_score, 4)
                diff_lines = list(
                    difflib.unified_diff(
                        orig_cl.text.splitlines(),
                        rev_cl.text.splitlines(),
                        fromfile="original",
                        tofile="revised",
                        lineterm="",
                    )
                )
                rec = rev_cl.redline_suggestion
                if not rec and delta < 0:
                    rec = "Risk reduced to low; no further redline required."

            clause_title = rev_cl.title if rev_cl else (orig_cl.title if orig_cl else f"Clause {idx + 1}")
            clause_type = rev_cl.clause_type if rev_cl else (orig_cl.clause_type if orig_cl else "general")

            clause_diffs.append(
                {
                    "index": idx + 1,
                    "status": status,
                    "title": clause_title,
                    "clause_type": clause_type,
                    "original_text": orig_cl.text if orig_cl else None,
                    "revised_text": rev_cl.text if rev_cl else None,
                    "original_risk_level": orig_cl.risk_level if orig_cl else None,
                    "original_risk_score": orig_cl.risk_score if orig_cl else None,
                    "revised_risk_level": rev_cl.risk_level if rev_cl else None,
                    "revised_risk_score": rev_cl.risk_score if rev_cl else None,
                    "risk_delta": delta,
                    "redline_recommendation": rec,
                    "diff_lines": diff_lines,
                }
            )

            if rev_cl and rev_cl.redline_suggestion:
                redline_recommendations.append(
                    {
                        "clause_index": idx + 1,
                        "title": rev_cl.title,
                        "clause_type": rev_cl.clause_type,
                        "risk_level": rev_cl.risk_level,
                        "recommendation": rev_cl.redline_suggestion,
                    }
                )

        audit_entry = self.record_audit(
            event_type="CONTRACT_REDLINE_DIFF",
            actor=requested_by,
            target_id=contract_id,
            details={
                "original_risk_level": orig_level,
                "revised_risk_level": rev_level,
                "risk_score_delta": risk_score_delta,
                "risk_trend": risk_trend,
                "pii_masked_count": orig_pii + rev_pii,
            },
        )

        return {
            "contract_id": contract_id,
            "title": title,
            "original_risk_score": orig_score,
            "original_risk_level": orig_level,
            "revised_risk_score": rev_score,
            "revised_risk_level": rev_level,
            "risk_score_delta": risk_score_delta,
            "risk_trend": risk_trend,
            "pii_masked_count": orig_pii + rev_pii,
            "original_clause_count": len(orig_clauses),
            "revised_clause_count": len(rev_clauses),
            "clause_diffs": clause_diffs,
            "redline_recommendations": redline_recommendations,
            "audit_entry": audit_entry,
        }
