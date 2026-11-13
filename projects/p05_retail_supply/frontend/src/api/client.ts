export interface DashboardOverview {
  total_skus: number;
  stockout_alerts: number;
  critical_alerts: number;
  warehouses: number;
  suppliers: number;
  wiki_pages: number;
  pending_hitl_pos: number;
  executed_actions: number;
  blocked_actions: number;
  audit_logs: number;
  total_inventory_value: number;
}

export interface SafetyCheckItem {
  sku_id: string;
  sku_name: string;
  warehouse_id: string;
  supplier_id: string;
  current_stock: number;
  safety_stock: number;
  reorder_point: number;
  days_of_supply: number;
  lead_time_days: number;
  lead_time_breach: boolean;
  below_safety_stock: boolean;
  risk_level: "CRITICAL" | "WARNING" | "HEALTHY" | string;
  recommended_order_qty: number;
  message: string;
}

export interface SKUItem {
  sku_id: string;
  name: string;
  category: string;
  unit_cost: number;
  list_price: number;
  current_stock: number;
  safety_stock: number;
  reorder_point: number;
  warehouse_id: string;
  supplier_id: string;
  min_margin_pct: number;
  promo_discount_pct: number;
  status: string;
}

export interface WarehouseItem {
  warehouse_id: string;
  name: string;
  region: string;
  capacity_units: number;
  current_utilization_units: number;
  is_cold_chain: boolean;
}

export interface SupplierItem {
  supplier_id: string;
  name: string;
  lead_time_days: number;
  moq: number;
  reliability_score: number;
  on_time_rate: number;
}

export interface InventoryResponse {
  items: SafetyCheckItem[];
  total: number;
  skus?: SKUItem[];
  warehouses?: WarehouseItem[];
  suppliers?: SupplierItem[];
}

export interface MarginSimResultItem {
  sku_id: string;
  sku_name: string;
  category: string;
  unit_cost: number;
  list_price: number;
  promo_discount_pct: number;
  effective_price: number;
  gross_margin_pct: number;
  min_margin_pct: number;
  guardrail_passed: boolean;
  reason: string;
  projected_units: number;
  projected_revenue: number;
  projected_cost: number;
  projected_profit: number;
}

export interface MarginSimulateResponse {
  total_skus_simulated: number;
  guardrail_passed_count: number;
  guardrail_blocked_count: number;
  all_passed: boolean;
  total_projected_revenue: number;
  total_projected_cost: number;
  total_projected_profit: number;
  blended_margin_pct: number;
  results: MarginSimResultItem[];
}

export interface WikiPageItem {
  id: string;
  title: string;
  entity_type: string;
  path: string;
  preview: string;
  content: string;
}

export interface SupplyActionItem {
  action_id: string;
  action_type: string;
  sku_id: string;
  quantity: number;
  proposed_price: number | null;
  estimated_cost: number;
  requires_hitl: boolean;
  status: string;
  reason: string;
  approved_by: string | null;
  created_at: string;
}

export interface AuditLogItem {
  audit_id: string;
  timestamp: string;
  event: string;
  sku_id: string;
  actor: string;
  details: Record<string, unknown>;
}

const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }
  return res.json() as Promise<T>;
}

export const apiClient = {
  getOverview: () => request<DashboardOverview>("/api/v1/dashboard/overview"),
  getInventory: () => request<InventoryResponse>("/api/v1/ontology/inventory"),
  planReplenishment: (payload: {
    sku_id: string;
    requested_qty?: number | null;
    proposed_price?: number | null;
    actor?: string;
  }) =>
    request<{ action: SupplyActionItem; margin_guardrail: Record<string, unknown> }>(
      "/api/v1/supply/replenish",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
  simulateMargin: (payload: {
    items?: Array<{
      sku_id: string;
      promo_discount_pct?: number;
      proposed_price?: number | null;
      projected_units?: number | null;
    }>;
    global_discount_pct?: number | null;
  }) =>
    request<MarginSimulateResponse>("/api/v1/supply/margin-simulate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getWikiPages: () =>
    request<{ items: WikiPageItem[]; total: number }>("/api/v1/wiki/pages"),
  queryWiki: (q: string) =>
    request<{ question: string; matches: Array<Record<string, unknown>>; answer: string }>(
      `/api/v1/wiki/query?q=${encodeURIComponent(q)}`
    ),
  lintWiki: () =>
    request<{
      status: string;
      total_issues: number;
      stockout_risks: Array<Record<string, unknown>>;
      conflicting_promo_rules: Array<Record<string, unknown>>;
      orphan_skus: Array<Record<string, unknown>>;
      broken_links: Array<Record<string, unknown>>;
    }>("/api/v1/wiki/lint"),
  ingestWiki: (payload: {
    doc_id: string;
    title: string;
    content: string;
    entity_id?: string;
    entity_type?: string;
  }) =>
    request<Record<string, unknown>>("/api/v1/wiki/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getActions: (includeAll = true) =>
    request<{ items: SupplyActionItem[]; total: number }>(
      `/api/v1/actions/pending?include_all=${includeAll}`
    ),
  approveAction: (payload: {
    action_id: string;
    approved: boolean;
    approver: string;
    comment?: string;
  }) =>
    request<{ action: SupplyActionItem }>("/api/v1/actions/approve", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAuditLogs: () =>
    request<{ items: AuditLogItem[]; total: number }>("/api/v1/audit/logs"),
};
