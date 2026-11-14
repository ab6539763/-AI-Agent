"""Deterministic Legal Redline Playbook Engine & Obligation Calendar Extractor."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from .ontology import LegalOntologyRegistry

ObligationCategory = Literal[
    "sla",
    "notice",
    "renewal",
    "breach_notification",
    "payment",
    "audit",
    "general",
]


class PlaybookClauseEntry(BaseModel):
    id: str
    clause_type: str
    title: str
    risk_trigger: str
    standard_position: str
    fallback_position: str
    walk_away_trigger: str
    rationale: str
    keywords: list[str] = Field(default_factory=list)


class RedlineProposal(BaseModel):
    clause_type: str
    playbook_id: str
    position_tier: Literal["standard", "fallback"]
    original_text: str
    proposed_text: str
    rationale: str
    requires_gc_escalation: bool = False


class TimelineObligation(BaseModel):
    id: str
    clause_title: str
    category: ObligationCategory
    party: Literal["vendor", "customer", "mutual"] = "mutual"
    due_days: int | None = None
    due_hours: int | None = None
    due_date_iso: str | None = None
    deadline_label: str
    recurring: bool = False
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    summary: str
    source_excerpt: str


class ObligationTimeline(BaseModel):
    contract_id: str
    title: str
    effective_date: str
    total_obligations: int
    summary_counts: dict[str, int] = Field(default_factory=dict)
    obligations: list[TimelineObligation] = Field(default_factory=list)


class RedlinePlaybookEngine:
    """Offline deterministic law-firm fallback clause library & redline proposer."""

    def __init__(self) -> None:
        self._entries: dict[str, PlaybookClauseEntry] = {
            "liability_cap": PlaybookClauseEntry(
                id="pb_liability_cap",
                clause_type="liability_cap",
                title="Limitation of Liability Cap",
                risk_trigger="Uncapped/unlimited liability or liability cap below 6 months of fees.",
                standard_position=(
                    "Except for gross negligence or willful misconduct, each party's aggregate "
                    "liability arising out of or related to this Agreement shall not exceed the "
                    "total fees paid or payable by Customer in the twelve (12) months preceding "
                    "the event giving rise to liability. Neither party shall be liable for indirect, "
                    "incidental, or consequential damages."
                ),
                fallback_position=(
                    "For general claims, aggregate liability is capped at twelve (12) months of "
                    "fees paid; for data breach, confidentiality, and third-party IP indemnification "
                    "claims, a mutual super-cap of two times (2x) annual fees or $500,000 (whichever "
                    "is greater) shall apply."
                ),
                walk_away_trigger="Unlimited liability, uncapped consequential damages, or cap < 3 months fees.",
                rationale=(
                    "Eliminates existential balance-sheet exposure while preserving enhanced recovery "
                    "for data protection and IP infringement under Civil Code Art. 584 & GDPR."
                ),
                keywords=["liability", "damages", "cap", "unlimited", "uncapped", "consequential"],
            ),
            "indemnification": PlaybookClauseEntry(
                id="pb_indemnification",
                clause_type="indemnification",
                title="Mutual Indemnification",
                risk_trigger="One-sided or uncapped indemnification without defense control or notice.",
                standard_position=(
                    "Each party shall defend, indemnify, and hold harmless the other party from "
                    "third-party claims arising from: (a) bodily injury, death, or tangible property "
                    "damage caused by gross negligence or willful misconduct; and (b) infringement "
                    "of third-party intellectual property rights, provided the indemnified party "
                    "gives prompt written notice within fifteen (15) days and grants sole control "
                    "of the defense and settlement."
                ),
                fallback_position=(
                    "Vendor shall indemnify Customer against third-party IP infringement claims and "
                    "material data protection breaches caused by Vendor, subject to the Agreement's "
                    "super-cap and Customer's prompt written notice within thirty (30) days."
                ),
                walk_away_trigger="Unlimited indemnification for any breach or assumption of counterparty's own negligence.",
                rationale=(
                    "Balances third-party IP/data risk with procedural safeguards (notice + defense control) "
                    "and aligns indemnity exposure with the negotiated liability cap."
                ),
                keywords=["indemnif", "hold harmless", "defend", "third-party claim"],
            ),
            "ip_ownership": PlaybookClauseEntry(
                id="pb_ip_ownership",
                clause_type="ip_ownership",
                title="Intellectual Property Ownership",
                risk_trigger="Assignment of pre-existing IP, background tooling, or core platform rights.",
                standard_position=(
                    "Each party retains all right, title, and interest in and to its Pre-Existing IP "
                    "and Background Technology. Custom Deliverables created exclusively for Customer "
                    "under an SOW shall be owned by Customer upon full payment, excluding any Vendor "
                    "Background IP incorporated therein (which is licensed on a non-exclusive, "
                    "perpetual basis for internal business use)."
                ),
                fallback_position=(
                    "Vendor retains ownership of its core platform, methodologies, and generic tooling, "
                    "and grants Customer a worldwide, non-exclusive, perpetual, royalty-free license "
                    "to use all Deliverables for Customer's internal business operations."
                ),
                walk_away_trigger="Assignment of all Pre-Existing IP or broad work-made-for-hire over core SaaS IP.",
                rationale=(
                    "Protects core proprietary platform assets while ensuring Customer receives clear "
                    "commercial rights to bespoke deliverables."
                ),
                keywords=["intellectual property", "ip ownership", "pre-existing ip", "work made for hire", "patent"],
            ),
            "termination": PlaybookClauseEntry(
                id="pb_termination",
                clause_type="termination",
                title="Termination & Renewal Notice",
                risk_trigger="Termination without notice at sole discretion, or silent auto-renewal > 60 days.",
                standard_position=(
                    "Either party may terminate this Agreement for material breach upon thirty (30) "
                    "days' prior written notice if such breach remains uncured. Customer may terminate "
                    "for convenience upon thirty (30) days' written notice. This Agreement shall not "
                    "automatically renew unless Vendor provides written renewal reminder at least "
                    "sixty (60) days prior to term expiration."
                ),
                fallback_position=(
                    "Material breach requires thirty (30) days' written notice and cure period. "
                    "Agreement may auto-renew for successive twelve (12) month terms unless either "
                    "party delivers written non-renewal notice at least thirty (30) days prior to "
                    "the end of the then-current term."
                ),
                walk_away_trigger="Sole discretion to terminate without notice or > 90-day non-renewal lock-in.",
                rationale=(
                    "Prevents abrupt operational cut-off and eliminates trapped multi-year auto-renewals."
                ),
                keywords=["terminat", "notice period", "convenience", "auto-renew", "automatic renewal", "cure"],
            ),
        }

    def list_entries(self, clause_type: str | None = None) -> list[PlaybookClauseEntry]:
        if clause_type:
            entry = self._entries.get(clause_type)
            return [entry] if entry else []
        return list(self._entries.values())

    def get_entry(self, clause_type: str) -> PlaybookClauseEntry | None:
        return self._entries.get(clause_type)

    def propose_redline(
        self,
        clause_text: str,
        clause_type: str | None = None,
        tier: Literal["standard", "fallback"] = "standard",
    ) -> RedlineProposal:
        detected_type, _, risk_level, _ = LegalOntologyRegistry.classify_clause_risk(
            clause_text, hint_type=clause_type
        )
        resolved_type = detected_type if detected_type in self._entries else "liability_cap"
        entry = self._entries[resolved_type]
        proposed_text = entry.standard_position if tier == "standard" else entry.fallback_position

        lower = clause_text.lower()
        escalate = risk_level == "critical" or any(
            trigger in lower
            for trigger in (
                "unlimited liability",
                "uncapped liability",
                "unlimited indemnification",
                "assign all pre-existing ip",
                "sole discretion to terminate without notice",
            )
        )

        return RedlineProposal(
            clause_type=resolved_type,
            playbook_id=entry.id,
            position_tier=tier,
            original_text=clause_text,
            proposed_text=proposed_text,
            rationale=entry.rationale,
            requires_gc_escalation=escalate,
        )


class ObligationExtractor:
    """Extracts SLA, notice, renewal, payment, and breach-notification deadlines into a timeline."""

    DAYS_RE = re.compile(r"(\d+)\s*(?:calendar\s+|business\s+)?days?", re.IGNORECASE)
    HOURS_RE = re.compile(r"(\d+)\s*hours?", re.IGNORECASE)
    NET_DAYS_RE = re.compile(r"\bnet\s+(\d+)\b", re.IGNORECASE)
    SLA_PCT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%\s*(?:uptime|availability|sla)?", re.IGNORECASE)

    @staticmethod
    def _parse_effective_date(effective_date: str) -> date:
        try:
            return datetime.strptime(effective_date[:10], "%Y-%m-%d").date()
        except ValueError:
            return date(2026, 1, 1)

    @staticmethod
    def _detect_party(text: str) -> Literal["vendor", "customer", "mutual"]:
        lower = text.lower()
        vendor_hit = any(w in lower for w in ("vendor shall", "vendor must", "supplier shall", "provider shall"))
        customer_hit = any(w in lower for w in ("customer shall", "customer must", "client shall", "buyer shall"))
        if vendor_hit and not customer_hit:
            return "vendor"
        if customer_hit and not vendor_hit:
            return "customer"
        return "mutual"

    @staticmethod
    def _split_blocks(text: str) -> list[tuple[str, str]]:
        raw_blocks = [b.strip() for b in re.split(r"\n\s*\n+", text.strip()) if b.strip()]
        if len(raw_blocks) == 1:
            numbered = re.split(r"(?m)(?=^(?:\d+\.|Section\s+\d+[:.]))", text.strip())
            candidates = [n.strip() for n in numbered if n.strip()]
            if len(candidates) > 1:
                raw_blocks = candidates
        results: list[tuple[str, str]] = []
        for idx, block in enumerate(raw_blocks, start=1):
            first_line = block.splitlines()[0].strip()
            results.append((first_line[:80] if first_line else f"Clause {idx}", block))
        return results

    def extract_timeline(
        self,
        contract_id: str,
        title: str,
        text: str,
        effective_date: str = "2026-01-01",
    ) -> ObligationTimeline:
        base_date = self._parse_effective_date(effective_date)
        blocks = self._split_blocks(text)
        obligations: list[TimelineObligation] = []
        summary_counts: dict[str, int] = {
            "sla": 0,
            "notice": 0,
            "renewal": 0,
            "breach_notification": 0,
            "payment": 0,
            "audit": 0,
            "general": 0,
        }

        idx_counter = 0
        for cl_title, block in blocks:
            # Split block into sentences for granular obligation extraction
            sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", block) if s.strip()]
            for sentence in sentences:
                lower = sentence.lower()
                days_match = self.DAYS_RE.search(sentence)
                hours_match = self.HOURS_RE.search(sentence)
                net_match = self.NET_DAYS_RE.search(sentence)
                sla_match = self.SLA_PCT_RE.search(sentence)

                has_obligation_verb = any(
                    v in lower
                    for v in (
                        "shall",
                        "must",
                        "within",
                        "prior written notice",
                        "auto-renew",
                        "automatic renewal",
                        "uptime",
                        "availability",
                        "sla",
                        "net ",
                        "notice",
                        "audit",
                    )
                )
                if not has_obligation_verb:
                    continue

                category: ObligationCategory = "general"
                severity: Literal["low", "medium", "high", "critical"] = "medium"
                recurring = False

                if any(k in lower for k in ("breach", "security incident", "unauthorized access")):
                    category = "breach_notification"
                    severity = "critical"
                elif any(k in lower for k in ("auto-renew", "automatic renewal", "non-renewal", "renew")):
                    category = "renewal"
                    severity = "high"
                    recurring = True
                elif any(k in lower for k in ("uptime", "availability", "sla", "service level", "response time")) or sla_match:
                    category = "sla"
                    severity = "high"
                    recurring = True
                elif any(k in lower for k in ("notice", "cure period", "terminat")):
                    category = "notice"
                    severity = "high" if "without notice" in lower or "90" in lower else "medium"
                elif any(k in lower for k in ("invoice", "payment", "net ")) or net_match:
                    category = "payment"
                    severity = "low"
                elif any(k in lower for k in ("audit", "soc2", "inspection")):
                    category = "audit"
                    severity = "medium"
                    recurring = "annual" in lower

                due_days: int | None = None
                due_hours: int | None = None
                due_date_iso: str | None = None
                deadline_label = "Ongoing Obligation"

                if hours_match:
                    due_hours = int(hours_match.group(1))
                    due_date_iso = (
                        datetime.combine(base_date, datetime.min.time()) + timedelta(hours=due_hours)
                    ).date().isoformat()
                    deadline_label = f"{due_hours} Hours"
                elif net_match:
                    due_days = int(net_match.group(1))
                    due_date_iso = (base_date + timedelta(days=due_days)).isoformat()
                    deadline_label = f"Net {due_days} Days"
                elif days_match:
                    due_days = int(days_match.group(1))
                    due_date_iso = (base_date + timedelta(days=due_days)).isoformat()
                    deadline_label = f"{due_days} Days"
                elif sla_match:
                    deadline_label = f"{sla_match.group(1)}% SLA"
                elif "without notice" in lower:
                    due_days = 0
                    due_date_iso = base_date.isoformat()
                    deadline_label = "Immediate (0d Notice)"
                    severity = "critical"

                # Only record if it has a concrete deadline or recognized domain category
                if category == "general" and due_days is None and due_hours is None:
                    continue

                idx_counter += 1
                summary_counts[category] = summary_counts.get(category, 0) + 1
                obligations.append(
                    TimelineObligation(
                        id=f"obl_cal_{contract_id}_{idx_counter}",
                        clause_title=cl_title,
                        category=category,
                        party=self._detect_party(sentence),
                        due_days=due_days,
                        due_hours=due_hours,
                        due_date_iso=due_date_iso,
                        deadline_label=deadline_label,
                        recurring=recurring,
                        severity=severity,
                        summary=sentence[:180],
                        source_excerpt=sentence,
                    )
                )

        # Sort by due_days / due_hours ascending (immediate/shortest deadlines first)
        def _sort_key(item: TimelineObligation) -> tuple[int, int]:
            if item.due_hours is not None:
                return (0, item.due_hours)
            if item.due_days is not None:
                return (1, item.due_days)
            return (2, 999999)

        obligations.sort(key=_sort_key)

        return ObligationTimeline(
            contract_id=contract_id,
            title=title,
            effective_date=base_date.isoformat(),
            total_obligations=len(obligations),
            summary_counts=summary_counts,
            obligations=obligations,
        )
