"""Comprehensive pytest suite for Project P01: FinTech Research & Compliance Agent."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from app.fde_pipeline import FinTechFDEPipeline
from app.llm_wiki import FinTechLLMWiki
from app.ontology import (
    ActionStatus,
    ComplianceAction,
    FinancialMetric,
    Issuer,
    LinkType,
    OntologyLink,
    OntologyRegistry,
    RiskSignal,
    SeverityLevel,
)


def test_ontology_validation_and_link_traversal() -> None:
    reg = OntologyRegistry()

    # Invalid credit rating rejected by Pydantic validator
    with pytest.raises(ValueError):
        Issuer(issuer_id="iss_bad", name="Bad Corp", ticker="BAD", sector="Tech", credit_rating="INVALID")

    iss_a = reg.register_issuer(
        Issuer(issuer_id="issuer_alpha", name="Alpha Fin", ticker="ALPH", sector="Lending", credit_rating="BBB")
    )
    reg.register_issuer(
        Issuer(issuer_id="issuer_beta", name="Beta Pay", ticker="BETA", sector="Payments", credit_rating="A")
    )
    metric = reg.register_metric(
        FinancialMetric(
            metric_id="m_alpha_de",
            issuer_id=iss_a.issuer_id,
            name="debt_to_equity",
            value=2.7,
            period="2025-Q4",
        )
    )
    signal = reg.register_risk_signal(
        RiskSignal(
            signal_id="sig_alpha_lev",
            issuer_id=iss_a.issuer_id,
            category="leverage",
            severity=SeverityLevel.HIGH,
            description="Debt-to-equity exceeds 2.0",
            triggered_by_metric=metric.metric_id,
        )
    )
    action = reg.register_action(
        ComplianceAction(
            action_id="act_alpha_1",
            issuer_id=iss_a.issuer_id,
            action_type="ESCALATE_REVIEW",
            required_role="compliance_officer",
            min_severity=SeverityLevel.HIGH,
            rationale="High leverage requires review",
        )
    )
    reg.add_link(OntologyLink(source_id=iss_a.issuer_id, target_id="issuer_beta", relation=LinkType.PEER_OF))

    # Schema violation: PEER_OF cannot connect Issuer -> FinancialMetric
    with pytest.raises(ValueError, match="Schema violation"):
        reg.add_link(OntologyLink(source_id=iss_a.issuer_id, target_id=metric.metric_id, relation=LinkType.PEER_OF))

    # Graph traversal from issuer_alpha
    graph = reg.traverse_graph(iss_a.issuer_id, max_depth=2)
    node_ids = {n["id"] for n in graph["nodes"]}
    assert {iss_a.issuer_id, "issuer_beta", metric.metric_id, signal.signal_id, action.action_id} <= node_ids

    # Precondition checks
    ok_bad_role, _ = reg.check_action_preconditions(action.action_id, actor_role="junior_analyst")
    assert not ok_bad_role
    ok_good, _ = reg.check_action_preconditions(action.action_id, actor_role="compliance_officer")
    assert ok_good


def test_llm_wiki_ingest_query_and_lint(tmp_path: Path) -> None:
    wiki = FinTechLLMWiki(tmp_path / "wiki")

    wiki.ingest(
        doc_id="doc_1",
        title="Q4 Report Alpha",
        content="Alpha Fin peer comparison with [[issuer_beta]].",
        entities=[
            {
                "id": "issuer_alpha",
                "name": "Alpha Fin",
                "type": "Issuer",
                "period": "2025-Q4",
                "metrics": {"debt_to_equity": 1.8},
                "links": ["issuer_beta"],
            },
            {
                "id": "issuer_beta",
                "name": "Beta Pay",
                "type": "Issuer",
                "period": "2025-Q4",
                "metrics": {"debt_to_equity": 0.9},
                "links": [],
            },
        ],
        timestamp="2025-12-01T00:00:00Z",
    )

    # Ingest conflicting metric for issuer_alpha in the same period + orphan page
    wiki.ingest(
        doc_id="doc_2",
        title="Revised Filing Alpha",
        content="Updated debt ratio for Alpha Fin.",
        entities=[
            {
                "id": "issuer_alpha",
                "name": "Alpha Fin",
                "type": "Issuer",
                "period": "2025-Q4",
                "metrics": {"debt_to_equity": 2.5},
                "links": ["nonexistent_peer"],
            },
            {
                "id": "issuer_stale_orphan",
                "name": "Stale Orphan Corp",
                "type": "Issuer",
                "period": "2024-Q1",
                "metrics": {"current_ratio": 1.2},
                "links": [],
            },
        ],
        timestamp="2025-01-01T00:00:00Z",
    )

    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "wiki" / "entities" / "issuer_alpha.md").exists()

    q_res = wiki.query("What is Alpha Fin debt_to_equity?")
    assert q_res["confidence"] > 0.0
    assert any(c["entity_id"] == "issuer_alpha" for c in q_res["citations"])
    assert "[[issuer_beta]]" in q_res["matched_links"]

    lint_res = wiki.lint(stale_days=90, reference_date="2026-01-01T00:00:00Z")
    assert lint_res["status"] == "issues_found"
    assert "issuer_stale_orphan" in lint_res["orphan_pages"]
    assert any(b["target"] == "nonexistent_peer" for b in lint_res["broken_links"])
    assert any(
        c["entity_id"] == "issuer_alpha" and c["metric"] == "debt_to_equity"
        for c in lint_res["conflicting_metrics"]
    )
    assert any(s["entity_id"] == "issuer_stale_orphan" for s in lint_res["stale_entries"])


def test_fde_pipeline_guardrails_ratios_and_hitl(tmp_path: Path) -> None:
    wiki = FinTechLLMWiki(tmp_path / "wiki")
    pipeline = FinTechFDEPipeline(wiki=wiki, audit_log_path=tmp_path / "audit.jsonl")

    pipeline.ingest_document(
        doc_id="doc_gamma",
        title="Gamma Credit Brief",
        content="Gamma Credit initial onboarding.",
        entities=[
            {
                "id": "issuer_gamma",
                "name": "Gamma Credit",
                "type": "Issuer",
                "ticker": "GAMM",
                "sector": "Credit",
                "credit_rating": "BB",
                "period": "2025-Q4",
                "metrics": {"revenue_growth": 0.05},
            }
        ],
    )

    # MNPI / insider trading query must be blocked
    blocked = pipeline.run_research(
        question="Give me insider trading MNPI tips on Gamma Credit",
        issuer_id="issuer_gamma",
    )
    assert blocked["status"] == "blocked"

    # PII in query must be redacted, high leverage/low coverage must enqueue HITL action
    res = pipeline.run_research(
        question="Check Gamma Credit risk; contact 13912345678 or analyst@example.com",
        issuer_id="issuer_gamma",
        financials={
            "total_debt": 300.0,
            "shareholders_equity": 100.0,
            "current_assets": 70.0,
            "current_liabilities": 100.0,
            "ebit": 12.0,
            "interest_expense": 10.0,
            "net_income": 5.0,
        },
        period="2025-Q4",
    )
    assert res["status"] == "completed"
    assert "[REDACTED_PHONE]" in res["question"]
    assert "[REDACTED_EMAIL]" in res["question"]
    assert res["ratios"]["ratios"]["debt_to_equity"] == 3.0
    assert res["hitl_pending_action"] is not None

    action_id = res["hitl_pending_action"]["action_id"]

    # Unauthorized role cannot approve
    with pytest.raises(PermissionError):
        pipeline.approve_action(
            action_id=action_id,
            decision="approve",
            actor_role="intern",
            approver="bob",
        )

    # Authorized compliance_officer can approve
    approved = pipeline.approve_action(
        action_id=action_id,
        decision="approve",
        actor_role="compliance_officer",
        approver="alice.chen",
        comment="Limit frozen per Q4 covenant breach",
    )
    assert approved["action"]["status"] == ActionStatus.APPROVED.value
    assert approved["action"]["approved_by"] == "alice.chen"

    audit_records = pipeline.read_audit_trail()
    assert len(audit_records) >= 4


def test_fastapi_health_ready_metrics_and_request_id(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    r_health = client.get("/health", headers={"X-Request-ID": "req-test-123"})
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert r_health.headers["X-Request-ID"] == "req-test-123"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert "X-Request-ID" in r_ready.headers

    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    assert r_metrics.json()["requests_total"] >= 3


def test_fastapi_end_to_end_research_and_hitl_flow(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    # 1. Ingest
    r_ing = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "doc_e2e_1",
            "title": "Delta Bank Q4",
            "content": "Delta Bank exposure analysis.",
            "entities": [
                {
                    "id": "issuer_delta",
                    "name": "Delta Bank",
                    "type": "Issuer",
                    "ticker": "DLTA",
                    "sector": "Banking",
                    "credit_rating": "BBB",
                    "period": "2025-Q4",
                    "metrics": {"roe": 0.11},
                }
            ],
        },
    )
    assert r_ing.status_code == 200
    assert "issuer_delta" in r_ing.json()["pages_updated"]

    # 2. Research query with risky financials
    r_query = client.post(
        "/api/v1/research/query",
        json={
            "question": "Assess Delta Bank solvency",
            "issuer_id": "issuer_delta",
            "financials": {
                "total_debt": 250.0,
                "shareholders_equity": 100.0,
                "current_assets": 90.0,
                "current_liabilities": 100.0,
                "ebit": 20.0,
                "interest_expense": 10.0,
                "net_income": 11.0,
            },
            "period": "2025-Q4",
        },
    )
    assert r_query.status_code == 200
    q_data = r_query.json()
    assert q_data["status"] == "completed"
    action_id = q_data["hitl_pending_action"]["action_id"]

    # 3. Ontology graph endpoint
    r_graph = client.get("/api/v1/ontology/graph", params={"issuer_id": "issuer_delta"})
    assert r_graph.status_code == 200
    assert r_graph.json()["root"] == "issuer_delta"

    # 4. Approve action
    r_app = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "decision": "approve",
            "actor_role": "compliance_officer",
            "approver": "cro.wang",
            "comment": "Approved via API",
        },
    )
    assert r_app.status_code == 200
    assert r_app.json()["action"]["status"] == "APPROVED"

    # 5. Wiki lint
    r_lint = client.get("/api/v1/wiki/lint")
    assert r_lint.status_code == 200
    assert "total_pages" in r_lint.json()


def test_fastapi_structured_error_handling(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    # 404 on unknown issuer graph traversal
    r_404 = client.get("/api/v1/ontology/graph", params={"issuer_id": "unknown_issuer"})
    assert r_404.status_code == 404
    assert r_404.json()["error"] == "NotFound"
    assert "request_id" in r_404.json()

    # 404 on unknown action approval
    r_act_404 = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": "missing_action",
            "decision": "approve",
            "actor_role": "compliance_officer",
            "approver": "alice",
        },
    )
    assert r_act_404.status_code == 404
    assert r_act_404.json()["error"] == "NotFound"


def test_fastapi_cors_headers(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    r_preflight = client.options(
        "/api/v1/dashboard/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert r_preflight.status_code == 200
    assert r_preflight.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")

    r_get = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r_get.status_code == 200
    assert r_get.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_fastapi_enterprise_dashboard_wiki_actions_and_audit(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    # Ingest entity into wiki & ontology
    r_ing = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "doc_ent_1",
            "title": "Epsilon Pay Q4",
            "content": "Epsilon Pay liquidity and leverage filing.",
            "entities": [
                {
                    "id": "issuer_epsilon",
                    "name": "Epsilon Pay",
                    "type": "Issuer",
                    "ticker": "EPSI",
                    "sector": "Payments",
                    "credit_rating": "BBB",
                    "period": "2025-Q4",
                    "metrics": {"roe": 0.08},
                }
            ],
        },
    )
    assert r_ing.status_code == 200

    # Trigger risk signal + pending HITL action
    r_query = client.post(
        "/api/v1/research/query",
        json={
            "question": "Evaluate Epsilon Pay debt coverage",
            "issuer_id": "issuer_epsilon",
            "financials": {
                "total_debt": 320.0,
                "shareholders_equity": 100.0,
                "current_assets": 80.0,
                "current_liabilities": 100.0,
                "ebit": 10.0,
                "interest_expense": 10.0,
                "net_income": 8.0,
            },
            "period": "2025-Q4",
        },
    )
    assert r_query.status_code == 200
    action_id = r_query.json()["hitl_pending_action"]["action_id"]

    # 1. Dashboard overview KPIs
    r_dash = client.get("/api/v1/dashboard/overview")
    assert r_dash.status_code == 200
    dash = r_dash.json()
    assert dash["total_issuers"] == 1
    assert dash["risk_signals"] >= 2
    assert dash["wiki_pages_count"] == 1
    assert dash["pending_hitl_count"] == 1
    assert dash["audit_events_count"] >= 2

    # 2. Wiki pages listing
    r_pages = client.get("/api/v1/wiki/pages")
    assert r_pages.status_code == 200
    pages_data = r_pages.json()
    assert pages_data["total"] == 1
    page = pages_data["pages"][0]
    assert page["id"] == "issuer_epsilon"
    assert page["title"] == "Epsilon Pay"
    assert page["path"].endswith("issuer_epsilon.md")
    assert len(page["preview"]) > 0

    # 3. Pending HITL actions
    r_pending = client.get("/api/v1/actions/pending")
    assert r_pending.status_code == 200
    assert r_pending.json()["total"] == 1
    assert r_pending.json()["actions"][0]["action_id"] == action_id

    # Approve action and verify pending queue clears
    r_approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "decision": "approve",
            "actor_role": "compliance_officer",
            "approver": "cco.li",
            "comment": "Reviewed Q4 risk",
        },
    )
    assert r_approve.status_code == 200
    assert client.get("/api/v1/actions/pending").json()["total"] == 0

    # 4. Audit logs
    r_logs = client.get("/api/v1/audit/logs", params={"limit": 10})
    assert r_logs.status_code == 200
    logs_data = r_logs.json()
    assert logs_data["total"] >= 3
    assert logs_data["logs"][0]["event_type"] == "HITL_DECISION"


def test_fastapi_batch_screen(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    r_batch = client.post(
        "/api/v1/research/batch-screen",
        json={
            "actor_role": "risk_analyst",
            "items": [
                {
                    "issuer_id": "issuer_safe",
                    "name": "Safe FinTech",
                    "ticker": "SAFE",
                    "sector": "Payments",
                    "credit_rating": "AA",
                    "period": "2025-Q4",
                    "financials": {
                        "total_debt": 50.0,
                        "shareholders_equity": 100.0,
                        "current_assets": 180.0,
                        "current_liabilities": 100.0,
                        "ebit": 40.0,
                        "interest_expense": 5.0,
                        "net_income": 25.0,
                    },
                },
                {
                    "issuer_id": "issuer_risky",
                    "name": "Risky Credit",
                    "ticker": "RISK",
                    "sector": "Lending",
                    "credit_rating": "BB",
                    "period": "2025-Q4",
                    "financials": {
                        "total_debt": 350.0,
                        "shareholders_equity": 100.0,
                        "current_assets": 75.0,
                        "current_liabilities": 100.0,
                        "ebit": 10.0,
                        "interest_expense": 10.0,
                        "net_income": 2.0,
                    },
                },
            ],
        },
    )
    assert r_batch.status_code == 200
    data = r_batch.json()
    assert data["status"] == "completed"
    assert data["screened_count"] == 2
    assert data["high_risk_count"] == 1

    by_id = {item["issuer_id"]: item for item in data["results"]}
    assert by_id["issuer_safe"]["risk_level"] == "LOW"
    assert by_id["issuer_safe"]["hitl_pending_action"] is None
    assert by_id["issuer_risky"]["risk_level"] == "CRITICAL"
    assert by_id["issuer_risky"]["hitl_pending_action"] is not None

    dash = client.get("/api/v1/dashboard/overview").json()
    assert dash["total_issuers"] == 2
    assert dash["pending_hitl_count"] == 1

