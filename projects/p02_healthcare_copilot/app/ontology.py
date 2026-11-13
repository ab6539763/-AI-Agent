"""Clinical Ontology models and deterministic constraint-checking registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SeverityLevel = Literal["mild", "moderate", "severe", "critical"]
InteractionSeverity = Literal["moderate", "major", "contraindicated"]
ActionType = Literal[
    "triage_escalation",
    "medication_order",
    "diagnostic_workup",
    "discharge_plan",
]
ActionStatus = Literal["pending_review", "approved", "rejected", "blocked"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class Symptom(BaseModel):
    """Represents a clinical symptom with optional red-flag emergency status."""

    symptom_id: str
    name: str
    severity: SeverityLevel = "moderate"
    is_red_flag: bool = False
    onset_hours: float | None = Field(default=None, ge=0)
    description: str = ""


class Medication(BaseModel):
    """Represents a medication entity in the clinical ontology."""

    med_id: str
    name: str
    drug_class: str
    allergen_tags: list[str] = Field(default_factory=list)
    standard_dose_mg: float = Field(gt=0)
    max_daily_dose_mg: float = Field(gt=0)
    contraindicated_conditions: list[str] = Field(default_factory=list)


class ContraindicationLink(BaseModel):
    """Directed/symmetric drug-drug contraindication or interaction edge."""

    link_id: str
    source_med_id: str
    target_med_id: str
    severity: InteractionSeverity
    mechanism: str
    recommendation: str


class ClinicalGuideline(BaseModel):
    """Evidence-based clinical guideline linked to a condition and medications."""

    guideline_id: str
    condition_name: str
    recommended_med_ids: list[str] = Field(default_factory=list)
    recommended_dose_mg: float | None = Field(default=None, gt=0)
    source_citation: str
    evidence_grade: Literal["A", "B", "C"] = "A"
    red_flag_symptoms: list[str] = Field(default_factory=list)


class PatientCase(BaseModel):
    """De-identified patient clinical presentation for decision support."""

    case_id: str = Field(default_factory=lambda: f"case-{uuid4().hex[:8]}")
    patient_ref: str = "ANON-PATIENT"
    age: int = Field(ge=0, le=130)
    sex: Literal["M", "F", "O", "U"] = "U"
    chief_complaint: str
    symptoms: list[Symptom] = Field(default_factory=list)
    active_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    vital_signs: dict[str, float] = Field(default_factory=dict)


class ClinicalAction(BaseModel):
    """Proposed clinical action subject to guardrails and HITL physician review."""

    action_id: str = Field(default_factory=lambda: f"act-{uuid4().hex[:8]}")
    case_id: str
    action_type: ActionType
    proposed_med_ids: list[str] = Field(default_factory=list)
    rationale: str
    risk_level: RiskLevel = "medium"
    requires_hitl: bool = True
    status: ActionStatus = "pending_review"
    reviewer_id: str | None = None
    review_notes: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    reviewed_at: str | None = None


class InteractionCheckResult(BaseModel):
    """Structured result of drug-drug, allergy, and condition constraint checks."""

    has_conflicts: bool
    blocked: bool
    drug_interactions: list[dict[str, str]] = Field(default_factory=list)
    allergy_conflicts: list[dict[str, str]] = Field(default_factory=list)
    condition_conflicts: list[dict[str, str]] = Field(default_factory=list)
    summary: str


class ClinicalOntologyRegistry:
    """In-memory deterministic clinical ontology with drug-interaction & allergy checks."""

    def __init__(self, seed_defaults: bool = True) -> None:
        self.medications: dict[str, Medication] = {}
        self.contraindications: list[ContraindicationLink] = []
        self.guidelines: dict[str, ClinicalGuideline] = {}
        self.symptoms: dict[str, Symptom] = {}
        if seed_defaults:
            self._seed_clinical_ontology()

    def _seed_clinical_ontology(self) -> None:
        """Populate deterministic baseline medications, interactions, symptoms, and guidelines."""
        default_meds = [
            Medication(
                med_id="warfarin",
                name="Warfarin",
                drug_class="anticoagulant",
                allergen_tags=["coumarin"],
                standard_dose_mg=5.0,
                max_daily_dose_mg=10.0,
                contraindicated_conditions=["active_hemorrhage", "pregnancy"],
            ),
            Medication(
                med_id="aspirin",
                name="Aspirin",
                drug_class="antiplatelet_nsaid",
                allergen_tags=["salicylate", "nsaid"],
                standard_dose_mg=81.0,
                max_daily_dose_mg=325.0,
                contraindicated_conditions=["active_hemorrhage", "peptic_ulcer"],
            ),
            Medication(
                med_id="ibuprofen",
                name="Ibuprofen",
                drug_class="nsaid",
                allergen_tags=["nsaid"],
                standard_dose_mg=400.0,
                max_daily_dose_mg=2400.0,
                contraindicated_conditions=[
                    "active_hemorrhage",
                    "chronic_kidney_disease",
                    "peptic_ulcer",
                ],
            ),
            Medication(
                med_id="amoxicillin",
                name="Amoxicillin",
                drug_class="penicillin_antibiotic",
                allergen_tags=["penicillin", "beta_lactam"],
                standard_dose_mg=500.0,
                max_daily_dose_mg=3000.0,
                contraindicated_conditions=["infectious_mononucleosis"],
            ),
            Medication(
                med_id="lisinopril",
                name="Lisinopril",
                drug_class="ace_inhibitor",
                allergen_tags=["ace_inhibitor"],
                standard_dose_mg=10.0,
                max_daily_dose_mg=40.0,
                contraindicated_conditions=["angioedema", "pregnancy", "hyperkalemia"],
            ),
            Medication(
                med_id="metformin",
                name="Metformin",
                drug_class="biguanide",
                allergen_tags=["biguanide"],
                standard_dose_mg=500.0,
                max_daily_dose_mg=2000.0,
                contraindicated_conditions=["severe_renal_failure", "lactic_acidosis"],
            ),
            Medication(
                med_id="acetaminophen",
                name="Acetaminophen",
                drug_class="analgesic",
                allergen_tags=["acetaminophen"],
                standard_dose_mg=500.0,
                max_daily_dose_mg=4000.0,
                contraindicated_conditions=["acute_liver_failure"],
            ),
            Medication(
                med_id="nitroglycerin",
                name="Nitroglycerin",
                drug_class="nitrate",
                allergen_tags=["nitrate"],
                standard_dose_mg=0.4,
                max_daily_dose_mg=1.2,
                contraindicated_conditions=["severe_hypotension", "sildenafil_use"],
            ),
        ]
        for med in default_meds:
            self.register_medication(med)

        default_links = [
            ContraindicationLink(
                link_id="ddi-warfarin-aspirin",
                source_med_id="warfarin",
                target_med_id="aspirin",
                severity="major",
                mechanism="Additive anticoagulant and antiplatelet effect increases bleeding risk.",
                recommendation="Avoid concurrent use unless specifically indicated; monitor INR closely.",
            ),
            ContraindicationLink(
                link_id="ddi-warfarin-ibuprofen",
                source_med_id="warfarin",
                target_med_id="ibuprofen",
                severity="contraindicated",
                mechanism="NSAID-induced GI mucosal injury plus anticoagulation causes severe hemorrhage risk.",
                recommendation="Contraindicated. Substitute with acetaminophen for analgesia.",
            ),
            ContraindicationLink(
                link_id="ddi-lisinopril-ibuprofen",
                source_med_id="lisinopril",
                target_med_id="ibuprofen",
                severity="moderate",
                mechanism="NSAIDs attenuate ACE inhibitor antihypertensive effect and impair renal perfusion.",
                recommendation="Monitor blood pressure and serum creatinine; minimize NSAID duration.",
            ),
        ]
        for link in default_links:
            self.register_contraindication(link)

        default_symptoms = [
            Symptom(
                symptom_id="chest_pain",
                name="Chest Pain",
                severity="critical",
                is_red_flag=True,
                description="Acute substernal or radiating chest pain; rule out ACS/PE/aortic dissection.",
            ),
            Symptom(
                symptom_id="dyspnea",
                name="Shortness of Breath",
                severity="severe",
                is_red_flag=True,
                description="Acute dyspnea or respiratory distress.",
            ),
            Symptom(
                symptom_id="focal_neurologic_deficit",
                name="Focal Neurologic Deficit",
                severity="critical",
                is_red_flag=True,
                description="Sudden unilateral weakness, aphasia, or facial droop; rule out stroke.",
            ),
            Symptom(
                symptom_id="anaphylaxis",
                name="Anaphylaxis",
                severity="critical",
                is_red_flag=True,
                description="Airway compromise, angioedema, or systemic hypersensitivity shock.",
            ),
            Symptom(
                symptom_id="fever",
                name="Fever",
                severity="moderate",
                is_red_flag=False,
                description="Elevated body temperature >= 38.0 C.",
            ),
        ]
        for sym in default_symptoms:
            self.register_symptom(sym)

        default_guidelines = [
            ClinicalGuideline(
                guideline_id="gl-acs-001",
                condition_name="acute_coronary_syndrome",
                recommended_med_ids=["aspirin", "nitroglycerin"],
                recommended_dose_mg=325.0,
                source_citation="AHA/ACC Chest Pain Guideline 2021",
                evidence_grade="A",
                red_flag_symptoms=["chest_pain", "dyspnea"],
            ),
            ClinicalGuideline(
                guideline_id="gl-htn-001",
                condition_name="hypertension",
                recommended_med_ids=["lisinopril"],
                recommended_dose_mg=10.0,
                source_citation="ACC/AHA High Blood Pressure Guideline",
                evidence_grade="A",
                red_flag_symptoms=["chest_pain", "focal_neurologic_deficit"],
            ),
        ]
        for gl in default_guidelines:
            self.register_guideline(gl)

    def register_medication(self, med: Medication) -> None:
        self.medications[med.med_id.lower()] = med

    def register_contraindication(self, link: ContraindicationLink) -> None:
        self.contraindications.append(link)

    def register_guideline(self, guideline: ClinicalGuideline) -> None:
        self.guidelines[guideline.guideline_id] = guideline

    def register_symptom(self, symptom: Symptom) -> None:
        self.symptoms[symptom.symptom_id.lower()] = symptom

    def get_medication(self, med_id: str) -> Medication | None:
        return self.medications.get(med_id.strip().lower())

    def is_red_flag_symptom(self, symptom: Symptom) -> bool:
        if symptom.is_red_flag:
            return True
        known = self.symptoms.get(symptom.symptom_id.lower())
        if known and known.is_red_flag:
            return True
        return symptom.severity == "critical"

    def check_interactions(
        self,
        proposed_med_ids: list[str],
        active_med_ids: list[str] | None = None,
        allergies: list[str] | None = None,
        conditions: list[str] | None = None,
    ) -> InteractionCheckResult:
        """Check drug-drug interactions, allergy cross-reactivity, and condition contraindications."""
        proposed = [m.strip().lower() for m in proposed_med_ids if m.strip()]
        active = [m.strip().lower() for m in (active_med_ids or []) if m.strip()]
        all_meds = list(dict.fromkeys(proposed + active))
        allergy_set = {a.strip().lower() for a in (allergies or []) if a.strip()}
        condition_set = {c.strip().lower() for c in (conditions or []) if c.strip()}

        drug_interactions: list[dict[str, str]] = []
        allergy_conflicts: list[dict[str, str]] = []
        condition_conflicts: list[dict[str, str]] = []
        blocked = False

        # 1. Drug-drug interaction checks across all pairs involving at least one proposed med
        seen_pairs: set[tuple[str, str, str]] = set()
        for link in self.contraindications:
            src = link.source_med_id.lower()
            tgt = link.target_med_id.lower()
            if src in all_meds and tgt in all_meds and (src in proposed or tgt in proposed):
                pair_key = (min(src, tgt), max(src, tgt), link.link_id)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                if link.severity == "contraindicated":
                    blocked = True
                drug_interactions.append(
                    {
                        "link_id": link.link_id,
                        "med_a": src,
                        "med_b": tgt,
                        "severity": link.severity,
                        "mechanism": link.mechanism,
                        "recommendation": link.recommendation,
                    }
                )

        # 2. Allergy checks on proposed medications
        for med_id in proposed:
            med = self.get_medication(med_id)
            if not med:
                continue
            med_tags = {t.lower() for t in med.allergen_tags} | {
                med.med_id.lower(),
                med.name.lower(),
                med.drug_class.lower(),
            }
            matched_allergies = sorted(allergy_set & med_tags)
            if matched_allergies:
                blocked = True
                allergy_conflicts.append(
                    {
                        "med_id": med.med_id,
                        "matched_allergies": ", ".join(matched_allergies),
                        "severity": "contraindicated",
                        "recommendation": f"Hold {med.name}; documented allergy to {', '.join(matched_allergies)}.",
                    }
                )

            # 3. Condition contraindication checks
            med_contras = {c.lower() for c in med.contraindicated_conditions}
            matched_conditions = sorted(condition_set & med_contras)
            if matched_conditions:
                blocked = True
                condition_conflicts.append(
                    {
                        "med_id": med.med_id,
                        "matched_conditions": ", ".join(matched_conditions),
                        "severity": "contraindicated",
                        "recommendation": f"Avoid {med.name} in patient with {', '.join(matched_conditions)}.",
                    }
                )

        has_conflicts = bool(drug_interactions or allergy_conflicts or condition_conflicts)
        if not has_conflicts:
            summary = "No drug-drug, allergy, or condition contraindications detected."
        else:
            parts = []
            if drug_interactions:
                parts.append(f"{len(drug_interactions)} drug interaction(s)")
            if allergy_conflicts:
                parts.append(f"{len(allergy_conflicts)} allergy conflict(s)")
            if condition_conflicts:
                parts.append(f"{len(condition_conflicts)} condition contraindication(s)")
            prefix = "BLOCKED" if blocked else "CAUTION"
            summary = f"{prefix}: Detected " + ", ".join(parts) + "."

        return InteractionCheckResult(
            has_conflicts=has_conflicts,
            blocked=blocked,
            drug_interactions=drug_interactions,
            allergy_conflicts=allergy_conflicts,
            condition_conflicts=condition_conflicts,
            summary=summary,
        )

    def evaluate_action_constraints(
        self, case: PatientCase, proposed_med_ids: list[str]
    ) -> InteractionCheckResult:
        """Evaluate ontology constraints for a specific PatientCase."""
        return self.check_interactions(
            proposed_med_ids=proposed_med_ids,
            active_med_ids=case.active_medications,
            allergies=case.allergies,
            conditions=case.conditions,
        )
