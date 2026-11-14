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

export interface EOQTradeoffPoint {
  multiplier: number;
  order_qty: number;
  annual_ordering_cost: number;
  annual_holding_cost: number;
  annual_stockout_cost: number;
  total_relevant_cost: number;
}

export interface EOQResultItem {
  sku_id: string;
  sku_name: string;
  category: string;
  supplier_id: string;
  warehouse_id: string;
  current_stock: number;
  daily_demand: number;
  annual_demand: number;
  lead_time_days: number;
  service_level: number;
  z_score: number;
  eoq_raw: number;
  recommended_order_qty: number;
  safety_stock: number;
  reorder_point: number;
  needs_replenishment: boolean;
  orders_per_year: number;
  annual_ordering_cost: number;
  annual_holding_cost: number;
  annual_stockout_cost: number;
  total_relevant_cost: number;
  holding_vs_stockout_ratio: number;
  tradeoff_curve: EOQTradeoffPoint[];
}

export interface EOQOptimizeResponse {
  items: EOQResultItem[];
  total_skus: number;
  skus_needing_replenishment: number;
  total_annual_ordering_cost: number;
  total_annual_holding_cost: number;
  total_annual_stockout_cost: number;
  total_relevant_cost: number;
}

export interface TransferPlanItem {
  transfer_id: string;
  sku_id: string;
  sku_name: string;
  from_warehouse: string;
  to_warehouse: string;
  quantity: number;
  estimated_transfer_cost: number;
  estimated_stockout_savings: number;
  net_benefit: number;
  reason: string;
}

export interface WarehouseSKUCell {
  sku_id: string;
  sku_name: string;
  warehouse_id: string;
  current_qty: number;
  target_qty: number;
  delta: number;
  status: "SURPLUS" | "BALANCED" | "DEFICIT" | string;
}

export interface WarehouseSummary {
  warehouse_id: string;
  name: string;
  region: string;
  capacity_units: number;
  current_utilization_units: number;
  utilization_pct: number;
  total_sku_units: number;
  surplus_units: number;
  deficit_units: number;
}

export interface RebalanceResponse {
  transfers: TransferPlanItem[];
  total_transfers: number;
  total_units_rebalanced: number;
  total_transfer_cost: number;
  total_stockout_savings: number;
  total_net_benefit: number;
  warehouse_summary: WarehouseSummary[];
  matrix: WarehouseSKUCell[];
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
  optimizeEOQ: (payload: {
    sku_id?: string | null;
    ordering_cost?: number;
    holding_cost_rate?: number;
    service_level?: number;
    daily_demand_override?: number | null;
    lead_time_override?: number | null;
    promo_lift_pct?: number;
  }) =>
    request<EOQOptimizeResponse>("/api/v1/supply/eoq-optimize", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rebalanceWarehouses: (payload: {
    sku_ids?: string[] | null;
    stock_matrix?: Record<string, Record<string, number>> | null;
    target_cover_days?: number;
    transfer_cost_per_unit?: number;
    min_transfer_qty?: number;
  }) =>
    request<RebalanceResponse>("/api/v1/supply/rebalance", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
