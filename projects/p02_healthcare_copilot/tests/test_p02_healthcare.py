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
