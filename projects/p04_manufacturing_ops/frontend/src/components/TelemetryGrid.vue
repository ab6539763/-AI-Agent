<script setup lang="ts">
import type { EquipmentItem, TelemetryMetricStats } from "../api/client";

const props = defineProps<{
  equipment: EquipmentItem[];
  selectedEquipmentId: string;
  snapshots: Record<string, Record<string, TelemetryMetricStats>>;
  streaming?: boolean;
}>();

const emit = defineEmits<{
  (e: "select", equipmentId: string): void;
  (e: "stream-nominal"): void;
  (e: "inject-spike"): void;
}>();

function ledClass(status: string): string {
  const s = status.toUpperCase();
  if (s === "OPERATIONAL") return "led led-ok";
  if (s === "DEGRADED") return "led led-warn";
  return "led led-crit";
}

function cardClass(eq: EquipmentItem): Record<string, boolean> {
  const snap = props.snapshots[eq.equipment_id] ?? {};
  const hasAnomaly = Object.values(snap).some((m) => m.is_anomaly);
  return {
    "twin-card": true,
    "twin-selected": eq.equipment_id === props.selectedEquipmentId,
    "twin-anomaly": hasAnomaly || eq.status === "FAULTED" || eq.status === "SHUTDOWN",
  };
}

function getMetricStat(equipmentId: string, metric: string): TelemetryMetricStats | null {
  return props.snapshots[equipmentId]?.[metric] ?? null;
}

function defaultNominalValue(metric: string): number {
  if (metric === "temperature_c") return 62.4;
  if (metric === "vibration_mms") return 2.1;
  if (metric === "pressure_bar") return 142.0;
  return 0;
}

function gaugePercent(value: number, critical: number): number {
  const max = critical * 1.2;
  return Math.max(4, Math.min(100, Math.round((value / max) * 100)));
}

function gaugeStrokeColor(value: number, warn: number, critical: number, isAnomaly: boolean): string {
  if (isAnomaly || value >= critical) return "#ef4444";
  if (value >= warn) return "#f59e0b";
  return "#06b6d4";
}

