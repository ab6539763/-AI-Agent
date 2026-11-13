"""Legal Ontology & Deterministic Clause-Risk / Regulation Registry."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]
RegulationStatus = Literal["active", "superseded", "draft"]
ActionStatus = Literal["pending", "approved", "rejected"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Contract(BaseModel):
    id: str
    title: str
    counterparty: str = "Unknown Counterparty"
    jurisdiction: str = "US-NY"
    effective_date: str = "2026-01-01"
    liability_cap_usd: float | None = None
    status: str = "under_review"
    clauses: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Clause(BaseModel):
    id: str
    contract_id: str
    title: str
    clause_type: str = "general"
    text: str
    risk_level: RiskLevel = "low"
    risk_score: float = 0.1
    matched_regulations: list[str] = Field(default_factory=list)
    redline_suggestion: str | None = None
    extracted_cap_usd: float | None = None


class Regulation(BaseModel):
    id: str
    code: str
    title: str
    jurisdiction: str
    status: RegulationStatus = "active"
    superseded_by: str | None = None
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)


class Obligation(BaseModel):
    id: str
    clause_id: str
    party: Literal["vendor", "customer", "mutual"] = "mutual"
    description: str
    due_days: int | None = None
    mandatory: bool = True


class LegalLink(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0


class LegalAction(BaseModel):
    id: str
    contract_id: str
    clause_id: str | None = None
    action_type: str = "GENERAL_COUNSEL_APPROVAL"
    risk_level: RiskLevel = "high"
    status: ActionStatus = "pending"
    requested_by: str = "fde_pipeline"
    approver: str | None = None
    decision_notes: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    decided_at: str | None = None


class LegalOntologyRegistry:
    """In-memory deterministic Legal Ontology Registry with risk & regulation mapping."""

    def __init__(self, seed_defaults: bool = True) -> None:
        self.contracts: dict[str, Contract] = {}
        self.clauses: dict[str, Clause] = {}
        self.regulations: dict[str, Regulation] = {}
        self.obligations: dict[str, Obligation] = {}
        self.links: dict[str, LegalLink] = {}
        self.actions: dict[str, LegalAction] = {}
        if seed_defaults:
            self._seed_default_regulations()

    def _seed_default_regulations(self) -> None:
        defaults = [
            Regulation(
                id="reg_gdpr_art28",
                code="GDPR-Art28",
                title="GDPR Article 28 Data Processing Agreement",
                jurisdiction="EU",
                status="active",
                summary="Requires written DPA, subprocessor controls, and breach notification.",
                keywords=["personal data", "gdpr", "data processing", "subprocessor", "data breach", "privacy"],
            ),
            Regulation(
                id="reg_pipl_art38",
                code="PIPL-Art38",
                title="China PIPL Article 38 Cross-Border Data Transfer",
                jurisdiction="CN",
                status="active",
                summary="Governs cross-border transfer of personal information and security assessment.",
                keywords=["cross-border", "pipl", "personal information", "data transfer", "overseas"],
            ),
            Regulation(
                id="reg_ccpa_1798",
                code="CCPA-1798.100",
                title="CCPA Consumer Data & Sale Prohibition",
                jurisdiction="US-CA",
                status="active",
                summary="Restricts selling or sharing consumer personal information without opt-out.",
                keywords=["ccpa", "sell personal", "consumer data", "opt-out", "california"],
            ),
            Regulation(
                id="reg_soc2_cc6",
                code="SOC2-CC6.1",
                title="SOC 2 Logical Access & Confidentiality Controls",
                jurisdiction="GLOBAL",
                status="active",
                summary="Requires encryption, access controls, and confidentiality safeguards.",
                keywords=["confidential", "encryption", "security", "audit", "soc2", "access control"],
            ),
            Regulation(
                id="reg_civil_584",
                code="CIVIL-CODE-584",
                title="Contractual Liability & Damages Cap Standard",
                jurisdiction="CN",
                status="active",
                summary="Defines foreseeable damages and enforces reasonable liability limitations.",
                keywords=["liability", "indemnification", "damages", "cap", "unlimited"],
            ),
            Regulation(
                id="reg_eu_dpd_95",
                code="EU-DPD-95/46/EC",
                title="EU Data Protection Directive 95/46/EC",
                jurisdiction="EU",
                status="superseded",
                superseded_by="reg_gdpr_art28",
                summary="Legacy EU data protection directive replaced by GDPR in 2018.",
                keywords=["95/46/ec", "data protection directive", "safe harbor"],
            ),
        ]
        for reg in defaults:
            self.regulations[reg.id] = reg

    def add_link(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> LegalLink:
        link_id = f"lnk_{source_id}_{target_id}_{relation}".lower()
        link = LegalLink(
            id=link_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
        )
        self.links[link_id] = link
        return link

    def register_regulation(self, regulation: Regulation) -> Regulation:
        self.regulations[regulation.id] = regulation
        if regulation.superseded_by:
            self.add_link(regulation.id, regulation.superseded_by, "SUPERSEDED_BY")
        return regulation

    def register_contract(self, contract: Contract) -> Contract:
        self.contracts[contract.id] = contract
        return contract

    def register_clause(self, clause: Clause, auto_classify: bool = True, auto_map: bool = True) -> Clause:
        if auto_classify:
            ctype, score, level, redline = self.classify_clause_risk(clause.text, clause.clause_type)
            clause.clause_type = ctype
            clause.risk_score = score
            clause.risk_level = level
            if clause.redline_suggestion is None:
                clause.redline_suggestion = redline
            if clause.extracted_cap_usd is None:
                clause.extracted_cap_usd = self.extract_liability_cap_usd(clause.text)

        self.clauses[clause.id] = clause
        if clause.contract_id in self.contracts:
            contract = self.contracts[clause.contract_id]
            if clause.id not in contract.clauses:
                contract.clauses.append(clause.id)
            self.add_link(contract.id, clause.id, "CONTAINS_CLAUSE")

        if auto_map:
            self.map_clause_to_regulations(clause)
        return clause

    def register_obligation(self, obligation: Obligation) -> Obligation:
        self.obligations[obligation.id] = obligation
        self.add_link(obligation.clause_id, obligation.id, "IMPOSES_OBLIGATION")
        return obligation

    def register_action(self, action: LegalAction) -> LegalAction:
        self.actions[action.id] = action
        target = action.clause_id or action.contract_id
        self.add_link(target, action.id, "REQUIRES_APPROVAL")
        return action

    @staticmethod
    def extract_liability_cap_usd(text: str) -> float | None:
        """Deterministically extract USD cap amount from text if present."""
        lower = text.lower()
        if "unlimited liability" in lower or "no limit on liability" in lower or "uncapped liability" in lower:
            return float("inf")
        match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|m|k|thousand)?", lower)
        if not match:
            return None
        raw = float(match.group(1).replace(",", ""))
        unit = match.group(2)
        if unit in ("million", "m"):
            raw *= 1_000_000
        elif unit in ("k", "thousand"):
            raw *= 1_000
        return raw

    @staticmethod
    def classify_clause_risk(
        text: str,
        hint_type: str | None = None,
    ) -> tuple[str, float, RiskLevel, str | None]:
        """Deterministic rule-based clause type & risk classifier."""
        lower = text.lower()

        # Detect clause type
        clause_type = hint_type if hint_type and hint_type != "general" else "general"
        if clause_type == "general":
            if any(k in lower for k in ("liability", "damages", "cap on liability", "limitation of liability")):
                clause_type = "liability_cap"
            elif any(k in lower for k in ("indemnif", "hold harmless", "defend")):
                clause_type = "indemnification"
            elif any(k in lower for k in ("personal data", "gdpr", "pipl", "ccpa", "privacy", "data protection", "95/46/ec")):
                clause_type = "data_privacy"
            elif any(k in lower for k in ("terminat", "notice period", "convenience")):
                clause_type = "termination"
            elif any(k in lower for k in ("intellectual property", "ip ownership", "work made for hire", "patent")):
                clause_type = "ip_ownership"
            elif any(k in lower for k in ("confidential", "non-disclosure", "nda", "proprietary")):
                clause_type = "confidentiality"
            elif any(k in lower for k in ("governing law", "jurisdiction", "arbitration", "venue")):
                clause_type = "governing_law"

        # Critical risk patterns
        if any(
            p in lower
            for p in (
                "unlimited liability",
                "no limit on liability",
                "uncapped liability",
                "unlimited indemnification",
                "waive all gdpr",
                "waive pipl",
            )
        ):
            return (
                clause_type,
                0.95,
                "critical",
                "REDLINE: Replace uncapped/unlimited liability with a mutual cap equal to 12 months of fees paid.",
            )

        # High risk patterns
        if any(
            p in lower
            for p in (
                "sell personal data",
                "cross-border transfer without",
                "sole discretion to terminate without notice",
                "assign all pre-existing ip",
                "95/46/ec",
                "safe harbor",
                "consequential damages",
            )
        ):
            return (
                clause_type,
                0.80,
                "high",
                "REDLINE: Require statutory safeguards (GDPR Art.28 / PIPL Art.38 SCCs), 30-day termination notice, and carve out pre-existing IP.",
            )

        # Medium risk patterns
        if any(
            p in lower
            for p in (
                "auto-renew",
                "automatic renewal",
                "90 days",
                "indemnify",
                "non-compete",
                "audit right",
            )
        ):
            return (
                clause_type,
                0.55,
                "medium",
                "REDLINE: Add 30-day prior written opt-out notice for renewal and cap indemnity to direct damages.",
            )

        # Low risk default
        return (clause_type, 0.20, "low", None)

    def map_clause_to_regulations(self, clause: Clause) -> list[str]:
        """Map a clause to matching Regulation IDs and create GOVERNED_BY links."""
        lower = f"{clause.title} {clause.text} {clause.clause_type}".lower()
        matched: list[str] = []
        for reg_id, reg in self.regulations.items():
            if any(kw.lower() in lower for kw in reg.keywords):
                matched.append(reg_id)
                self.add_link(clause.id, reg_id, "GOVERNED_BY")

        # Merge any pre-specified matched_regulations without duplicates
        for existing in clause.matched_regulations:
            if existing not in matched and existing in self.regulations:
                matched.append(existing)
                self.add_link(clause.id, existing, "GOVERNED_BY")

        clause.matched_regulations = matched
        return matched
