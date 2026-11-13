"""Comprehensive offline tests for Project P03: Legal Compliance & Contract Review Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from app.fde_pipeline import LegalFDEPipeline
from app.llm_wiki import LegalLLMWiki
from app.ontology import Clause, Contract, LegalOntologyRegistry


def test_ontology_classification_and_regulation_mapping() -> None:
    registry = LegalOntologyRegistry(seed_defaults=True)
    contract = Contract(id="ctr_001", title="Enterprise SaaS MSA", counterparty="Acme Corp")
    registry.register_contract(contract)

    critical_clause = Clause(
        id="cl_001",
        contract_id="ctr_001",
        title="Liability",
        text="Vendor shall have unlimited liability for all data breach and GDPR personal data claims.",
    )
    registry.register_clause(critical_clause)

    assert critical_clause.clause_type == "liability_cap"
    assert critical_clause.risk_level == "critical"
    assert critical_clause.risk_score >= 0.85
    assert critical_clause.redline_suggestion is not None
    assert "reg_gdpr_art28" in critical_clause.matched_regulations
    assert "reg_civil_584" in critical_clause.matched_regulations
    assert "lnk_cl_001_reg_gdpr_art28_governed_by" in registry.links


def test_llm_wiki_ingest_query_and_markdown_persistence(tmp_path: Path) -> None:
    wiki = LegalLLMWiki(root_dir=tmp_path)
    result = wiki.ingest(
        doc_id="ctr_wiki_1",
        title="Global DPA 2026",
        content=(
            "1. Data Processing\nVendor shall process personal data strictly under GDPR instructions.\n\n"
            "2. Security Controls\nVendor shall maintain SOC2 encryption and confidential access controls."
        ),
        doc_type="contract",
        metadata={"counterparty": "Beta Ltd", "jurisdiction": "EU"},
    )

    assert "ctr_wiki_1" in result["entities"]
    assert (tmp_path / "index.md").exists()
    assert (tmp_path / "log.md").exists()
    contract_md = (tmp_path / "entities" / "ctr_wiki_1.md").read_text(encoding="utf-8")
    assert "[[ctr_wiki_1_cl_1]]" in contract_md
    assert "[[ctr_wiki_1_cl_2]]" in contract_md

    hits = wiki.query("GDPR personal data")
    assert len(hits) >= 1
    assert any(h["entity_id"] == "ctr_wiki_1_cl_1" for h in hits)
    log_text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "INGEST" in log_text and "QUERY" in log_text


def test_llm_wiki_lint_detects_superseded_unlinked_and_conflicting_caps(tmp_path: Path) -> None:
    registry = LegalOntologyRegistry(seed_defaults=True)
    wiki = LegalLLMWiki(root_dir=tmp_path, registry=registry)

    contract = Contract(
        id="ctr_lint",
        title="Conflicting MSA",
        liability_cap_usd=500_000.0,
    )
    registry.register_contract(contract)

    # 1. Clause referencing superseded EU DPD 95/46/EC
    cl_sup = Clause(
        id="cl_sup",
        contract_id="ctr_lint",
        title="Legacy Privacy",
        text="Data transfers shall comply with EU Directive 95/46/EC.",
    )
    registry.register_clause(cl_sup)

    # 2. Unlinked clause (no regulation keywords)
    cl_unlinked = Clause(
        id="cl_unlinked",
        contract_id="ctr_lint",
        title="Miscellaneous",
        text="Notices shall be delivered by courier on business days.",
    )
    registry.register_clause(cl_unlinked)

    # 3. Conflicting liability cap clause ($100,000 vs contract $500,000)
    cl_cap = Clause(
        id="cl_cap",
        contract_id="ctr_lint",
        title="Liability Cap",
        text="Total aggregate liability under this agreement shall not exceed $100,000.",
    )
    registry.register_clause(cl_cap)
    wiki.sync_contract(contract)

    report = wiki.lint()
    assert report["total_issues"] >= 3
    assert any(item["regulation_code"] == "EU-DPD-95/46/EC" for item in report["superseded_regulations"])
    assert any(item["clause_id"] == "cl_unlinked" for item in report["unlinked_clauses"])
    assert any(item["contract_id"] == "ctr_lint" for item in report["conflicting_liability_caps"])


def test_fde_pipeline_pii_masking_and_clause_extraction(tmp_path: Path) -> None:
    registry = LegalOntologyRegistry(seed_defaults=True)
    wiki = LegalLLMWiki(root_dir=tmp_path, registry=registry)
    pipeline = LegalFDEPipeline(registry=registry, wiki=wiki)

    raw_contract = (
        "1. Contacts\n"
        "Legal notices go to counsel@acme.com or +1-415-555-0199, SSN 123-45-6789, IBAN DE89370400440532013000.\n\n"
        "2. Confidentiality\n"
        "Both parties shall keep all proprietary and confidential information secure."
    )
    review = pipeline.review_contract(
        contract_id="ctr_pii",
        title="NDA with PII",
        raw_text=raw_contract,
    )

    assert review["pii_masked_count"] == 4
    assert "counsel@acme.com" not in review["masked_text"]
    assert "123-45-6789" not in review["masked_text"]
    assert "[EMAIL_REDACTED]" in review["masked_text"]
    assert "[ID_REDACTED]" in review["masked_text"]
    assert "[ACCOUNT_REDACTED]" in review["masked_text"]
    assert "[PHONE_REDACTED]" in review["masked_text"]
    assert len(review["clauses"]) == 2


def test_fde_pipeline_hitl_approval_and_audit_trail(tmp_path: Path) -> None:
    registry = LegalOntologyRegistry(seed_defaults=True)
    wiki = LegalLLMWiki(root_dir=tmp_path, registry=registry)
    pipeline = LegalFDEPipeline(registry=registry, wiki=wiki)

    review = pipeline.review_contract(
        contract_id="ctr_hitl",
        title="High Risk Vendor Agreement",
        raw_text=(
            "1. Liability\nVendor accepts unlimited liability for all claims.\n\n"
            "2. Governing Law\nThis agreement is governed by New York law."
        ),
    )

    assert review["requires_hitl"] is True
    assert review["overall_risk_level"] == "critical"
    assert review["contract"]["status"] == "pending_gc_approval"
    assert len(review["pending_actions"]) == 1

    action_id = review["pending_actions"][0]["id"]
    decided = pipeline.approve_action(
        action_id=action_id,
        decision="approved",
        approver="gc_jane_doe",
        notes="Approved with executive exception.",
    )
    assert decided.status == "approved"
    assert registry.contracts["ctr_hitl"].status == "approved"
    assert any(e["event_type"] == "HITL_ACTION_DECIDED" for e in pipeline.audit_trail)


def test_fastapi_health_ready_metrics_and_request_id(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    h_resp = client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert h_resp.status_code == 200
    assert h_resp.json()["status"] == "ok"
    assert h_resp.headers["X-Request-ID"] == "req-abc-123"

    r_resp = client.get("/ready")
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "ready"
    assert "X-Request-ID" in r_resp.headers

    m_resp = client.get("/metrics")
    assert m_resp.status_code == 200
    assert m_resp.json()["requests_total"] >= 3


def test_fastapi_wiki_ingest_lint_and_ontology_clauses(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    ingest_resp = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "ctr_api_1",
            "title": "API Ingested DPA",
            "doc_type": "contract",
            "content": "Data processing shall follow EU Directive 95/46/EC and confidential standards.",
        },
    )
    assert ingest_resp.status_code == 200
    assert "ctr_api_1" in ingest_resp.json()["entities"]

    clauses_resp = client.get("/api/v1/ontology/clauses", params={"contract_id": "ctr_api_1"})
    assert clauses_resp.status_code == 200
    assert clauses_resp.json()["count"] == 1
    assert clauses_resp.json()["clauses"][0]["risk_level"] == "high"

    lint_resp = client.get("/api/v1/wiki/lint")
    assert lint_resp.status_code == 200
    assert lint_resp.json()["total_issues"] >= 1
    assert len(lint_resp.json()["superseded_regulations"]) == 1


def test_fastapi_contract_review_and_hitl_approve_e2e(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    rev_resp = client.post(
        "/api/v1/contracts/review",
        json={
            "contract_id": "ctr_e2e",
            "title": "Cloud Enterprise Agreement",
            "counterparty": "Delta Cloud Inc.",
            "text": (
                "1. Privacy\nVendor may sell personal data without opt-out.\n\n"
                "2. Contact\nEmail legal@delta.io for notices."
            ),
        },
    )
    assert rev_resp.status_code == 200
    data = rev_resp.json()
    assert data["requires_hitl"] is True
    assert data["pii_masked_count"] == 1
    action_id = data["pending_actions"][0]["id"]

    app_resp = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "decision": "rejected",
            "approver": "gc_chief",
            "notes": "Cannot sell personal data under CCPA.",
        },
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["action"]["status"] == "rejected"
    assert app_resp.json()["contract_status"] == "rejected"


def test_fastapi_cors_headers(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    preflight = client.options(
        "/api/v1/dashboard/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"

    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_fastapi_dashboard_overview_wiki_pages_and_regulations(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    # Review a contract with a critical clause
    rev_resp = client.post(
        "/api/v1/contracts/review",
        json={
            "contract_id": "ctr_dash_1",
            "title": "Enterprise MSA",
            "counterparty": "Globex Corp",
            "text": "1. Liability\nVendor shall have unlimited liability for GDPR data breach claims.",
        },
    )
    assert rev_resp.status_code == 200

    dash_resp = client.get("/api/v1/dashboard/overview")
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["contracts_reviewed"] == 1
    assert dash["high_risk_clauses"] >= 1
    assert dash["active_regulations"] >= 5
    assert dash["pending_gc_approvals"] == 1
    assert dash["audit_logs_count"] >= 1
    assert dash["wiki_pages_count"] >= 6

    pages_resp = client.get("/api/v1/wiki/pages")
    assert pages_resp.status_code == 200
    pages_data = pages_resp.json()
    assert pages_data["count"] >= 6
    page_ids = {p["id"] for p in pages_data["pages"]}
    assert "reg_gdpr_art28" in page_ids
    assert "ctr_dash_1" in page_ids
    for page in pages_data["pages"]:
        assert {"id", "title", "path", "preview"}.issubset(page.keys())

    regs_resp = client.get("/api/v1/ontology/regulations")
    assert regs_resp.status_code == 200
    assert regs_resp.json()["count"] >= 6


def test_fastapi_pending_actions_audit_logs_and_redline_diff(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path)
    client = TestClient(app)

    # 1. Trigger a pending HITL approval
    rev_resp = client.post(
        "/api/v1/contracts/review",
        json={
            "contract_id": "ctr_pending_1",
            "title": "Vendor DPA",
            "text": "1. Liability\nVendor accepts unlimited liability for all damages.",
        },
    )
    assert rev_resp.status_code == 200

    pending_resp = client.get("/api/v1/actions/pending")
    assert pending_resp.status_code == 200
    pending_data = pending_resp.json()
    assert pending_data["count"] == 1
    assert pending_data["actions"][0]["status"] == "pending"

    # 2. Run redline-diff comparing uncapped v1 against capped v2
    diff_resp = client.post(
        "/api/v1/contracts/redline-diff",
        json={
            "contract_id": "ctr_diff_1",
            "title": "MSA v1 vs v2",
            "original_text": (
                "1. Liability\nVendor shall have unlimited liability for all claims.\n\n"
                "2. Privacy\nVendor may sell personal data without opt-out."
            ),
            "revised_text": (
                "1. Liability\nVendor total aggregate liability shall not exceed $500,000.\n\n"
                "2. Privacy\nVendor shall process personal data strictly under GDPR Art.28."
            ),
        },
    )
    assert diff_resp.status_code == 200
    diff = diff_resp.json()
    assert diff["original_risk_level"] == "critical"
    assert diff["revised_risk_level"] == "low"
    assert diff["risk_score_delta"] < 0
    assert diff["risk_trend"] == "improved"
    assert len(diff["clause_diffs"]) == 2
    assert diff["clause_diffs"][0]["risk_delta"] < 0

    # 3. Verify audit logs record both events
    audit_resp = client.get("/api/v1/audit/logs")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["count"] >= 2
    event_types = {entry["event_type"] for entry in audit_data["logs"]}
    assert "CONTRACT_REVIEWED" in event_types
    assert "CONTRACT_REDLINE_DIFF" in event_types