function sparklinePoints(history: number[]): string {
  if (!history || history.length < 2) return "0,18 100,18";
  const min = Math.min(...history);
  const max = Math.max(...history);
  const span = max - min || 1;
  return history
    .map((v, idx) => {
      const x = (idx / (history.length - 1)) * 100;
      const y = 22 - ((v - min) / span) * 18;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function formatMetricLabel(metric: string): string {
  if (metric === "temperature_c") return "SPINDLE / MOLD TEMP";
  if (metric === "vibration_mms") return "VIBRATION RMS";
  if (metric === "pressure_bar") return "HYDRAULIC PRESSURE";
  return metric.toUpperCase();
}
</script>

<template>
  <section class="scada-grid-wrap">
    <div class="scada-section-head">
      <div>
        <div class="scada-eyebrow">DIGITAL TWIN TELEMETRY MATRIX · SLIDING-WINDOW Z-SCORE</div>
        <h2>SCADA 产线数字孪生实时监控矩阵</h2>
      </div>
      <div class="scada-btn-group">
        <button class="scada-btn scada-btn-cyan" :disabled="streaming" @click="emit('stream-nominal')">
          {{ streaming ? "采集写入中..." : "采集稳态批次 (6x RingBuffer)" }}
        </button>
        <button class="scada-btn scada-btn-amber" :disabled="streaming" @click="emit('inject-spike')">
          注入 Z-Score 异常脉冲
        </button>
      </div>
    </div>

    <div class="twin-grid">
      <article
        v-for="eq in equipment"
        :key="eq.equipment_id"
        :class="cardClass(eq)"
        @click="emit('select', eq.equipment_id)"
      >
        <header class="twin-head">
          <div class="twin-id-row">
            <span :class="ledClass(eq.status)"></span>
            <div>
              <div class="twin-id">{{ eq.equipment_id }}</div>
              <div class="twin-name">{{ eq.name }}</div>
            </div>
          </div>
          <div class="twin-meta">
            <span class="scada-tag">{{ eq.line_id }}</span>
            <span class="scada-tag">{{ eq.location }}</span>
            <span class="status-pill" :data-status="eq.status">{{ eq.status }}</span>
          </div>
        </header>

        <div class="gauge-grid">
          <div
            v-for="(thresh, metric) in eq.thresholds"
            :key="metric"
            class="gauge-cell"
            :class="{ 'gauge-anomaly': getMetricStat(eq.equipment_id, String(metric))?.is_anomaly }"
          >
            <div class="gauge-label-row">
              <span class="gauge-label">{{ formatMetricLabel(String(metric)) }}</span>
              <span
                v-if="getMetricStat(eq.equipment_id, String(metric))"
                class="z-badge"
                :class="{
                  'z-crit': getMetricStat(eq.equipment_id, String(metric))?.is_anomaly,
                }"
              >
                Z={{ (getMetricStat(eq.equipment_id, String(metric))?.z_score ?? 0).toFixed(2) }}
              </span>
              <span v-else class="z-badge">IDLE</span>
            </div>

            <div class="gauge-body">
              <!-- Semicircular Industrial Arc Gauge -->
              <svg class="arc-svg" viewBox="0 0 120 70">
                <path
                  d="M 14 60 A 46 46 0 0 1 106 60"
                  fill="none"
                  stroke="#1f2937"
                  stroke-width="10"
                  stroke-linecap="round"
                />
                <path
                  d="M 14 60 A 46 46 0 0 1 106 60"
                  fill="none"
                  :stroke="
                    gaugeStrokeColor(
                      getMetricStat(eq.equipment_id, String(metric))?.latest_value ??
                        defaultNominalValue(String(metric)),
                      thresh.warn,
                      thresh.critical,
                      Boolean(getMetricStat(eq.equipment_id, String(metric))?.is_anomaly)
                    )
                  "
                  stroke-width="10"
                  stroke-linecap="round"
                  :stroke-dasharray="`${
                    (gaugePercent(
                      getMetricStat(eq.equipment_id, String(metric))?.latest_value ??
                        defaultNominalValue(String(metric)),
                      thresh.critical
                    ) /
                      100) *
                    144.5
                  } 144.5`"
                />
                <text x="60" y="54" text-anchor="middle" class="arc-val">
                  {{
                    (
                      getMetricStat(eq.equipment_id, String(metric))?.latest_value ??
                      defaultNominalValue(String(metric))
                    ).toFixed(1)
                  }}
                </text>
                <text x="60" y="66" text-anchor="middle" class="arc-unit">
                  {{ thresh.unit }} (WARN {{ thresh.warn }} / CRIT {{ thresh.critical }})
                </text>
              </svg>
            </div>

            <div v-if="getMetricStat(eq.equipment_id, String(metric))" class="spark-row">
              <svg class="spark-svg" viewBox="0 0 100 24" preserveAspectRatio="none">
                <polyline
                  fill="none"
                  :stroke="
                    getMetricStat(eq.equipment_id, String(metric))?.is_anomaly
                      ? '#ef4444'
                      : '#06b6d4'
                  "
                  stroke-width="1.8"
                  :points="
                    sparklinePoints(getMetricStat(eq.equipment_id, String(metric))?.history ?? [])
                  "
                />
              </svg>
              <span class="spark-meta">
                μ={{ getMetricStat(eq.equipment_id, String(metric))?.rolling_mean.toFixed(1) }} · n={{
                  getMetricStat(eq.equipment_id, String(metric))?.sample_count
                }}
              </span>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.scada-grid-wrap {
  background: #0b1120;
  border: 1px solid #1f2937;
  border-top: 2px solid #06b6d4;
  border-radius: 10px;
  padding: 1rem 1.15rem;
  margin-bottom: 1rem;
  box-shadow: 0 0 24px rgba(6, 182, 212, 0.08);
}

.scada-section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.9rem;
}

.scada-eyebrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  color: #06b6d4;
}

.scada-section-head h2 {
  margin: 0.15rem 0 0;
  font-size: 1.05rem;
  color: #f9fafb;
}

.scada-btn-group {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.scada-btn {
  border-radius: 6px;
  padding: 0.48rem 0.85rem;
  font-size: 0.82rem;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.scada-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.scada-btn-cyan {
  background: rgba(6, 182, 212, 0.14);
  color: #22d3ee;
  border-color: #06b6d4;
}

.scada-btn-cyan:hover:not(:disabled) {
  background: rgba(6, 182, 212, 0.25);
}

.scada-btn-amber {
  background: rgba(245, 158, 11, 0.14);
  color: #fbbf24;
  border-color: #f59e0b;
}

.scada-btn-amber:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.26);
}

.twin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 0.9rem;
}

.twin-card {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 8px;
  padding: 0.9rem;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.twin-card:hover {
  border-color: #06b6d4;
}

.twin-selected {
  border-color: #06b6d4;
  box-shadow: 0 0 0 1px rgba(6, 182, 212, 0.5), 0 0 18px rgba(6, 182, 212, 0.15);
}

.twin-anomaly {
  border-color: #ef4444;
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.45), 0 0 20px rgba(239, 68, 68, 0.18);
}

.twin-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.6rem;
  margin-bottom: 0.8rem;
  padding-bottom: 0.65rem;
  border-bottom: 1px solid #1f2937;
}

.twin-id-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.led {
  width: 11px;
  height: 11px;
  border-radius: 999px;
  flex-shrink: 0;
}

.led-ok {
  background: #22d3ee;
  box-shadow: 0 0 10px #06b6d4, 0 0 4px #22d3ee;
}

.led-warn {
  background: #f59e0b;
  box-shadow: 0 0 10px #f59e0b, 0 0 4px #fbbf24;
}

.led-crit {
  background: #ef4444;
  box-shadow: 0 0 12px #ef4444, 0 0 6px #f87171;
  animation: pulse-led 1.2s infinite;
}

@keyframes pulse-led {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.twin-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 700;
  font-size: 0.96rem;
  color: #f9fafb;
}

.twin-name {
  font-size: 0.78rem;
  color: #9ca3af;
}

.twin-meta {
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.scada-tag {
  background: #1f2937;
  color: #9ca3af;
  border: 1px solid #374151;
  border-radius: 4px;
  padding: 0.12rem 0.42rem;
  font-size: 0.7rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.status-pill {
  border-radius: 4px;
  padding: 0.12rem 0.48rem;
  font-size: 0.7rem;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: rgba(6, 182, 212, 0.15);
  color: #22d3ee;
  border: 1px solid rgba(6, 182, 212, 0.5);
}

.status-pill[data-status="DEGRADED"] {
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
  border-color: rgba(245, 158, 11, 0.5);
}

.status-pill[data-status="FAULTED"],
.status-pill[data-status="SHUTDOWN"] {
  background: rgba(239, 68, 68, 0.18);
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.6);
}

.gauge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 0.65rem;
}

.gauge-cell {
  background: #0b1120;
  border: 1px solid #1f2937;
  border-radius: 6px;
  padding: 0.55rem 0.65rem;
}

.gauge-anomaly {
  border-color: #ef4444;
  background: rgba(127, 29, 29, 0.16);
}

.gauge-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.25rem;
}

.gauge-label {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.z-badge {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.68rem;
  padding: 0.08rem 0.35rem;
  border-radius: 4px;
  background: #1f2937;
  color: #22d3ee;
}

.z-crit {
  background: rgba(239, 68, 68, 0.22);
  color: #fca5a5;
  border: 1px solid #ef4444;
}

.arc-svg {
  width: 100%;
  height: 74px;
  display: block;
}

.arc-val {
  fill: #f9fafb;
  font-size: 16px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.arc-unit {
  fill: #9ca3af;
  font-size: 7.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.spark-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.25rem;
  padding-top: 0.25rem;
  border-top: 1px dashed #1f2937;
}

.spark-svg {
  width: 72px;
  height: 22px;
}

.spark-meta {
  font-size: 0.68rem;
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
