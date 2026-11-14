export type ApplicantType = 'citizen' | 'enterprise'

export interface CitizenProfile {
  applicant_id: string
  applicant_type: ApplicantType
  name: string
  identifier: string
  region: string
  annual_income_or_revenue: number
  employee_count: number
  industry: string
  tags: string[]
  attributes?: Record<string, unknown>
}

export interface RuleEvaluationDetail {
  rule_id: string
  field: string
  operator: string
  expected: unknown
  actual: unknown
  passed: boolean
  clause_ref: string
  description: string
}

export interface EligibilityEvaluation {
  applicant_id: string
  program_id: string
  program_name: string
  department: string
  eligible: boolean
  estimated_subsidy: number
  matched_rules: RuleEvaluationDetail[]
  failed_rules: RuleEvaluationDetail[]
  exact_clauses: string[]
}

export interface GovAction {
  action_id: string
  applicant_id: string
  program_id: string
  department: string
  action_type: string
  amount: number
  status: 'pending_approval' | 'approved' | 'rejected'
  requires_hitl: boolean
  clause_citations: string[]
  approved_by?: string | null
  decision_note: string
  created_at: string
  decided_at?: string | null
}

export interface WikiQueryHit {
  doc_id: string
  title: string
  department: string
  score: number
  snippet: string
  wiki_links: string[]
  clauses: Record<string, string>
  path: string
}

export interface PolicyAskResponse {
  request_id: string
  status: 'answered' | 'refused'
  masked_question: string
  masked_pii_types: string[]
  department: string
  answer: string
  clause_citations: string[]
  wiki_hits: WikiQueryHit[]
  eligibility_evaluations: EligibilityEvaluation[]
  pending_action: GovAction | null
  refusal_reason: string | null
}

export interface BatchMatchApplicantResult {
  applicant_id: string
  applicant_name: string
  applicant_type: ApplicantType
  masked_identifier: string
  region: string
  eligible_count: number
  total_estimated_subsidy: number
  recommended_department: string
  evaluations: EligibilityEvaluation[]
}

export interface BatchMatchResponse {
  batch_id: string
  total_applicants: number
  total_programs_evaluated: number
  eligible_applicants: number
  total_potential_subsidy: number
  matrix: BatchMatchApplicantResult[]
}

export interface DashboardOverview {
  service: string
  active_policies: number
  total_policies: number
  benefit_programs: number
  eligibility_rules: number
  wiki_pages: number
  pending_hitl_reviews: number
  approved_hitl_reviews: number
  rejected_hitl_reviews: number
  audit_logs_count: number
  departments: string[]
  policies: Array<{
    policy_id: string
    title: string
    department: string
    status: string
    effective_date: string
    expiry_date: string | null
    tags: string[]
  }>
  programs: Array<{
    program_id: string
    name: string
    department: string
    policy_id: string
    max_subsidy_amount: number
    requires_hitl: boolean
    hitl_threshold_amount: number
    active: boolean
  }>
  rules: Array<{
    rule_id: string
    program_id: string
    policy_id: string
    field: string
    operator: string
    value: unknown
    clause_ref: string
    description: string
  }>
  ontology_links: Array<{
    source_id: string
    target_id: string
    relation_type: string
  }>
}

export interface WikiPageSummary {
  id: string
  title: string
  path: string
  preview: string
  department: string
  entity_type: string
  effective_date: string
  expiry_date: string | null
  wiki_links: string[]
}

export interface LintIssue {
  issue_type: string
  severity: string
  entity_id: string
  message: string
  details: Record<string, unknown>
}

export interface LintReport {
  checked_at: string
  reference_date: string
  total_entities: number
  healthy: boolean
  expired_policies: LintIssue[]
  conflicting_thresholds: LintIssue[]
  orphan_rules: LintIssue[]
  issues: LintIssue[]
}

export interface AuditEvent {
  event_id: string
  timestamp: string
  stage: string
  actor: string
  masked_pii_types: string[]
  summary: string
  metadata: Record<string, unknown>
}

