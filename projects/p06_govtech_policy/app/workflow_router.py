"""Cross-Department Workflow Router & Policy Gazette Differ for Project P06.

Provides 100% offline deterministic:
1. CrossDeptWorkflowRouter: routes approved benefit/subsidy cases through
   sequential and parallel government bureaus (e.g., 人社局 -> 科技局 -> 财政局)
   with SLA days and per-bureau required document checklists.
2. PolicyGazetteDiffer: compares policy revisions and highlights changed
   subsidy caps, eligibility thresholds, effective status, and clause diffs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BureauStage(BaseModel):
    """Single government bureau processing stage in a cross-department route."""

    stage_id: str
    bureau: str
    bureau_short: str
    execution_mode: Literal["sequential", "parallel"] = "sequential"
    step_order: int
    sla_days: int
    status: Literal["completed", "in_progress", "pending"] = "pending"
    required_documents: list[str] = Field(default_factory=list)
    responsibility: str = ""


class WorkflowRouteRequest(BaseModel):
    """Input payload for routing an approved or matched benefit/subsidy case."""

    case_id: str | None = None
    applicant_id: str
    applicant_type: Literal["citizen", "enterprise"] = "enterprise"
    program_id: str
    program_name: str = ""
    amount: float = 0.0
    approved: bool = True
    tags: list[str] = Field(default_factory=list)
    current_step: int = Field(default=1, ge=1, le=4)


class WorkflowRouteResult(BaseModel):
    """Routed cross-department workflow plan with SLA and document checklist."""

    case_id: str
    applicant_id: str
    program_id: str
    workflow_pattern: Literal["sequential", "hybrid_parallel"]
    route_summary: str
    total_sla_days: int
    fast_track: bool = False
    stages: list[BureauStage] = Field(default_factory=list)
    consolidated_documents: list[str] = Field(default_factory=list)
    routed_at: str = Field(default_factory=_utc_now_iso)


class CrossDeptWorkflowRouter:
    """Deterministic cross-department workflow router for GovTech cases."""

    def route_case(self, request: WorkflowRouteRequest) -> WorkflowRouteResult:
        case_id = request.case_id or f"CASE-{uuid4().hex[:8].upper()}"
        is_enterprise_or_tech = (
            request.applicant_type == "enterprise"
            or "TECH" in request.program_id.upper()
            or any(t in request.tags for t in ("高新技术", "专精特新", "研发", "制造业"))
        )
        # High-value enterprise subsidies (>= 200k) run HR & Tech bureau checks in parallel
        use_parallel_precheck = is_enterprise_or_tech and request.amount >= 200_000.0
        fast_track = request.approved and request.amount < 50_000.0

        if is_enterprise_or_tech:
            hr_mode: Literal["sequential", "parallel"] = (
                "parallel" if use_parallel_precheck else "sequential"
            )
            tech_step = 1 if use_parallel_precheck else 2
            finance_step = 2 if use_parallel_precheck else 3

            stages = [
                BureauStage(
                    stage_id="STAGE-HR",
                    bureau="市人力资源和社会保障局",
                    bureau_short="人社局",
                    execution_mode=hr_mode,
                    step_order=1,
                    sla_days=2,
                    status=self._stage_status(1, request.current_step),
                    required_documents=[
                        "社会保险参保缴费证明（近12个月）",
                        "企业用工及稳岗承诺书",
                    ],
                    responsibility="核验企业参保人数、社保缴费连续性及劳动用工合规性",
                ),
                BureauStage(
                    stage_id="STAGE-TECH",
                    bureau="市科学技术局",
                    bureau_short="科技局",
                    execution_mode=hr_mode,
                    step_order=tech_step,
                    sla_days=4 if fast_track else 5,
                    status=self._stage_status(tech_step, request.current_step),
                    required_documents=[
                        "高新技术企业认定证书或研发机构备案表",
                        "上一年度研发费用专项审计报告",
                        "核心自主知识产权权属证明",
                    ],
                    responsibility="核定研发投入强度、高企资质及项目条款匹配度",
                ),
                BureauStage(
                    stage_id="STAGE-FIN",
                    bureau="市财政局",
                    bureau_short="财政局",
                    execution_mode="sequential",
                    step_order=finance_step,
                    sla_days=2 if fast_track else 3,
                    status=self._stage_status(finance_step, request.current_step),
                    required_documents=[
                        "市级财政专项资金拨付申请表",
                        "企业基本存款账户开户许可证",
                        "经办人 HITL 核准批复单",
                    ],
                    responsibility="资金预算复核、国库集中支付及补贴拨付公示",
                ),
            ]
        else:
            # Citizen / talent subsidy still follows 人社局 -> 科技局(人才创新协办) -> 财政局
            stages = [
                BureauStage(
                    stage_id="STAGE-HR",
                    bureau="市人力资源和社会保障局",
                    bureau_short="人社局",
                    execution_mode="sequential",
                    step_order=1,
                    sla_days=2,
                    status=self._stage_status(1, request.current_step),
                    required_documents=[
                        "申请人居民身份证及学历/职称证明",
                        "本市城镇职工社保缴费记录",
                    ],
                    responsibility="核验青年人才资格、年龄/收入条件及社保参保状态",
                ),
                BureauStage(
                    stage_id="STAGE-TECH",
                    bureau="市科学技术局",
                    bureau_short="科技局",
                    execution_mode="sequential",
                    step_order=2,
                    sla_days=2,
                    status=self._stage_status(2, request.current_step),
                    required_documents=[
                        "所在单位创新创业或研发岗位在职证明",
                    ],
                    responsibility="协办核验重点产业/科创载体人才认定加分项",
                ),
                BureauStage(
                    stage_id="STAGE-FIN",
                    bureau="市财政局",
                    bureau_short="财政局",
                    execution_mode="sequential",
                    step_order=3,
                    sla_days=2,
                    status=self._stage_status(3, request.current_step),
                    required_documents=[
                        "个人社会保障卡金融账户信息确认表",
                        "惠民补贴发放核准单",
                    ],
                    responsibility="补贴资金拨付至个人社保卡金融账户并留存审计凭证",
                ),
            ]

        total_sla = self._compute_total_sla(stages)
        route_summary = " -> ".join(s.bureau_short for s in stages)
        consolidated_docs: list[str] = []
        for stage in stages:
            for doc in stage.required_documents:
                if doc not in consolidated_docs:
                    consolidated_docs.append(doc)

        return WorkflowRouteResult(
            case_id=case_id,
            applicant_id=request.applicant_id,
            program_id=request.program_id,
            workflow_pattern="hybrid_parallel" if use_parallel_precheck else "sequential",
            route_summary=route_summary,
            total_sla_days=total_sla,
            fast_track=fast_track,
            stages=stages,
            consolidated_documents=consolidated_docs,
        )

    @staticmethod
    def _stage_status(
        step_order: int, current_step: int
    ) -> Literal["completed", "in_progress", "pending"]:
        if step_order < current_step:
            return "completed"
        if step_order == current_step:
            return "in_progress"
        return "pending"

    @staticmethod
    def _compute_total_sla(stages: list[BureauStage]) -> int:
        by_step: dict[int, list[int]] = {}
        for stage in stages:
            by_step.setdefault(stage.step_order, []).append(stage.sla_days)
        return sum(max(days) for days in by_step.values())


class PolicyRevision(BaseModel):
    """Structured snapshot of a policy version for gazette revision diffing."""

    policy_id: str
    version: str
    title: str
    department: str = "市科学技术局"
    effective_date: str
    expiry_date: str | None = None
    status: Literal["active", "expired", "draft", "revoked"] = "active"
    subsidy_cap: float = 0.0
    eligibility_threshold: str = ""
    clauses: dict[str, str] = Field(default_factory=dict)


class ThresholdChange(BaseModel):
    """Highlighted change in subsidy cap, threshold, status, or effective date."""

    field: str
    label: str
    old_value: Any
    new_value: Any
    delta: float | None = None
    change_type: Literal["increased", "decreased", "modified", "unchanged"]


class ClauseDiffItem(BaseModel):
    """Clause-level comparison between old and new policy revisions."""

    clause_ref: str
    change_type: Literal["added", "removed", "modified", "unchanged"]
    old_text: str | None = None
    new_text: str | None = None
    highlight_summary: str


class PolicyDiffRequest(BaseModel):
    """Request to diff two policy revisions or diff a seeded policy against its prior version."""

    policy_id: str | None = None
    old_revision: PolicyRevision | None = None
    new_revision: PolicyRevision | None = None


class PolicyDiffResult(BaseModel):
    """Structured Policy Gazette diff highlighting subsidy cap & clause changes."""

    policy_id: str
    old_version: str
    new_version: str
    title: str
    department: str
    old_status: str
    new_status: str
    has_changes: bool
    subsidy_cap_delta: float
    threshold_changes: list[ThresholdChange] = Field(default_factory=list)
    clause_diffs: list[ClauseDiffItem] = Field(default_factory=list)
    summary: str


DEFAULT_POLICY_BASELINES: dict[str, tuple[PolicyRevision, PolicyRevision]] = {
    "POL-2026-TECH-01": (
        PolicyRevision(
            policy_id="POL-2026-TECH-01",
            version="2025试行版",
            title="高新技术企业研发创新补贴办法",
            department="市科学技术局",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
            status="expired",
            subsidy_cap=300000.0,
            eligibility_threshold="年营收>=200万元且参保人数>=15人",
            clauses={
                "§第3条": "适用于在本市注册满一年的高新技术企业。",
                "§第4条": "企业上年度营业收入不低于200万元且参保员工不少于15人。",
                "§第5条": "经核准后，最高给予300000元人民币研发创新补贴。",
            },
        ),
        PolicyRevision(
            policy_id="POL-2026-TECH-01",
            version="2026正式版",
            title="高新技术企业研发创新补贴办法",
            department="市科学技术局",
            effective_date="2026-01-01",
            expiry_date="2027-12-31",
            status="active",
            subsidy_cap=500000.0,
            eligibility_threshold="年营收>=100万元且参保人数>=10人",
            clauses={
                "§第3条": "适用于在本市注册并具备有效高新技术企业资质的法人单位。",
                "§第4条": "企业上年度营业收入不低于100万元且参保员工不少于10人。",
                "§第5条": "经核准后，最高给予500000元人民币研发创新补贴。",
                "§第6条": "实行人社局、科技局并联初审与财政局国库直拨联动机制。",
            },
        ),
    ),
    "POL-2026-HR-02": (
        PolicyRevision(
            policy_id="POL-2026-HR-02",
            version="2025版",
            title="青年人才安居与稳岗补贴实施细则",
            department="市人力资源和社会保障局",
            effective_date="2025-01-01",
            expiry_date="2025-12-31",
            status="expired",
            subsidy_cap=18000.0,
            eligibility_threshold="年收入<=25万元且连续社保>=12个月",
            clauses={
                "§第2条": "面向本市重点产业新引进青年人才，年收入不超过250000元。",
                "§第4条": "按月发放安居补贴，年度累计最高18000元人民币。",
            },
        ),
        PolicyRevision(
            policy_id="POL-2026-HR-02",
            version="2026修订版",
            title="青年人才安居与稳岗补贴实施细则",
            department="市人力资源和社会保障局",
            effective_date="2026-01-01",
            expiry_date="2027-12-31",
            status="active",
            subsidy_cap=24000.0,
            eligibility_threshold="年收入<=30万元且连续社保>=6个月",
            clauses={
                "§第2条": "面向本市重点产业新引进青年人才，年收入不超过300000元。",
                "§第4条": "按月发放安居补贴，年度累计最高24000元人民币。",
                "§第5条": "支持跨部门一网通办电子证照免提交核验。",
            },
        ),
    ),
}


class PolicyGazetteDiffer:
    """Deterministic Policy Gazette revision comparator."""

    def diff(self, request: PolicyDiffRequest) -> PolicyDiffResult:
        old_rev = request.old_revision
        new_rev = request.new_revision

        if (old_rev is None or new_rev is None) and request.policy_id:
            if request.policy_id not in DEFAULT_POLICY_BASELINES:
                raise KeyError(
                    f"No baseline policy revisions found for {request.policy_id}"
                )
            default_old, default_new = DEFAULT_POLICY_BASELINES[request.policy_id]
            old_rev = old_rev or default_old
            new_rev = new_rev or default_new

        if old_rev is None or new_rev is None:
            raise ValueError(
                "Either both old_revision/new_revision or a known policy_id must be provided."
            )

        threshold_changes: list[ThresholdChange] = []

        cap_delta = new_rev.subsidy_cap - old_rev.subsidy_cap
        cap_type: Literal["increased", "decreased", "modified", "unchanged"] = (
            "increased"
            if cap_delta > 0
            else "decreased" if cap_delta < 0 else "unchanged"
        )
        threshold_changes.append(
            ThresholdChange(
                field="subsidy_cap",
                label="最高补贴上限 (CNY)",
                old_value=old_rev.subsidy_cap,
                new_value=new_rev.subsidy_cap,
                delta=cap_delta,
                change_type=cap_type,
            )
        )

        threshold_changes.append(
            ThresholdChange(
                field="eligibility_threshold",
                label="申报门槛条件",
                old_value=old_rev.eligibility_threshold,
                new_value=new_rev.eligibility_threshold,
                delta=None,
                change_type=(
                    "modified"
                    if old_rev.eligibility_threshold != new_rev.eligibility_threshold
                    else "unchanged"
                ),
            )
        )

        threshold_changes.append(
            ThresholdChange(
                field="status",
                label="公报效力状态",
                old_value=old_rev.status,
                new_value=new_rev.status,
                delta=None,
                change_type=(
                    "modified" if old_rev.status != new_rev.status else "unchanged"
                ),
            )
        )

        # Clause-by-clause comparison
        all_refs: list[str] = list(old_rev.clauses.keys())
        for ref in new_rev.clauses.keys():
            if ref not in all_refs:
                all_refs.append(ref)

        clause_diffs: list[ClauseDiffItem] = []
        for ref in all_refs:
            old_text = old_rev.clauses.get(ref)
            new_text = new_rev.clauses.get(ref)
            if old_text is None and new_text is not None:
                clause_diffs.append(
                    ClauseDiffItem(
                        clause_ref=ref,
                        change_type="added",
                        old_text=None,
                        new_text=new_text,
                        highlight_summary=f"新增条款 {ref}",
                    )
                )
            elif old_text is not None and new_text is None:
                clause_diffs.append(
                    ClauseDiffItem(
                        clause_ref=ref,
                        change_type="removed",
                        old_text=old_text,
                        new_text=None,
                        highlight_summary=f"废止/删除条款 {ref}",
                    )
                )
            elif old_text != new_text:
                clause_diffs.append(
                    ClauseDiffItem(
                        clause_ref=ref,
                        change_type="modified",
                        old_text=old_text,
                        new_text=new_text,
                        highlight_summary=f"修订条款 {ref}",
                    )
                )
            else:
                clause_diffs.append(
                    ClauseDiffItem(
                        clause_ref=ref,
                        change_type="unchanged",
                        old_text=old_text,
                        new_text=new_text,
                        highlight_summary=f"条款 {ref} 保持不变",
                    )
                )

        has_changes = any(
            tc.change_type != "unchanged" for tc in threshold_changes
        ) or any(cd.change_type != "unchanged" for cd in clause_diffs)

        changed_clauses_count = sum(
            1 for cd in clause_diffs if cd.change_type != "unchanged"
        )
        if cap_delta > 0:
            cap_note = f"补贴上限上调 {cap_delta:,.0f} 元"
        elif cap_delta < 0:
            cap_note = f"补贴上限下调 {abs(cap_delta):,.0f} 元"
        else:
            cap_note = "补贴上限保持不变"

        summary = (
            f"《{new_rev.title}》({old_rev.version} → {new_rev.version})：{cap_note}，"
            f"共 {changed_clauses_count} 处条款发生新增/修订。"
        )

        return PolicyDiffResult(
            policy_id=new_rev.policy_id,
            old_version=old_rev.version,
            new_version=new_rev.version,
            title=new_rev.title,
            department=new_rev.department,
            old_status=old_rev.status,
            new_status=new_rev.status,
            has_changes=has_changes,
            subsidy_cap_delta=cap_delta,
            threshold_changes=threshold_changes,
            clause_diffs=clause_diffs,
            summary=summary,
        )
