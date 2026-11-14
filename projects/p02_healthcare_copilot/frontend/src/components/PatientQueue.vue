<script setup lang="ts">
import type { ESITriageEntry } from "../api/client";

defineProps<{
  entries: ESITriageEntry[];
  selectedCaseId: string | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: "select", entry: ESITriageEntry): void;
  (e: "refresh"): void;
}>();

function esiClass(level: number): string {
  return `esi-${level}`;
}

function esiShort(level: number): string {
  const labels: Record<number, string> = {
    1: "ESI 1 · RESUS",
    2: "ESI 2 · EMERG",
    3: "ESI 3 · URGENT",
    4: "ESI 4 · LESS",
    5: "ESI 5 · ROUTINE",
  };
  return labels[level] ?? `ESI ${level}`;
}
</script>

<template>
  <aside class="emr-queue-pane">
    <div class="pane-header">
      <div>
        <span class="pane-kicker">ED TRIAGE BOARD</span>
        <h2>ESI 1–5 Priority Queue</h2>
      </div>
      <button
        type="button"
        class="btn-icon"
        :disabled="loading"
        title="Refresh ESI Queue"
        @click="emit('refresh')"
      >
        ↻
      </button>
    </div>

    <div class="esi-legend">
      <span class="legend-dot esi-1">1 Resus</span>
      <span class="legend-dot esi-2">2 Emerg</span>
      <span class="legend-dot esi-3">3 Urgent</span>
      <span class="legend-dot esi-4">4 Less</span>
      <span class="legend-dot esi-5">5 Routine</span>
    </div>

    <div v-if="entries.length === 0" class="empty-queue">
      No patients in ESI triage queue. Submit an encounter to triage.
    </div>

    <div v-else class="queue-list">
      <button
        v-for="entry in entries"
        :key="entry.case_id"
        type="button"
        class="queue-card"
        :class="{
          active: entry.case_id === selectedCaseId,
          blocked: entry.guardrail_blocked,
        }"
        @click="emit('select', entry)"
      >
        <div class="queue-card-top">
          <span class="esi-badge" :class="esiClass(entry.esi_level)">
            {{ esiShort(entry.esi_level) }}
          </span>
          <span class="patient-ref">{{ entry.patient_ref }}</span>
        </div>

        <div class="queue-patient-meta">
          <strong>{{ entry.case_id }}</strong>
          <span>{{ entry.age }}y / {{ entry.sex }}</span>
          <span class="status-pill" :class="`status-${entry.status}`">
            {{ entry.status }}
          </span>
        </div>

        <p class="queue-complaint">{{ entry.chief_complaint }}</p>

        <div class="vitals-strip">
          <span v-if="entry.vital_signs.spo2 !== undefined" :class="{ 'vital-crit': entry.vital_signs.spo2 < 90 }">
            SpO2 {{ entry.vital_signs.spo2 }}%
          </span>
          <span v-if="entry.vital_signs.hr !== undefined" :class="{ 'vital-crit': entry.vital_signs.hr > 130 || entry.vital_signs.hr < 40 }">
            HR {{ entry.vital_signs.hr }}
          </span>
          <span v-if="entry.vital_signs.sbp !== undefined" :class="{ 'vital-crit': entry.vital_signs.sbp < 90 }">
            SBP {{ entry.vital_signs.sbp }}
          </span>
        </div>

        <div v-if="entry.red_flags.length > 0 || entry.guardrail_blocked" class="queue-flags">
          <span v-if="entry.red_flags.length > 0" class="flag-chip">
            ⚑ {{ entry.red_flags.length }} Red Flag(s)
          </span>
          <span v-if="entry.guardrail_blocked" class="block-chip">
            ⛔ Guardrail Blocked
          </span>
        </div>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.emr-queue-pane {
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #d8e5f0;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 2px 8px rgba(15, 45, 75, 0.04);
  min-height: 0;
}

.pane-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.pane-kicker {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0284c7;
}

.pane-header h2 {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.btn-icon {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  color: #0284c7;
  border-radius: 8px;
  width: 30px;
  height: 30px;
  font-size: 15px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon:hover:not(:disabled) {
  background: #e0f2fe;
}

.esi-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e6eff6;
}

.legend-dot {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  max-height: calc(100vh - 230px);
}

.queue-card {
  text-align: left;
  width: 100%;
  background: #f8fbfe;
  border: 1px solid #dce8f2;
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.queue-card:hover {
  border-color: #38bdf8;
  background: #f0f9ff;
}

.queue-card.active {
  border-color: #0284c7;
  background: #eff8ff;
  box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15);
}

.queue-card.blocked {
  border-left: 4px solid #dc2626;
}

.queue-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.esi-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.03em;
}

.esi-1 {
  background: #fee2e2;
  color: #b91c1c;
  border: 1px solid #fca5a5;
}
.esi-2 {
  background: #ffedd5;
  color: #c2410c;
  border: 1px solid #fdba74;
}
.esi-3 {
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fcd34d;
}
.esi-4 {
  background: #e0f2fe;
  color: #0369a1;
  border: 1px solid #7dd3fc;
}
.esi-5 {
  background: #dcfce7;
  color: #15803d;
  border: 1px solid #86efac;
}

.patient-ref {
  font-size: 11px;
  font-weight: 700;
  color: #475569;
}

.queue-patient-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #334155;
  margin-bottom: 4px;
}

.status-pill {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  background: #e2e8f0;
  color: #334155;
}

.status-approved {
  background: #dcfce7;
  color: #166534;
}
.status-blocked,
.status-rejected {
  background: #fee2e2;
  color: #991b1b;
}
.status-pending_review {
  background: #fef3c7;
  color: #92400e;
}

.queue-complaint {
  margin: 4px 0 6px;
  font-size: 12px;
  line-height: 1.35;
  color: #1e293b;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.vitals-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: #475569;
}

.vitals-strip span {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 1px 5px;
  border-radius: 4px;
}

.vitals-strip span.vital-crit {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #b91c1c;
  font-weight: 700;
}

.queue-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 6px;
}

.flag-chip {
  font-size: 10px;
  font-weight: 700;
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
  padding: 1px 6px;
  border-radius: 4px;
}

.block-chip {
  font-size: 10px;
  font-weight: 700;
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
  padding: 1px 6px;
  border-radius: 4px;
}

.empty-queue {
  font-size: 12px;
  color: #64748b;
  padding: 20px 8px;
  text-align: center;
}
</style>
