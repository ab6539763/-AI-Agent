"""GovTech Ontology: Policy documents, citizen/enterprise profiles, benefit programs,
eligibility rules, policy links, administrative actions, and multi-rule evaluation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyDoc(BaseModel):
    """Structured representation of a government policy document."""

    policy_id: str
    title: str
    department: str
    effective_date: str  # YYYY-MM-DD
    expiry_date: str | None = None  # YYYY-MM-DD or None if open-ended
    status: Literal["active", "expired", "draft", "revoked"] = "active"
    summary: str = ""
    clauses: dict[str, str] = Field(default_factory=dict)  # e.g. {"§3.1": "..."}
    tags: list[str] = Field(default_factory=list)


class CitizenProfile(BaseModel):
    """Profile for an individual citizen or enterprise applicant."""

    applicant_id: str
    applicant_type: Literal["citizen", "enterprise"]
    name: str
    identifier: str  # Resident ID or Unified Social Credit Code (USCC)
    region: str
    annual_income_or_revenue: float = 0.0  # CNY
    employee_count: int = 0
    industry: str = ""
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class BenefitProgram(BaseModel):
    """Government subsidy, tax relief, or public service benefit program."""

    program_id: str
    name: str
    department: str
    policy_id: str
    max_subsidy_amount: float = 0.0
    currency: str = "CNY"
    description: str = ""
    requires_hitl: bool = True
    hitl_threshold_amount: float = 50000.0
    active: bool = True


RuleOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]


class EligibilityRule(BaseModel):
    """Single deterministic eligibility rule tied to a BenefitProgram and PolicyDoc clause."""

    rule_id: str
    program_id: str
    policy_id: str
    field: str  # Attribute path on CitizenProfile or attributes dict
    operator: RuleOperator
    value: Any
    clause_ref: str  # e.g., "POL-2026-TECH-01 §第3条"
    description: str = ""


class PolicyLink(BaseModel):
    """Typed semantic link between ontology entities."""

    source_id: str
    target_id: str
    relation_type: Literal[
        "ISSUED_BY",
        "GOVERNS",
        "REQUIRES_RULE",
        "SUPERSEDES",
        "COMPLEMENTS",
        "ROUTED_TO",
    ]
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovAction(BaseModel):
    """Administrative action / benefit determination subject to HITL case-officer sign-off."""

    action_id: str = Field(default_factory=lambda: f"ACT-{uuid4().hex[:10].upper()}")
    applicant_id: str
    program_id: str
    department: str
    action_type: Literal["subsidy_grant", "tax_relief", "service_approval"] = "subsidy_grant"
    amount: float = 0.0
    status: Literal["pending_approval", "approved", "rejected"] = "pending_approval"
    requires_hitl: bool = True
    clause_citations: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    decision_note: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    decided_at: str | None = None


class RuleEvaluationDetail(BaseModel):
    rule_id: str
    field: str
    operator: RuleOperator
    expected: Any
    actual: Any
    passed: bool
    clause_ref: str
    description: str = ""


class EligibilityEvaluation(BaseModel):
    """Result of evaluating a CitizenProfile against a BenefitProgram."""

    applicant_id: str
    program_id: str
    program_name: str
    department: str
    eligible: bool
    estimated_subsidy: float
    matched_rules: list[RuleEvaluationDetail] = Field(default_factory=list)
    failed_rules: list[RuleEvaluationDetail] = Field(default_factory=list)
    exact_clauses: list[str] = Field(default_factory=list)


DEPARTMENT_ROUTING_TABLE: dict[str, str] = {
    "高新技术": "市科学技术局",
    "研发补贴": "市科学技术局",
    "专精特新": "市工业和信息化局",
    "制造业": "市工业和信息化局",
    "稳岗": "市人力资源和社会保障局",
    "社保": "市人力资源和社会保障局",
    "人才": "市人力资源和社会保障局",
    "税收": "市税务局",
    "减免": "市税务局",
    "营业执照": "市市场监督管理局",
    "政务": "市政务服务和数据管理局",
}


class GovOntologyRegistry:
    """In-memory GovTech Ontology registry supporting multi-rule evaluation & routing."""

    def __init__(self) -> None:
        self.policies: dict[str, PolicyDoc] = {}
        self.profiles: dict[str, CitizenProfile] = {}
        self.programs: dict[str, BenefitProgram] = {}
        self.rules: dict[str, EligibilityRule] = {}
        self.links: list[PolicyLink] = []
        self.actions: dict[str, GovAction] = {}

    def register_policy(self, policy: PolicyDoc) -> None:
        self.policies[policy.policy_id] = policy

    def register_profile(self, profile: CitizenProfile) -> None:
        self.profiles[profile.applicant_id] = profile

    def register_program(self, program: BenefitProgram) -> None:
        self.programs[program.program_id] = program
        self.links.append(
            PolicyLink(
                source_id=program.policy_id,
                target_id=program.program_id,
                relation_type="GOVERNS",
            )
        )

    def register_rule(self, rule: EligibilityRule) -> None:
        self.rules[rule.rule_id] = rule
        self.links.append(
            PolicyLink(
                source_id=rule.program_id,
                target_id=rule.rule_id,
                relation_type="REQUIRES_RULE",
            )
        )

    def add_link(self, link: PolicyLink) -> None:
        self.links.append(link)

    def record_action(self, action: GovAction) -> GovAction:
        self.actions[action.action_id] = action
        return action

    def route_department(self, topic_or_program_id: str) -> str:
        """Route a program ID or policy topic to the responsible government department."""
        if topic_or_program_id in self.programs:
            return self.programs[topic_or_program_id].department
        if topic_or_program_id in self.policies:
            return self.policies[topic_or_program_id].department
        for keyword, dept in DEPARTMENT_ROUTING_TABLE.items():
            if keyword in topic_or_program_id:
                return dept
        return "市政务服务和数据管理局"

    @staticmethod
    def _extract_field(profile: CitizenProfile, field: str) -> Any:
        if hasattr(profile, field):
            return getattr(profile, field)
        return profile.attributes.get(field)

    @staticmethod
    def _eval_operator(actual: Any, operator: RuleOperator, expected: Any) -> bool:
        if actual is None:
            return False
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "gt":
            return actual > expected
        if operator == "gte":
            return actual >= expected
        if operator == "lt":
            return actual < expected
        if operator == "lte":
            return actual <= expected
        if operator == "in":
            return actual in expected
        if operator == "contains":
            return expected in actual
        return False

    def evaluate_program(
        self, profile: CitizenProfile, program_id: str
    ) -> EligibilityEvaluation:
        program = self.programs[program_id]
        program_rules = [r for r in self.rules.values() if r.program_id == program_id]
        policy = self.policies.get(program.policy_id)

        matched: list[RuleEvaluationDetail] = []
        failed: list[RuleEvaluationDetail] = []
        clauses: list[str] = []

        # If policy is expired or revoked, program is ineligible
        policy_active = policy is None or policy.status == "active"

        for rule in program_rules:
            actual = self._extract_field(profile, rule.field)
            passed = policy_active and self._eval_operator(actual, rule.operator, rule.value)
            detail = RuleEvaluationDetail(
                rule_id=rule.rule_id,
                field=rule.field,
                operator=rule.operator,
                expected=rule.value,
                actual=actual,
                passed=passed,
                clause_ref=rule.clause_ref,
                description=rule.description,
            )
            if passed:
                matched.append(detail)
                if rule.clause_ref not in clauses:
                    clauses.append(rule.clause_ref)
            else:
                failed.append(detail)

        eligible = bool(program.active and policy_active and program_rules and not failed)
        estimated = program.max_subsidy_amount if eligible else 0.0

        return EligibilityEvaluation(
            applicant_id=profile.applicant_id,
            program_id=program.program_id,
            program_name=program.name,
            department=program.department,
            eligible=eligible,
            estimated_subsidy=estimated,
            matched_rules=matched,
            failed_rules=failed,
            exact_clauses=clauses,
        )

    def evaluate_eligibility(
        self, profile: CitizenProfile, program_id: str | None = None
    ) -> list[EligibilityEvaluation]:
        if program_id is not None:
            if program_id not in self.programs:
                raise KeyError(f"Unknown program_id: {program_id}")
            return [self.evaluate_program(profile, program_id)]
        return [self.evaluate_program(profile, pid) for pid in sorted(self.programs)]


def seed_default_ontology() -> GovOntologyRegistry:
    """Create a pre-seeded deterministic GovTech Ontology registry for demo & API startup."""
    reg = GovOntologyRegistry()

    pol_tech = PolicyDoc(
        policy_id="POL-2026-TECH-01",
        title="高新技术企业研发费用加计扣除与创新补贴办法",
        department="市科学技术局",
        effective_date="2026-01-01",
        expiry_date="2027-12-31",
        status="active",
        summary="支持注册在本市的高新技术企业开展核心技术研发，按研发投入给予最高50万元财政补贴。",
        clauses={
            "§第3条": "申请主体须为在本市依法登记注册的独立法人企业（applicant_type == enterprise）。",
            "§第4条": "企业上年度营业收入不低于100万元人民币且研发人员或员工不少于10人。",
            "§第5条": "符合条件的高新技术企业最高可获500000元人民币研发创新补贴。",
        },
        tags=["高新技术", "研发补贴", "企业服务"],
    )
    pol_talent = PolicyDoc(
        policy_id="POL-2026-HR-02",
        title="青年科技人才安居租房补贴实施细则",
        department="市人力资源和社会保障局",
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        status="active",
        summary="面向在本市重点产业就业的青年人才发放每月安居补贴，年度最高24000元。",
        clauses={
            "§第2条": "申请人须为自然人（applicant_type == citizen）且在本市连续缴纳社保。",
            "§第4条": "申请人年度应税收入不超过300000元人民币。",
        },
        tags=["人才", "社保", "民生服务"],
    )
    reg.register_policy(pol_tech)
    reg.register_policy(pol_talent)

    prog_tech = BenefitProgram(
        program_id="PROG-TECH-RD-500K",
        name="高新技术企业研发创新专项补贴",
        department="市科学技术局",
        policy_id="POL-2026-TECH-01",
        max_subsidy_amount=500000.0,
        description="面向高新技术企业的研发创新财政补助",
        requires_hitl=True,
        hitl_threshold_amount=50000.0,
    )
    prog_talent = BenefitProgram(
        program_id="PROG-HR-HOUSING-24K",
        name="青年科技人才安居补贴",
        department="市人力资源和社会保障局",
        policy_id="POL-2026-HR-02",
        max_subsidy_amount=24000.0,
        description="面向青年科技人才的年度租房补贴",
        requires_hitl=True,
        hitl_threshold_amount=10000.0,
    )
    reg.register_program(prog_tech)
    reg.register_program(prog_talent)

    rules = [
        EligibilityRule(
            rule_id="RULE-TECH-01",
            program_id="PROG-TECH-RD-500K",
            policy_id="POL-2026-TECH-01",
            field="applicant_type",
            operator="eq",
            value="enterprise",
            clause_ref="POL-2026-TECH-01 §第3条",
            description="申请主体必须为企业法人",
        ),
        EligibilityRule(
            rule_id="RULE-TECH-02",
            program_id="PROG-TECH-RD-500K",
            policy_id="POL-2026-TECH-01",
            field="annual_income_or_revenue",
            operator="gte",
            value=1000000.0,
            clause_ref="POL-2026-TECH-01 §第4条",
            description="上年度营业收入不低于100万元",
        ),
        EligibilityRule(
            rule_id="RULE-TECH-03",
            program_id="PROG-TECH-RD-500K",
            policy_id="POL-2026-TECH-01",
            field="employee_count",
            operator="gte",
            value=10,
            clause_ref="POL-2026-TECH-01 §第4条",
            description="企业员工人数不少于10人",
        ),
        EligibilityRule(
            rule_id="RULE-TECH-04",
            program_id="PROG-TECH-RD-500K",
            policy_id="POL-2026-TECH-01",
            field="tags",
            operator="contains",
            value="高新技术",
            clause_ref="POL-2026-TECH-01 §第5条",
            description="具备高新技术企业资质标签",
        ),
        EligibilityRule(
            rule_id="RULE-HR-01",
            program_id="PROG-HR-HOUSING-24K",
            policy_id="POL-2026-HR-02",
            field="applicant_type",
            operator="eq",
            value="citizen",
            clause_ref="POL-2026-HR-02 §第2条",
            description="申请人必须为自然人",
        ),
        EligibilityRule(
            rule_id="RULE-HR-02",
            program_id="PROG-HR-HOUSING-24K",
            policy_id="POL-2026-HR-02",
            field="annual_income_or_revenue",
            operator="lte",
            value=300000.0,
            clause_ref="POL-2026-HR-02 §第4条",
            description="年度应税收入不超过30万元",
        ),
    ]
    for r in rules:
        reg.register_rule(r)

    return reg
