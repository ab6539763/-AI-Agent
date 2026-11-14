"""Comprehensive offline deterministic pytest suite for Project P06: GovTech Policy Agent."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from projects.p06_govtech_policy.app.api import create_app
from projects.p06_govtech_policy.app.fde_pipeline import GovTechFDEPipeline, mask_pii
from projects.p06_govtech_policy.app.llm_wiki import GovTechLLMWiki
from projects.p06_govtech_policy.app.ontology import (
    CitizenProfile,
    seed_default_ontology,
)
from projects.p06_govtech_policy.app.workflow_router import (
    CrossDeptWorkflowRouter,
    PolicyDiffRequest,
    PolicyGazetteDiffer,
    PolicyRevision,
    WorkflowRouteRequest,
)


def test_ontology_multi_rule_eligibility_and_routing() -> None:
    """Test multi-rule eligibility evaluation (pass & fail) and department routing."""
    registry = seed_default_ontology()

    qualified_enterprise = CitizenProfile(
        applicant_id="ENT-001",
        applicant_type="enterprise",
        name="星辰智能科技有限公司",
        identifier="91310000MA1K3XYZ88",
        region="浦东新区",
        annual_income_or_revenue=3_500_000.0,
        employee_count=42,
        industry="人工智能",
        tags=["高新技术", "专精特新"],
    )
    evals = registry.evaluate_eligibility(
        qualified_enterprise, program_id="PROG-TECH-RD-500K"
    )
    assert len(evals) == 1
    ev = evals[0]
    assert ev.eligible is True
    assert ev.estimated_subsidy == 500000.0
    assert ev.department == "市科学技术局"
    assert len(ev.matched_rules) == 4
    assert not ev.failed_rules
    assert "POL-2026-TECH-01 §第4条" in ev.exact_clauses

    # Small enterprise failing revenue and employee count rules
    small_enterprise = CitizenProfile(
        applicant_id="ENT-002",
        applicant_type="enterprise",
        name="微光初创工作室",
        identifier="91310000MA1K9ABC12",
        region="徐汇区",
        annual_income_or_revenue=200_000.0,
        employee_count=3,
        tags=["高新技术"],
    )
    fail_ev = registry.evaluate_eligibility(
        small_enterprise, program_id="PROG-TECH-RD-500K"
    )[0]
    assert fail_ev.eligible is False
    assert fail_ev.estimated_subsidy == 0.0
    assert len(fail_ev.failed_rules) == 2

    # Department routing
    assert registry.route_department("PROG-TECH-RD-500K") == "市科学技术局"
    assert registry.route_department("青年人才社保稳岗") == "市人力资源和社会保障局"
    assert registry.route_department("企业税收减免") == "市税务局"


def test_llm_wiki_ingest_query_and_persistence(tmp_path: Path) -> None:
    """Test GovTechLLMWiki persistence (index.md, log.md, entities/<id>.md with [[wiki_links]]) and query."""
    wiki = GovTechLLMWiki(tmp_path / "wiki")
    entity_path = wiki.ingest(
        doc_id="POL-2026-TECH-01",
        title="高新技术企业研发创新补贴办法",
        content="本办法支持本市高新技术企业加大研发投入，最高补贴50万元。",
        department="市科学技术局",
        program_id="PROG-TECH-RD-500K",
        effective_date="2026-01-01",
        expiry_date="2027-12-31",
        subsidy_threshold=500000.0,
        rule_ids=["RULE-TECH-01"],
        related_ids=["PROG-TECH-RD-500K"],
        clauses={"§第5条": "最高可获500000元人民币研发创新补贴。"},
    )

    assert entity_path.exists()
    entity_md = entity_path.read_text(encoding="utf-8")
    assert "[[PROG-TECH-RD-500K]]" in entity_md
    assert "[[RULE-TECH-01]]" in entity_md

    index_md = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "[[entities/POL-2026-TECH-01]]" in index_md

    hits = wiki.query("高新技术 研发补贴")
    assert len(hits) >= 1
    assert hits[0].doc_id == "POL-2026-TECH-01"
    assert "PROG-TECH-RD-500K" in hits[0].wiki_links

    log_md = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "INGEST" in log_md
    assert "QUERY" in log_md


def test_llm_wiki_lint_detects_expired_conflicts_and_orphans(tmp_path: Path) -> None:
    """Test lint() detecting expired policies, conflicting subsidy thresholds, and orphan rules."""
    wiki = GovTechLLMWiki(tmp_path / "wiki")

    # 1. Expired policy
    wiki.ingest(
        doc_id="POL-2024-OLD-01",
        title="2024旧版产业扶持政策",
        content="已于2025年底废止的补贴政策。",
        department="市工业和信息化局",
        program_id="PROG-TECH-RD-500K",
        effective_date="2024-01-01",
        expiry_date="2025-12-31",
        subsidy_threshold=300000.0,
    )

    # 2. Two active policies with conflicting thresholds for the same program
    wiki.ingest(
        doc_id="POL-2026-A",
        title="科技补贴方案A",
        content="研发补贴上限50万元。",
        department="市科学技术局",
        program_id="PROG-TECH-RD-500K",
        effective_date="2026-01-01",
        expiry_date="2027-12-31",
        subsidy_threshold=500000.0,
    )
    wiki.ingest(
        doc_id="POL-2026-B",
        title="科技补贴方案B（冲突阈值）",
        content="研发补贴上限80万元。",
        department="市科学技术局",
        program_id="PROG-TECH-RD-500K",
        effective_date="2026-01-01",
        expiry_date="2027-12-31",
        subsidy_threshold=800000.0,
    )

    # 3. Orphan rule entity with no program_id
    wiki.ingest(
        doc_id="RULE-ORPHAN-99",
        title="孤立资格规则",
        content="未绑定任何项目的规则。",
        entity_type="rule",
        program_id=None,
        related_ids=["NON-EXISTENT-ENTITY"],
    )

    report = wiki.lint(
        reference_date="2026-06-01",
        known_program_ids={"PROG-TECH-RD-500K"},
        known_rule_ids={"RULE-TECH-01"},
    )
    assert report.healthy is False
    assert len(report.expired_policies) == 1
    assert report.expired_policies[0].entity_id == "POL-2024-OLD-01"
    assert len(report.conflicting_thresholds) == 1
    assert report.conflicting_thresholds[0].entity_id == "PROG-TECH-RD-500K"
    assert len(report.orphan_rules) >= 2


def test_pii_masking_and_refusal_on_unsupported_claims(tmp_path: Path) -> None:
    """Test citizen/enterprise PII masking and deterministic refusal on unsupported claims."""
    raw = "申请人张三，身份证310101199001011234，手机13812345678，企业信用代码91310000MA1K3XYZ88，邮箱zhangsan@example.com。"
    masked, pii_types = mask_pii(raw)
    assert "310101199001011234" not in masked
    assert "13812345678" not in masked
    assert "91310000MA1K3XYZ88" not in masked
    assert "zhangsan@example.com" not in masked
    assert set(pii_types) >= {"id_card", "phone", "uscc", "email"}

    registry = seed_default_ontology()
    wiki = GovTechLLMWiki(tmp_path / "wiki")
    pipeline = GovTechFDEPipeline(
        registry=registry,
        wiki=wiki,
        audit_log_path=tmp_path / "audit.jsonl",
    )

    # Unsupported claim: no matching wiki docs and no profile
    refusal = pipeline.ask("请问火星基地建设无息贷款1000万元怎么申请？身份证310101199001011234")
    assert refusal.status == "refused"
    assert refusal.refusal_reason is not None
    assert refusal.clause_citations == []
    assert "310101199001011234" not in refusal.masked_question


def test_hitl_case_officer_signoff_and_audit_trail(tmp_path: Path) -> None:
    """Test HITL GovAction creation, case-officer approval, and audit trail persistence."""
    registry = seed_default_ontology()
    wiki = GovTechLLMWiki(tmp_path / "wiki")
    wiki.ingest(
        doc_id="POL-2026-TECH-01",
        title="高新技术企业研发创新补贴办法",
        content="高新技术企业研发补贴最高50万元。",
        department="市科学技术局",
        program_id="PROG-TECH-RD-500K",
        clauses={"§第5条": "最高可获500000元人民币研发创新补贴。"},
    )
    audit_path = tmp_path / "audit.jsonl"
    pipeline = GovTechFDEPipeline(
        registry=registry, wiki=wiki, audit_log_path=audit_path
    )

    profile = CitizenProfile(
        applicant_id="ENT-HITL-01",
        applicant_type="enterprise",
        name="未来芯片有限公司",
        identifier="91310000MA1K888899",
        region="张江科学城",
        annual_income_or_revenue=8_000_000.0,
        employee_count=85,
        tags=["高新技术"],
    )
    resp = pipeline.ask(
        question="我司（统一社会信用代码91310000MA1K888899）能否申请高新技术企业研发补贴？",
        profile=profile,
    )
    assert resp.status == "answered"
    assert resp.pending_action is not None
    assert resp.pending_action.status == "pending_approval"
    assert resp.pending_action.requires_hitl is True
    assert "POL-2026-TECH-01 §第4条" in resp.clause_citations

    approved = pipeline.approve_action(
        action_id=resp.pending_action.action_id,
        officer_id="OFFICER-ZHANG-07",
        approved=True,
        note="材料齐全，核准发放研发补贴。",
    )
    assert approved.status == "approved"
    assert approved.approved_by == "OFFICER-ZHANG-07"
    assert approved.decided_at is not None

    stages = [e.stage for e in pipeline.get_audit_trail()]
    assert "pii_masking" in stages
    assert "hitl_created" in stages
    assert "hitl_signoff" in stages
    assert audit_path.exists()


def test_fastapi_endpoints_and_request_id_middleware(tmp_path: Path) -> None:
    """Test all FastAPI endpoints and X-Request-ID middleware via TestClient + tmp_path."""
    app = create_app(data_dir=tmp_path / "api_data", seed_defaults=True)
    client = TestClient(app)

    # Health & Ready with X-Request-ID
    r_health = client.get("/health", headers={"X-Request-ID": "req-gov-123"})
    assert r_health.status_code == 200
    assert r_health.headers["X-Request-ID"] == "req-gov-123"
    assert r_health.json()["status"] == "ok"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert r_ready.json()["policies"] >= 2

    # Wiki ingest & lint
    r_ingest = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "POL-2026-MFG-03",
            "title": "专精特新制造业数字化转型补贴",
            "content": "支持专精特新企业实施智能制造改造。",
            "department": "市工业和信息化局",
            "effective_date": "2026-01-01",
            "expiry_date": "2027-12-31",
            "clauses": {"§第2条": "按改造投入的20%给予补助。"},
        },
    )
    assert r_ingest.status_code == 200
    assert r_ingest.json()["doc_id"] == "POL-2026-MFG-03"

    r_lint = client.post("/api/v1/wiki/lint", json={"reference_date": "2026-06-01"})
    assert r_lint.status_code == 200
    assert r_lint.json()["healthy"] is True

    # Ontology eligibility
    citizen = {
        "applicant_id": "CIT-2026-01",
        "applicant_type": "citizen",
        "name": "李明",
        "identifier": "310101199505051234",
        "region": "静安区",
        "annual_income_or_revenue": 180000.0,
        "employee_count": 0,
        "tags": ["青年人才"],
    }
    r_elig = client.post(
        "/api/v1/ontology/eligibility",
        json={"profile": citizen, "program_id": "PROG-HR-HOUSING-24K"},
    )
    assert r_elig.status_code == 200
    assert r_elig.json()["evaluations"][0]["eligible"] is True

    # Policy ask + HITL approve
    r_ask = client.post(
        "/api/v1/policy/ask",
        json={
            "question": "本人手机13900001111，请问是否符合青年科技人才安居补贴？",
            "profile": citizen,
            "program_id": "PROG-HR-HOUSING-24K",
        },
    )
    assert r_ask.status_code == 200
    ask_data = r_ask.json()
    assert ask_data["status"] == "answered"
    assert "13900001111" not in ask_data["masked_question"]
    action_id = ask_data["pending_action"]["action_id"]

    r_approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "officer_id": "OFFICER-WANG-02",
            "approved": True,
            "note": "社保与收入核验通过",
        },
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["status"] == "approved"

    # Metrics
    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    assert r_metrics.json()["hitl_approved"] >= 1
    assert r_metrics.json()["requests_total"] >= 6


def test_cors_middleware_headers(tmp_path: Path) -> None:
    """Test CORSMiddleware allows cross-origin requests and preflight OPTIONS."""
    app = create_app(data_dir=tmp_path / "cors_data", seed_defaults=True)
    client = TestClient(app)

    r_preflight = client.options(
        "/api/v1/dashboard/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_preflight.status_code == 200
    assert r_preflight.headers.get("access-control-allow-origin") == "*"

    r_get = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r_get.status_code == 200
    assert r_get.headers.get("access-control-allow-origin") == "*"


def test_enterprise_dashboard_wiki_pending_actions_and_audit_logs(tmp_path: Path) -> None:
    """Test /api/v1/dashboard/overview, /api/v1/wiki/pages, /api/v1/actions/pending, and /api/v1/audit/logs."""
    app = create_app(data_dir=tmp_path / "ent_data", seed_defaults=True)
    client = TestClient(app)

    # 1. Dashboard overview
    r_overview = client.get("/api/v1/dashboard/overview")
    assert r_overview.status_code == 200
    ov = r_overview.json()
    assert ov["service"] == "p06-govtech-policy"
    assert ov["active_policies"] >= 2
    assert ov["benefit_programs"] >= 2
    assert ov["wiki_pages"] >= 2
    assert ov["pending_hitl_reviews"] == 0

    # 2. Wiki pages listing
    r_pages = client.get("/api/v1/wiki/pages")
    assert r_pages.status_code == 200
    pages = r_pages.json()
    assert len(pages) >= 2
    for page in pages:
        assert "id" in page
        assert "title" in page
        assert "path" in page
        assert "preview" in page

    # 3. Trigger a pending HITL action via /api/v1/policy/ask
    enterprise_profile = {
        "applicant_id": "ENT-PEND-01",
        "applicant_type": "enterprise",
        "name": "量子云科技有限公司",
        "identifier": "91310000MA1K777766",
        "region": "浦东新区",
        "annual_income_or_revenue": 5000000.0,
        "employee_count": 50,
        "industry": "云计算",
        "tags": ["高新技术"],
    }
    r_ask = client.post(
        "/api/v1/policy/ask",
        json={
            "question": "我司统一社会信用代码91310000MA1K777766，联系人手机13800138000，申请研发补贴。",
            "profile": enterprise_profile,
            "program_id": "PROG-TECH-RD-500K",
            "create_hitl_action": True,
        },
    )
    assert r_ask.status_code == 200
    action_id = r_ask.json()["pending_action"]["action_id"]

    # 4. Pending actions endpoint
    r_pending = client.get("/api/v1/actions/pending")
    assert r_pending.status_code == 200
    pending_list = r_pending.json()
    assert any(a["action_id"] == action_id for a in pending_list)

    # 5. Audit logs endpoint (must be PII-safe)
    r_audit = client.get("/api/v1/audit/logs")
    assert r_audit.status_code == 200
    logs = r_audit.json()
    assert len(logs) >= 2
    serialized = str(logs)
    assert "91310000MA1K777766" not in serialized
    assert "13800138000" not in serialized


def test_enterprise_policy_batch_match_matrix(tmp_path: Path) -> None:
    """Test POST /api/v1/policy/batch-match multi-program eligibility matrix."""
    app = create_app(data_dir=tmp_path / "batch_data", seed_defaults=True)
    client = TestClient(app)

    payload = {
        "profiles": [
            {
                "applicant_id": "ENT-BATCH-01",
                "applicant_type": "enterprise",
                "name": "智算未来有限公司",
                "identifier": "91310000MA1K111122",
                "region": "张江科学城",
                "annual_income_or_revenue": 6000000.0,
                "employee_count": 60,
                "industry": "人工智能",
                "tags": ["高新技术"],
            },
            {
                "applicant_id": "CIT-BATCH-02",
                "applicant_type": "citizen",
                "name": "王芳",
                "identifier": "310101199808081234",
                "region": "徐汇区",
                "annual_income_or_revenue": 220000.0,
                "employee_count": 0,
                "industry": "集成电路",
                "tags": ["青年人才"],
            },
            {
                "applicant_id": "ENT-BATCH-03",
                "applicant_type": "enterprise",
                "name": "微小商贸个体",
                "identifier": "91310000MA1K333344",
                "region": "黄浦区",
                "annual_income_or_revenue": 150000.0,
                "employee_count": 2,
                "industry": "零售",
                "tags": [],
            },
        ]
    }

    r_batch = client.post("/api/v1/policy/batch-match", json=payload)
    assert r_batch.status_code == 200
    data = r_batch.json()
    assert data["total_applicants"] == 3
    assert data["total_programs_evaluated"] >= 2
    assert data["eligible_applicants"] == 2
    assert data["total_potential_subsidy"] == 524000.0
    assert len(data["matrix"]) == 3

    # Verify identifiers are masked in response
    for row in data["matrix"]:
        assert "91310000MA1K111122" not in row["masked_identifier"]
        assert "310101199808081234" not in row["masked_identifier"]
        assert "*" in row["masked_identifier"]

    # Unknown program_id returns 404
    r_err = client.post(
        "/api/v1/policy/batch-match",
        json={"profiles": [payload["profiles"][0]], "program_ids": ["UNKNOWN-PROG"]},
    )
    assert r_err.status_code == 404


def test_cross_dept_workflow_router_sequential_and_parallel() -> None:
    """Test CrossDeptWorkflowRouter for hybrid_parallel enterprise & sequential citizen cases."""
    router = CrossDeptWorkflowRouter()

    # High-value enterprise case: 人社局 & 科技局 run in parallel (5 SLA days), then 财政局 (3 SLA days) = 8 days
    ent_route = router.route_case(
        WorkflowRouteRequest(
            applicant_id="ENT-ROUTE-01",
            applicant_type="enterprise",
            program_id="PROG-TECH-RD-500K",
            program_name="高新技术企业研发创新补贴",
            amount=500000.0,
            approved=True,
            tags=["高新技术", "专精特新"],
            current_step=2,
        )
    )
    assert ent_route.route_summary == "人社局 -> 科技局 -> 财政局"
    assert ent_route.workflow_pattern == "hybrid_parallel"
    assert ent_route.fast_track is False
    assert ent_route.total_sla_days == 8
    assert len(ent_route.stages) == 3
    assert ent_route.stages[0].execution_mode == "parallel"
    assert ent_route.stages[1].execution_mode == "parallel"
    assert ent_route.stages[2].execution_mode == "sequential"
    assert ent_route.stages[0].status == "completed"
    assert ent_route.stages[2].status == "in_progress"
    assert len(ent_route.consolidated_documents) >= 6

    # Citizen fast-track case (< 50k): sequential 2 + 2 + 2 = 6 SLA days
    cit_route = router.route_case(
        WorkflowRouteRequest(
            applicant_id="CIT-ROUTE-02",
            applicant_type="citizen",
            program_id="PROG-HR-HOUSING-24K",
            amount=24000.0,
            approved=True,
            tags=["青年人才"],
            current_step=1,
        )
    )
    assert cit_route.route_summary == "人社局 -> 科技局 -> 财政局"
    assert cit_route.workflow_pattern == "sequential"
    assert cit_route.fast_track is True
    assert cit_route.total_sla_days == 6


def test_policy_gazette_differ_subsidy_caps_and_clauses() -> None:
    """Test PolicyGazetteDiffer baseline diff and custom revision diff."""
    differ = PolicyGazetteDiffer()

    baseline_diff = differ.diff(PolicyDiffRequest(policy_id="POL-2026-TECH-01"))
    assert baseline_diff.has_changes is True
    assert baseline_diff.subsidy_cap_delta == 200000.0
    assert baseline_diff.old_status == "expired"
    assert baseline_diff.new_status == "active"
    assert any(c.change_type == "added" and c.clause_ref == "§第6条" for c in baseline_diff.clause_diffs)
    assert any(c.change_type == "modified" and c.clause_ref == "§第5条" for c in baseline_diff.clause_diffs)

    # Custom revisions
    custom_diff = differ.diff(
        PolicyDiffRequest(
            old_revision=PolicyRevision(
                policy_id="POL-CUSTOM-01",
                version="v1",
                title="数字化转型专项资金",
                effective_date="2025-01-01",
                status="expired",
                subsidy_cap=100000.0,
                eligibility_threshold="年营收>=50万元",
                clauses={"§第1条": "支持中小企业上云。", "§第2条": "旧版附加条款。"},
            ),
            new_revision=PolicyRevision(
                policy_id="POL-CUSTOM-01",
                version="v2",
                title="数字化转型专项资金",
                effective_date="2026-01-01",
                status="active",
                subsidy_cap=250000.0,
                eligibility_threshold="年营收>=30万元",
                clauses={"§第1条": "支持中小企业上云与智改数转。", "§第3条": "新增绿色通道。"},
            ),
        )
    )
    assert custom_diff.subsidy_cap_delta == 150000.0
    clause_map = {c.clause_ref: c.change_type for c in custom_diff.clause_diffs}
    assert clause_map["§第1条"] == "modified"
    assert clause_map["§第2条"] == "removed"
    assert clause_map["§第3条"] == "added"


def test_fastapi_workflow_route_and_gazette_diff_endpoints(tmp_path: Path) -> None:
    """Test POST /api/v1/workflow/route-case and POST /api/v1/policy/gazette-diff."""
    app = create_app(data_dir=tmp_path / "workflow_api_data", seed_defaults=True)
    client = TestClient(app)

    r_route = client.post(
        "/api/v1/workflow/route-case",
        json={
            "applicant_id": "ENT-API-01",
            "applicant_type": "enterprise",
            "program_id": "PROG-TECH-RD-500K",
            "amount": 500000.0,
            "approved": True,
            "tags": ["高新技术"],
            "current_step": 1,
        },
    )
    assert r_route.status_code == 200
    route_data = r_route.json()
    assert route_data["route_summary"] == "人社局 -> 科技局 -> 财政局"
    assert route_data["total_sla_days"] == 8
    assert len(route_data["stages"]) == 3

    r_diff = client.post(
        "/api/v1/policy/gazette-diff",
        json={"policy_id": "POL-2026-HR-02"},
    )
    assert r_diff.status_code == 200
    diff_data = r_diff.json()
    assert diff_data["subsidy_cap_delta"] == 6000.0
    assert diff_data["new_status"] == "active"

    # Unknown policy_id returns 404
    r_missing = client.post(
        "/api/v1/policy/gazette-diff",
        json={"policy_id": "POL-NON-EXISTENT"},
    )
    assert r_missing.status_code == 404

    # Missing both policy_id and revisions returns 400
    r_bad = client.post("/api/v1/policy/gazette-diff", json={})
    assert r_bad.status_code == 400

