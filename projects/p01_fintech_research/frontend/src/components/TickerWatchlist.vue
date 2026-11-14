<script setup lang="ts">
import { computed, ref } from "vue";

export interface WatchlistIssuer {
  issuer_id: string;
  ticker: string;
  name: string;
  sector: string;
  credit_rating: string;
  risk_level: string;
  z_score?: number;
  composite_score?: number;
  financials?: Record<string, number>;
}

const props = defineProps<{
  issuers: WatchlistIssuer[];
  selectedIssuerId: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: "select-issuer", issuer: WatchlistIssuer): void;
  (e: "run-batch-screen"): void;
}>();

const searchTerm = ref("");

const filteredIssuers = computed(() => {
  const q = searchTerm.value.trim().toLowerCase();
  if (!q) return props.issuers;
  return props.issuers.filter(
    (item) =>
      item.ticker.toLowerCase().includes(q) ||
      item.name.toLowerCase().includes(q) ||
      item.sector.toLowerCase().includes(q) ||
      item.issuer_id.toLowerCase().includes(q)
  );
});

function riskBadgeClass(level: string): string {
  const norm = level.toUpperCase();
  if (norm === "CRITICAL" || norm === "DISTRESS") return "badge-critical";
  if (norm === "HIGH" || norm === "GREY") return "badge-high";
  return "badge-safe";
}
</script>

<template>
  <aside class="terminal-panel watchlist-panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <span class="panel-dot"></span>
        <h2>ISSUER WATCHLIST</h2>
      </div>
      <span class="count-pill">{{ filteredIssuers.length }}</span>
    </div>

    <div class="watchlist-controls">
      <input
        v-model="searchTerm"
        type="text"
        class="terminal-input"
        placeholder="Filter ticker, issuer, sector..."
      />
      <button
        class="btn-amber-outline"
        :disabled="loading"
        @click="emit('run-batch-screen')"
      >
        BATCH SCREEN
      </button>
    </div>

    <div class="watchlist-table-head">
      <span>TICKER / ISSUER</span>
      <span>RTG</span>
      <span>RISK</span>
    </div>

    <div class="watchlist-rows">
      <button
        v-for="item in filteredIssuers"
        :key="item.issuer_id"
        type="button"
        class="watchlist-row"
        :class="{ active: item.issuer_id === selectedIssuerId }"
        @click="emit('select-issuer', item)"
      >
        <div class="row-main">
          <div class="row-ticker">
            <span class="ticker-code">{{ item.ticker }}</span>
            <span class="sector-tag">{{ item.sector }}</span>
          </div>
          <div class="row-name">{{ item.name }}</div>
          <div v-if="item.z_score !== undefined || item.composite_score !== undefined" class="row-quant">
            <span v-if="item.z_score !== undefined">Z: {{ item.z_score.toFixed(2) }}</span>
            <span v-if="item.composite_score !== undefined">SCR: {{ item.composite_score.toFixed(1) }}</span>
          </div>
        </div>

        <span class="rating-chip">{{ item.credit_rating }}</span>
        <span class="risk-badge" :class="riskBadgeClass(item.risk_level)">
          {{ item.risk_level }}
        </span>
      </button>

      <div v-if="filteredIssuers.length === 0" class="empty-state">
        No matching issuers in watchlist.
      </div>
    </div>
  </aside>
</template>

<style scoped>
.watchlist-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.watchlist-controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #1e293b;
}

.watchlist-table-head {
  display: grid;
  grid-template-columns: 1fr 48px 74px;
  gap: 6px;
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #64748b;
  border-bottom: 1px solid #1e293b;
  background: #070b12;
}

.watchlist-rows {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.watchlist-row {
  display: grid;
  grid-template-columns: 1fr 48px 74px;
  align-items: center;
  gap: 6px;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-bottom: 1px solid #131c2e;
  color: #e2e8f0;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.watchlist-row:hover {
  background: #11192a;
}

.watchlist-row.active {
  background: rgba(245, 158, 11, 0.09);
  border-left: 3px solid #f59e0b;
  padding-left: 9px;
}

.row-main {
  min-width: 0;
}

.row-ticker {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ticker-code {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-weight: 700;
  font-size: 12px;
  color: #f59e0b;
}

.sector-tag {
  font-size: 10px;
  color: #94a3b8;
  background: #172033;
  padding: 1px 5px;
  border-radius: 3px;
}

.row-name {
  font-size: 12px;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.row-quant {
  display: flex;
  gap: 8px;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #64748b;
  margin-top: 3px;
}

.rating-chip {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  color: #f8fafc;
  background: #1e293b;
  border: 1px solid #334155;
  padding: 2px 4px;
  border-radius: 3px;
}

.risk-badge {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
  text-align: center;
  padding: 2px 5px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}

.badge-critical {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.45);
}

.badge-high {
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.45);
}

.badge-safe {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.4);
}
</style>
