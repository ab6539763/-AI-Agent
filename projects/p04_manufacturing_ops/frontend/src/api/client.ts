export interface TelemetryThreshold {
  metric: string;
  warn: number;
  critical: number;
  unit: string;
  fault_code_on_critical?: string | null;
  fault_code_on_warn?: string | null;
}

export interface EquipmentItem {
  equipment_id: string;
  name: string;
  equipment_type: string;
  line_id: string;
  location: string;
  status: string;
  thresholds: Record<string, TelemetryThreshold>;
  sop_ids: string[];
}

export interface FaultCodeItem {
  code: string;
  title: string;
  equipment_type: string;
  severity: string;
  root_cause: string;
  recommended_sop_id?: string | null;
  requires_shutdown: boolean;
}

export interface MaintenanceSOPItem {
  sop_id: string;
  title: string;
  revision: string;
  latest_revision: string;
  steps: string[];
  safety_precautions: string[];
  estimated_minutes: number;
  target_fault_codes: string[];
}

export interface OpsLinkItem {
  link_id: string;
  source_type: string;
  source_id: string;
  relation: string;
  target_type: string;
  target_id: string;
}

export type WorkOrderStatus =
  | "OPEN"
  | "ASSIGNED"
  | "LOCKOUT_TAGOUT"
  | "VERIFIED"
  | "CLOSED";

export interface WorkOrderHistoryEntry {
  from_status: string | null;
  to_status: string;
  actor: string;
  timestamp: string;
  notes: string;
}

export interface WorkOrderItem {
  work_order_id: string;
  equipment_id: string;
  title: string;
  fault_code?: string | null;
  sop_id?: string | null;
  priority: string;
  status: WorkOrderStatus;
  assigned_to?: string | null;
  loto_tag_id?: string | null;
  verified_by?: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  history: WorkOrderHistoryEntry[];
}

export interface TelemetryMetricStats {
  metric: string;
  latest_value: number;
  rolling_mean: number;
  rolling_std: number;
  z_score: number;
  is_anomaly: boolean;
  sample_count: number;
  history: number[];
}

export interface TelemetryAnomaly {
  equipment_id: string;
  metric: string;
  value: number;
  rolling_mean: number;
  rolling_std: number;
  z_score: number;
  z_threshold: number;
  timestamp: string;
}

export interface TelemetryBatchResponse {
  ingested_count: number;
  anomaly_count: number;
  anomalies: TelemetryAnomaly[];
  results: Array<{
    equipment_id: string;
    timestamp: string;
    metrics: TelemetryMetricStats[];
    anomalies: TelemetryAnomaly[];
    anomaly_detected: boolean;
  }>;
  equipment_snapshots: Record<string, Record<string, TelemetryMetricStats>>;
}

export interface DashboardOverview {
  service: string;
  equipment_count: number;
  fault_codes_count: number;
  sops_count: number;
  wiki_pages_count: number;
  pending_hitl_shutdowns: number;
  audit_logs_count: number;
  equipment_status_breakdown: Record<string, number>;
  equipment: EquipmentItem[];
  fault_codes: FaultCodeItem[];
  sops: MaintenanceSOPItem[];
  links: OpsLinkItem[];
  work_orders?: WorkOrderItem[];
  telemetry_snapshots?: Record<string, Record<string, TelemetryMetricStats>>;
}

export interface SensorAlertItem {
  alert_id: string;
  equipment_id: string;
  sensor_type: string;
  value: number;
  unit: string;
  threshold: number;
  severity: string;
  fault_code?: string | null;
  message: string;
}

export interface DiagnosisResult {
  equipment_id: string;
  equipment_name: string;
  equipment_status: string;
  alerts: SensorAlertItem[];
  fault_codes: FaultCodeItem[];
  sops: MaintenanceSOPItem[];
  links: OpsLinkItem[];
  requires_shutdown: boolean;
  highest_severity: string;
}

