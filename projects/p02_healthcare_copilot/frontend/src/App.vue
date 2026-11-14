<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import PatientQueue from "./components/PatientQueue.vue";
import MedicationMatrix from "./components/MedicationMatrix.vue";
import {
  apiClient,
  type AuditLogEntry,
  type ClinicalAction,
  type ClinicalTriageResponse,
  type DashboardOverview,
  type DischargeSummaryResponse,
  type ESITriageEntry,
  type FHIRBundleResponse,
  type InteractionCheckResult,
  type OntologyCatalog,
  type SOAPNote,
  type WikiLintResponse,
  type WikiPageItem,
} from "./api/client";

type WorkspaceMode = "encounter" | "fhir" | "discharge" | "wiki";

const workspaceMode = ref<WorkspaceMode>("encounter");
const loading = ref(false);
const errorMsg = ref("");

const overview = ref<DashboardOverview | null>(null);
const catalog = ref<OntologyCatalog | null>(null);
const triageQueue = ref<ESITriageEntry[]>([]);
const selectedCaseId = ref<string | null>(null);
const wikiPages = ref<WikiPageItem[]>([]);
const wikiLintResult = ref<WikiLintResponse | null>(null);
const pendingActions = ref<ClinicalAction[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);

// Center Pane: Clinical Encounter Form
const triageForm = reactive({
  case_id: "case-er-101",
  patient_ref: "ED-BAY-01",
  age: 64,
  sex: "M" as "M" | "F" | "O" | "U",
  chief_complaint:
    "Patient: Zhang Wei (MRN-882190) presents with acute substernal chest pain, phone 555-222-3333",
  symptom_id: "chest_pain",
  symptom_name: "Chest Pain",
  symptom_severity: "critical" as "mild" | "moderate" | "severe" | "critical",
  is_red_flag: true,
  spo2: 88,
  hr: 118,
  sbp: 102,
  active_medications: "warfarin",
  allergies: "",
  conditions: "hypertension, acute_coronary_syndrome",
  proposed_med_ids: "aspirin",
  raw_notes: "DOB 1962-04-11, SSN 123-45-6789, Email zhang.wei@example.com",
});

const triageResult = ref<ClinicalTriageResponse | null>(null);
const fhirResult = ref<FHIRBundleResponse | null>(null);
const interactionResult = ref<InteractionCheckResult | null>(null);

// Discharge Summary Form
const dischargeForm = reactive({
  case_id: "case-dc-2026",
  diagnosis: "Hypertension and atrial fibrillation",
  raw_notes:
    "Patient: Li Ming, MRN-778899, SSN 123-45-6789, DOB 1965-03-21, Phone 555-123-9876, Email li.ming@example.com. Discharged stable on Warfarin and Lisinopril.",
  conditions: "hypertension",
  medications: "warfarin, lisinopril",
  follow_up_days: 7,
});
const dischargeResult = ref<DischargeSummaryResponse | null>(null);

// Wiki Ingest Form
const wikiForm = reactive({
  doc_id: "gl_acs_aspirin",
  title: "ACS Aspirin Loading Protocol",
  content:
    "Administer Aspirin 325 mg chewed immediately for suspected acute coronary syndrome unless active hemorrhage is present.",
  entity_type: "guideline",
  condition: "acute_coronary_syndrome",
  medication: "aspirin",
  dose_mg: 325,
  citation: "AHA/ACC Chest Pain Guideline 2021",
  related_ids: "chest_pain",
});

// Right Pane: Physician HITL Sign-off
const hitlPhysicianId = ref("dr-lin-01");
const hitlNotes = ref("Reviewed ESI acuity, ontology contraindications, and SOAP note.");

const activeSoapNote = computed<SOAPNote | null>(() => {
  return fhirResult.value?.soap_note ?? triageResult.value?.soap_note ?? null;
});

