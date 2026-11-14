export interface ServiceSummary {
  service_id: string
  name: string
  tier: string
  owner_team: string
  environment: string
  runbook_id: string | null
}

export interface DashboardOverview {
  services_total: number
  critical_cves_total: number
  active_incidents_total: number
  pending_hitl_rollbacks: number
  audit_logs_total: number
  wiki_pages_total: number
  services: ServiceSummary[]
}

export interface ImpactedService {
  service_id: string
  name: string
  tier: string
  depth: number
  criticality: string
  propagation_path: string[]
}

export interface BlastRadiusResponse {
  root_service_id: string
  root_tier: string
  impacted_upstream: ImpactedService[]
  total_impacted_services: number
  tier0_impacted: string[]
  downstream_dependencies: Array<{
    service_id: string
    relation: string
    criticality: string
  }>
  active_cves: Array<{
    cve_id: string
    cvss_score: number
    severity: string
  }>
  cvss_gate: {
    service_id: string
    blocked: boolean
    max_cvss: number
    block_threshold: number
    gate_decision: string
  }
}

export interface TriageResponse {
  service_id: string
  severity: string
  redacted_symptom: string
  redactions_applied: string[]
  root_cause_hypotheses: string[]
  blast_radius: BlastRadiusResponse
  cvss_gate: BlastRadiusResponse['cvss_gate']
  wiki_references: Array<{
    entity_id: string
    entity_type: string
    title: string
    score: number
    snippet: string
  }>
  action: {
    action_id: string
    action_type: string
    target_service_id: string
    environment: string
    requires_hitl: boolean
    status: string
    created_at: string
  }
  audit_id: string
}

export interface CveGateResponse {
  service_id: string
  release_version: string
  decision: 'ALLOW' | 'BLOCK_DEPLOY'
  allowed: boolean
  max_cvss: number
  block_threshold: number
  checked_services: string[]
  blocking_cves: Array<{
    cve_id: string
    service_id: string
    cvss_score: number
    severity: string
    remediation: string
  }>
  audit_id: string
}

export interface WikiPage {
  id: string
  entity_type: string
  title: string
  path: string
  preview: string
  content?: string
}

export interface WikiLintReport {
  reference_date: string
  stale_days: number
  healthy: boolean
  total_issues: number
  services_without_runbooks: string[]
  unpatched_critical_cves: Array<{
    cve_id: string
    service_id: string
    cvss_score: number
  }>
  stale_postmortems: Array<{
    incident_id: string
    service_id: string
    reason: string
  }>
  broken_wiki_links: Array<{
    source: string
    missing_target: string
  }>
}

export interface PendingAction {
  action_id: string
  action_type: string
  target_service_id: string
  environment: string
  requires_hitl: boolean
  status: string
  requested_by: string
  reason: string
  created_at: string
}

export interface AuditLogEntry {
  audit_id: string
  timestamp: string
  event_type: string
  actor: string
  payload: Record<string, unknown>
}

export interface SBOMFinding {
  cve_id: string
  package_ref: string
  package_name: string
  package_version: string
  cvss_score: number
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  exposure: 'direct' | 'transitive'
  depth: number
  dependency_path: string[]
  impacted_consumers: string[]
  fixed_version: string
  description: string
}

export interface SBOMScanResponse {
  bom_format: string
  spec_version: string
  root_component: string | null
  total_components: number
  vulnerable_components: number
  total_cves: number
  max_cvss: number
  block_threshold: number
  gate_decision: 'BLOCK_DEPLOY' | 'WARN' | 'PASS'
  blocked: boolean
  severity_counts: Record<'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW', number>
  topological_blast_order: string[]
  blast_radius_order: string[]
  findings: SBOMFinding[]
}

export interface PostmortemTimelineEntry {
  timestamp: string
  actor: string
  event: string
}

export interface PostmortemActionItem {
  priority: string
  owner: string
  task: string
  due_date: string
}

export interface PostmortemExportResponse {
  incident_id: string
  service_id: string
  severity: string
  commander: string
  redactions_applied: string[]
  blast_radius_summary: {
    total_impacted_services: number
    tier0_impacted: string[]
  }
  markdown: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`API ${response.status}: ${detail}`)
  }
  return (await response.json()) as T
}

export const devsecopsApi = {
  getDashboardOverview: () =>
    requestJson<DashboardOverview>('/api/v1/dashboard/overview'),

  getBlastRadius: (serviceId: string, maxDepth = 5) =>
    requestJson<BlastRadiusResponse>(
      `/api/v1/ontology/blast-radius?service_id=${encodeURIComponent(serviceId)}&max_depth=${maxDepth}`,
    ),

  triageIncident: (payload: {
    service_id: string
    symptom: string
    severity: string
    proposed_action: string
    environment: string
    requested_by: string
  }) =>
    requestJson<TriageResponse>('/api/v1/incidents/triage', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  evaluateCveGate: (payload: {
    service_id: string
    release_version: string
    include_dependencies: boolean
    block_threshold: number
  }) =>
    requestJson<CveGateResponse>('/api/v1/security/cve-gate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  scanSBOM: (payload: {
    service_id?: string
    sbom?: Record<string, unknown>
    block_threshold?: number
  }) =>
    requestJson<SBOMScanResponse>('/api/v1/security/sbom-scan', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  exportPostmortem: (payload: {
    incident_id: string
    title: string
    service_id: string
    severity: string
    commander: string
    summary: string
    root_cause: string
    timeline: PostmortemTimelineEntry[]
    action_items: PostmortemActionItem[]
    include_blast_radius?: boolean
    sbom?: Record<string, unknown>
  }) =>
    requestJson<PostmortemExportResponse>('/api/v1/incidents/postmortem', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getWikiPages: () =>
    requestJson<{ pages: WikiPage[]; total: number }>('/api/v1/wiki/pages'),

  ingestWikiPage: (payload: {
    entity_type: string
    entity_id: string
    title: string
    content: string
    links: string[]
  }) =>
    requestJson<{ status: string; entity_id: string; path: string }>(
      '/api/v1/wiki/ingest',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  lintWiki: (referenceDate = '2026-11-13', staleDays = 30) =>
    requestJson<WikiLintReport>(
      `/api/v1/wiki/lint?reference_date=${encodeURIComponent(referenceDate)}&stale_days=${staleDays}`,
    ),

  getPendingActions: () =>
    requestJson<{ actions: PendingAction[]; total: number }>('/api/v1/actions/pending'),

  approveAction: (payload: {
    action_id: string
    approved: boolean
    approver: string
    comment: string
  }) =>
    requestJson<{ action_id: string; status: string; audit_id: string }>(
      '/api/v1/actions/approve',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  getAuditLogs: () =>
    requestJson<{ logs: AuditLogEntry[]; total: number }>('/api/v1/audit/logs'),
}
