"""FinTech Domain Ontology: Entities, Links, Schema Validation, Traversal, and Precondition Checks."""

from __future__ import annotations

from collections import deque
from enum import Enum
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    ISSUER = "Issuer"
    FINANCIAL_METRIC = "FinancialMetric"
    RISK_SIGNAL = "RiskSignal"
    COMPLIANCE_ACTION = "ComplianceAction"


class LinkType(str, Enum):
    HAS_METRIC = "HAS_METRIC"
    TRIGGERS_RISK = "TRIGGERS_RISK"
    REQUIRES_ACTION = "REQUIRES_ACTION"
    PEER_OF = "PEER_OF"
    MITIGATED_BY = "MITIGATED_BY"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_RANK: dict[SeverityLevel, int] = {
    SeverityLevel.LOW: 1,
    SeverityLevel.MEDIUM: 2,
    SeverityLevel.HIGH: 3,
    SeverityLevel.CRITICAL: 4,
}


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


ALLOWED_RATINGS = {
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "B",
    "CCC",
    "D",
}

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-:.]{1,63}$")


def _validate_id(value: str, field_name: str) -> str:
    if not _ID_PATTERN.match(value):
        raise ValueError(
            f"Invalid {field_name} '{value}': must be 2-64 chars starting with alphanumeric."
        )
    return value


class Issuer(BaseModel):
    issuer_id: str
    name: str = Field(..., min_length=1, max_length=200)
    ticker: str = Field(..., min_length=1, max_length=32)
    sector: str = Field(..., min_length=1, max_length=100)
    country: str = Field(default="CN", min_length=2, max_length=16)
    credit_rating: str = Field(default="A")

    @field_validator("issuer_id")
    @classmethod
    def check_issuer_id(cls, v: str) -> str:
        return _validate_id(v, "issuer_id")

    @field_validator("credit_rating")
    @classmethod
    def check_rating(cls, v: str) -> str:
        upper = v.upper()
        if upper not in ALLOWED_RATINGS:
            raise ValueError(f"Unsupported credit_rating '{v}'. Allowed: {sorted(ALLOWED_RATINGS)}")
        return upper


class FinancialMetric(BaseModel):
    metric_id: str
    issuer_id: str
    name: str = Field(..., min_length=1, max_length=100)
    value: float
    unit: str = Field(default="ratio", max_length=32)
    period: str = Field(..., min_length=4, max_length=32)
    source_doc_id: Optional[str] = None

    @field_validator("metric_id")
    @classmethod
    def check_metric_id(cls, v: str) -> str:
        return _validate_id(v, "metric_id")

    @field_validator("issuer_id")
    @classmethod
    def check_issuer_id(cls, v: str) -> str:
        return _validate_id(v, "issuer_id")


class RiskSignal(BaseModel):
    signal_id: str
    issuer_id: str
    category: str = Field(..., pattern=r"^(liquidity|leverage|compliance|credit|market)$")
    severity: SeverityLevel
    description: str = Field(..., min_length=1, max_length=500)
    triggered_by_metric: Optional[str] = None

    @field_validator("signal_id")
    @classmethod
    def check_signal_id(cls, v: str) -> str:
        return _validate_id(v, "signal_id")


class ComplianceAction(BaseModel):
    action_id: str
    issuer_id: str
    action_type: str = Field(
        ...,
        pattern=r"^(FREEZE_LIMIT|ESCALATE_REVIEW|DISCLOSURE_CHECK|WATCHLIST_ADD)$",
    )
    required_role: str = Field(default="compliance_officer", min_length=2, max_length=64)
    min_severity: SeverityLevel = SeverityLevel.HIGH
    status: ActionStatus = ActionStatus.PENDING
    rationale: str = Field(..., min_length=1, max_length=500)
    approved_by: Optional[str] = None

    @field_validator("action_id")
    @classmethod
    def check_action_id(cls, v: str) -> str:
        return _validate_id(v, "action_id")


class OntologyLink(BaseModel):
    source_id: str
    target_id: str
    relation: LinkType
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


# Allowed (source_type, target_type) pairs per LinkType
LINK_SCHEMA_RULES: dict[LinkType, set[tuple[EntityType, EntityType]]] = {
    LinkType.HAS_METRIC: {(EntityType.ISSUER, EntityType.FINANCIAL_METRIC)},
    LinkType.TRIGGERS_RISK: {
        (EntityType.FINANCIAL_METRIC, EntityType.RISK_SIGNAL),
        (EntityType.ISSUER, EntityType.RISK_SIGNAL),
    },
    LinkType.REQUIRES_ACTION: {
        (EntityType.RISK_SIGNAL, EntityType.COMPLIANCE_ACTION),
        (EntityType.ISSUER, EntityType.COMPLIANCE_ACTION),
    },
    LinkType.PEER_OF: {(EntityType.ISSUER, EntityType.ISSUER)},
    LinkType.MITIGATED_BY: {(EntityType.RISK_SIGNAL, EntityType.COMPLIANCE_ACTION)},
}


