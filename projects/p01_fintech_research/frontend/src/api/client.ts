export interface DashboardOverview {
  total_issuers: number;
  risk_signals: number;
  wiki_pages_count: number;
  pending_hitl_count: number;
  audit_events_count: number;
  ontology_links_count?: number;
}

export interface WikiPageSummary {
  id: string;
  title: string;
  path: string;
  preview: string;
  type?: string;
  updated_at?: string;
  metrics?: Record<string, number>;
  links?: string[];
}

export interface WikiPagesResponse {
  pages: WikiPageSummary[];
  total: number;
}

export interface WikiIngestPayload {
  doc_id: string;
  title: string;
  content: string;
  entities: Array<{
    id: string;
    name?: string;
    type?: string;
    ticker?: string;
    sector?: string;
    credit_rating?: string;
    period?: string;
    metrics?: Record<string, number>;
    links?: string[];
  }>;
  timestamp?: string;
}

export interface WikiLintResponse {
  status: string;
  total_pages: number;
  orphan_pages: string[];
  broken_links: Array<{ source: string; target: string }>;
  conflicting_metrics: Array<{
    entity_id: string;
    metric: string;
    period: string;
    values: number[];
  }>;
  stale_entries: Array<{ entity_id: string; updated_at: string }>;
}

export interface OntologyNode {
  id: string;
  type?: string;
  name?: string;
  [key: string]: unknown;
}

export interface OntologyEdge {
  source_id: string;
  target_id: string;
  relation: string;
  weight?: number;
}

export interface OntologyGraphResponse {
  root?: string;
  nodes: OntologyNode[];
  edges: OntologyEdge[];
}

export interface ResearchQueryPayload {
  question: string;
  issuer_id?: string;
  actor_role?: string;
  financials?: Record<string, number>;
  period?: string;
}

export interface ComplianceAction {
  action_id: string;
  issuer_id: string;
  action_type: string;
  required_role: string;
  min_severity: string;
  status: string;
  rationale: string;
  approved_by?: string | null;
}

export interface ResearchQueryResponse {
  status: string;
  question?: string;
  reason?: string;
  guardrail: {
    passed: boolean;
    blocked: boolean;
    redacted_text: string;
    findings: string[];
  };
  wiki?: {
    confidence: number;
    citations: Array<{ entity_id: string; snippet?: string }>;
    matched_links: string[];
  };
  ratios?: {
    issuer_id: string;
    period: string;
    ratios: Record<string, number>;
    triggered_risks: Array<{
      category: string;
      severity: string;
      metric: string;
      description: string;
    }>;
  } | null;
  ontology_graph?: OntologyGraphResponse;
  hitl_pending_action?: ComplianceAction | null;
  audit_event_id: string;
}

export interface BatchScreenItem {
  issuer_id: string;
  name?: string;
  ticker?: string;
  sector?: string;
  credit_rating?: string;
  period?: string;
  financials: Record<string, number>;
}

export interface BatchScreenResponse {
  status: string;
  screened_count: number;
  high_risk_count: number;
  results: Array<{
    issuer_id: string;
    name: string;
    period: string;
    risk_level: string;
    ratios: Record<string, number>;
    triggered_risks: Array<{
      category: string;
      severity: string;
      metric: string;
      description: string;
    }>;
    hitl_pending_action: ComplianceAction | null;
  }>;
  audit_event_id: string;
}

export interface PendingActionsResponse {
  actions: ComplianceAction[];
  total: number;
}

export interface ActionApprovePayload {
  action_id: string;
  decision: "approve" | "reject";
  actor_role: string;
  approver: string;
  comment?: string;
}

export interface AuditLogEntry {
  event_id: string;
  timestamp: string;
  event_type: string;
  [key: string]: unknown;
}

export interface AuditLogsResponse {
  logs: AuditLogEntry[];
  total: number;
}

export interface CreditScorePayload {
  issuer_id: string;
  period?: string;
  total_debt: number;
  shareholders_equity: number;
  current_assets: number;
  current_liabilities: number;
  ebit: number;
  interest_expense: number;
  net_income: number;
  wacc?: number;
  terminal_growth?: number;
}

export interface CreditScoreResponse {
  issuer_id: string;
  period: string;
  credit_rating: string;
  composite_score: number;
  implied_spread_bps: number;
  probability_of_default_1y_pct: number;
  altman_z_score: {
    score: number;
    zone: "SAFE" | "GREY" | "DISTRESS";
    components: Record<string, number>;
  };
  piotroski_f_score: {
    score: number;
    max_score: number;
    criteria: Record<string, boolean>;
  };
  sub_scores: {
    leverage_score: number;
    liquidity_score: number;
  };
  ratios: Record<string, number>;
  dcf_valuation: {
    fcf_base: number;
    projected_5y_growth: number;
    wacc: number;
    terminal_growth: number;
    enterprise_value: number;
    implied_equity_value: number;
    sensitivity_matrix: Array<{
      wacc: string;
      equity_values_by_terminal_growth: Record<string, number>;
    }>;
  };
  audit_event_id?: string;
}

