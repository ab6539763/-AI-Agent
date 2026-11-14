<script setup lang="ts">
import { computed, ref } from "vue";
import type { EquipmentItem, WorkOrderItem, WorkOrderStatus } from "../api/client";

const props = defineProps<{
  workOrders: WorkOrderItem[];
  equipment: EquipmentItem[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  (
    e: "transition",
    payload: {
      work_order_id: string;
      target_status: WorkOrderStatus;
      actor: string;
      assigned_to?: string;
      loto_tag_id?: string;
      notes?: string;
    }
  ): void;
  (
    e: "create",
    payload: {
      equipment_id: string;
      title: string;
      fault_code?: string;
      sop_id?: string;
      priority: string;
      actor: string;
      notes?: string;
    }
  ): void;
}>();

const columns: Array<{ status: WorkOrderStatus; label: string; next: WorkOrderStatus | null; actionLabel: string }> = [
  { status: "OPEN", label: "OPEN · 待派单", next: "ASSIGNED", actionLabel: "派工 (Assign)" },
  { status: "ASSIGNED", label: "ASSIGNED · 已派工", next: "LOCKOUT_TAGOUT", actionLabel: "挂牌上锁 (LOTO)" },
  { status: "LOCKOUT_TAGOUT", label: "LOCKOUT/TAGOUT · 隔离锁定", next: "VERIFIED", actionLabel: "安全核验 (Verify)" },
  { status: "VERIFIED", label: "VERIFIED · 已复核", next: "CLOSED", actionLabel: "闭环归档 (Close)" },
  { status: "CLOSED", label: "CLOSED · 已闭环", next: null, actionLabel: "" },
];

const actorName = ref("safety-lead-01");
const assigneeName = ref("tech-wang");
const lotoTagInput = ref("LOTO-480V-07");

const newEqId = ref("CNC-LINE1-01");
const newTitle = ref("Spindle Thermal & Bearing LOTO Check");
const newPriority = ref("HIGH");

const groupedOrders = computed(() => {
  const map: Record<WorkOrderStatus, WorkOrderItem[]> = {
    OPEN: [],
    ASSIGNED: [],
    LOCKOUT_TAGOUT: [],
    VERIFIED: [],
    CLOSED: [],
  };
  for (const wo of props.workOrders) {
    if (map[wo.status]) {
      map[wo.status].push(wo);
    }
  }
  return map;
});

function advanceWorkOrder(wo: WorkOrderItem, nextStatus: WorkOrderStatus) {
  emit("transition", {
    work_order_id: wo.work_order_id,
    target_status: nextStatus,
    actor: actorName.value.trim() || "scada-operator",
    assigned_to: nextStatus === "ASSIGNED" ? assigneeName.value.trim() || "tech-wang" : undefined,
    loto_tag_id:
      nextStatus === "LOCKOUT_TAGOUT"
        ? lotoTagInput.value.trim() || `LOTO-${wo.equipment_id}`
        : undefined,
    notes: `SCADA Kanban transition -> ${nextStatus}`,
  });
}

function submitNewWorkOrder() {
  if (!newTitle.value.trim()) return;
  emit("create", {
    equipment_id: newEqId.value,
    title: newTitle.value.trim(),
    priority: newPriority.value,
    actor: actorName.value.trim() || "scada-operator",
    notes: "Created from SCADA LOTO Kanban Board.",
  });
}
</script>

<template>
  <section class="loto-board-wrap">
    <div class="board-header">
      <div>
        <div class="board-eyebrow">LOCKOUT / TAGOUT (LOTO) · DETERMINISTIC STATE MACHINE</div>
        <h2>维保工单与 LOTO 挂牌上锁状态看板</h2>
      </div>
      <div class="operator-controls">
        <label>
          <span>操作员</span>
          <input v-model="actorName" />
        </label>
        <label>
          <span>指派技师</span>
          <input v-model="assigneeName" />
        </label>
        <label>
          <span>LOTO 锁具编号</span>
          <input v-model="lotoTagInput" />
        </label>
      </div>
    </div>

    <!-- Quick Create Work Order Bar -->
    <div class="create-bar">
      <select v-model="newEqId">
        <option v-for="eq in equipment" :key="eq.equipment_id" :value="eq.equipment_id">
          {{ eq.equipment_id }}
        </option>
      </select>
      <input v-model="newTitle" class="title-input" placeholder="输入 LOTO 维保工单标题..." />
      <select v-model="newPriority">
        <option value="CRITICAL">CRITICAL</option>
        <option value="HIGH">HIGH</option>
        <option value="MEDIUM">MEDIUM</option>
      </select>
      <button class="btn-create" :disabled="busy" @click="submitNewWorkOrder">
        + 新建 LOTO 工单
      </button>
    </div>

    <!-- 5-Column Kanban -->
    <div class="kanban-grid">
      <div
        v-for="col in columns"
        :key="col.status"
        class="kanban-col"
        :data-col="col.status"
      >
        <header class="col-head">
          <span>{{ col.label }}</span>
          <span class="col-count">{{ groupedOrders[col.status].length }}</span>
        </header>

        <div class="col-body">
          <p v-if="groupedOrders[col.status].length === 0" class="empty-col">暂无工单</p>
          <article
            v-for="wo in groupedOrders[col.status]"
            :key="wo.work_order_id"
            class="wo-card"
          >
            <div class="wo-top">
              <span class="wo-id">{{ wo.work_order_id }}</span>
              <span class="prio-badge" :data-prio="wo.priority">{{ wo.priority }}</span>
            </div>
            <div class="wo-title">{{ wo.title }}</div>
            <div class="wo-meta">
              <span>设备: <code>{{ wo.equipment_id }}</code></span>
              <span v-if="wo.fault_code">故障: <code>{{ wo.fault_code }}</code></span>
              <span v-if="wo.sop_id">SOP: <code>{{ wo.sop_id }}</code></span>
            </div>

            <div v-if="wo.assigned_to || wo.loto_tag_id || wo.verified_by" class="wo-badges">
              <span v-if="wo.assigned_to" class="meta-chip">技师: {{ wo.assigned_to }}</span>
              <span v-if="wo.loto_tag_id" class="loto-chip">🔒 {{ wo.loto_tag_id }}</span>
              <span v-if="wo.verified_by" class="meta-chip">✓ {{ wo.verified_by }}</span>
            </div>

            <div v-if="wo.notes" class="wo-notes">{{ wo.notes }}</div>

            <button
              v-if="col.next"
              class="btn-advance"
              :disabled="busy"
              @click="advanceWorkOrder(wo, col.next)"
            >
              {{ col.actionLabel }} →
            </button>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.loto-board-wrap {
  background: #0b1120;
  border: 1px solid #1f2937;
  border-top: 2px solid #f59e0b;
  border-radius: 10px;
  padding: 1rem 1.15rem;
}

.board-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.85rem;
}

