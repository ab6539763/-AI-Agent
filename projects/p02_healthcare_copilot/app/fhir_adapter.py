"""HL7 FHIR R4 Bundle Adapter, ESI 1-5 Triage Queue, and SOAP Note Formatter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .fde_pipeline import HealthcareFDEPipeline
from .ontology import (
    ClinicalOntologyRegistry,
    InteractionCheckResult,
    PatientCase,
)

ESILevel = Literal[1, 2, 3, 4, 5]

ESI_LABELS: dict[int, str] = {
    1: "ESI-1 Resuscitation (Immediate)",
    2: "ESI-2 Emergent (High Risk)",
    3: "ESI-3 Urgent (Multi-Resource)",
    4: "ESI-4 Less Urgent (Single Resource)",
    5: "ESI-5 Non-Urgent (Routine)",
}

VITAL_LOINC_MAP: dict[str, dict[str, str]] = {
    "spo2": {"code": "59408-5", "display": "Oxygen saturation in Arterial blood by Pulse oximetry", "unit": "%"},
    "hr": {"code": "8867-4", "display": "Heart rate", "unit": "beats/min"},
    "sbp": {"code": "8480-6", "display": "Systolic blood pressure", "unit": "mmHg"},
    "dbp": {"code": "8462-4", "display": "Diastolic blood pressure", "unit": "mmHg"},
    "temp_c": {"code": "8310-5", "display": "Body temperature", "unit": "Cel"},
    "rr": {"code": "9279-1", "display": "Respiratory rate", "unit": "breaths/min"},
}


class SOAPNote(BaseModel):
    """Structured clinical SOAP note (Subjective, Objective, Assessment, Plan)."""

    case_id: str
    esi_level: ESILevel
    esi_label: str
    subjective: str
    objective: str
    assessment: str
    plan: str
    formatted_text: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ESITriageEntry(BaseModel):
    """Single patient encounter in the Emergency Severity Index (ESI 1-5) queue."""

    case_id: str
    patient_ref: str
    age: int
    sex: Literal["M", "F", "O", "U"]
    esi_level: ESILevel
    esi_label: str
    chief_complaint: str
    symptoms: list[dict[str, Any]] = Field(default_factory=list)
    vital_signs: dict[str, float] = Field(default_factory=dict)
    active_medications: list[str] = Field(default_factory=list)
    proposed_med_ids: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    guardrail_blocked: bool = False
    action_id: str | None = None
    status: str = "waiting"
    queued_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _detect_vital_abnormalities(vitals: dict[str, float]) -> list[str]:
    flags: list[str] = []
    if "spo2" in vitals and vitals["spo2"] < 90.0:
        flags.append(f"critical_hypoxia:spo2={vitals['spo2']}")
    if "sbp" in vitals and vitals["sbp"] < 90.0:
        flags.append(f"hypotension:sbp={vitals['sbp']}")
    if "hr" in vitals and (vitals["hr"] > 130.0 or vitals["hr"] < 40.0):
        flags.append(f"critical_hr:hr={vitals['hr']}")
    if "temp_c" in vitals and vitals["temp_c"] >= 40.0:
        flags.append(f"hyperpyrexia:temp_c={vitals['temp_c']}")
    return flags


class ESITriageQueue:
    """Deterministic Emergency Severity Index (ESI 1-5) priority queue."""

    def __init__(self, seed_defaults: bool = False) -> None:
        self._entries: dict[str, ESITriageEntry] = {}
        if seed_defaults:
            self._seed_default_encounters()

    @staticmethod
    def compute_esi_level(
        case: PatientCase,
        registry: ClinicalOntologyRegistry | None = None,
        interaction_result: InteractionCheckResult | None = None,
    ) -> tuple[ESILevel, list[str]]:
        """Deterministically assign ESI 1-5 based on vitals, red flags, symptoms, and conflicts."""
        reg = registry or ClinicalOntologyRegistry(seed_defaults=True)
        vitals = case.vital_signs
        vital_flags = _detect_vital_abnormalities(vitals)

        red_flag_symptoms: list[str] = []
        for sym in case.symptoms:
            if reg.is_red_flag_symptom(sym):
                red_flag_symptoms.append(f"red_flag_symptom:{sym.symptom_id}")

        all_red_flags = red_flag_symptoms + vital_flags

        # ESI 1: Immediate life-saving intervention (critical vitals or airway/neuro/cardiac arrest risk)
        critical_symptom_ids = {"anaphylaxis", "focal_neurologic_deficit"}
        has_immediate_symptom = any(
            s.symptom_id.lower() in critical_symptom_ids for s in case.symptoms
        )
        if vital_flags or has_immediate_symptom:
            return 1, all_red_flags

        # ESI 2: High-risk situation (red-flag symptom like chest_pain/dyspnea, or blocked contraindication)
        if red_flag_symptoms or (interaction_result and interaction_result.blocked):
            return 2, all_red_flags

        # ESI 3: Urgent - severe non-red-flag symptom, moderate/major interaction, or >=2 resources
        has_severe = any(s.severity in ("severe", "critical") for s in case.symptoms)
        has_conflicts = bool(interaction_result and interaction_result.has_conflicts)
        resource_count = len(case.conditions) + len(case.active_medications)
        if has_severe or has_conflicts or resource_count >= 2:
            return 3, all_red_flags

        # ESI 4: Less urgent - moderate symptom or single resource
        has_moderate = any(s.severity == "moderate" for s in case.symptoms)
        if has_moderate or resource_count == 1:
            return 4, all_red_flags

        # ESI 5: Non-urgent / routine
        return 5, all_red_flags

    def enqueue_case(
        self,
        case: PatientCase,
        proposed_med_ids: list[str] | None = None,
        registry: ClinicalOntologyRegistry | None = None,
        interaction_result: InteractionCheckResult | None = None,
        action_id: str | None = None,
        status: str = "waiting",
    ) -> ESITriageEntry:
        """Compute ESI priority and insert or update a patient encounter in the queue."""
        masked_complaint, _ = HealthcareFDEPipeline.deidentify_phi(case.chief_complaint)
        esi_level, red_flags = self.compute_esi_level(
            case=case,
            registry=registry,
            interaction_result=interaction_result,
        )
        entry = ESITriageEntry(
            case_id=case.case_id,
            patient_ref=case.patient_ref,
            age=case.age,
            sex=case.sex,
            esi_level=esi_level,
            esi_label=ESI_LABELS[esi_level],
            chief_complaint=masked_complaint,
            symptoms=[s.model_dump() for s in case.symptoms],
            vital_signs=dict(case.vital_signs),
            active_medications=list(case.active_medications),
            proposed_med_ids=list(proposed_med_ids or []),
            allergies=list(case.allergies),
            conditions=list(case.conditions),
            red_flags=red_flags,
            guardrail_blocked=bool(interaction_result and interaction_result.blocked),
            action_id=action_id,
            status=status,
        )
        self._entries[case.case_id] = entry
        return entry

    def update_status(self, case_id: str, status: str) -> None:
        if case_id in self._entries:
            self._entries[case_id].status = status

    def list_queue(self) -> list[ESITriageEntry]:
        """Return all queued encounters sorted by ESI 1 -> 5, then FIFO timestamp."""
        return sorted(
            self._entries.values(),
            key=lambda e: (e.esi_level, e.queued_at),
        )

    def _seed_default_encounters(self) -> None:
        """Seed realistic de-identified ED encounters across ESI 1-4 for EMR workstation."""
        reg = ClinicalOntologyRegistry(seed_defaults=True)
        samples: list[tuple[PatientCase, list[str]]] = [
            (
                PatientCase(
                    case_id="case-er-101",
                    patient_ref="ED-BAY-01",
                    age=64,
                    sex="M",
                    chief_complaint="Acute substernal chest pain radiating to left arm, diaphoresis",
                    symptoms=[
                        {
                            "symptom_id": "chest_pain",
                            "name": "Chest Pain",
                            "severity": "critical",
                            "is_red_flag": True,
                            "onset_hours": 1.0,
                        }
                    ],
                    active_medications=["warfarin"],
                    allergies=[],
                    conditions=["hypertension", "acute_coronary_syndrome"],
                    vital_signs={"spo2": 88.0, "hr": 118.0, "sbp": 102.0, "temp_c": 37.1},
                ),
                ["aspirin"],
            ),
            (
                PatientCase(
                    case_id="case-er-102",
                    patient_ref="ED-BAY-02",
                    age=52,
                    sex="F",
                    chief_complaint="Progressive dyspnea and bilateral wheezing",
                    symptoms=[
                        {
                            "symptom_id": "dyspnea",
                            "name": "Shortness of Breath",
                            "severity": "severe",
                            "is_red_flag": True,
                            "onset_hours": 3.0,
                        }
                    ],
                    active_medications=["lisinopril"],
                    allergies=["penicillin"],
                    conditions=["hypertension"],
                    vital_signs={"spo2": 93.0, "hr": 104.0, "sbp": 138.0, "temp_c": 37.6},
                ),
                ["amoxicillin"],
            ),
            (
                PatientCase(
                    case_id="case-er-103",
                    patient_ref="ED-BAY-03",
                    age=71,
                    sex="F",
                    chief_complaint="Acute right knee pain after minor fall, requesting analgesia",
                    symptoms=[
                        {
                            "symptom_id": "pain",
                            "name": "Knee Pain",
                            "severity": "moderate",
                            "is_red_flag": False,
                            "onset_hours": 6.0,
                        }
                    ],
                    active_medications=["warfarin"],
                    allergies=[],
                    conditions=["atrial_fibrillation"],
                    vital_signs={"spo2": 98.0, "hr": 78.0, "sbp": 126.0, "temp_c": 36.8},
                ),
                ["ibuprofen"],
            ),
            (
                PatientCase(
                    case_id="case-er-104",
                    patient_ref="ED-BAY-04",
                    age=39,
                    sex="M",
                    chief_complaint="Low-grade fever and sore throat for 2 days",
                    symptoms=[
                        {
                            "symptom_id": "fever",
                            "name": "Fever",
                            "severity": "moderate",
                            "is_red_flag": False,
                            "onset_hours": 48.0,
                        }
                    ],
                    active_medications=[],
                    allergies=[],
                    conditions=[],
                    vital_signs={"spo2": 99.0, "hr": 84.0, "sbp": 118.0, "temp_c": 38.3},
                ),
                ["acetaminophen"],
            ),
        ]
        for case, proposed in samples:
            res = reg.evaluate_action_constraints(case, proposed)
            self.enqueue_case(
                case=case,
                proposed_med_ids=proposed,
                registry=reg,
                interaction_result=res,
            )


class FHIRAdapter:
    """Converts clinical encounters into HL7 FHIR R4-style Bundles and SOAP notes."""

    def __init__(self, registry: ClinicalOntologyRegistry | None = None) -> None:
        self.registry = registry or ClinicalOntologyRegistry(seed_defaults=True)

    @staticmethod
    def _map_gender(sex: str) -> str:
        return {"M": "male", "F": "female", "O": "other", "U": "unknown"}.get(
            sex.upper(), "unknown"
        )

    def to_fhir_bundle(
        self,
        case: PatientCase,
        proposed_med_ids: list[str] | None = None,
        interaction_result: InteractionCheckResult | None = None,
    ) -> dict[str, Any]:
        """Build an HL7 FHIR R4 collection Bundle with Patient, Condition, MedicationRequest, and Observation."""
        proposed = proposed_med_ids or []
        res = interaction_result or self.registry.evaluate_action_constraints(case, proposed)
        masked_complaint, _ = HealthcareFDEPipeline.deidentify_phi(case.chief_complaint)

        now_iso = datetime.now(timezone.utc).isoformat()
        patient_id = f"pat-{case.case_id}"
        entries: list[dict[str, Any]] = []

        # 1. Patient Resource (de-identified)
        patient_resource: dict[str, Any] = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [
                {
                    "system": "urn:p02:deidentified-case",
                    "value": case.case_id,
                },
                {
                    "system": "urn:p02:patient-ref",
                    "value": case.patient_ref,
                },
            ],
            "gender": self._map_gender(case.sex),
            "extension": [
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/patient-age",
                    "valueInteger": case.age,
                }
            ],
        }
        entries.append(
            {
                "fullUrl": f"urn:uuid:{patient_id}",
                "resource": patient_resource,
            }
        )

        # 2. Condition Resources (chief complaint, conditions, symptoms)
        cond_items: list[tuple[str, str, str]] = [
            ("chief-complaint", masked_complaint, "encounter-diagnosis")
        ]
        for cond in case.conditions:
            cond_items.append((cond.lower().replace(" ", "_"), cond, "problem-list-item"))
        for sym in case.symptoms:
            cond_items.append((sym.symptom_id, f"{sym.name} ({sym.severity})", "problem-list-item"))

        for idx, (code, display, category) in enumerate(cond_items, start=1):
            cond_id = f"cond-{case.case_id}-{idx}"
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{cond_id}",
                    "resource": {
                        "resourceType": "Condition",
                        "id": cond_id,
                        "clinicalStatus": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                    "code": "active",
                                }
                            ]
                        },
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                        "code": category,
                                    }
                                ]
                            }
                        ],
                        "code": {"text": display, "coding": [{"code": code, "display": display}]},
                        "subject": {"reference": f"Patient/{patient_id}"},
                        "recordedDate": now_iso,
                    },
                }
            )

        # 3. MedicationRequest Resources (proposed + active)
        all_meds: list[tuple[str, str]] = [
            (m, "order") for m in proposed
        ] + [
            (m, "active-home-med") for m in case.active_medications
        ]
        for idx, (med_id, intent_tag) in enumerate(all_meds, start=1):
            med_obj = self.registry.get_medication(med_id)
            med_name = med_obj.name if med_obj else med_id
            dose_mg = med_obj.standard_dose_mg if med_obj else None
            if intent_tag == "order":
                status = "stopped" if res.blocked else "draft"
                intent = "order"
            else:
                status = "active"
                intent = "plan"

            mr_id = f"medreq-{case.case_id}-{idx}"
            mr_resource: dict[str, Any] = {
                "resourceType": "MedicationRequest",
                "id": mr_id,
                "status": status,
                "intent": intent,
                "medicationCodeableConcept": {
                    "coding": [
                        {
                            "system": "urn:p02:clinical-ontology:medication",
                            "code": med_id.lower(),
                            "display": med_name,
                        }
                    ],
                    "text": med_name,
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "authoredOn": now_iso,
                "note": [
                    {
                        "text": (
                            f"Ontology Guardrail: {res.summary}"
                            if intent_tag == "order"
                            else "Active home medication"
                        )
                    }
                ],
            }
            if dose_mg is not None:
                mr_resource["dosageInstruction"] = [
                    {
                        "doseAndRate": [
                            {
                                "doseQuantity": {
                                    "value": dose_mg,
                                    "unit": "mg",
                                    "system": "http://unitsofmeasure.org",
                                    "code": "mg",
                                }
                            }
                        ]
                    }
                ]
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{mr_id}",
                    "resource": mr_resource,
                }
            )

        # 4. Observation Resources (vital signs)
        for idx, (vital_key, vital_val) in enumerate(case.vital_signs.items(), start=1):
            meta = VITAL_LOINC_MAP.get(
                vital_key.lower(),
                {"code": vital_key, "display": vital_key.upper(), "unit": "unit"},
            )
            obs_id = f"obs-{case.case_id}-{idx}"
            is_abnormal = (
                (vital_key.lower() == "spo2" and vital_val < 90.0)
                or (vital_key.lower() == "sbp" and vital_val < 90.0)
                or (vital_key.lower() == "hr" and (vital_val > 130.0 or vital_val < 40.0))
                or (vital_key.lower() == "temp_c" and vital_val >= 40.0)
            )
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{obs_id}",
                    "resource": {
                        "resourceType": "Observation",
                        "id": obs_id,
                        "status": "final",
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                        "code": "vital-signs",
                                        "display": "Vital Signs",
                                    }
                                ]
                            }
                        ],
                        "code": {
                            "coding": [
                                {
                                    "system": "http://loinc.org",
                                    "code": meta["code"],
                                    "display": meta["display"],
                                }
                            ],
                            "text": meta["display"],
                        },
                        "subject": {"reference": f"Patient/{patient_id}"},
                        "effectiveDateTime": now_iso,
                        "valueQuantity": {
                            "value": vital_val,
                            "unit": meta["unit"],
                            "system": "http://unitsofmeasure.org",
                        },
                        "interpretation": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                        "code": "H" if is_abnormal else "N",
                                        "display": "Critical/Abnormal" if is_abnormal else "Normal",
                                    }
                                ]
                            }
                        ],
                    },
                }
            )

        return {
            "resourceType": "Bundle",
            "id": f"bundle-{case.case_id}-{uuid4().hex[:6]}",
            "type": "collection",
            "timestamp": now_iso,
            "total": len(entries),
            "entry": entries,
        }

    def format_soap_note(
        self,
        case: PatientCase,
        proposed_med_ids: list[str] | None = None,
        raw_notes: str = "",
        interaction_result: InteractionCheckResult | None = None,
    ) -> SOAPNote:
        """Format a structured Subjective / Objective / Assessment / Plan clinical note."""
        proposed = proposed_med_ids or []
        res = interaction_result or self.registry.evaluate_action_constraints(case, proposed)
        esi_level, red_flags = ESITriageQueue.compute_esi_level(
            case=case,
            registry=self.registry,
            interaction_result=res,
        )
        esi_label = ESI_LABELS[esi_level]

        masked_complaint, _ = HealthcareFDEPipeline.deidentify_phi(case.chief_complaint)
        masked_notes, _ = HealthcareFDEPipeline.deidentify_phi(raw_notes)

        sym_str = (
            ", ".join(
                f"{s.name} ({s.severity}{', RED FLAG' if self.registry.is_red_flag_symptom(s) else ''})"
                for s in case.symptoms
            )
            or "None documented"
        )
        allergy_str = ", ".join(case.allergies) if case.allergies else "NKDA (No Known Drug Allergies)"

        subjective = (
            f"{case.age}yo {case.sex} ({case.patient_ref}) presenting with: {masked_complaint}. "
            f"Symptoms: {sym_str}. Allergies: {allergy_str}."
        )
        if masked_notes:
            subjective += f" Clinical notes: {masked_notes}"

        vitals_str = (
            ", ".join(f"{k.upper()}={v}" for k, v in case.vital_signs.items())
            or "No vitals recorded"
        )
        active_meds_str = ", ".join(case.active_medications) if case.active_medications else "None"
        conds_str = ", ".join(case.conditions) if case.conditions else "None"
        objective = (
            f"Vitals: {vitals_str}. Active Medications: {active_meds_str}. "
            f"Problem List: {conds_str}."
        )

        rf_str = ", ".join(red_flags) if red_flags else "None"
        assessment = (
            f"Triage Acuity: {esi_label}. Red Flags: {rf_str}. "
            f"Ontology Safety Check: {res.summary}"
        )

        if res.blocked:
            plan = (
                f"HOLD proposed order ({', '.join(proposed) or 'none'}) due to contraindication/allergy block. "
                "Await Attending Physician HITL review and select safe alternative."
            )
        elif proposed:
            plan = (
                f"Propose medication order: {', '.join(proposed)}. "
                "Requires Attending Physician HITL sign-off prior to administration."
            )
        else:
            plan = "Diagnostic workup and continuous vital sign monitoring; pending Physician HITL sign-off."

        formatted_text = (
            f"S (Subjective): {subjective}\n"
            f"O (Objective):  {objective}\n"
            f"A (Assessment): {assessment}\n"
            f"P (Plan):       {plan}"
        )

        return SOAPNote(
            case_id=case.case_id,
            esi_level=esi_level,
            esi_label=esi_label,
            subjective=subjective,
            objective=objective,
            assessment=assessment,
            plan=plan,
            formatted_text=formatted_text,
        )
