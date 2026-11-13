"""Comprehensive offline deterministic test suite for Project P02 Healthcare Copilot."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app  # noqa: E402
from app.fde_pipeline import HealthcareFDEPipeline  # noqa: E402
from app.llm_wiki import ClinicalLLMWiki  # noqa: E402
from app.ontology import (  # noqa: E402
    ClinicalOntologyRegistry,
    PatientCase,
    Symptom,
)


def test_ontology_drug_interaction_and_allergy_checks() -> None:
    registry = ClinicalOntologyRegistry(seed_defaults=True)

    # Contraindicated drug-drug interaction: warfarin + ibuprofen -> blocked=True
    ddi_res = registry.check_interactions(
        proposed_med_ids=["ibuprofen"],
        active_med_ids=["warfarin"],
    )
    assert ddi_res.has_conflicts is True
    assert ddi_res.blocked is True
    assert len(ddi_res.drug_interactions) == 1
    assert ddi_res.drug_interactions[0]["severity"] == "contraindicated"

    # Allergy cross-reactivity: penicillin allergy + amoxicillin -> blocked=True
    allergy_res = registry.check_interactions(
        proposed_med_ids=["amoxicillin"],
        allergies=["penicillin"],
    )
    assert allergy_res.has_conflicts is True
    assert allergy_res.blocked is True
    assert allergy_res.allergy_conflicts[0]["med_id"] == "amoxicillin"

    # Safe combination: acetaminophen with warfarin
    safe_res = registry.check_interactions(
        proposed_med_ids=["acetaminophen"],
        active_med_ids=["warfarin"],
        allergies=["penicillin"],
    )
    assert safe_res.has_conflicts is False
    assert safe_res.blocked is False


def test_llm_wiki_ingest_and_query(tmp_path: Path) -> None:
    wiki = ClinicalLLMWiki(tmp_path / "wiki")
    wiki.ingest(
        doc_id="gl_acs_aspirin",
        title="ACS Aspirin Loading Protocol",
        content="Administer Aspirin 325 mg chewed immediately for suspected acute coronary syndrome.",
        entity_type="guideline",
        condition="acute_coronary_syndrome",
        medication="aspirin",
        dose_mg=325.0,
        citation="AHA/ACC 2021",
        related_ids=["chest_pain"],
    )

    entity_file = tmp_path / "wiki" / "entities" / "gl_acs_aspirin.md"
    assert entity_file.exists()
    content = entity_file.read_text(encoding="utf-8")
    assert "[[chest_pain]]" in content
    assert "[[acute_coronary_syndrome]]" in content
    assert "[[aspirin]]" in content

    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    log_text = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "gl_acs_aspirin" in index_text
    assert "INGEST" in log_text

    hits = wiki.query("aspirin acute coronary syndrome", top_k=3)
    assert len(hits) == 1
    assert hits[0]["doc_id"] == "gl_acs_aspirin"
    assert hits[0]["score"] > 0


def test_llm_wiki_lint_detects_conflicts_orphans_and_missing_citations(
    tmp_path: Path,
) -> None:
    wiki = ClinicalLLMWiki(tmp_path / "wiki")

    # Two guidelines for same (condition, medication) with conflicting doses
    wiki.ingest(
        doc_id="gl_htn_v1",
        title="Hypertension Lisinopril Initial Dose A",
        content="Start Lisinopril at 10 mg daily.",
        entity_type="guideline",
        condition="hypertension",
        medication="lisinopril",
        dose_mg=10.0,
        citation="ACC/AHA 2020",
    )
    wiki.ingest(
        doc_id="gl_htn_v2",
        title="Hypertension Lisinopril Initial Dose B",
        content="Start Lisinopril at 20 mg daily.",
        entity_type="guideline",
        condition="hypertension",
        medication="lisinopril",
        dose_mg=20.0,
        citation="",  # missing citation
    )
    # Standalone orphan condition with no links
    wiki.ingest(
        doc_id="orphan_syncope",
        title="Unexplained Syncope",
        content="Condition page without linked guidelines.",
        entity_type="condition",
    )

    report = wiki.lint()
    assert report["status"] == "issues_found"
    assert report["counts"]["conflicting_dosage_guidelines"] >= 1
    assert report["counts"]["orphan_conditions"] >= 1
    assert report["counts"]["missing_citations"] >= 1


def test_phi_deidentification_masking(tmp_path: Path) -> None:
    pipeline = HealthcareFDEPipeline(audit_log_path=tmp_path / "audit.jsonl")
    raw = (
        "Patient: John Doe, SSN 123-45-6789, MRN-998877, DOB 1980-05-14, "
        "Phone 555-867-5309, Email john.doe@example.com has chest pain."
    )
    masked, categories = pipeline.deidentify_phi(raw)

    assert "John Doe" not in masked
    assert "123-45-6789" not in masked
    assert "MRN-998877" not in masked
    assert "1980-05-14" not in masked
    assert "555-867-5309" not in masked
    assert "john.doe@example.com" not in masked
    assert "[REDACTED_SSN]" in masked
    assert "[REDACTED_MRN]" in masked
    assert "[REDACTED_EMAIL]" in masked
    assert set(categories) >= {"SSN", "MRN", "DATE", "PHONE", "EMAIL", "NAME"}


def test_emergency_red_flag_triage_and_hitl_signoff(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    wiki = ClinicalLLMWiki(tmp_path / "wiki")
    wiki.ingest(
        doc_id="gl_acs",
        title="Acute Chest Pain Guideline",
        content="Immediate ECG and Aspirin 325 mg if no bleeding contraindication.",
        entity_type="guideline",
        condition="acute_coronary_syndrome",
        medication="aspirin",
        dose_mg=325.0,
        citation="AHA 2021",
    )

    pipeline = HealthcareFDEPipeline(wiki=wiki, audit_log_path=audit_path)
    case = PatientCase(
        case_id="case-er-001",
        age=64,
        sex="M",
        chief_complaint="Patient: Jane Roe reports substernal chest pain, phone 555-222-3333",
        symptoms=[
            Symptom(
                symptom_id="chest_pain",
                name="Chest Pain",
                severity="critical",
                is_red_flag=True,
            )
        ],
        vital_signs={"spo2": 88.0, "hr": 118.0},
    )

    triage_out = pipeline.triage_case(case, proposed_med_ids=["aspirin"])
    assert triage_out["triage_level"] == "emergency"
    assert triage_out["emergency_escalated"] is True
    assert "Jane Roe" not in triage_out["deidentified_complaint"]
    assert "555-222-3333" not in triage_out["deidentified_complaint"]
    assert len(triage_out["wiki_references"]) >= 1

    action_id = triage_out["proposed_action"]["action_id"]
    assert triage_out["proposed_action"]["requires_hitl"] is True
    assert triage_out["proposed_action"]["status"] == "pending_review"

    approved = pipeline.approve_action(
        action_id=action_id,
        physician_id="dr-house-01",
        decision="approved",
        notes="Proceed with STAT ECG and Aspirin.",
    )
    assert approved.status == "approved"
    assert approved.reviewer_id == "dr-house-01"

    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    assert events[0]["event_type"] == "CLINICAL_TRIAGE"
    assert events[1]["event_type"] == "HITL_SIGNOFF"


def test_blocked_contraindicated_triage_and_rejection(tmp_path: Path) -> None:
    pipeline = HealthcareFDEPipeline(audit_log_path=tmp_path / "audit.jsonl")
    case = PatientCase(
        case_id="case-blk-002",
        age=71,
        sex="F",
        chief_complaint="Knee pain",
        active_medications=["warfarin"],
        symptoms=[Symptom(symptom_id="pain", name="Knee Pain", severity="mild")],
    )
    triage_out = pipeline.triage_case(case, proposed_med_ids=["ibuprofen"])
    assert triage_out["interaction_check"]["blocked"] is True
    assert triage_out["proposed_action"]["status"] == "blocked"

    rejected = pipeline.approve_action(
        action_id=triage_out["proposed_action"]["action_id"],
        physician_id="dr-cuddy-02",
        decision="rejected",
        notes="Switch to acetaminophen due to warfarin interaction.",
    )
    assert rejected.status == "rejected"


def test_fastapi_endpoints_and_request_id_middleware(tmp_path: Path) -> None:
    test_app = create_app(
        wiki_dir=tmp_path / "api_wiki",
        audit_log_path=tmp_path / "api_audit.jsonl",
    )
    client = TestClient(test_app)

    # 1. Health & Ready with X-Request-ID propagation
    h_resp = client.get("/health", headers={"X-Request-ID": "req-test-123"})
    assert h_resp.status_code == 200
    assert h_resp.json()["status"] == "healthy"
    assert h_resp.headers["X-Request-ID"] == "req-test-123"

    r_resp = client.get("/ready")
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "ready"
    assert "X-Request-ID" in r_resp.headers

    # 2. Wiki ingest & lint
    ing_resp = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "gl_api_htn",
            "title": "Hypertension ACEi Guideline",
            "content": "Use Lisinopril 10 mg daily for stage 1 hypertension.",
            "entity_type": "guideline",
            "condition": "hypertension",
            "medication": "lisinopril",
            "dose_mg": 10.0,
            "citation": "ACC/AHA 2021",
        },
    )
    assert ing_resp.status_code == 200
    assert ing_resp.json()["status"] == "ingested"

    lint_resp = client.get("/api/v1/wiki/lint")
    assert lint_resp.status_code == 200
    assert "counts" in lint_resp.json()

    # 3. Ontology check-interaction
    chk_resp = client.post(
        "/api/v1/ontology/check-interaction",
        json={
            "proposed_med_ids": ["ibuprofen"],
            "active_med_ids": ["warfarin"],
            "allergies": [],
            "conditions": [],
        },
    )
    assert chk_resp.status_code == 200
    assert chk_resp.json()["blocked"] is True

    # 4. Clinical triage & HITL action approve
    tri_resp = client.post(
        "/api/v1/clinical/triage",
        json={
            "patient_case": {
                "case_id": "case-api-99",
                "age": 55,
                "sex": "M",
                "chief_complaint": "Patient: Bob Lee with acute chest pain",
                "symptoms": [
                    {
                        "symptom_id": "chest_pain",
                        "name": "Chest Pain",
                        "severity": "critical",
                        "is_red_flag": True,
                    }
                ],
                "active_medications": [],
                "allergies": [],
                "conditions": ["hypertension"],
                "vital_signs": {"spo2": 95.0, "hr": 105.0},
            },
            "proposed_med_ids": ["aspirin"],
            "raw_notes": "Contact 555-999-1111",
        },
    )
    assert tri_resp.status_code == 200
    tri_data = tri_resp.json()
    assert tri_data["triage_level"] == "emergency"
    assert "Bob Lee" not in tri_data["deidentified_complaint"]
    action_id = tri_data["proposed_action"]["action_id"]

    app_resp = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "physician_id": "dr-wilson-03",
            "decision": "approved",
            "notes": "Approved for immediate administration.",
        },
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"

    # 5. Metrics
    m_resp = client.get("/metrics")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert m_data["triage_total"] == 1
    assert m_data["hitl_approvals_total"] == 1
    assert m_data["blocked_interactions_total"] >= 1


def test_cors_middleware_headers(tmp_path: Path) -> None:
    test_app = create_app(
        wiki_dir=tmp_path / "cors_wiki",
        audit_log_path=tmp_path / "cors_audit.jsonl",
    )
    client = TestClient(test_app)

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

    get_resp = client.get(
        "/api/v1/dashboard/overview",
        headers={"Origin": "http://localhost:5173"},
    )
    assert get_resp.status_code == 200
    assert get_resp.headers.get("access-control-allow-origin") == "*"


def test_enterprise_dashboard_wiki_pages_pending_hitl_and_audit(tmp_path: Path) -> None:
    test_app = create_app(
        wiki_dir=tmp_path / "ent_wiki",
        audit_log_path=tmp_path / "ent_audit.jsonl",
    )
    client = TestClient(test_app)

    # Ingest a clinical wiki page
    ing = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "gl_dm_metformin",
            "title": "Type 2 Diabetes Metformin First-Line",
            "content": "Initiate Metformin 500 mg with meals if eGFR >= 30.",
            "entity_type": "guideline",
            "condition": "type_2_diabetes",
            "medication": "metformin",
            "dose_mg": 500.0,
            "citation": "ADA Standards of Care 2024",
        },
    )
    assert ing.status_code == 200

    # List wiki pages
    pages_resp = client.get("/api/v1/wiki/pages")
    assert pages_resp.status_code == 200
    pages_data = pages_resp.json()
    assert pages_data["total"] == 1
    page = pages_data["pages"][0]
    assert page["id"] == "gl_dm_metformin"
    assert page["title"] == "Type 2 Diabetes Metformin First-Line"
    assert page["path"].endswith("gl_dm_metformin.md")
    assert "Metformin 500 mg" in page["preview"]

    # Triage a case so a pending HITL action is created
    triage_resp = client.post(
        "/api/v1/clinical/triage",
        json={
            "patient_case": {
                "case_id": "case-ent-101",
                "age": 58,
                "sex": "F",
                "chief_complaint": "Patient: Alice Wong elevated fasting glucose, MRN-445566",
                "symptoms": [
                    {"symptom_id": "fever", "name": "Fever", "severity": "mild"}
                ],
                "active_medications": [],
                "allergies": [],
                "conditions": ["type_2_diabetes"],
                "vital_signs": {"spo2": 98.0, "hr": 76.0},
            },
            "proposed_med_ids": ["metformin"],
            "raw_notes": "Phone 555-333-4444",
        },
    )
    assert triage_resp.status_code == 200
    action_id = triage_resp.json()["proposed_action"]["action_id"]

    # Dashboard overview reflects counts before sign-off
    ov_resp = client.get("/api/v1/dashboard/overview")
    assert ov_resp.status_code == 200
    ov = ov_resp.json()
    assert ov["guidelines_count"] >= 2
    assert ov["medications_count"] >= 8
    assert ov["wiki_pages_count"] == 1
    assert ov["pending_hitl_count"] == 1
    assert ov["audit_logs_count"] == 1

    # Pending actions endpoint lists the action
    pend_resp = client.get("/api/v1/actions/pending")
    assert pend_resp.status_code == 200
    pend = pend_resp.json()
    assert pend["total"] == 1
    assert pend["actions"][0]["action_id"] == action_id
    assert pend["actions"][0]["status"] == "pending_review"

    # Approve action and verify pending queue drains
    app_resp = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action_id,
            "physician_id": "dr-chen-09",
            "decision": "approved",
            "notes": "Confirmed eGFR normal; start Metformin.",
        },
    )
    assert app_resp.status_code == 200

    pend_after = client.get("/api/v1/actions/pending").json()
    assert pend_after["total"] == 0

    # Audit logs contain both events and no raw PHI
    audit_resp = client.get("/api/v1/audit/logs")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["total"] == 2
    serialized = json.dumps(audit_data)
    assert "Alice Wong" not in serialized
    assert "MRN-445566" not in serialized
    assert "555-333-4444" not in serialized


def test_enterprise_discharge_summary_endpoint(tmp_path: Path) -> None:
    test_app = create_app(
        wiki_dir=tmp_path / "dc_wiki",
        audit_log_path=tmp_path / "dc_audit.jsonl",
    )
    client = TestClient(test_app)

    resp = client.post(
        "/api/v1/clinical/discharge-summary",
        json={
            "case_id": "case-dc-501",
            "diagnosis": "Hypertension and atrial fibrillation",
            "raw_notes": (
                "Patient: Robert King, MRN-778899, SSN 123-45-6789, "
                "DOB 1965-03-21, Phone 555-123-9876, Email r.king@example.com. "
                "Discharged in stable condition on Warfarin and Lisinopril."
            ),
            "conditions": ["hypertension"],
            "medications": ["warfarin", "lisinopril"],
            "follow_up_days": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "case-dc-501"
    assert "Robert King" not in data["deidentified_note"]
    assert "123-45-6789" not in data["deidentified_note"]
    assert "MRN-778899" not in data["deidentified_note"]
    assert "r.king@example.com" not in data["deidentified_note"]
    assert set(data["redacted_phi_types"]) >= {"NAME", "MRN", "SSN", "DATE", "PHONE", "EMAIL"}

    step_ids = {item["step_id"] for item in data["follow_up_checklist"]}
    assert "chk-med-reconciliation" in step_ids
    assert "chk-followup-visit" in step_ids
    assert "chk-warfarin-inr" in step_ids
    assert "chk-bp-renal" in step_ids
    assert len(data["red_flag_precautions"]) >= 3

    # Audit log recorded DISCHARGE_SUMMARY
    audit_data = client.get("/api/v1/audit/logs").json()
    assert audit_data["total"] == 1
    assert audit_data["logs"][0]["event_type"] == "DISCHARGE_SUMMARY"