.board-eyebrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  color: #f59e0b;
}

.board-header h2 {
  margin: 0.15rem 0 0;
  font-size: 1.05rem;
  color: #f9fafb;
}

.operator-controls {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.operator-controls label {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.72rem;
  color: #9ca3af;
}

.operator-controls input {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #f9fafb;
  padding: 0.35rem 0.55rem;
  font-size: 0.8rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  width: 135px;
}

.create-bar {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
  margin-bottom: 0.9rem;
  padding: 0.65rem;
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
}

.create-bar select,
.create-bar input {
  background: #0b1120;
  border: 1px solid #374151;
  border-radius: 6px;
  color: #f9fafb;
  padding: 0.42rem 0.6rem;
  font-size: 0.82rem;
}

.title-input {
  flex: 1 1 240px;
}

.btn-create {
  background: rgba(245, 158, 11, 0.16);
  border: 1px solid #f59e0b;
  color: #fbbf24;
  border-radius: 6px;
  padding: 0.42rem 0.85rem;
  font-weight: 700;
  font-size: 0.82rem;
  cursor: pointer;
}

.btn-create:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.28);
}

.kanban-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(210px, 1fr));
  gap: 0.7rem;
  overflow-x: auto;
}

.kanban-col {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  min-height: 320px;
}

.col-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.55rem 0.7rem;
  border-bottom: 1px solid #1f2937;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.73rem;
  font-weight: 700;
  color: #e5e7eb;
}

.kanban-col[data-col="LOCKOUT_TAGOUT"] .col-head {
  border-bottom-color: #f59e0b;
  color: #fbbf24;
  background: rgba(245, 158, 11, 0.08);
}

.kanban-col[data-col="OPEN"] .col-head,
.kanban-col[data-col="ASSIGNED"] .col-head {
  border-bottom-color: #06b6d4;
  color: #22d3ee;
}

.col-count {
  background: #1f2937;
  color: #f9fafb;
  border-radius: 999px;
  padding: 0.08rem 0.45rem;
  font-size: 0.7rem;
}

.col-body {
  padding: 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.empty-col {
  color: #6b7280;
  font-size: 0.78rem;
  text-align: center;
  margin-top: 1.5rem;
}

.wo-card {
  background: #0b1120;
  border: 1px solid #374151;
  border-radius: 7px;
  padding: 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.wo-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.wo-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.76rem;
  font-weight: 700;
  color: #06b6d4;
}

.prio-badge {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.66rem;
  padding: 0.08rem 0.35rem;
  border-radius: 4px;
  background: #1f2937;
  color: #d1d5db;
}

.prio-badge[data-prio="CRITICAL"] {
  background: rgba(239, 68, 68, 0.22);
  color: #fca5a5;
  border: 1px solid #ef4444;
}

.prio-badge[data-prio="HIGH"] {
  background: rgba(245, 158, 11, 0.18);
  color: #fbbf24;
  border: 1px solid #f59e0b;
}

.wo-title {
  font-size: 0.83rem;
  font-weight: 600;
  color: #f9fafb;
  line-height: 1.3;
}

.wo-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  font-size: 0.72rem;
  color: #9ca3af;
}

.wo-meta code {
  color: #e5e7eb;
}

.wo-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.meta-chip {
  background: #1f2937;
  color: #22d3ee;
  border-radius: 4px;
  padding: 0.1rem 0.38rem;
  font-size: 0.68rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.loto-chip {
  background: rgba(245, 158, 11, 0.2);
  border: 1px solid #f59e0b;
  color: #fbbf24;
  border-radius: 4px;
  padding: 0.1rem 0.38rem;
  font-size: 0.68rem;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.wo-notes {
  font-size: 0.72rem;
  color: #9ca3af;
  line-height: 1.35;
}

.btn-advance {
  margin-top: 0.2rem;
  width: 100%;
  background: rgba(6, 182, 212, 0.14);
  border: 1px solid #06b6d4;
  color: #22d3ee;
  border-radius: 5px;
  padding: 0.35rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  cursor: pointer;
}

.btn-advance:hover:not(:disabled) {
  background: rgba(6, 182, 212, 0.26);
}
</style>