export interface BureauStage {
  stage_id: string
  bureau: string
  bureau_short: string
  execution_mode: 'sequential' | 'parallel'
  step_order: number
  sla_days: number
  status: 'completed' | 'in_progress' | 'pending'
  required_documents: string[]
  responsibility: string
}

export interface WorkflowRouteRequest {
  case_id?: string | null
  applicant_id: string
  applicant_type: ApplicantType
  program_id: string
  program_name?: string
  amount: number
  approved?: boolean
  tags?: string[]
  current_step?: number
}

export interface WorkflowRouteResult {
  case_id: string
  applicant_id: string
  program_id: string
  workflow_pattern: 'sequential' | 'hybrid_parallel'
  route_summary: string
  total_sla_days: number
  fast_track: boolean
  stages: BureauStage[]
  consolidated_documents: string[]
  routed_at: string
}

export interface PolicyRevision {
  policy_id: string
  version: string
  title: string
  department?: string
  effective_date: string
  expiry_date?: string | null
  status?: 'active' | 'expired' | 'draft' | 'revoked'
  subsidy_cap: number
  eligibility_threshold?: string
  clauses: Record<string, string>
}

export interface ThresholdChange {
  field: string
  label: string
  old_value: unknown
  new_value: unknown
  delta: number | null
  change_type: 'increased' | 'decreased' | 'modified' | 'unchanged'
}

export interface ClauseDiffItem {
  clause_ref: string
  change_type: 'added' | 'removed' | 'modified' | 'unchanged'
  old_text: string | null
  new_text: string | null
  highlight_summary: string
}

export interface PolicyDiffRequest {
  policy_id?: string | null
  old_revision?: PolicyRevision | null
  new_revision?: PolicyRevision | null
}

export interface PolicyDiffResult {
  policy_id: string
  old_version: string
  new_version: string
  title: string
  department: string
  old_status: string
  new_status: string
  has_changes: boolean
  subsidy_cap_delta: number
  threshold_changes: ThresholdChange[]
  clause_diffs: ClauseDiffItem[]
  summary: string
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const govtechApi = {
  getOverview: () => requestJson<DashboardOverview>('/api/v1/dashboard/overview'),
  getWikiPages: () => requestJson<WikiPageSummary[]>('/api/v1/wiki/pages'),
  ingestWiki: (payload: {
    doc_id: string
    title: string
    content: string
    department: string
    entity_type?: string
    program_id?: string | null
    effective_date?: string
    expiry_date?: string | null
    subsidy_threshold?: number | null
    clauses?: Record<string, string>
  }) =>
    requestJson<{ doc_id: string; path: string; total_entities: number }>(
      '/api/v1/wiki/ingest',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  lintWiki: (referenceDate?: string) =>
    requestJson<LintReport>('/api/v1/wiki/lint', {
      method: 'POST',
      body: JSON.stringify(referenceDate ? { reference_date: referenceDate } : {}),
    }),
  askPolicy: (payload: {
    question: string
    profile?: CitizenProfile | null
    program_id?: string | null
    create_hitl_action?: boolean
  }) =>
    requestJson<PolicyAskResponse>('/api/v1/policy/ask', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  batchMatch: (payload: { profiles: CitizenProfile[]; program_ids?: string[] | null }) =>
    requestJson<BatchMatchResponse>('/api/v1/policy/batch-match', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getPendingActions: () => requestJson<GovAction[]>('/api/v1/actions/pending'),
  approveAction: (payload: {
    action_id: string
    officer_id: string
    approved: boolean
    note: string
  }) =>
    requestJson<GovAction>('/api/v1/actions/approve', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getAuditLogs: (limit = 100) =>
    requestJson<AuditEvent[]>(`/api/v1/audit/logs?limit=${limit}`),
  routeCase: (payload: WorkflowRouteRequest) =>
    requestJson<WorkflowRouteResult>('/api/v1/workflow/route-case', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  diffPolicyGazette: (payload: PolicyDiffRequest) =>
    requestJson<PolicyDiffResult>('/api/v1/policy/gazette-diff', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
