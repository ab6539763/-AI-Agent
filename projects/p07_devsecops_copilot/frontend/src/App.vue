<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  devsecopsApi,
  type AuditLogEntry,
  type BlastRadiusResponse,
  type CveGateResponse,
  type DashboardOverview,
  type PendingAction,
  type TriageResponse,
  type WikiLintReport,
  type WikiPage,
} from './api/client'

type WorkbenchTab = 'triage' | 'blast' | 'wiki' | 'hitl'

const activeTab = ref<WorkbenchTab>('triage')
const loading = ref(false)
const errorMessage = ref('')

const overview = ref<DashboardOverview | null>(null)
const selectedServiceId = ref('svc-auth')

// Tab 1: 故障定界与 CVE 门禁
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

// Tab 2: 微服务爆炸半径图谱
const blastRadius = ref<BlastRadiusResponse | null>(null)

// Tab 3: Runbook LLM Wiki
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

// Tab 4: SRE HITL 审批与审计
const pendingActions = ref<PendingAction[]>([])
const auditLogs = ref<AuditLogEntry[]>([])
const approverName = ref('sre-lead-alice')
const approvalComment = ref('Verified canary metrics and blast radius.')

const serviceOptions = computed(() => overview.value?.services ?? [])

async function refreshOverview() {
  overview.value = await devsecopsApi.getDashboardOverview()
}

