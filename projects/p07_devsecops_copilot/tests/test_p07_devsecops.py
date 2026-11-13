"""Pytest suite for Project P07: Enterprise R&D Efficiency & DevSecOps Copilot."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

# Ensure projects/p07_devsecops_copilot is importable cleanly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app
from app.fde_pipeline import DevSecOpsFDEPipeline, redact_secrets
from app.llm_wiki import DevSecOpsLLMWiki
from app.ontology import (
    CVE,
    DependencyLink,
    DevSecOpsOntologyRegistry,
    Incident,
    Runbook,
    Service,
)


def test_ontology_blast_radius_and_cvss_gate() -> None:
    registry = DevSecOpsOntologyRegistry()
    registry.seed_default_topology()

    blast = registry.compute_blast_radius("svc-auth")
    impacted_ids = {item["service_id"] for item in blast["impacted_upstream"]}

    assert blast["root_service_id"] == "svc-auth"
    assert impacted_ids == {"svc-payment", "svc-checkout", "svc-web-portal"}
    assert blast["total_impacted_services"] == 3
    assert "svc-auth" in blast["tier0_impacted"]
    assert "svc-payment" in blast["tier0_impacted"]
    assert blast["cvss_gate"]["blocked"] is True
    assert blast["cvss_gate"]["gate_decision"] == "BLOCK_DEPLOY"
    assert blast["cvss_gate"]["max_cvss"] == 9.4

    # Checkout has only a patched CVE -> PASS
    checkout_gate = registry.evaluate_cvss_gate("svc-checkout")
    assert checkout_gate["blocked"] is False
    assert checkout_gate["gate_decision"] == "PASS"


def test_llm_wiki_ingest_query_and_lint(tmp_path: Path) -> None:
    registry = DevSecOpsOntologyRegistry()
    registry.register_service(Service("svc-core", "Core API", tier="tier-0", runbook_id="rb-core"))
    registry.register_service(Service("svc-orphan", "Orphan Worker", tier="tier-2", runbook_id=None))
    registry.register_runbook(Runbook("rb-core", "Core API Runbook", "svc-core", steps=["Restart pod"]))
    registry.register_cve(CVE("CVE-2026-9999", "svc-core", cvss_score=9.8, patched=False, description="RCE flaw"))
    registry.register_incident(
        Incident(
            "INC-900",
            "Stale Outage",
            "svc-core",
            severity="SEV-1",
            status="RESOLVED",
            postmortem_updated_at="2026-08-01",
        )
    )

    wiki = DevSecOpsLLMWiki(tmp_path / "wiki")
    ingested_count = wiki.sync_from_ontology(registry)
    assert ingested_count == 5
    assert wiki.index_path.exists()
    assert wiki.log_path.exists()
    assert (wiki.entities_dir / "svc-core.md").exists()
    assert "[[svc-core]]" in wiki.index_path.read_text(encoding="utf-8")

    # Ingest a custom page with a broken wiki link
    wiki.ingest(
        "note",
        "note-arch",
        "Architecture Note",
        "References [[svc-core]] and missing [[svc-ghost]].",
        links=["svc-core", "svc-ghost"],
    )

    hits = wiki.query("RCE flaw svc-core")
    assert len(hits) >= 1
    assert hits[0]["entity_id"] in {"CVE-2026-9999", "svc-core"}

    lint_report = wiki.lint(registry=registry, reference_date="2026-11-13", stale_days=30)
    assert lint_report["healthy"] is False
    assert "svc-orphan" in lint_report["services_without_runbooks"]
    assert any(c["cve_id"] == "CVE-2026-9999" for c in lint_report["unpatched_critical_cves"])
    assert any(i["incident_id"] == "INC-900" for i in lint_report["stale_postmortems"])
    assert any(b["missing_target"] == "svc-ghost" for b in lint_report["broken_wiki_links"])


def test_secret_redaction_guardrail() -> None:
    raw = (
        "Auth failed with Bearer eyJhbGciOiJIUzI1NiJ9.abc123 "
        "and ghp_1234567890abcdefghij123456 "
        "and AKIAIOSFODNN7EXAMPLE "
        "and sk-proj1234567890abcdef "
        "password=supersecretpass"
    )
    redacted, applied = redact_secrets(raw)

    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "ghp_1234567890abcdefghij123456" not in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "sk-proj1234567890abcdef" not in redacted
    assert "supersecretpass" not in redacted
    assert set(applied) == {
        "OPENAI_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY",
        "BEARER_TOKEN",
        "CREDENTIAL_KV",
    }


def test_fde_pipeline_hitl_gate_and_audit_trail(tmp_path: Path) -> None:
    registry = DevSecOpsOntologyRegistry()
    registry.seed_default_topology()
    wiki = DevSecOpsLLMWiki(tmp_path / "wiki")
    wiki.sync_from_ontology(registry)
    pipeline = DevSecOpsFDEPipeline(registry=registry, wiki=wiki)

    triage = pipeline.triage_incident(
        service_id="svc-payment",
        symptom="500 error in ledger with Bearer secret_abc_123456789",
        severity="SEV-1",
        proposed_action="rollback",
        environment="prod",
    )

    assert "secret_abc_123456789" not in triage["redacted_symptom"]
    assert "BEARER_TOKEN" in triage["redactions_applied"]
    assert triage["action"]["requires_hitl"] is True
    assert triage["action"]["status"] == "PENDING_APPROVAL"
    assert len(pipeline.audit_trail) == 1

    decision = pipeline.approve_action(
        action_id=triage["action"]["action_id"],
        approved=True,
        approver="sre-lead-bob",
        comment="Verified canary metrics, proceed with rollback.",
    )
    assert decision["status"] == "EXECUTED"
    assert decision["approved_by"] == "sre-lead-bob"
    assert len(pipeline.audit_trail) == 2

    # Non-destructive notify action should auto-execute without HITL
    notify_triage = pipeline.triage_incident(
        service_id="svc-checkout",
        symptom="Minor latency bump",
        severity="SEV-3",
        proposed_action="notify",
        environment="prod",
    )
    assert notify_triage["action"]["requires_hitl"] is False
    assert notify_triage["action"]["status"] == "EXECUTED"


def test_fastapi_health_ready_metrics_and_request_id(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "wiki", seed_demo=True)
    client = TestClient(app)

    r_health = client.get("/health", headers={"X-Request-ID": "trace-custom-001"})
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert r_health.headers["X-Request-ID"] == "trace-custom-001"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert r_ready.json()["services_count"] == 4

    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    assert r_metrics.json()["requests_total"] >= 2
    assert r_metrics.headers["X-Request-ID"].startswith("req-")


def test_fastapi_wiki_ontology_triage_and_approve_flow(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "wiki", seed_demo=True)
    client = TestClient(app)

    # 1. Ingest into Wiki
    r_ingest = client.post(
        "/api/v1/wiki/ingest",
        json={
            "entity_type": "runbook",
            "entity_id": "rb-portal",
            "title": "Portal Cache Flush",
            "content": "Flush CDN edge cache for [[svc-web-portal]].",
            "links": ["svc-web-portal"],
        },
    )
    assert r_ingest.status_code == 200
    assert r_ingest.json()["status"] == "ingested"

    # 2. Lint Wiki
    r_lint = client.get("/api/v1/wiki/lint")
    assert r_lint.status_code == 200
    lint_data = r_lint.json()
    assert "svc-web-portal" in lint_data["services_without_runbooks"]
    assert any(c["cve_id"] == "CVE-2026-1042" for c in lint_data["unpatched_critical_cves"])

    # 3. Blast Radius
    r_blast = client.get("/api/v1/ontology/blast-radius", params={"service_id": "svc-auth"})
    assert r_blast.status_code == 200
    assert r_blast.json()["total_impacted_services"] == 3

    # 4. Triage Incident (quarantine in prod -> HITL)
    r_triage = client.post(
        "/api/v1/incidents/triage",
        json={
            "service_id": "svc-auth",
            "symptom": "JWT bypass attempt with ghp_1234567890abcdefghij123456",
            "severity": "SEV-1",
            "proposed_action": "quarantine",
            "environment": "prod",
        },
    )
    assert r_triage.status_code == 200
    triage_data = r_triage.json()
    assert "ghp_1234567890abcdefghij123456" not in triage_data["redacted_symptom"]
    assert triage_data["action"]["status"] == "PENDING_APPROVAL"
    action_id = triage_data["action"]["action_id"]

    # 5. Approve Action
    r_approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "approved": False,
            "approver": "sre-oncall-alice",
            "comment": "False positive, keep running.",
        },
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["status"] == "REJECTED"


def test_fastapi_cors_headers(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "wiki", seed_demo=True)
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
    assert r_preflight.headers.get("access-control-allow-origin") == "*"

    r_get = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r_get.status_code == 200
    assert r_get.headers.get("access-control-allow-origin") == "*"


def test_fastapi_dashboard_wiki_pages_pending_and_audit(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "wiki", seed_demo=True)
    client = TestClient(app)

    # 1. Dashboard overview KPIs
    r_overview = client.get("/api/v1/dashboard/overview")
    assert r_overview.status_code == 200
    overview = r_overview.json()
    assert overview["services_total"] == 4
    assert overview["critical_cves_total"] == 1
    assert overview["pending_hitl_rollbacks"] == 0
    assert len(overview["services"]) == 4

    # 2. Wiki pages list
    r_pages = client.get("/api/v1/wiki/pages")
    assert r_pages.status_code == 200
    pages_data = r_pages.json()
    assert pages_data["total"] >= 7
    first_page = pages_data["pages"][0]
    assert {"id", "title", "path", "preview"}.issubset(first_page.keys())

    # 3. Trigger HITL triage -> appears in /api/v1/actions/pending
    r_triage = client.post(
        "/api/v1/incidents/triage",
        json={
            "service_id": "svc-payment",
            "symptom": "Ledger timeout with sk-testkey1234567890abcdef",
            "severity": "SEV-1",
            "proposed_action": "rollback",
            "environment": "prod",
        },
    )
    assert r_triage.status_code == 200
    action_id = r_triage.json()["action"]["action_id"]

    r_pending = client.get("/api/v1/actions/pending")
    assert r_pending.status_code == 200
    pending_data = r_pending.json()
    assert pending_data["total"] == 1
    assert pending_data["actions"][0]["action_id"] == action_id

    # 4. Approve action -> removed from pending, recorded in audit logs
    r_approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "approved": True,
            "approver": "sre-lead-carol",
            "comment": "Approved rollback with token=mysecret12345",
        },
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["status"] == "EXECUTED"

    r_pending_after = client.get("/api/v1/actions/pending")
    assert r_pending_after.status_code == 200
    assert r_pending_after.json()["total"] == 0

    r_audit = client.get("/api/v1/audit/logs")
    assert r_audit.status_code == 200
    audit_data = r_audit.json()
    assert audit_data["total"] == 2
    serialized = str(audit_data)
    assert "sk-testkey1234567890abcdef" not in serialized
    assert "mysecret12345" not in serialized


def test_fastapi_security_cve_gate(tmp_path: Path) -> None:
    app = create_app(wiki_dir=tmp_path / "wiki", seed_demo=True)
    client = TestClient(app)

    # Transitive dependency on svc-auth (CVE-2026-1042 CVSS 9.4) -> BLOCK_DEPLOY
    r_blocked = client.post(
        "/api/v1/security/cve-gate",
        json={
            "service_id": "svc-checkout",
            "release_version": "v2.4.0",
            "include_dependencies": True,
            "block_threshold": 9.0,
        },
    )
    assert r_blocked.status_code == 200
    blocked_data = r_blocked.json()
    assert blocked_data["decision"] == "BLOCK_DEPLOY"
    assert blocked_data["allowed"] is False
    assert blocked_data["max_cvss"] == 9.4
    assert any(c["cve_id"] == "CVE-2026-1042" for c in blocked_data["blocking_cves"])

    # Direct service only (svc-checkout has only patched CVE) -> ALLOW
    r_allow = client.post(
        "/api/v1/security/cve-gate",
        json={
            "service_id": "svc-checkout",
            "release_version": "v2.4.0",
            "include_dependencies": False,
            "block_threshold": 9.0,
        },
    )
    assert r_allow.status_code == 200
    allow_data = r_allow.json()
    assert allow_data["decision"] == "ALLOW"
    assert allow_data["allowed"] is True

    # Dependency CVSS override -> BLOCK_DEPLOY
    r_override = client.post(
        "/api/v1/security/cve-gate",
        json={
            "service_id": "svc-checkout",
            "release_version": "v2.4.1",
            "include_dependencies": False,
            "dependency_cvss_overrides": {"lib-openssl": 9.8},
        },
    )
    assert r_override.status_code == 200
    assert r_override.json()["decision"] == "BLOCK_DEPLOY"

    # Unknown service -> 404
    r_404 = client.post(
        "/api/v1/security/cve-gate",
        json={"service_id": "svc-nonexistent"},
    )
    assert r_404.status_code == 404

