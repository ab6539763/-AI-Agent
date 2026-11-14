<script setup lang="ts">
import { computed } from 'vue'
import type {
  BlastRadiusResponse,
  SBOMScanResponse,
  ServiceSummary,
} from '../api/client'

const props = defineProps<{
  services: ServiceSummary[]
  selectedServiceId: string
  blastRadius: BlastRadiusResponse | null
  sbomScan: SBOMScanResponse | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'select-service', serviceId: string): void
  (e: 'run-sbom-scan', serviceId: string): void
}>()

const heatmapCells = computed(() => {
  const counts = props.sbomScan?.severity_counts ?? {
    CRITICAL: 0,
    HIGH: 0,
    MEDIUM: 0,
    LOW: 0,
  }
  return [
    { level: 'CRITICAL', range: '9.0 - 10.0', count: counts.CRITICAL, tone: 'crit' },
    { level: 'HIGH', range: '7.0 - 8.9', count: counts.HIGH, tone: 'high' },
    { level: 'MEDIUM', range: '4.0 - 6.9', count: counts.MEDIUM, tone: 'med' },
    { level: 'LOW', range: '0.1 - 3.9', count: counts.LOW, tone: 'low' },
  ]
})

function onServiceChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('select-service', target.value)
}
</script>

<template>
  <section class="war-panel">
    <div class="panel-header">
      <div>
        <div class="panel-kicker">TOPOLOGY &amp; CYCLONEDX SBOM TELEMETRY</div>
        <h2>Service Blast-Radius &amp; CVSS Severity Heatmap</h2>
      </div>
      <div class="controls">
        <select
          :value="selectedServiceId"
          class="term-select"
          @change="onServiceChange"
        >
          <option v-for="svc in services" :key="svc.service_id" :value="svc.service_id">
            {{ svc.service_id }} [{{ svc.tier }}] — {{ svc.name }}
          </option>
        </select>
        <button
          class="term-btn"
          :disabled="loading"
          @click="emit('select-service', selectedServiceId)"
        >
          REFRESH GRAPH
        </button>
        <button
          class="term-btn primary"
          :disabled="loading"
          @click="emit('run-sbom-scan', selectedServiceId)"
        >
          SCAN CYCLONEDX SBOM
        </button>
      </div>
    </div>

    <!-- CVSS Severity Heatmap -->
    <div class="heatmap-strip">
      <div
        v-for="cell in heatmapCells"
        :key="cell.level"
        class="heat-cell"
        :class="[cell.tone, { active: cell.count > 0 }]"
      >
        <div class="heat-top">
          <span class="heat-level">{{ cell.level }}</span>
          <span class="heat-range">CVSS {{ cell.range }}</span>
        </div>
        <div class="heat-count">{{ cell.count }}</div>
      </div>
    </div>

    <div v-if="blastRadius" class="split-grid">
      <!-- Left: Service Topological Blast Radius -->
      <div class="sub-box">
        <div class="sub-title">
          <span>SERVICE DEPENDENCY BLAST RADIUS</span>
          <span
            class="gate-pill"
            :class="blastRadius.cvss_gate.blocked ? 'danger' : 'ok'"
          >
            {{ blastRadius.cvss_gate.gate_decision }} (MAX CVSS {{ blastRadius.cvss_gate.max_cvss }})
          </span>
        </div>

        <div class="root-banner">
          <div>
            <span class="tier-chip">{{ blastRadius.root_tier }}</span>
            <strong class="root-name">{{ blastRadius.root_service_id }}</strong>
          </div>
          <div class="impact-metric">
            UPSTREAM IMPACTED: <strong>{{ blastRadius.total_impacted_services }}</strong>
          </div>
        </div>

        <div class="tier0-row">
          <span class="muted-label">TIER-0 EXPOSURE:</span>
          <span
            v-for="t0 in blastRadius.tier0_impacted"
            :key="t0"
            class="tag-danger"
          >
            {{ t0 }}
          </span>
          <span v-if="blastRadius.tier0_impacted.length === 0" class="tag-ok">NONE</span>
        </div>

        <ul class="term-list">
          <li v-for="item in blastRadius.impacted_upstream" :key="item.service_id">
            <div class="row-top">
              <strong>{{ item.service_id }}</strong>
              <span class="meta-chip">{{ item.tier }} · HOP {{ item.depth }} · {{ item.criticality }}</span>
            </div>
            <div class="path-trace">
              {{ item.propagation_path.join(' ⇐ ') }}
            </div>
          </li>
          <li v-if="blastRadius.impacted_upstream.length === 0" class="empty-line">
            NO UPSTREAM CONSUMERS IMPACTED
          </li>
        </ul>
      </div>

      <!-- Right: SBOM Topological Order & Transitive CVEs -->
      <div class="sub-box">
        <div class="sub-title">
          <span>SBOM TOPOLOGICAL BLAST ORDER</span>
          <span
            v-if="sbomScan"
            class="gate-pill"
            :class="sbomScan.blocked ? 'danger' : 'ok'"
          >
            {{ sbomScan.gate_decision }} · {{ sbomScan.total_cves }} CVEs
          </span>
        </div>

        <div v-if="sbomScan" class="sbom-body">
          <div class="topo-chain">
            <span class="muted-label">PROPAGATION ORDER (LEAF → ROOT):</span>
            <div class="chain-nodes">
              <template v-for="(node, idx) in sbomScan.topological_blast_order" :key="node">
                <span
                  class="topo-node"
                  :class="{ vulnerable: sbomScan.blast_radius_order.includes(node) }"
                >
                  {{ node }}
                </span>
                <span v-if="idx < sbomScan.topological_blast_order.length - 1" class="arrow">→</span>
              </template>
            </div>
          </div>

          <ul class="term-list">
            <li v-for="finding in sbomScan.findings" :key="`${finding.cve_id}-${finding.package_ref}`">
              <div class="row-top">
                <span>
                  <span class="cve-id">{{ finding.cve_id }}</span>
                  <span class="pkg-ref">{{ finding.package_name }}@{{ finding.package_version }}</span>
                </span>
                <span
                  class="sev-badge"
                  :class="finding.severity.toLowerCase()"
                >
                  {{ finding.severity }} {{ finding.cvss_score }} · {{ finding.exposure.toUpperCase() }}
                </span>
              </div>
              <div class="path-trace">
                PATH: {{ finding.dependency_path.join(' → ') }} | FIX: {{ finding.fixed_version }}
              </div>
            </li>
            <li v-if="sbomScan.findings.length === 0" class="empty-line">
              0 VULNERABLE PACKAGES DETECTED IN CYCLONEDX BOM
            </li>
          </ul>
        </div>
        <div v-else class="empty-line">
          CLICK "SCAN CYCLONEDX SBOM" TO ANALYZE TRANSITIVE PACKAGE EXPOSURE
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.war-panel {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 12px;
}