class OntologyRegistry:
    """In-memory FinTech Domain Ontology Registry with schema validation and graph traversal."""

    def __init__(self) -> None:
        self.issuers: dict[str, Issuer] = {}
        self.metrics: dict[str, FinancialMetric] = {}
        self.risk_signals: dict[str, RiskSignal] = {}
        self.actions: dict[str, ComplianceAction] = {}
        self.links: list[OntologyLink] = []

    def get_entity_type(self, entity_id: str) -> Optional[EntityType]:
        if entity_id in self.issuers:
            return EntityType.ISSUER
        if entity_id in self.metrics:
            return EntityType.FINANCIAL_METRIC
        if entity_id in self.risk_signals:
            return EntityType.RISK_SIGNAL
        if entity_id in self.actions:
            return EntityType.COMPLIANCE_ACTION
        return None

    def get_entity(self, entity_id: str) -> Optional[BaseModel]:
        return (
            self.issuers.get(entity_id)
            or self.metrics.get(entity_id)
            or self.risk_signals.get(entity_id)
            or self.actions.get(entity_id)
        )

    def register_issuer(self, issuer: Issuer) -> Issuer:
        self.issuers[issuer.issuer_id] = issuer
        return issuer

    def register_metric(self, metric: FinancialMetric, auto_link: bool = True) -> FinancialMetric:
        if metric.issuer_id not in self.issuers:
            raise ValueError(f"Cannot register metric '{metric.metric_id}': unknown issuer '{metric.issuer_id}'.")
        self.metrics[metric.metric_id] = metric
        if auto_link:
            self._ensure_link(
                OntologyLink(
                    source_id=metric.issuer_id,
                    target_id=metric.metric_id,
                    relation=LinkType.HAS_METRIC,
                )
            )
        return metric

    def register_risk_signal(self, signal: RiskSignal, auto_link: bool = True) -> RiskSignal:
        if signal.issuer_id not in self.issuers:
            raise ValueError(f"Cannot register risk signal '{signal.signal_id}': unknown issuer '{signal.issuer_id}'.")
        if signal.triggered_by_metric and signal.triggered_by_metric not in self.metrics:
            raise ValueError(
                f"RiskSignal '{signal.signal_id}' references unknown metric '{signal.triggered_by_metric}'."
            )
        self.risk_signals[signal.signal_id] = signal
        if auto_link:
            source = signal.triggered_by_metric or signal.issuer_id
            self._ensure_link(
                OntologyLink(
                    source_id=source,
                    target_id=signal.signal_id,
                    relation=LinkType.TRIGGERS_RISK,
                )
            )
        return signal

    def register_action(self, action: ComplianceAction, auto_link: bool = True) -> ComplianceAction:
        if action.issuer_id not in self.issuers:
            raise ValueError(f"Cannot register action '{action.action_id}': unknown issuer '{action.issuer_id}'.")
        self.actions[action.action_id] = action
        if auto_link:
            self._ensure_link(
                OntologyLink(
                    source_id=action.issuer_id,
                    target_id=action.action_id,
                    relation=LinkType.REQUIRES_ACTION,
                )
            )
        return action

    def _ensure_link(self, link: OntologyLink) -> None:
        for existing in self.links:
            if (
                existing.source_id == link.source_id
                and existing.target_id == link.target_id
                and existing.relation == link.relation
            ):
                return
        self.add_link(link)

    def add_link(self, link: OntologyLink) -> OntologyLink:
        if link.source_id == link.target_id:
            raise ValueError(f"Self-referential link is not allowed: {link.source_id}")
        src_type = self.get_entity_type(link.source_id)
        tgt_type = self.get_entity_type(link.target_id)
        if src_type is None:
            raise ValueError(f"Link source '{link.source_id}' does not exist in OntologyRegistry.")
        if tgt_type is None:
            raise ValueError(f"Link target '{link.target_id}' does not exist in OntologyRegistry.")

        allowed_pairs = LINK_SCHEMA_RULES.get(link.relation, set())
        if (src_type, tgt_type) not in allowed_pairs:
            raise ValueError(
                f"Schema violation: link {link.relation.value} cannot connect "
                f"{src_type.value} -> {tgt_type.value}."
            )
        self.links.append(link)
        return link

    def get_neighbors(
        self,
        entity_id: str,
        relation: Optional[LinkType] = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        if self.get_entity_type(entity_id) is None:
            raise KeyError(f"Entity '{entity_id}' not found in OntologyRegistry.")
        results: list[dict[str, Any]] = []
        for link in self.links:
            if relation is not None and link.relation != relation:
                continue
            if direction in ("outgoing", "both") and link.source_id == entity_id:
                tgt = self.get_entity(link.target_id)
                results.append(
                    {
                        "direction": "outgoing",
                        "relation": link.relation.value,
                        "entity_id": link.target_id,
                        "entity_type": self.get_entity_type(link.target_id).value,  # type: ignore[union-attr]
                        "data": tgt.model_dump() if tgt else {},
                    }
                )
            if direction in ("incoming", "both") and link.target_id == entity_id:
                src = self.get_entity(link.source_id)
                results.append(
                    {
                        "direction": "incoming",
                        "relation": link.relation.value,
                        "entity_id": link.source_id,
                        "entity_type": self.get_entity_type(link.source_id).value,  # type: ignore[union-attr]
                        "data": src.model_dump() if src else {},
                    }
                )
        return results

    def traverse_graph(self, start_id: str, max_depth: int = 2) -> dict[str, Any]:
        if self.get_entity_type(start_id) is None:
            raise KeyError(f"Start entity '{start_id}' not found in OntologyRegistry.")

        visited: set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        while queue:
            curr_id, depth = queue.popleft()
            curr_entity = self.get_entity(curr_id)
            curr_type = self.get_entity_type(curr_id)
            nodes.append(
                {
                    "id": curr_id,
                    "type": curr_type.value if curr_type else "Unknown",
                    "depth": depth,
                    "data": curr_entity.model_dump() if curr_entity else {},
                }
            )
            if depth >= max_depth:
                continue
            for link in self.links:
                if link.source_id == curr_id:
                    edge_key = (link.source_id, link.target_id, link.relation.value)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append(
                            {
                                "source": link.source_id,
                                "target": link.target_id,
                                "relation": link.relation.value,
                                "weight": link.weight,
                            }
                        )
                    if link.target_id not in visited:
                        visited.add(link.target_id)
                        queue.append((link.target_id, depth + 1))

        return {"root": start_id, "nodes": nodes, "edges": edges}

    def check_action_preconditions(self, action_id: str, actor_role: str) -> tuple[bool, str]:
        action = self.actions.get(action_id)
        if action is None:
            return False, f"Action '{action_id}' does not exist."
        if action.status != ActionStatus.PENDING:
            return False, f"Action '{action_id}' is in status '{action.status.value}', expected PENDING."
        allowed_roles = {action.required_role, "chief_risk_officer", "admin"}
        if actor_role not in allowed_roles:
            return (
                False,
                f"Role '{actor_role}' is not authorized; requires one of {sorted(allowed_roles)}.",
            )
        issuer_signals = [s for s in self.risk_signals.values() if s.issuer_id == action.issuer_id]
        min_rank = SEVERITY_RANK[action.min_severity]
        qualifying = [s for s in issuer_signals if SEVERITY_RANK[s.severity] >= min_rank]
        if not qualifying:
            return (
                False,
                f"Precondition failed: issuer '{action.issuer_id}' has no RiskSignal >= {action.min_severity.value}.",
            )
        return True, f"Preconditions satisfied ({len(qualifying)} qualifying risk signals)."

    def to_graph_dict(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for eid, item in self.issuers.items():
            nodes.append({"id": eid, "type": EntityType.ISSUER.value, "data": item.model_dump()})
        for eid, item in self.metrics.items():
            nodes.append({"id": eid, "type": EntityType.FINANCIAL_METRIC.value, "data": item.model_dump()})
        for eid, item in self.risk_signals.items():
            nodes.append({"id": eid, "type": EntityType.RISK_SIGNAL.value, "data": item.model_dump()})
        for eid, item in self.actions.items():
            nodes.append({"id": eid, "type": EntityType.COMPLIANCE_ACTION.value, "data": item.model_dump()})

        edges = [
            {
                "source": lk.source_id,
                "target": lk.target_id,
                "relation": lk.relation.value,
                "weight": lk.weight,
            }
            for lk in self.links
        ]
        return {
            "summary": {
                "issuers": len(self.issuers),
                "metrics": len(self.metrics),
                "risk_signals": len(self.risk_signals),
                "actions": len(self.actions),
                "links": len(self.links),
            },
            "nodes": nodes,
            "edges": edges,
        }
