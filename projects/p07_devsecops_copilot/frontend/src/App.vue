<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BlastRadiusView from './components/BlastRadiusView.vue'
import IncidentTerminal from './components/IncidentTerminal.vue'
import {
  devsecopsApi,
  type AuditLogEntry,
  type BlastRadiusResponse,
  type CveGateResponse,
  type DashboardOverview,
  type PendingAction,
  type PostmortemExportResponse,
  type SBOMScanResponse,
  type TriageResponse,
  type WikiLintReport,
  type WikiPage,
} from './api/client'

type WarRoomTab = 'triage' | 'blast' | 'terminal' | 'wiki' | 'hitl'

const activeTab = ref<WarRoomTab>('blast')
const loading = ref(false)
const errorMessage = ref('')

const overview = ref<DashboardOverview | null>(null)
const selectedServiceId = ref('svc-auth')

const triageForm = ref({
  service_id: 'svc-auth',
  symptom: '502 Bad Gateway on /oauth/token with Bearer eyJhbGciOiJIUzI1NiJ9.secret_demo_token',
  severity: 'SEV-1',
  proposed_action: 'rollback',
  environment: 'prod',
  requested_by: 'fde-copilot',
})
const triageResult = ref<TriageResponse | null>(null)

const gateForm = ref({
  service_id: 'svc-checkout',
  release_version: 'v2.4.0',
  include_dependencies: true,
  block_threshold: 9.0,
})
const gateResult = ref<CveGateResponse | null>(null)

const blastRadius = ref<BlastRadiusResponse | null>(null)
const sbomScan = ref<SBOMScanResponse | null>(null)
const postmortemResult = ref<PostmortemExportResponse | null>(null)

const wikiPages = ref<WikiPage[]>([])
const selectedWikiPage = ref<WikiPage | null>(null)
const wikiLint = ref<WikiLintReport | null>(null)
const wikiIngestForm = ref({
  entity_type: 'runbook',
  entity_id: 'rb-web-portal',
  title: 'Enterprise Web Portal Failover Runbook',
  content: 'Drain CDN edge nodes and verify [[svc-web-portal]] health checks against [[svc-checkout]].',
  links: 'svc-web-portal,svc-checkout',
})

const pendingActions = ref<PendingAction[]>([])
const auditLogs = ref<AuditLogEntry[]>([])
const approverName = ref('sre-lead-alice')
const approvalComment = ref('Verified canary metrics and blast radius.')

const serviceOptions = computed(() => overview.value?.services ?? [])

async function refreshOverview() {
  overview.value = await devsecopsApi.getDashboardOverview()
}

async function refreshAuditAndPending() {
  const [pendingRes, auditRes] = await Promise.all([
    devsecopsApi.getPendingActions(),
    devsecopsApi.getAuditLogs(),
  ])
  pendingActions.value = pendingRes.actions
  auditLogs.value = auditRes.logs
}

async function refreshWiki() {
  const [pagesRes, lintRes] = await Promise.all([
    devsecopsApi.getWikiPages(),
    devsecopsApi.lintWiki(),
  ])
  wikiPages.value = pagesRes.pages
  if (!selectedWikiPage.value && pagesRes.pages.length > 0) {
    selectedWikiPage.value = pagesRes.pages[0]
  }
  wikiLint.value = lintRes
}