export interface OpsActionItem {
  action_id: string;
  action_type: string;
  equipment_id: string;
  fault_code?: string | null;
  sop_id?: string | null;
  status: string;
  requires_hitl: boolean;
  requested_by: string;
  approved_by?: string | null;
  decision_reason?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface IncidentResponse {
  incident_id: string;
  diagnosis: DiagnosisResult;
  wiki_context: Array<Record<string, unknown>>;
  action: OpsActionItem | null;
  hitl_required: boolean;
}

export interface MaintenanceScheduleItem {
  equipment_id: string;
  equipment_name: string;
  line_id: string;
  health_score: number;
  risk_tier: string;
  priority: string;
  recommended_window_hours: number;
  estimated_mtbf_hours: number;
  operating_hours: number;
  triggered_fault_codes: string[];
  recommended_sops: string[];
}

export interface PredictiveMaintenanceResponse {
  generated_at: string;
  equipment_evaluated: number;
  average_health_score: number;
  critical_count: number;
  schedules: MaintenanceScheduleItem[];
}

export interface WikiPageItem {
  id: string;
  title: string;
  entity_type: string;
  path: string;
  preview: string;
  updated_at: string;
  wiki_links: string[];
  content: string;
}

export interface WikiLintReport {
  healthy: boolean;
  total_pages: number;
  unmapped_fault_codes: string[];
  outdated_sops: string[];
  orphan_equipment: string[];
  counts: Record<string, number>;
}

export interface AuditLogEntry {
  audit_id: string;
  timestamp: string;
  event_type: string;
  equipment_id: string;
  actor: string;
  detail: Record<string, unknown>;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const apiClient = {
  getDashboardOverview(): Promise<DashboardOverview> {
    return request<DashboardOverview>("/api/v1/dashboard/overview");
  },

  diagnoseOntology(payload: {
    equipment_id: string;
    readings: Record<string, number>;
    fault_code?: string | null;
  }): Promise<DiagnosisResult> {
    return request<DiagnosisResult>("/api/v1/ontology/diagnose", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  triggerIncident(payload: {
    equipment_id: string;
    sensor_readings: Record<string, number>;
    fault_code?: string | null;
    reporter?: string;
  }): Promise<IncidentResponse> {
    return request<IncidentResponse>("/api/v1/ops/incident", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  runPredictiveMaintenance(
    samples: Array<{
      equipment_id: string;
      readings: Record<string, number>;
      operating_hours: number;
    }> = []
  ): Promise<PredictiveMaintenanceResponse> {
    return request<PredictiveMaintenanceResponse>("/api/v1/ops/predictive-maintenance", {
      method: "POST",
      body: JSON.stringify({ samples }),
    });
  },

  getWikiPages(): Promise<{ pages: WikiPageItem[]; total: number }> {
    return request<{ pages: WikiPageItem[]; total: number }>("/api/v1/wiki/pages");
  },

  ingestWikiPage(payload: {
    entity_id: string;
    entity_type: string;
    title: string;
    content: string;
    links: string[];
  }): Promise<{ status: string; entity_id: string; path: string }> {
    return request("/api/v1/wiki/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  lintWiki(): Promise<WikiLintReport> {
    return request<WikiLintReport>("/api/v1/wiki/lint", { method: "POST" });
  },

  getPendingActions(): Promise<{ actions: OpsActionItem[]; total: number }> {
    return request<{ actions: OpsActionItem[]; total: number }>("/api/v1/actions/pending");
  },

  approveAction(payload: {
    action_id: string;
    approved: boolean;
    safety_officer: string;
    reason: string;
  }): Promise<{ action: OpsActionItem; equipment_status: string | null; audit_trail_count: number }> {
    return request("/api/v1/actions/approve", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getAuditLogs(): Promise<{ logs: AuditLogEntry[]; total: number }> {
    return request<{ logs: AuditLogEntry[]; total: number }>("/api/v1/audit/logs");
  },

  ingestTelemetryBatch(
    samples: Array<{
      equipment_id: string;
      readings: Record<string, number>;
      timestamp?: string;
    }>
  ): Promise<TelemetryBatchResponse> {
    return request<TelemetryBatchResponse>("/api/v1/telemetry/ingest-batch", {
      method: "POST",
      body: JSON.stringify({ samples }),
    });
  },

  listWorkOrders(): Promise<{ work_orders: WorkOrderItem[]; total: number }> {
    return request<{ work_orders: WorkOrderItem[]; total: number }>("/api/v1/workorders");
  },

  createWorkOrder(payload: {
    equipment_id: string;
    title: string;
    fault_code?: string | null;
    sop_id?: string | null;
    priority?: string;
    actor?: string;
    notes?: string;
  }): Promise<{ work_order: WorkOrderItem }> {
    return request<{ work_order: WorkOrderItem }>("/api/v1/workorders", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  transitionWorkOrder(payload: {
    work_order_id: string;
    target_status: WorkOrderStatus;
    actor?: string;
    assigned_to?: string;
    loto_tag_id?: string;
    notes?: string;
  }): Promise<{ work_order: WorkOrderItem; audit_trail_count: number }> {
    return request<{ work_order: WorkOrderItem; audit_trail_count: number }>(
      "/api/v1/workorders/transition",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
  },
};