.panel-kicker {
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #22c55e;
}

h2 {
  margin: 4px 0 0;
  font-size: 16px;
  color: #f8fafc;
}

.controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.term-select {
  background: #090d16;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 7px 10px;
  font-family: inherit;
  font-size: 12px;
}

.term-btn {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 7px 12px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.term-btn.primary {
  background: rgba(34, 197, 94, 0.14);
  color: #22c55e;
  border-color: #22c55e;
}

.term-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.heatmap-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.heat-cell {
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px 12px;
}

.heat-cell.crit.active {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
}

.heat-cell.high.active {
  border-color: #f97316;
  background: rgba(249, 115, 22, 0.1);
}

.heat-cell.med.active {
  border-color: #eab308;
  background: rgba(234, 179, 8, 0.08);
}

.heat-cell.low.active {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
}

.heat-top {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #94a3b8;
}

.heat-count {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
  color: #f8fafc;
}

.split-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.sub-box {
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 12px;
}

.sub-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  margin-bottom: 10px;
}

.gate-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
}

.gate-pill.danger {
  background: rgba(239, 68, 68, 0.16);
  color: #ef4444;
  border: 1px solid #ef4444;
}

.gate-pill.ok {
  background: rgba(34, 197, 94, 0.14);
  color: #22c55e;
  border: 1px solid #22c55e;
}

.root-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #111827;
  border-left: 3px solid #22c55e;
  padding: 8px 10px;
  margin-bottom: 10px;
}

.tier-chip {
  font-size: 10px;
  background: #1e293b;
  color: #22c55e;
  padding: 2px 6px;
  border-radius: 3px;
  margin-right: 8px;
}

.root-name {
  color: #f8fafc;
  font-size: 14px;
}

.impact-metric {
  font-size: 12px;
  color: #94a3b8;
}

.impact-metric strong {
  color: #22c55e;
}

.tier0-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.muted-label {
  font-size: 11px;
  color: #64748b;
}

.tag-danger {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 3px;
}

.tag-ok {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border-radius: 3px;
}

.term-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.term-list li {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 8px 10px;
}

.row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.meta-chip {
  font-size: 11px;
  color: #94a3b8;
}

.path-trace {
  margin-top: 4px;
  font-size: 11px;
  color: #22c55e;
  word-break: break-all;
}

.topo-chain {
  margin-bottom: 10px;
}

.chain-nodes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.topo-node {
  font-size: 11px;
  padding: 3px 7px;
  background: #111827;
  border: 1px solid #334155;
  border-radius: 3px;
  color: #cbd5e1;
}

.topo-node.vulnerable {
  border-color: #ef4444;
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.1);
}

.arrow {
  color: #22c55e;
  font-size: 12px;
}

.cve-id {
  color: #ef4444;
  font-weight: 700;
  margin-right: 8px;
}

.pkg-ref {
  color: #e2e8f0;
}

.sev-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 700;
}

.sev-badge.critical {
  background: rgba(239, 68, 68, 0.18);
  color: #ef4444;
}

.sev-badge.high {
  background: rgba(249, 115, 22, 0.18);
  color: #fb923c;
}

.sev-badge.medium {
  background: rgba(234, 179, 8, 0.18);
  color: #facc15;
}

.sev-badge.low {
  background: rgba(34, 197, 94, 0.18);
  color: #22c55e;
}

.empty-line {
  font-size: 12px;
  color: #64748b;
  padding: 12px;
  text-align: center;
}

@media (max-width: 960px) {
  .heatmap-strip,
  .split-grid {
    grid-template-columns: 1fr;
  }
}
</style>