async function loadBlastRadius(serviceId = selectedServiceId.value) {
  loading.value = true
  errorMessage.value = ''
  try {
    selectedServiceId.value = serviceId
    const [blastRes, sbomRes] = await Promise.all([
      devsecopsApi.getBlastRadius(serviceId),
      devsecopsApi.scanSBOM({ service_id: serviceId }),
    ])
    blastRadius.value = blastRes
    sbomScan.value = sbomRes
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function runSbomScan(serviceId = selectedServiceId.value) {
  loading.value = true
  errorMessage.value = ''
  try {
    sbomScan.value = await devsecopsApi.scanSBOM({ service_id: serviceId })
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function runTriage() {
  loading.value = true
  errorMessage.value = ''
  try {
    triageResult.value = await devsecopsApi.triageIncident(triageForm.value)
    await Promise.all([refreshOverview(), refreshAuditAndPending()])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function runCveGate() {
  loading.value = true
  errorMessage.value = ''
  try {
    gateResult.value = await devsecopsApi.evaluateCveGate(gateForm.value)
    await Promise.all([refreshOverview(), refreshAuditAndPending()])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function handleExportPostmortem(payload: Parameters<typeof devsecopsApi.exportPostmortem>[0]) {
  loading.value = true
  errorMessage.value = ''
  try {
    postmortemResult.value = await devsecopsApi.exportPostmortem(payload)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function submitWikiIngest() {
  loading.value = true
  errorMessage.value = ''
  try {
    const links = wikiIngestForm.value.links
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    await devsecopsApi.ingestWikiPage({
      entity_type: wikiIngestForm.value.entity_type,
      entity_id: wikiIngestForm.value.entity_id,
      title: wikiIngestForm.value.title,
      content: wikiIngestForm.value.content,
      links,
    })
    await Promise.all([refreshOverview(), refreshWiki()])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function handleHitlDecision(actionId: string, approved: boolean) {
  loading.value = true
  errorMessage.value = ''
  try {
    await devsecopsApi.approveAction({
      action_id: actionId,
      approved,
      approver: approverName.value,
      comment: approvalComment.value,
    })
    await Promise.all([refreshOverview(), refreshAuditAndPending()])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      refreshOverview(),
      loadBlastRadius('svc-auth'),
      refreshWiki(),
      refreshAuditAndPending(),
    ])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="war-shell">
    <header class="war-topbar">
      <div>
        <div class="eyebrow">P07 // SRE WAR ROOM &amp; SBOM BLAST-RADIUS TERMINAL</div>
        <h1>DevSecOps Incident Command &amp; Supply-Chain Console</h1>
      </div>
      <div class="status-pill" :class="{ busy: loading }">
        <span class="pulse" />
        {{ loading ? 'SYNCING TELEMETRY...' : 'TERMINAL ONLINE · OFFLINE DETERMINISTIC' }}
      </div>
    </header>

    <section v-if="overview" class="kpi-strip">
      <div class="kpi-tile">
        <span class="kpi-label">SERVICES</span>
        <strong class="kpi-value">{{ overview.services_total }}</strong>
      </div>
      <div class="kpi-tile alert">
        <span class="kpi-label">CRITICAL CVEs</span>
        <strong class="kpi-value">{{ overview.critical_cves_total }}</strong>
      </div>
      <div class="kpi-tile warn">
        <span class="kpi-label">ACTIVE INCIDENTS</span>
        <strong class="kpi-value">{{ overview.active_incidents_total }}</strong>
      </div>
      <div class="kpi-tile alert">
        <span class="kpi-label">HITL QUEUE</span>
        <strong class="kpi-value">{{ overview.pending_hitl_rollbacks }}</strong>
      </div>
      <div class="kpi-tile">
        <span class="kpi-label">WIKI RUNBOOKS</span>
        <strong class="kpi-value">{{ overview.wiki_pages_total }}</strong>
      </div>
      <div class="kpi-tile">
        <span class="kpi-label">REDACTED AUDITS</span>
        <strong class="kpi-value">{{ overview.audit_logs_total }}</strong>
      </div>
    </section>

    <div v-if="errorMessage" class="alert-banner">
      [ERROR] {{ errorMessage }}
    </div>

    <nav class="war-tabs">
      <button :class="{ active: activeTab === 'blast' }" @click="activeTab = 'blast'">
        01. BLAST-RADIUS &amp; SBOM
      </button>
      <button :class="{ active: activeTab === 'terminal' }" @click="activeTab = 'terminal'">
        02. INCIDENT TERMINAL &amp; POSTMORTEM
      </button>
      <button :class="{ active: activeTab === 'triage' }" @click="activeTab = 'triage'">
        03. TRIAGE &amp; CVE GATE
      </button>
      <button :class="{ active: activeTab === 'hitl' }" @click="activeTab = 'hitl'">
        04. HITL APPROVALS ({{ pendingActions.length }})
      </button>
      <button :class="{ active: activeTab === 'wiki' }" @click="activeTab = 'wiki'">
        05. RUNBOOK WIKI
      </button>
    </nav>

    <BlastRadiusView
      v-if="activeTab === 'blast'"
      :services="serviceOptions"
      :selected-service-id="selectedServiceId"
      :blast-radius="blastRadius"
      :sbom-scan="sbomScan"
      :loading="loading"
      @select-service="loadBlastRadius"
      @run-sbom-scan="runSbomScan"
    />

    <IncidentTerminal
      v-else-if="activeTab === 'terminal'"
      :services="serviceOptions"
      :audit-logs="auditLogs"
      :triage-result="triageResult"
      :postmortem-result="postmortemResult"
      :loading="loading"
      @export-postmortem="handleExportPostmortem"
    />

    <main v-else-if="activeTab === 'triage'" class="two-col">
      <section class="war-card">
        <h2>FDE INCIDENT TRIAGE &amp; SECRET REDACTION</h2>
        <div class="form-grid">
          <label>
            TARGET SERVICE
            <select v-model="triageForm.service_id">
              <option v-for="svc in serviceOptions" :key="svc.service_id" :value="svc.service_id">
                {{ svc.service_id }} ({{ svc.tier }})
              </option>
            </select>
          </label>
          <label>
            SEVERITY
            <select v-model="triageForm.severity">
              <option value="SEV-1">SEV-1</option>
              <option value="SEV-2">SEV-2</option>
              <option value="SEV-3">SEV-3</option>
            </select>
          </label>
          <label>
            PROPOSED ACTION
            <select v-model="triageForm.proposed_action">
              <option value="rollback">rollback (HITL)</option>
              <option value="quarantine">quarantine (HITL)</option>
              <option value="notify">notify (AUTO)</option>
            </select>
          </label>
          <label>
            ENVIRONMENT
            <select v-model="triageForm.environment">
              <option value="prod">prod</option>
              <option value="staging">staging</option>
            </select>
          </label>
        </div>
        <label class="full-label">
          SYMPTOM / LOG PAYLOAD
          <textarea v-model="triageForm.symptom" rows="3" />
        </label>
        <button class="btn-green" :disabled="loading" @click="runTriage">
          EXECUTE TRIAGE
        </button>

        <div v-if="triageResult" class="result-box">
          <div class="result-head">
            <span class="badge ok">{{ triageResult.action.status }}</span>
            <span>ACTION: <code>{{ triageResult.action.action_id }}</code></span>
          </div>
          <p><strong>REDACTED:</strong> <code>{{ triageResult.redacted_symptom }}</code></p>
          <ul>
            <li v-for="(h, idx) in triageResult.root_cause_hypotheses" :key="idx">{{ h }}</li>
          </ul>
        </div>
      </section>

      <section class="war-card">
        <h2>CI/CD RELEASE CVE GATE</h2>
        <div class="form-grid">
          <label>
            SERVICE
            <select v-model="gateForm.service_id">
              <option v-for="svc in serviceOptions" :key="svc.service_id" :value="svc.service_id">
                {{ svc.service_id }}
              </option>
            </select>
          </label>
          <label>
            RELEASE VERSION
            <input v-model="gateForm.release_version" type="text" />
          </label>
          <label>
            CVSS THRESHOLD
            <input v-model.number="gateForm.block_threshold" type="number" step="0.1" min="0" max="10" />
          </label>
          <label class="checkbox-label">
            <input v-model="gateForm.include_dependencies" type="checkbox" />
            INCLUDE TRANSITIVE DEPS
          </label>
        </div>
        <button class="btn-green" :disabled="loading" @click="runCveGate">
          EVALUATE DEPLOY GATE
        </button>

        <div v-if="gateResult" class="result-box">
          <div class="result-head">
            <span class="badge" :class="gateResult.allowed ? 'ok' : 'danger'">
              {{ gateResult.decision }}
            </span>
            <span>MAX CVSS: <strong>{{ gateResult.max_cvss }}</strong></span>
          </div>
          <p><strong>CHECKED:</strong> {{ gateResult.checked_services.join(' -> ') }}</p>
          <ul v-if="gateResult.blocking_cves.length">
            <li v-for="cve in gateResult.blocking_cves" :key="cve.cve_id">
              <code>{{ cve.cve_id }}</code> ({{ cve.service_id }}, CVSS {{ cve.cvss_score }}) — {{ cve.remediation }}
            </li>
          </ul>
        </div>
      </section>
    </main>

    <main v-else-if="activeTab === 'hitl'" class="war-card">
      <div class="toolbar">
        <h2>SRE HITL APPROVAL QUEUE</h2>
        <div class="inline-inputs">
          <input v-model="approverName" placeholder="Approver ID" />
          <input v-model="approvalComment" placeholder="Decision rationale" />
        </div>
      </div>

      <div v-if="pendingActions.length === 0" class="empty-state">
        NO PENDING HITL ROLLBACK / QUARANTINE REQUESTS
      </div>
      <div v-else class="pending-list">
        <div v-for="act in pendingActions" :key="act.action_id" class="pending-item">
          <div>
            <strong>{{ act.action_type.toUpperCase() }}</strong> → <code>{{ act.target_service_id }}</code>
            ({{ act.environment }})
            <div class="muted">{{ act.action_id }} · {{ act.reason }}</div>
          </div>
          <div class="inline-inputs">
            <button class="btn-green" :disabled="loading" @click="handleHitlDecision(act.action_id, true)">
              APPROVE
            </button>
            <button class="btn-red" :disabled="loading" @click="handleHitlDecision(act.action_id, false)">
              REJECT
            </button>
          </div>
        </div>
      </div>
    </main>

    <main v-else-if="activeTab === 'wiki'" class="two-col">
      <section class="war-card">
        <div class="toolbar">
          <h2>RUNBOOK / POSTMORTEM WIKI</h2>
          <button class="btn-outline" @click="refreshWiki">LINT WIKI</button>
        </div>
        <div v-if="wikiLint" class="lint-bar" :class="wikiLint.healthy ? 'ok' : 'danger'">
          STATUS: {{ wikiLint.healthy ? 'HEALTHY' : `${wikiLint.total_issues} ISSUES` }}
        </div>
        <div class="wiki-list">
          <button
            v-for="page in wikiPages"
            :key="page.id"
            class="wiki-item"
            :class="{ selected: selectedWikiPage?.id === page.id }"
            @click="selectedWikiPage = page"
          >
            <strong>[{{ page.entity_type }}] {{ page.id }}</strong>
            <span>{{ page.title }}</span>
          </button>
        </div>
      </section>

      <section class="war-card">
        <h2>{{ selectedWikiPage?.title ?? 'SELECT A WIKI PAGE' }}</h2>
        <pre v-if="selectedWikiPage" class="wiki-content">{{ selectedWikiPage.content }}</pre>
        <h3>INGEST RUNBOOK</h3>
        <div class="form-grid">
          <input v-model="wikiIngestForm.entity_id" placeholder="Entity ID" />
          <input v-model="wikiIngestForm.title" placeholder="Title" />
        </div>
        <textarea v-model="wikiIngestForm.content" rows="3" />
        <button class="btn-green" :disabled="loading" @click="submitWikiIngest">
          INGEST TO WIKI
        </button>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #090d16;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.war-shell {
  min-height: 100vh;
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.war-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 14px;
  margin-bottom: 16px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: #22c55e;
}

h1 {
  margin: 4px 0 0;
  font-size: 20px;
  color: #f8fafc;
}

h2 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #22c55e;
  letter-spacing: 0.05em;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 6px 12px;
  border: 1px solid #22c55e;
  border-radius: 4px;
  color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
}

.status-pill.busy {
  border-color: #f59e0b;
  color: #fbbf24;
}

.pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.kpi-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.kpi-tile {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px 12px;
}

.kpi-tile.alert {
  border-color: rgba(239, 68, 68, 0.55);
}

.kpi-tile.warn {
  border-color: rgba(245, 158, 11, 0.5);
}

.kpi-label {
  display: block;
  font-size: 10px;
  color: #94a3b8;
  letter-spacing: 0.08em;
}

.kpi-value {
  font-size: 22px;
  color: #f8fafc;
}

.kpi-tile.alert .kpi-value {
  color: #ef4444;
}

.alert-banner {
  background: rgba(239, 68, 68, 0.14);
  border: 1px solid #ef4444;
  color: #fca5a5;
  padding: 10px 12px;
  border-radius: 4px;
  margin-bottom: 14px;
  font-size: 12px;
}

.war-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.war-tabs button {
  background: #0d1320;
  color: #94a3b8;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 8px 14px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.war-tabs button.active {
  color: #22c55e;
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.12);
}

.two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.war-card {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #94a3b8;
}

.checkbox-label {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

input,
select,
textarea {
  background: #090d16;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 7px 9px;
  font-family: inherit;
  font-size: 12px;
}

.btn-green {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border: 1px solid #22c55e;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.btn-red {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid #ef4444;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.btn-outline {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 7px 12px;
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
}

.result-box {
  background: #090d16;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 10px;
  font-size: 12px;
}

.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: 700;
}

.badge.ok {
  background: rgba(34, 197, 94, 0.16);
  color: #22c55e;
}

.badge.danger {
  background: rgba(239, 68, 68, 0.18);
  color: #ef4444;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.inline-inputs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pending-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pending-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
}

.muted,
.empty-state {
  font-size: 12px;
  color: #64748b;
}

.lint-bar {
  padding: 8px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.lint-bar.ok {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.lint-bar.danger {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.wiki-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.wiki-item {
  text-align: left;
  background: #090d16;
  color: #cbd5e1;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
}

.wiki-item.selected {
  border-color: #22c55e;
  color: #22c55e;
}

.wiki-content {
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 220px;
  overflow-y: auto;
}

@media (max-width: 960px) {
  .kpi-strip,
  .two-col,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