function splitCsv(val: string): string[] {
  return val
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function buildPatientCasePayload() {
  return {
    case_id: triageForm.case_id,
    patient_ref: triageForm.patient_ref,
    age: triageForm.age,
    sex: triageForm.sex,
    chief_complaint: triageForm.chief_complaint,
    symptoms: [
      {
        symptom_id: triageForm.symptom_id,
        name: triageForm.symptom_name,
        severity: triageForm.symptom_severity,
        is_red_flag: triageForm.is_red_flag,
      },
    ],
    active_medications: splitCsv(triageForm.active_medications),
    allergies: splitCsv(triageForm.allergies),
    conditions: splitCsv(triageForm.conditions),
    vital_signs: {
      spo2: triageForm.spo2,
      hr: triageForm.hr,
      sbp: triageForm.sbp,
    },
  };
}

async function refreshAll() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const [ov, cat, queueRes, pages, pending, logs] = await Promise.all([
      apiClient.getDashboardOverview(),
      apiClient.getOntologyCatalog(),
      apiClient.getTriageQueue(),
      apiClient.getWikiPages(),
      apiClient.getPendingActions(),
      apiClient.getAuditLogs(),
    ]);
    overview.value = ov;
    catalog.value = cat;
    triageQueue.value = queueRes.queue;
    wikiPages.value = pages.pages;
    pendingActions.value = pending.actions;
    auditLogs.value = logs.logs;
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function selectQueuePatient(entry: ESITriageEntry) {
  selectedCaseId.value = entry.case_id;
  triageForm.case_id = entry.case_id;
  triageForm.patient_ref = entry.patient_ref;
  triageForm.age = entry.age;
  triageForm.sex = entry.sex;
  triageForm.chief_complaint = entry.chief_complaint;
  const firstSym = entry.symptoms[0];
  if (firstSym) {
    triageForm.symptom_id = firstSym.symptom_id;
    triageForm.symptom_name = firstSym.name;
    triageForm.symptom_severity = firstSym.severity;
    triageForm.is_red_flag = firstSym.is_red_flag;
  }
  triageForm.spo2 = entry.vital_signs.spo2 ?? 98;
  triageForm.hr = entry.vital_signs.hr ?? 80;
  triageForm.sbp = entry.vital_signs.sbp ?? 120;
  triageForm.active_medications = entry.active_medications.join(", ");
  triageForm.proposed_med_ids = entry.proposed_med_ids.join(", ");
  triageForm.allergies = entry.allergies.join(", ");
  triageForm.conditions = entry.conditions.join(", ");

  await runFhirBundle();
}

async function runTriage() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await apiClient.clinicalTriage({
      patient_case: buildPatientCasePayload(),
      proposed_med_ids: splitCsv(triageForm.proposed_med_ids),
      raw_notes: triageForm.raw_notes,
    });
    triageResult.value = res;
    interactionResult.value = res.interaction_check;
    selectedCaseId.value = res.case_id;
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runFhirBundle() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await apiClient.generateFhirBundle({
      patient_case: buildPatientCasePayload(),
      proposed_med_ids: splitCsv(triageForm.proposed_med_ids),
      raw_notes: triageForm.raw_notes,
    });
    fhirResult.value = res;
    interactionResult.value = res.interaction_check;
    selectedCaseId.value = res.case_id;
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runInteractionCheck() {
  loading.value = true;
  errorMsg.value = "";
  try {
    interactionResult.value = await apiClient.checkInteraction({
      proposed_med_ids: splitCsv(triageForm.proposed_med_ids),
      active_med_ids: splitCsv(triageForm.active_medications),
      allergies: splitCsv(triageForm.allergies),
      conditions: splitCsv(triageForm.conditions),
    });
    overview.value = await apiClient.getDashboardOverview();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runDischargeSummary() {
  loading.value = true;
  errorMsg.value = "";
  try {
    dischargeResult.value = await apiClient.generateDischargeSummary({
      case_id: dischargeForm.case_id,
      raw_notes: dischargeForm.raw_notes,
      diagnosis: dischargeForm.diagnosis,
      conditions: splitCsv(dischargeForm.conditions),
      medications: splitCsv(dischargeForm.medications),
      follow_up_days: dischargeForm.follow_up_days,
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiIngest() {
  loading.value = true;
  errorMsg.value = "";
  try {
    await apiClient.ingestWikiPage({
      doc_id: wikiForm.doc_id,
      title: wikiForm.title,
      content: wikiForm.content,
      entity_type: wikiForm.entity_type,
      condition: wikiForm.condition || null,
      medication: wikiForm.medication || null,
      dose_mg: wikiForm.dose_mg,
      citation: wikiForm.citation || null,
      related_ids: splitCsv(wikiForm.related_ids),
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiLint() {
  loading.value = true;
  errorMsg.value = "";
  try {
    wikiLintResult.value = await apiClient.lintWiki();
    overview.value = await apiClient.getDashboardOverview();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function handleHitlDecision(
  actionId: string,
  decision: "approved" | "rejected"
) {
  loading.value = true;
  errorMsg.value = "";
  try {
    await apiClient.approveAction({
      action_id: actionId,
      physician_id: hitlPhysicianId.value,
      decision,
      notes: hitlNotes.value,
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await refreshAll();
  if (triageQueue.value.length > 0) {
    await selectQueuePatient(triageQueue.value[0]);
  }
});
</script>

<template>
  <div class="emr-shell">
    <!-- Top Clinical EMR Header -->
    <header class="emr-topbar">
      <div class="brand-area">
        <div class="med-cross">+</div>
        <div>
          <h1>P02 Hospital EMR · Clinical Decision &amp; FHIR Triage Workstation</h1>
          <p class="subtitle">
            HL7 FHIR R4 Bundle Adapter · ESI 1–5 Triage · HIPAA Safe Harbor De-ID · Deterministic Ontology Guardrails
          </p>
        </div>
      </div>

      <div class="topbar-metrics">
        <div class="metric-chip">
          <span class="m-label">ESI Queue</span>
          <strong>{{ triageQueue.length }}</strong>
        </div>
        <div class="metric-chip">
          <span class="m-label">Pending HITL</span>
          <strong class="accent-warn">{{ overview?.pending_hitl_count ?? 0 }}</strong>
        </div>
        <div class="metric-chip">
          <span class="m-label">Blocked Orders</span>
          <strong class="accent-danger">{{ overview?.metrics?.blocked_interactions_total ?? 0 }}</strong>
        </div>
        <div class="metric-chip">
          <span class="m-label">Audit Events</span>
          <strong>{{ overview?.audit_logs_count ?? 0 }}</strong>
        </div>
        <button type="button" class="btn-outline" :disabled="loading" @click="refreshAll">
          Sync EMR
        </button>
      </div>
    </header>

    <div v-if="errorMsg" class="error-toast">
      <strong>System Alert:</strong> {{ errorMsg }}
    </div>

    <!-- 3-Pane EMR Workstation Layout -->
    <main class="emr-three-pane">
      <!-- PANE 1: Left - ESI 1-5 Triage Priority Queue -->
      <PatientQueue
        :entries="triageQueue"
        :selected-case-id="selectedCaseId"
        :loading="loading"
        @select="selectQueuePatient"
        @refresh="refreshAll"
      />

      <!-- PANE 2: Center - SOAP & FHIR Encounter Workspace -->
      <section class="emr-center-pane">
        <div class="workspace-tabs">
          <button
            type="button"
            class="tab-btn"
            :class="{ active: workspaceMode === 'encounter' }"
            @click="workspaceMode = 'encounter'"
          >
            SOAP &amp; Encounter Intake
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: workspaceMode === 'fhir' }"
            @click="workspaceMode = 'fhir'"
          >
            HL7 FHIR R4 Bundle ({{ fhirResult?.bundle.total ?? 0 }})
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: workspaceMode === 'discharge' }"
            @click="workspaceMode = 'discharge'"
          >
            Discharge Summary
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: workspaceMode === 'wiki' }"
            @click="workspaceMode = 'wiki'"
          >
            Clinical Wiki ({{ wikiPages.length }})
          </button>
        </div>

        <!-- Mode: Encounter Intake & SOAP Note -->
        <div v-if="workspaceMode === 'encounter'" class="pane-scroll">
          <div class="card">
            <div class="card-head">
              <h3>Patient Encounter &amp; Vitals Intake</h3>
              <span class="phi-badge">HIPAA Safe Harbor Auto-Masking</span>
            </div>

            <div class="form-grid">
              <label>
                Case ID
                <input v-model="triageForm.case_id" />
              </label>
              <label>
                Bay / Patient Ref
                <input v-model="triageForm.patient_ref" />
              </label>
              <label>
                Age
                <input v-model.number="triageForm.age" type="number" min="0" max="130" />
              </label>
              <label>
                Sex
                <select v-model="triageForm.sex">
                  <option value="M">M</option>
                  <option value="F">F</option>
                  <option value="O">O</option>
                  <option value="U">U</option>
                </select>
              </label>
            </div>

            <div class="vitals-grid">
              <label>
                SpO2 (%)
                <input v-model.number="triageForm.spo2" type="number" />
              </label>
              <label>
                HR (bpm)
                <input v-model.number="triageForm.hr" type="number" />
              </label>
              <label>
                SBP (mmHg)
                <input v-model.number="triageForm.sbp" type="number" />
              </label>
              <label>
                Symptom Severity
                <select v-model="triageForm.symptom_severity">
                  <option value="mild">Mild</option>
                  <option value="moderate">Moderate</option>
                  <option value="severe">Severe</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
            </div>

            <div class="form-grid">
              <label class="span-2">
                Chief Complaint (auto-deidentified)
                <input v-model="triageForm.chief_complaint" />
              </label>
              <label>
                Active Medications (CSV)
                <input v-model="triageForm.active_medications" placeholder="warfarin, lisinopril" />
              </label>
              <label>
                Proposed Order (CSV)
                <input v-model="triageForm.proposed_med_ids" placeholder="aspirin, ibuprofen" />
              </label>
              <label>
                Allergies (CSV)
                <input v-model="triageForm.allergies" placeholder="penicillin, nsaid" />
              </label>
              <label>
                Conditions (CSV)
                <input v-model="triageForm.conditions" placeholder="hypertension" />
              </label>
              <label class="span-2">
                Clinical Notes (PHI redacted on submit)
                <textarea v-model="triageForm.raw_notes" rows="2" />
              </label>
            </div>

            <div class="action-bar">
              <button type="button" class="btn-primary" :disabled="loading" @click="runTriage">
                Run ESI Triage &amp; Queue HITL
              </button>
              <button type="button" class="btn-secondary" :disabled="loading" @click="runFhirBundle">
                Generate SOAP &amp; FHIR Bundle
              </button>
            </div>
          </div>

          <!-- SOAP Note Card -->
          <div v-if="activeSoapNote" class="card soap-card">
            <div class="card-head">
              <h3>Structured Clinical SOAP Note</h3>
              <span class="esi-pill" :class="`esi-bg-${activeSoapNote.esi_level}`">
                {{ activeSoapNote.esi_label }}
              </span>
            </div>
            <div class="soap-grid">
              <div class="soap-block">
                <span class="soap-letter">S</span>
                <div>
                  <strong>Subjective</strong>
                  <p>{{ activeSoapNote.subjective }}</p>
                </div>
              </div>
              <div class="soap-block">
                <span class="soap-letter">O</span>
                <div>
                  <strong>Objective</strong>
                  <p>{{ activeSoapNote.objective }}</p>
                </div>
              </div>
              <div class="soap-block">
                <span class="soap-letter">A</span>
                <div>
                  <strong>Assessment</strong>
                  <p>{{ activeSoapNote.assessment }}</p>
                </div>
              </div>
              <div class="soap-block">
                <span class="soap-letter">P</span>
                <div>
                  <strong>Plan</strong>
                  <p>{{ activeSoapNote.plan }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Mode: HL7 FHIR R4 Bundle Viewer -->
        <div v-if="workspaceMode === 'fhir'" class="pane-scroll">
          <div class="card">
            <div class="card-head">
              <h3>HL7 FHIR R4 Collection Bundle</h3>
              <button type="button" class="btn-primary" :disabled="loading" @click="runFhirBundle">
                Regenerate Bundle
              </button>
            </div>
            <div v-if="fhirResult" class="fhir-summary">
              <span class="fhir-tag">Bundle ID: {{ fhirResult.bundle.id }}</span>
              <span class="fhir-tag">Resources: {{ fhirResult.bundle.total }}</span>
              <span class="fhir-tag">
                PHI Redacted: {{ fhirResult.redacted_phi_types.join(", ") || "None" }}
              </span>
            </div>
            <pre v-if="fhirResult" class="fhir-json">{{ JSON.stringify(fhirResult.bundle, null, 2) }}</pre>
            <p v-else class="muted">Select a patient or click Regenerate Bundle to inspect HL7 FHIR JSON.</p>
          </div>
        </div>

        <!-- Mode: Discharge Summary -->
        <div v-if="workspaceMode === 'discharge'" class="pane-scroll">
          <div class="card">
            <div class="card-head">
              <h3>De-Identified Discharge Summary &amp; Checklist</h3>
            </div>
            <div class="form-grid">
              <label>
                Case ID
                <input v-model="dischargeForm.case_id" />
              </label>
              <label>
                Follow-up (Days)
                <input v-model.number="dischargeForm.follow_up_days" type="number" min="1" max="90" />
              </label>
              <label class="span-2">
                Discharge Diagnosis
                <input v-model="dischargeForm.diagnosis" />
              </label>
              <label>
                Conditions (CSV)
                <input v-model="dischargeForm.conditions" />
              </label>
              <label>
                Discharge Meds (CSV)
                <input v-model="dischargeForm.medications" />
              </label>
              <label class="span-2">
                Raw Clinical Discharge Note
                <textarea v-model="dischargeForm.raw_notes" rows="3" />
              </label>
            </div>
            <div class="action-bar">
              <button type="button" class="btn-primary" :disabled="loading" @click="runDischargeSummary">
                Generate De-Identified Discharge Plan
              </button>
            </div>
          </div>

          <div v-if="dischargeResult" class="card">
            <h4>De-Identified Note (Redacted: {{ dischargeResult.redacted_phi_types.join(", ") || "None" }})</h4>
            <p class="deid-box">{{ dischargeResult.deidentified_note }}</p>
            <h4>Follow-up Checklist</h4>
            <ul class="checklist">
              <li v-for="item in dischargeResult.follow_up_checklist" :key="item.step_id">
                <strong>[{{ item.category }} · {{ item.timeframe }}]</strong> {{ item.task }}
              </li>
            </ul>
          </div>
        </div>

        <!-- Mode: Clinical LLM Wiki -->
        <div v-if="workspaceMode === 'wiki'" class="pane-scroll">
          <div class="card">
            <div class="card-head">
              <h3>Clinical Guidelines Wiki &amp; Lint</h3>
              <button type="button" class="btn-secondary" :disabled="loading" @click="runWikiLint">
                Run Wiki Lint
              </button>
            </div>
            <div class="form-grid">
              <label>
                Doc ID
                <input v-model="wikiForm.doc_id" />
              </label>
              <label>
                Title
                <input v-model="wikiForm.title" />
              </label>
              <label>
                Condition
                <input v-model="wikiForm.condition" />
              </label>
              <label>
                Medication
                <input v-model="wikiForm.medication" />
              </label>
              <label class="span-2">
                Guideline Content
                <textarea v-model="wikiForm.content" rows="2" />
              </label>
            </div>
            <div class="action-bar">
              <button type="button" class="btn-primary" :disabled="loading" @click="runWikiIngest">
                Ingest Guideline
              </button>
            </div>
          </div>

          <div v-if="wikiLintResult" class="card">
            <h4>Wiki Lint: {{ wikiLintResult.status }} ({{ wikiLintResult.total_issues }} issue(s))</h4>
            <pre class="fhir-json">{{ JSON.stringify(wikiLintResult.counts, null, 2) }}</pre>
          </div>
        </div>
      </section>

      <!-- PANE 3: Right - Contraindication Matrix & Physician HITL Sign-Off -->
      <aside class="emr-right-pane">
        <MedicationMatrix
          :catalog="catalog"
          :active-meds="splitCsv(triageForm.active_medications)"
          :proposed-meds="splitCsv(triageForm.proposed_med_ids)"
          :allergies="splitCsv(triageForm.allergies)"
          :conditions="splitCsv(triageForm.conditions)"
          :interaction-result="interactionResult"
          :loading="loading"
          @check="runInteractionCheck"
        />

        <!-- Physician HITL Sign-Off -->
        <section class="hitl-card">
          <div class="card-head">
            <div>
              <span class="pane-kicker">HUMAN-IN-THE-LOOP</span>
              <h3>Physician Sign-Off Queue</h3>
            </div>
            <span class="count-pill">{{ pendingActions.length }}</span>
          </div>

          <div class="hitl-inputs">
            <label>
              Attending Physician ID
              <input v-model="hitlPhysicianId" />
            </label>
            <label>
              Sign-Off Notes
              <input v-model="hitlNotes" />
            </label>
          </div>

          <div v-if="pendingActions.length === 0" class="muted">
            No pending clinical actions awaiting sign-off.
          </div>

          <div v-else class="hitl-list">
            <div v-for="act in pendingActions" :key="act.action_id" class="hitl-item">
              <div class="hitl-item-top">
                <strong>{{ act.case_id }}</strong>
                <span class="risk-pill" :class="`risk-${act.risk_level}`">{{ act.risk_level }}</span>
              </div>
              <p class="hitl-rationale">{{ act.rationale }}</p>
              <div class="hitl-btns">
                <button
                  type="button"
                  class="btn-approve"
                  :disabled="loading"
                  @click="handleHitlDecision(act.action_id, 'approved')"
                >
                  Approve
                </button>
                <button
                  type="button"
                  class="btn-reject"
                  :disabled="loading"
                  @click="handleHitlDecision(act.action_id, 'rejected')"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- Compact Audit Log -->
        <section class="audit-card">
          <div class="card-head">
            <h3>HIPAA Audit Trail</h3>
            <span class="count-pill">{{ auditLogs.length }}</span>
          </div>
          <div class="audit-list">
            <div v-for="(log, idx) in auditLogs.slice(-5).reverse()" :key="idx" class="audit-row">
              <span class="audit-type">{{ log.event_type }}</span>
              <span class="audit-case">{{ log.case_id }}</span>
            </div>
          </div>
        </section>
      </aside>
    </main>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f4f8fb;
  color: #0f172a;
}
</style>

<style scoped>
.emr-shell {
  min-height: 100vh;
  background: #f4f8fb;
  color: #0f172a;
  display: flex;
  flex-direction: column;
}

.emr-topbar {
  background: #ffffff;
  border-bottom: 1px solid #d8e5f0;
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 4px rgba(2, 132, 199, 0.06);
}

.brand-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.med-cross {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #0284c7;
  color: #ffffff;
  font-size: 24px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}

.emr-topbar h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: #475569;
}

.topbar-metrics {
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-chip {
  background: #f4f8fb;
  border: 1px solid #d8e5f0;
  border-radius: 8px;
  padding: 5px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 78px;
}

.m-label {
  font-size: 10px;
  color: #64748b;
  text-transform: uppercase;
  font-weight: 600;
}

.metric-chip strong {
  font-size: 14px;
  color: #0284c7;
}

.metric-chip strong.accent-warn {
  color: #d97706;
}

.metric-chip strong.accent-danger {
  color: #dc2626;
}

.btn-outline {
  background: #ffffff;
  border: 1px solid #0284c7;
  color: #0284c7;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.btn-outline:hover:not(:disabled) {
  background: #f0f9ff;
}

.error-toast {
  margin: 10px 20px 0;
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
  border-radius: 8px;
  font-size: 13px;
}

.emr-three-pane {
  flex: 1;
  display: grid;
  grid-template-columns: 300px minmax(460px, 1fr) 360px;
  gap: 14px;
  padding: 14px 20px 20px;
  align-items: start;
}

@media (max-width: 1180px) {
  .emr-three-pane {
    grid-template-columns: 1fr;
  }
}

.emr-center-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.workspace-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  background: #ffffff;
  padding: 6px;
  border-radius: 10px;
  border: 1px solid #d8e5f0;
}

.tab-btn {
  background: transparent;
  border: none;
  border-radius: 7px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
}

.tab-btn.active {
  background: #0284c7;
  color: #ffffff;
}

.pane-scroll {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card,
.hitl-card,
.audit-card {
  background: #ffffff;
  border: 1px solid #d8e5f0;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 2px 8px rgba(15, 45, 75, 0.04);
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.card-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.pane-kicker {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0284c7;
}

.phi-badge {
  font-size: 10px;
  font-weight: 700;
  background: #e0f2fe;
  color: #0369a1;
  padding: 3px 8px;
  border-radius: 999px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.vitals-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
  background: #f4f8fb;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #e2ecf4;
}

.span-2 {
  grid-column: span 2;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #334155;
}

input,
select,
textarea {
  width: 100%;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  padding: 7px 9px;
  font-size: 12px;
  color: #0f172a;
}

input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: #0284c7;
  box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15);
}

.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.btn-primary {
  background: #0284c7;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:hover:not(:disabled) {
  background: #0369a1;
}

.btn-secondary {
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #7dd3fc;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.btn-secondary:hover:not(:disabled) {
  background: #e0f2fe;
}

.soap-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.soap-block {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: #f8fbfe;
  border: 1px solid #e2ecf4;
  border-radius: 8px;
  padding: 9px 10px;
}

.soap-letter {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: #0284c7;
  color: #ffffff;
  font-weight: 800;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.soap-block strong {
  font-size: 12px;
  color: #0f172a;
}

.soap-block p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #334155;
  line-height: 1.4;
}

.esi-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
}

.esi-bg-1 {
  background: #fee2e2;
  color: #b91c1c;
}
.esi-bg-2 {
  background: #ffedd5;
  color: #c2410c;
}
.esi-bg-3 {
  background: #fef3c7;
  color: #b45309;
}

.fhir-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.fhir-tag {
  font-size: 11px;
  font-weight: 600;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  color: #0369a1;
  padding: 3px 8px;
  border-radius: 6px;
}

.fhir-json {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
  font-size: 11px;
  overflow-x: auto;
  max-height: 460px;
  color: #0f172a;
}

.deid-box {
  background: #f4f8fb;
  border-left: 3px solid #0284c7;
  padding: 8px 10px;
  font-size: 12px;
  border-radius: 4px;
}

.checklist {
  padding-left: 18px;
  font-size: 12px;
  color: #334155;
}

.emr-right-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.count-pill {
  background: #e0f2fe;
  color: #0369a1;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
}

.hitl-inputs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.hitl-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hitl-item {
  background: #f8fbfe;
  border: 1px solid #dce8f2;
  border-radius: 8px;
  padding: 9px;
}

.hitl-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.risk-pill {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 4px;
}

.risk-critical,
.risk-high {
  background: #fee2e2;
  color: #b91c1c;
}
.risk-medium {
  background: #fef3c7;
  color: #b45309;
}
.risk-low {
  background: #dcfce7;
  color: #15803d;
}

.hitl-rationale {
  margin: 5px 0 8px;
  font-size: 11px;
  color: #334155;
}

.hitl-btns {
  display: flex;
  gap: 6px;
}

.btn-approve {
  flex: 1;
  background: #16a34a;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.btn-reject {
  flex: 1;
  background: #dc2626;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.audit-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.audit-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  padding: 4px 6px;
  background: #f8fafc;
  border-radius: 5px;
}

.audit-type {
  font-weight: 700;
  color: #0284c7;
}

.audit-case {
  color: #475569;
}

.muted {
  font-size: 12px;
  color: #64748b;
}
</style>
