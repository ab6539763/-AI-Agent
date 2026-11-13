export interface DashboardOverview {
  contracts_reviewed: number;
  contracts_total: number;
  clauses_total: number;
  high_risk_clauses: number;
  critical_risk_clauses: number;
  active_regulations: number;
  regulations_total: number;
  pending_gc_approvals: number;
  audit_logs_count: number;
  pii_masked_total: number;
  wiki_pages_count: number;
  recent_contracts: Array<{
    id: string;
    title: string;
    counterparty: string;
    jurisdiction: string;
    status: string;
  }>;
}

export interface ClauseItem {
  id: string;
  contract_id: string;
  title: string;
  clause_type: string;
  text: string;
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  matched_regulations: string[];
  redline_suggestion: string | null;
  extracted_cap_usd: number | null;
}

export interface RegulationItem {
  id: string;
  code: string;
  title: string;
  jurisdiction: string;
  status: "active" | "superseded" | "draft";
  superseded_by: string | null;
  summary: string;
  keywords: string[];
}

export interface LegalLinkItem {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  weight: number;
}

export interface LegalActionItem {
  id: string;
  contract_id: string;
  clause_id: string | null;
  action_type: string;
  risk_level: "low" | "medium" | "high" | "critical";
  status: "pending" | "approved" | "rejected";
  requested_by: string;
  approver: string | null;
  decision_notes: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface AuditLogEntry {
  timestamp: string;
  event_type: string;
  actor: string;
  target_id: string;
  details: Record<string, unknown>;
}

export interface ContractReviewResponse {
  contract: {
    id: string;
    title: string;
    counterparty: string;
    jurisdiction: string;
    status: string;
  };
  masked_text: string;
  pii_masked_count: number;
  overall_risk_score: number;
  overall_risk_level: "low" | "medium" | "high" | "critical";
  requires_hitl: boolean;
  clauses: ClauseItem[];
  pending_actions: LegalActionItem[];
  audit_entry: AuditLogEntry;
}

export interface ClauseDiffItem {
  index: number;
  status: "added" | "removed" | "modified" | "unchanged";
  title: string;
  clause_type: string;
  original_text: string | null;
  revised_text: string | null;
  original_risk_level: string | null;
  original_risk_score: number | null;
  revised_risk_level: string | null;
  revised_risk_score: number | null;
  risk_delta: number;
  redline_recommendation: string | null;
  diff_lines: string[];
}

export interface RedlineDiffResponse {
  contract_id: string;
  title: string;
  original_risk_score: number;
  original_risk_level: string;
  revised_risk_score: number;
  revised_risk_level: string;
  risk_score_delta: number;
  risk_trend: "improved" | "worsened" | "unchanged";
  pii_masked_count: number;
  original_clause_count: number;
  revised_clause_count: number;
  clause_diffs: ClauseDiffItem[];
  redline_recommendations: Array<{
    clause_index: number;
    title: string;
    clause_type: string;
    risk_level: string;
    recommendation: string;
  }>;
  audit_entry: AuditLogEntry;
}

export interface WikiPageItem {
  id: string;
  title: string;
  path: string;
  preview: string;
}

export interface WikiLintResponse {
  total_issues: number;
  superseded_regulations: Array<{
    clause_id: string;
    contract_id: string;
    regulation_id: string;
    regulation_code: string;
    superseded_by: string | null;
  }>;
  unlinked_clauses: Array<{
    clause_id: string;
    contract_id: string;
    reason: string;
    entity_exists: boolean;
  }>;
  conflicting_liability_caps: Array<{
    contract_id: string;
    contract_cap_usd: number | null;
    clause_caps: Array<{ clause_id: string; cap_usd: number | string }>;
    reason: string;
  }>;
}

const BASE = "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const legalApi = {
  health: () => requestJson<{ status: string; service: string }>("/health"),
  getOverview: () => requestJson<DashboardOverview>("/api/v1/dashboard/overview"),
  reviewContract: (payload: {
    contract_id: string;
    title: string;
    text: string;
    counterparty?: string;
    jurisdiction?: string;
    liability_cap_usd?: number | null;
    requested_by?: string;
  }) =>
    requestJson<ContractReviewResponse>("/api/v1/contracts/review", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  redlineDiff: (payload: {
    contract_id: string;
    title: string;
    original_text: string;
    revised_text: string;
    requested_by?: string;
  }) =>
    requestJson<RedlineDiffResponse>("/api/v1/contracts/redline-diff", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listClauses: (riskLevel?: string) => {
    const qs = riskLevel ? `?risk_level=${encodeURIComponent(riskLevel)}` : "";
    return requestJson<{ count: number; clauses: ClauseItem[] }>(`/api/v1/ontology/clauses${qs}`);
  },
  listRegulations: () =>
    requestJson<{
      count: number;
      regulations: RegulationItem[];
      links_count: number;
      links: LegalLinkItem[];
    }>("/api/v1/ontology/regulations"),
  listWikiPages: () =>
    requestJson<{ count: number; pages: WikiPageItem[] }>("/api/v1/wiki/pages"),
  ingestWiki: (payload: {
    doc_id: string;
    title: string;
    content: string;
    doc_type: "contract" | "clause" | "regulation";
  }) =>
    requestJson<{ doc_id: string; doc_type: string; entities: string[]; index_path: string }>(
      "/api/v1/wiki/ingest",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  lintWiki: () =>
    requestJson<WikiLintResponse>("/api/v1/wiki/lint", { method: "POST" }),
  listPendingActions: () =>
    requestJson<{ count: number; actions: LegalActionItem[] }>("/api/v1/actions/pending"),
  approveAction: (payload: {
    action_id: string;
    decision: "approved" | "rejected";
    approver: string;
    notes?: string;
  }) =>
    requestJson<{ action: LegalActionItem; contract_status: string | null }>(
      "/api/v1/actions/approve",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  listAuditLogs: (limit = 100) =>
    requestJson<{ count: number; total: number; logs: AuditLogEntry[] }>(
      `/api/v1/audit/logs?limit=${limit}`
    ),
};