async function refreshTab4() {
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
    blastRadius.value = await devsecopsApi.getBlastRadius(serviceId)
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
    await Promise.all([refreshOverview(), refreshTab4()])
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
    await Promise.all([refreshOverview(), refreshTab4()])
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
    await Promise.all([refreshOverview(), refreshTab4()])
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
      refreshTab4(),
    ])
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div>
        <div class="eyebrow">PROJECT P07 · ENTERPRISE DEVSECOPS COPILOT</div>
        <h1>DevSecOps 故障定界、爆炸半径与 SRE HITL 治理工作台</h1>
      </div>
      <div class="status-pill" :class="{ busy: loading }">
        {{ loading ? '同步中...' : 'FastAPI + Vue 3 实时在线' }}
      </div>
    </header>

    <section v-if="overview" class="kpi-grid">
      <div class="kpi-card">
        <span class="kpi-label">纳管微服务</span>
        <strong class="kpi-value">{{ overview.services_total }}</strong>
      </div>
      <div class="kpi-card danger">
        <span class="kpi-label">未修复高危 CVE</span>
        <strong class="kpi-value">{{ overview.critical_cves_total }}</strong>
      </div>
      <div class="kpi-card warn">
        <span class="kpi-label">活跃故障</span>
        <strong class="kpi-value">{{ overview.active_incidents_total }}</strong>
      </div>
      <div class="kpi-card warn">
        <span class="kpi-label">待审批 HITL 回滚/隔离</span>
        <strong class="kpi-value">{{ overview.pending_hitl_rollbacks }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">LLM Wiki 页面</span>
        <strong class="kpi-value">{{ overview.wiki_pages_total }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">脱敏审计日志</span>
        <strong class="kpi-value">{{ overview.audit_logs_total }}</strong>
      </div>
    </section>

    <div v-if="errorMessage" class="alert-error">
      {{ errorMessage }}
    </div>

    <nav class="tabs">
      <button
        :class="{ active: activeTab === 'triage' }"
        @click="activeTab = 'triage'"
      >
        1. 故障定界与 CVE 门禁
      </button>
      <button
        :class="{ active: activeTab === 'blast' }"
        @click="activeTab = 'blast'"
      >
        2. 微服务爆炸半径图谱
      </button>
      <button
        :class="{ active: activeTab === 'wiki' }"
        @click="activeTab = 'wiki'"
      >
        3. Runbook LLM Wiki
      </button>
      <button
        :class="{ active: activeTab === 'hitl' }"
        @click="activeTab = 'hitl'"
      >
        4. SRE HITL 审批与审计 ({{ pendingActions.length }})
      </button>
    </nav>

    <!-- Tab 1: 故障定界与 CVE 门禁 -->
    <main v-if="activeTab === 'triage'" class="two-col">
      <section class="panel">
        <h2>FDE 故障定界与密钥脱敏</h2>
        <div class="form-grid">
          <label>
            目标服务
            <select v-model="triageForm.service_id">
              <option v-for="svc in serviceOptions" :key="svc.service_id" :value="svc.service_id">
                {{ svc.service_id }} ({{ svc.tier }})
              </option>
            </select>
          </label>
          <label>
            严重等级
            <select v-model="triageForm.severity">
              <option value="SEV-1">SEV-1</option>
              <option value="SEV-2">SEV-2</option>
              <option value="SEV-3">SEV-3</option>
            </select>
          </label>
          <label>
            拟议处置动作
            <select v-model="triageForm.proposed_action">
              <option value="rollback">rollback (触发 HITL)</option>
              <option value="quarantine">quarantine (触发 HITL)</option>
              <option value="notify">notify (自动执行)</option>
            </select>
          </label>
          <label>
            运行环境
            <select v-model="triageForm.environment">
              <option value="prod">prod</option>
              <option value="staging">staging</option>
            </select>
          </label>
        </div>
        <label class="full-label">
          故障症状 / 日志片段 (自动执行 Secret Redaction)
          <textarea v-model="triageForm.symptom" rows="3" />
        </label>
        <button class="primary-btn" :disabled="loading" @click="runTriage">
          执行故障定界与处置提案
        </button>

        <div v-if="triageResult" class="result-box">
          <div class="result-header">
            <span class="badge">{{ triageResult.action.status }}</span>
            <span>Action ID: <code>{{ triageResult.action.action_id }}</code></span>
          </div>
          <p><strong>脱敏后症状：</strong><code>{{ triageResult.redacted_symptom }}</code></p>
          <p v-if="triageResult.redactions_applied.length">
            <strong>触发脱敏规则：</strong>{{ triageResult.redactions_applied.join(', ') }}
          </p>
          <div>
            <strong>根因假设：</strong>
            <ul>
              <li v-for="(h, idx) in triageResult.root_cause_hypotheses" :key="idx">{{ h }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>CI/CD 发布 CVE 安全门禁</h2>
        <div class="form-grid">
          <label>
            发布服务
            <select v-model="gateForm.service_id">
              <option v-for="svc in serviceOptions" :key="svc.service_id" :value="svc.service_id">
                {{ svc.service_id }} ({{ svc.name }})
              </option>
            </select>
          </label>
          <label>
            发布版本
            <input v-model="gateForm.release_version" type="text" />
          </label>
          <label>
            阻断阈值 (CVSS)
            <input v-model.number="gateForm.block_threshold" type="number" step="0.1" min="0" max="10" />
          </label>
          <label class="checkbox-label">
            <input v-model="gateForm.include_dependencies" type="checkbox" />
            级联检查下游依赖 CVE
          </label>
        </div>
        <button class="primary-btn" :disabled="loading" @click="runCveGate">
          评估发布门禁 (ALLOW / BLOCK_DEPLOY)
        </button>

        <div v-if="gateResult" class="result-box">
          <div class="result-header">
            <span class="badge" :class="gateResult.allowed ? 'ok' : 'danger'">
              {{ gateResult.decision }}
            </span>
            <span>Max CVSS: <strong>{{ gateResult.max_cvss }}</strong></span>
          </div>
          <p><strong>检查范围：</strong>{{ gateResult.checked_services.join(' → ') }}</p>
          <div v-if="gateResult.blocking_cves.length">
            <strong>阻断 CVE 列表：</strong>
            <ul>
              <li v-for="cve in gateResult.blocking_cves" :key="cve.cve_id">
                <code>{{ cve.cve_id }}</code> ({{ cve.service_id }}, CVSS {{ cve.cvss_score }}) — {{ cve.remediation }}
              </li>
            </ul>
          </div>
          <p v-else class="ok-text">未发现超过阈值的未修复漏洞，允许发布。</p>
        </div>
      </section>
    </main>

    <!-- Tab 2: 微服务爆炸半径图谱 -->
    <main v-if="activeTab === 'blast'" class="panel">
      <div class="toolbar">
        <h2>微服务爆炸半径与 Tier-0 影响面分析</h2>
        <div class="toolbar-actions">
          <select v-model="selectedServiceId" @change="loadBlastRadius(selectedServiceId)">
            <option v-for="svc in serviceOptions" :key="svc.service_id" :value="svc.service_id">
              {{ svc.service_id }} — {{ svc.name }}
            </option>
          </select>
          <button class="secondary-btn" @click="loadBlastRadius(selectedServiceId)">刷新图谱</button>
        </div>
      </div>

      <div v-if="blastRadius" class="blast-layout">
        <div class="blast-summary">
          <div class="node-root">
            <span class="tier-tag">{{ blastRadius.root_tier }}</span>
            <strong>{{ blastRadius.root_service_id }}</strong>
            <small>受影响上游服务: {{ blastRadius.total_impacted_services }}</small>
          </div>
          <div class="tier0-box">
            <strong>波及 Tier-0 核心服务：</strong>
            <span v-for="t0 in blastRadius.tier0_impacted" :key="t0" class="badge danger">{{ t0 }}</span>
          </div>
        </div>

        <div class="two-col">
          <div>
            <h3>上游受影响链路 (Propagation Paths)</h3>
            <ul class="path-list">
              <li v-for="item in blastRadius.impacted_upstream" :key="item.service_id">
                <div class="path-head">
                  <strong>{{ item.service_id }}</strong>
                  <span class="badge">{{ item.tier }} · depth {{ item.depth }}</span>
                </div>
                <code>{{ item.propagation_path.join(' ⇐ ') }}</code>
              </li>
            </ul>
          </div>
          <div>
            <h3>下游依赖与活跃 CVE</h3>
            <ul class="path-list">
              <li v-for="dep in blastRadius.downstream_dependencies" :key="dep.service_id">
                依赖 <strong>{{ dep.service_id }}</strong> ({{ dep.relation }} / {{ dep.criticality }})
              </li>
              <li v-if="blastRadius.downstream_dependencies.length === 0">无下游服务依赖</li>
            </ul>
            <h3>活跃未修复 CVE</h3>
            <ul class="path-list">
              <li v-for="cve in blastRadius.active_cves" :key="cve.cve_id">
                <code>{{ cve.cve_id }}</code> — CVSS {{ cve.cvss_score }} ({{ cve.severity }})
              </li>
              <li v-if="blastRadius.active_cves.length === 0">当前服务无未修复 CVE</li>
            </ul>
          </div>
        </div>
      </div>
    </main>

    <!-- Tab 3: Runbook LLM Wiki -->
    <main v-if="activeTab === 'wiki'" class="two-col">
      <section class="panel">
        <div class="toolbar">
          <h2>Runbook / Postmortem Wiki 目录</h2>
          <button class="secondary-btn" @click="refreshWiki">刷新 &amp; Lint</button>
        </div>
        <div v-if="wikiLint" class="lint-bar" :class="wikiLint.healthy ? 'ok' : 'warn'">
          <span>Wiki 健康状态: <strong>{{ wikiLint.healthy ? 'HEALTHY' : `${wikiLint.total_issues} ISSUES` }}</strong></span>
          <span v-if="wikiLint.services_without_runbooks.length">
            缺 Runbook 服务: {{ wikiLint.services_without_runbooks.join(', ') }}
          </span>
        </div>
        <div class="wiki-list">
          <button
            v-for="page in wikiPages"
            :key="page.id"
            class="wiki-item"
            :class="{ selected: selectedWikiPage?.id === page.id }"
            @click="selectedWikiPage = page"
          >
            <div class="wiki-item-head">
              <strong>{{ page.title }}</strong>
              <span class="badge">{{ page.entity_type }}</span>
            </div>
            <small>{{ page.path }}</small>
            <p>{{ page.preview }}</p>
          </button>
        </div>
      </section>

      <section class="panel">
        <h2>Markdown 详情与知识入库</h2>
        <pre v-if="selectedWikiPage" class="wiki-preview">{{ selectedWikiPage.content || selectedWikiPage.preview }}</pre>

        <h3>新增 / 更新 Wiki 实体</h3>
        <div class="form-grid">
          <label>
            实体类型
            <input v-model="wikiIngestForm.entity_type" type="text" />
          </label>
          <label>
            实体 ID
            <input v-model="wikiIngestForm.entity_id" type="text" />
          </label>
        </div>
        <label class="full-label">
          标题
          <input v-model="wikiIngestForm.title" type="text" />
        </label>
        <label class="full-label">
          Markdown 正文 (支持 [[wiki_links]])
          <textarea v-model="wikiIngestForm.content" rows="3" />
        </label>
        <label class="full-label">
          关联实体 ID (逗号分隔)
          <input v-model="wikiIngestForm.links" type="text" />
        </label>
        <button class="primary-btn" :disabled="loading" @click="submitWikiIngest">
          写入 Wiki 并重建索引
        </button>
      </section>
    </main>

    <!-- Tab 4: SRE HITL 审批与审计 -->
    <main v-if="activeTab === 'hitl'" class="two-col">
      <section class="panel">
        <div class="toolbar">
          <h2>待审批 SRE HITL 动作</h2>
          <button class="secondary-btn" @click="refreshTab4">刷新队列</button>
        </div>
        <div class="form-grid">
          <label>
            审批人
            <input v-model="approverName" type="text" />
          </label>
          <label>
            审批备注
            <input v-model="approvalComment" type="text" />
          </label>
        </div>

        <div v-if="pendingActions.length === 0" class="empty-state">
          当前无待审批的生产环境回滚 / 隔离动作。可在「故障定界」页签发起 rollback 或 quarantine 提案。
        </div>
        <div v-for="act in pendingActions" :key="act.action_id" class="hitl-card">
          <div class="result-header">
            <span class="badge warn">{{ act.action_type.toUpperCase() }}</span>
            <code>{{ act.action_id }}</code>
            <span>{{ act.target_service_id }} ({{ act.environment }})</span>
          </div>
          <p>{{ act.reason }}</p>
          <div class="hitl-buttons">
            <button class="primary-btn" @click="handleHitlDecision(act.action_id, true)">
              批准执行 (Approve)
            </button>
            <button class="danger-btn" @click="handleHitlDecision(act.action_id, false)">
              拒绝 (Reject)
            </button>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>Secret-Redacted 不可变审计日志</h2>
        <div v-if="auditLogs.length === 0" class="empty-state">暂无审计事件。</div>
        <div v-for="log in auditLogs" :key="log.audit_id" class="audit-item">
          <div class="result-header">
            <span class="badge">{{ log.event_type }}</span>
            <span>{{ log.actor }}</span>
            <small>{{ log.timestamp }}</small>
          </div>
          <pre class="audit-payload">{{ JSON.stringify(log.payload, null, 2) }}</pre>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #0b1120;
  color: #e2e8f0;
}

.shell {
  max-width: 1360px;
  margin: 0 auto;
  padding: 24px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  color: #38bdf8;
  font-weight: 700;
}

h1 {
  margin: 4px 0 0;
  font-size: 22px;
}

h2 {
  margin: 0 0 14px;
  font-size: 17px;
  color: #f8fafc;
}

h3 {
  margin: 16px 0 8px;
  font-size: 14px;
  color: #94a3b8;
}

.status-pill {
  padding: 8px 14px;
  border-radius: 999px;
  background: #0f2937;
  border: 1px solid #0284c7;
  color: #7dd3fc;
  font-size: 13px;
}

.status-pill.busy {
  border-color: #f59e0b;
  color: #fcd34d;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.kpi-card {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kpi-card.danger {
  border-color: #7f1d1d;
}

.kpi-card.warn {
  border-color: #78350f;
}

.kpi-label {
  font-size: 12px;
  color: #94a3b8;
}

.kpi-value {
  font-size: 24px;
  color: #f8fafc;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.tabs button {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #1e293b;
  padding: 10px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

.tabs button.active {
  background: #0284c7;
  border-color: #38bdf8;
  color: #ffffff;
}

.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 16px;
}

.panel {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 18px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #94a3b8;
}

.full-label {
  margin-bottom: 12px;
}

.checkbox-label {
  flex-direction: row;
  align-items: center;
  padding-top: 20px;
}

input,
select,
textarea {
  background: #0f172a;
  border: 1px solid #334155;
  color: #f8fafc;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  border: none;
  border-radius: 8px;
  padding: 9px 14px;
  font-weight: 600;
  cursor: pointer;
  font-size: 13px;
}

.primary-btn {
  background: #0284c7;
  color: #ffffff;
}

.secondary-btn {
  background: #1e293b;
  color: #e2e8f0;
}

.danger-btn {
  background: #dc2626;
  color: #ffffff;
}

.result-box,
.hitl-card,
.audit-item {
  margin-top: 14px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 12px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.badge {
  background: #1e293b;
  color: #cbd5e1;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}

.badge.ok {
  background: #064e3b;
  color: #6ee7b7;
}

.badge.danger {
  background: #7f1d1d;
  color: #fca5a5;
}

.badge.warn {
  background: #78350f;
  color: #fcd34d;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.blast-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: #0f172a;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid #1e293b;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.node-root {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tier-tag {
  background: #0284c7;
  color: #ffffff;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}

.tier0-box {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.path-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-list li {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 10px;
}

.path-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.lint-bar {
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.lint-bar.ok {
  background: #064e3b;
}

.lint-bar.warn {
  background: #451a03;
  border: 1px solid #b45309;
}

.wiki-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 480px;
  overflow-y: auto;
}

.wiki-item {
  text-align: left;
  background: #0f172a;
  border: 1px solid #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
}

.wiki-item.selected {
  border-color: #38bdf8;
}

.wiki-item-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.wiki-item p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}

.wiki-preview,
.audit-payload {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}

.hitl-buttons {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.empty-state {
  padding: 16px;
  text-align: center;
  color: #94a3b8;
  background: #0f172a;
  border-radius: 8px;
}

.alert-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 14px;
}

.ok-text {
  color: #6ee7b7;
}
</style>