export interface ResearchStreamParams {
  issuer_id?: string;
  question: string;
  period?: string;
  total_debt?: number;
  shareholders_equity?: number;
  current_assets?: number;
  current_liabilities?: number;
  ebit?: number;
  interest_expense?: number;
  net_income?: number;
}

export interface ResearchStreamHandlers {
  onStage?: (data: Record<string, unknown>) => void;
  onToken?: (data: { index: number; text: string }) => void;
  onBlocked?: (data: Record<string, unknown>) => void;
  onDone?: (data: Record<string, unknown>) => void;
  onError?: (err: string) => void;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      (data as { detail?: string; error?: string }).detail ||
      (data as { error?: string }).error ||
      `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data as T;
}

export const p01Api = {
  getHealth: () => requestJson<{ status: string; service: string }>("/health"),
  getDashboardOverview: () =>
    requestJson<DashboardOverview>("/api/v1/dashboard/overview"),
  getWikiPages: () => requestJson<WikiPagesResponse>("/api/v1/wiki/pages"),
  ingestWiki: (payload: WikiIngestPayload) =>
    requestJson<Record<string, unknown>>("/api/v1/wiki/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  lintWiki: (staleDays = 90) =>
    requestJson<WikiLintResponse>(`/api/v1/wiki/lint?stale_days=${staleDays}`),
  getOntologyGraph: (issuerId?: string, maxDepth = 2) => {
    const params = new URLSearchParams({ max_depth: String(maxDepth) });
    if (issuerId) params.set("issuer_id", issuerId);
    return requestJson<OntologyGraphResponse>(
      `/api/v1/ontology/graph?${params.toString()}`
    );
  },
  runResearchQuery: (payload: ResearchQueryPayload) =>
    requestJson<ResearchQueryResponse>("/api/v1/research/query", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runBatchScreen: (items: BatchScreenItem[], actorRole = "analyst") =>
    requestJson<BatchScreenResponse>("/api/v1/research/batch-screen", {
      method: "POST",
      body: JSON.stringify({ items, actor_role: actorRole }),
    }),
  scoreCredit: (payload: CreditScorePayload) =>
    requestJson<CreditScoreResponse>("/api/v1/quant/credit-score", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  streamResearchMemo: (
    params: ResearchStreamParams,
    handlers: ResearchStreamHandlers
  ): (() => void) => {
    const qs = new URLSearchParams();
    if (params.issuer_id) qs.set("issuer_id", params.issuer_id);
    qs.set("question", params.question);
    if (params.period) qs.set("period", params.period);
    if (params.total_debt !== undefined) qs.set("total_debt", String(params.total_debt));
    if (params.shareholders_equity !== undefined) {
      qs.set("shareholders_equity", String(params.shareholders_equity));
    }
    if (params.current_assets !== undefined) {
      qs.set("current_assets", String(params.current_assets));
    }
    if (params.current_liabilities !== undefined) {
      qs.set("current_liabilities", String(params.current_liabilities));
    }
    if (params.ebit !== undefined) qs.set("ebit", String(params.ebit));
    if (params.interest_expense !== undefined) {
      qs.set("interest_expense", String(params.interest_expense));
    }
    if (params.net_income !== undefined) qs.set("net_income", String(params.net_income));

    const es = new EventSource(`${API_BASE}/api/v1/research/stream?${qs.toString()}`);

    es.addEventListener("stage", (ev) => {
      try {
        handlers.onStage?.(JSON.parse((ev as MessageEvent).data));
      } catch {
        // ignore malformed stage payload
      }
    });
    es.addEventListener("token", (ev) => {
      try {
        handlers.onToken?.(JSON.parse((ev as MessageEvent).data));
      } catch {
        // ignore malformed token payload
      }
    });
    es.addEventListener("blocked", (ev) => {
      try {
        handlers.onBlocked?.(JSON.parse((ev as MessageEvent).data));
      } finally {
        es.close();
      }
    });
    es.addEventListener("done", (ev) => {
      try {
        handlers.onDone?.(JSON.parse((ev as MessageEvent).data));
      } finally {
        es.close();
      }
    });
    es.onerror = () => {
      handlers.onError?.("SSE stream connection closed");
      es.close();
    };

    return () => es.close();
  },
  getPendingActions: () =>
    requestJson<PendingActionsResponse>("/api/v1/actions/pending"),
  approveAction: (payload: ActionApprovePayload) =>
    requestJson<{ action: ComplianceAction; message: string; audit_event_id: string }>(
      "/api/v1/actions/approve",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  getAuditLogs: (limit = 50) =>
    requestJson<AuditLogsResponse>(`/api/v1/audit/logs?limit=${limit}`),
};
