export interface DashboardOverview {
  service: string;
  guidelines_count: number;
  medications_count: number;
  contraindications_count: number;
  symptoms_count: number;
  wiki_pages_count: number;
  pending_hitl_count: number;
  audit_logs_count: number;
  metrics: Record<string, number>;
}

export interface SymptomInput {
  symptom_id: string;
  name: string;
  severity: "mild" | "moderate" | "severe" | "critical";
  is_red_flag: boolean;
  onset_hours?: number | null;
  description?: string;
}

export interface PatientCaseInput {
  case_id: string;
  patient_ref?: string;
  age: number;
  sex: "M" | "F" | "O" | "U";
  chief_complaint: string;
  symptoms: SymptomInput[];
  active_medications: string[];
  allergies: string[];
  conditions: string[];
  vital_signs: Record<string, number>;
}

export interface InteractionCheckResult {
  has_conflicts: boolean;
  blocked: boolean;
  drug_interactions: Array<Record<string, string>>;
  allergy_conflicts: Array<Record<string, string>>;
  condition_conflicts: Array<Record<string, string>>;
  summary: string;
}

export interface ClinicalAction {
  action_id: string;
  case_id: string;
  action_type: string;
  proposed_med_ids: string[];
  rationale: string;
  risk_level: "low" | "medium" | "high" | "critical";
  requires_hitl: boolean;
  status: "pending_review" | "approved" | "rejected" | "blocked";
  reviewer_id?: string | null;
  review_notes?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}

export interface ClinicalTriageResponse {
  case_id: string;
  triage_level: "emergency" | "urgent" | "routine";
  emergency_escalated: boolean;
  red_flags: string[];
  deidentified_complaint: string;
  deidentified_notes: string;
  redacted_phi_types: string[];
  interaction_check: InteractionCheckResult;
  wiki_references: Array<Record<string, unknown>>;
  proposed_action: ClinicalAction;
}

export interface ChecklistItem {
  step_id: string;
  category: string;
  task: string;
  timeframe: string;
  priority: string;
  completed: boolean;
}

export interface DischargeSummaryResponse {
  case_id: string;
  deidentified_diagnosis: string;
  deidentified_note: string;
  redacted_phi_types: string[];
  conditions: string[];
  medications: string[];
  interaction_check: InteractionCheckResult;
  follow_up_checklist: ChecklistItem[];
  red_flag_precautions: string[];
  wiki_references: Array<Record<string, unknown>>;
  generated_at: string;
}

export interface WikiPageItem {
  id: string;
  title: string;
  path: string;
  preview: string;
  entity_type: string;
  condition: string;
  medication: string;
  dose_mg: number | null;
  citation: string;
  wiki_links: string[];
  updated_at: string;
}

export interface WikiLintResponse {
  status: string;
  total_entities: number;
  total_issues: number;
  counts: Record<string, number>;
  issues: Array<Record<string, unknown>>;
}

export interface AuditLogEntry {
  timestamp: string;
  event_type: string;
  case_id: string;
  action_id: string | null;
  details: Record<string, unknown>;
}

export interface OntologyCatalog {
  medications: Array<{
    med_id: string;
    name: string;
    drug_class: string;
    allergen_tags: string[];
    standard_dose_mg: number;
    max_daily_dose_mg: number;
    contraindicated_conditions: string[];
  }>;
  contraindications: Array<{
    link_id: string;
    source_med_id: string;
    target_med_id: string;
    severity: string;
    mechanism: string;
    recommendation: string;
  }>;
  symptoms: SymptomInput[];
  guidelines: Array<{
    guideline_id: string;
    condition_name: string;
    recommended_med_ids: string[];
    recommended_dose_mg: number | null;
    source_citation: string;
    evidence_grade: string;
    red_flag_symptoms: string[];
  }>;
}

const API_BASE = "";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText || res.statusText}`);
  }
  return (await res.json()) as T;
}

export const apiClient = {
  getDashboardOverview: () =>
    request<DashboardOverview>("/api/v1/dashboard/overview"),

  getOntologyCatalog: () =>
    request<OntologyCatalog>("/api/v1/ontology/catalog"),

  checkInteraction: (payload: {
    proposed_med_ids: string[];
    active_med_ids: string[];
    allergies: string[];
    conditions: string[];
  }) =>
    request<InteractionCheckResult>("/api/v1/ontology/check-interaction", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  clinicalTriage: (payload: {
    patient_case: PatientCaseInput;
    proposed_med_ids: string[];
    raw_notes: string;
  }) =>
    request<ClinicalTriageResponse>("/api/v1/clinical/triage", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  generateDischargeSummary: (payload: {
    case_id: string;
    raw_notes: string;
    diagnosis: string;
    conditions: string[];
    medications: string[];
    follow_up_days: number;
  }) =>
    request<DischargeSummaryResponse>("/api/v1/clinical/discharge-summary", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getWikiPages: () =>
    request<{ total: number; pages: WikiPageItem[] }>("/api/v1/wiki/pages"),

  ingestWikiPage: (payload: {
    doc_id: string;
    title: string;
    content: string;
    entity_type: string;
    condition?: string | null;
    medication?: string | null;
    dose_mg?: number | null;
    citation?: string | null;
    related_ids?: string[];
  }) =>
    request<{ status: string; entity: Record<string, unknown> }>(
      "/api/v1/wiki/ingest",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  lintWiki: () => request<WikiLintResponse>("/api/v1/wiki/lint"),

  getPendingActions: () =>
    request<{ total: number; actions: ClinicalAction[] }>(
      "/api/v1/actions/pending"
    ),

  approveAction: (payload: {
    action_id: string;
    physician_id: string;
    decision: "approved" | "rejected";
    notes: string;
  }) =>
    request<{ status: string; action: ClinicalAction }>(
      "/api/v1/actions/approve",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  getAuditLogs: () =>
    request<{ total: number; logs: AuditLogEntry[] }>("/api/v1/audit/logs"),
};
