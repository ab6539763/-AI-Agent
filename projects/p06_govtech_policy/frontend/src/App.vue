<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  govtechApi,
  type AuditEvent,
  type DashboardOverview,
  type GovAction,
  type WikiPageSummary,
} from './api/client'
import EligibilityWizard from './components/EligibilityWizard.vue'
import PolicyGazette from './components/PolicyGazette.vue'

type PortalTab = 'wizard' | 'gazette' | 'hitl'

const activeTab = ref<PortalTab>('wizard')
const errorMessage = ref<string | null>(null)
const loading = ref(false)

const overview = ref<DashboardOverview | null>(null)
const wikiPages = ref<WikiPageSummary[]>([])
const pendingActions = ref<GovAction[]>([])
const auditLogs = ref<AuditEvent[]>([])

const officerId = ref('OFFICER-ZHANG-07')
const decisionNote = ref('材料齐全，符合政策条款，予以核准并路由至财政拨付。')

const kpiCards = computed(() => {
  const ov = overview.value
  return [
    {
      label: '现行有效公报政策',
      value: ov ? `${ov.active_policies} / ${ov.total_policies}` : '-',
      tone: 'red',
    },
    {
      label: '惠企便民补贴项目',
      value: ov ? String(ov.benefit_programs) : '-',
      tone: 'blue',
    },
    {
      label: '政策知识库词条',
      value: ov ? String(ov.wiki_pages) : '-',
      tone: 'blue',
    },
    {
      label: '待经办人 HITL 复核',
      value: ov ? String(ov.pending_hitl_reviews) : '-',
      tone: 'red',
    },
    {
      label: '脱敏审计日志',
      value: ov ? String(ov.audit_logs_count) : '-',
      tone: 'slate',
    },
  ]
})

async function refreshAll() {
  errorMessage.value = null
  try {
    const [ov, pages, pending, logs] = await Promise.all([
      govtechApi.getOverview(),
      govtechApi.getWikiPages(),
      govtechApi.getPendingActions(),
      govtechApi.getAuditLogs(50),
    ])
    overview.value = ov
    wikiPages.value = pages
    pendingActions.value = pending
    auditLogs.value = logs
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  }
}

async function handleApproveAction(actionId: string, approved: boolean) {
  loading.value = true
  errorMessage.value = null
  try {
    await govtechApi.approveAction({
      action_id: actionId,
      officer_id: officerId.value,
      approved,
      note: decisionNote.value,
    })
    await refreshAll()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refreshAll()
})
</script>

<template>
  <div class="portal-page">
    <!-- Top Crimson GovTech Ribbon -->
    <div class="gov-top-strip">
      <span>政务服务“一网通办”标准化数字平台 · 确定性政策本体 · 全流程 PII 脱敏审计</span>
      <span>P06 GovTech Policy &amp; Service Portal</span>
    </div>

    <!-- Dignified Portal Header -->
    <header class="portal-header">
      <div class="header-inner">
        <div class="brand-block">
          <div class="emblem">政务</div>
          <div>
            <h1>一网通办 · 政策公报与惠企便民智能向导</h1>
            <p class="subtitle">
              One-Stop GovTech Policy Gazette &amp; Step-by-Step Citizen/Enterprise Eligibility Wizard
            </p>
          </div>
        </div>
        <button type="button" class="btn-refresh" @click="refreshAll">
          刷新政务总览
        </button>
      </div>

      <!-- KPI Strip -->
      <div class="kpi-strip">
        <div v-for="card in kpiCards" :key="card.label" class="kpi-card" :class="card.tone">
          <small>{{ card.label }}</small>
          <strong>{{ card.value }}</strong>
        </div>
      </div>

      <!-- Portal Navigation -->
      <nav class="portal-nav" aria-label="主功能导航">
        <button
          type="button"
          class="nav-tab"
          :class="{ active: activeTab === 'wizard' }"
          @click="activeTab = 'wizard'"
        >
          一网通办四步向导
        </button>
        <button
          type="button"
          class="nav-tab"
          :class="{ active: activeTab === 'gazette' }"
          @click="activeTab = 'gazette'"
        >
          政策公报与修订比对
        </button>
        <button
          type="button"
          class="nav-tab"
          :class="{ active: activeTab === 'hitl' }"
          @click="activeTab = 'hitl'"
        >
          经办复核 (HITL) 与脱敏审计
          <span v-if="pendingActions.length" class="badge-count">{{ pendingActions.length }}</span>
        </button>
      </nav>
    </header>

    <main class="portal-main">
      <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

      <EligibilityWizard
        v-if="activeTab === 'wizard'"
        @refresh-overview="refreshAll"
      />

      <PolicyGazette
        v-else-if="activeTab === 'gazette'"
        :overview="overview"
        :wiki-pages="wikiPages"
      />

      <section v-else class="hitl-section">
        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>经办人人工复核队列 (HITL Sign-Off)</h2>
              <p>高额补贴或政策核定须经政务经办人员复核签批，批复后自动进入跨部门拨付流转。</p>
            </div>
            <div class="officer-inputs">
              <input v-model="officerId" type="text" placeholder="经办人工号" />
              <input v-model="decisionNote" type="text" placeholder="核准意见" />
            </div>
          </div>

          <div v-if="pendingActions.length" class="action-list">
            <div v-for="act in pendingActions" :key="act.action_id" class="action-card">
              <div class="action-info">
                <strong>{{ act.action_id }} · {{ act.program_id }}</strong>
                <span>
                  主体：{{ act.applicant_id }} · 牵头部门：{{ act.department }} · 金额：
                  <strong class="amt">¥{{ act.amount.toLocaleString() }}</strong>
                </span>
                <small>依据条款：{{ act.clause_citations.join('；') }}</small>
              </div>
              <div class="action-btns">
                <button
                  type="button"
                  class="btn-approve"
                  :disabled="loading"
                  @click="handleApproveAction(act.action_id, true)"
                >
                  核准通过
                </button>
                <button
                  type="button"
                  class="btn-reject"
                  :disabled="loading"
                  @click="handleApproveAction(act.action_id, false)"
                >
                  退回补正
                </button>
              </div>
            </div>
          </div>
          <div v-else class="empty-box">暂无待经办人复核的工单。</div>
        </div>

        <div class="panel-card">
          <h2>全链路 PII 脱敏审计日志 ({{ auditLogs.length }})</h2>
          <div class="audit-table-wrap">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>环节</th>
                  <th>脱敏类型</th>
                  <th>摘要</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in auditLogs" :key="log.event_id">
                  <td>{{ log.timestamp.slice(0, 19).replace('T', ' ') }}</td>
                  <td><span class="stage-pill">{{ log.stage }}</span></td>
                  <td>{{ log.masked_pii_types.join(', ') || '-' }}</td>
                  <td>{{ log.summary }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', system-ui, -apple-system, sans-serif;
  background: #fdfbf7;
  color: #0f172a;
}
</style>

<style scoped>
.portal-page {
  min-height: 100vh;
  background: #fdfbf7;
}

.gov-top-strip {
  background: #b91c1c;
  color: #ffffff;
  font-size: 0.78rem;
  padding: 0.4rem 1.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.portal-header {
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  padding: 1.15rem 1.5rem 0;
}

.header-inner {
  max-width: 1240px;
  margin: 0 auto 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.emblem {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, #b91c1c 0%, #991b1b 100%);
  color: #ffffff;
  font-weight: 800;
  font-size: 1.05rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(185, 28, 28, 0.25);
}

.brand-block h1 {
  margin: 0;
  font-size: 1.35rem;
  color: #0f172a;
}

.subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.82rem;
  color: #475569;
}

.btn-refresh {
  background: #fdfbf7;
  border: 1px solid #cbd5e1;
  color: #1d4ed8;
  font-weight: 600;
  padding: 0.5rem 0.95rem;
  border-radius: 6px;
  cursor: pointer;
}

.kpi-strip {
  max-width: 1240px;
  margin: 0 auto 1rem;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
}

.kpi-card {
  background: #fdfbf7;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #1d4ed8;
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.kpi-card.red {
  border-left-color: #b91c1c;
}

.kpi-card.slate {
  border-left-color: #475569;
}

.kpi-card small {
  font-size: 0.75rem;
  color: #64748b;
}

.kpi-card strong {
  font-size: 1.25rem;
  color: #0f172a;
}

.portal-nav {
  max-width: 1240px;
  margin: 0 auto;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.nav-tab {
  border: none;
  background: transparent;
  padding: 0.7rem 1.15rem;
  font-size: 0.92rem;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.nav-tab.active {
  color: #1d4ed8;
  border-bottom-color: #b91c1c;
  background: #fdfbf7;
}

.badge-count {
  background: #b91c1c;
  color: #ffffff;
  font-size: 0.72rem;
  padding: 0.08rem 0.45rem;
  border-radius: 999px;
}

.portal-main {
  max-width: 1240px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2.5rem;
}

.error-banner {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 8px;
  margin-bottom: 1rem;
}

.hitl-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.panel-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.15rem 1.25rem;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.panel-head h2,
.panel-card h2 {
  margin: 0;
  font-size: 1.05rem;
}

.panel-head p {
  margin: 0.2rem 0 0;
  font-size: 0.84rem;
  color: #64748b;
}

.officer-inputs {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.officer-inputs input {
  padding: 0.45rem 0.65rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fdfbf7;
  font-size: 0.84rem;
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.action-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.85rem 1rem;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #b91c1c;
  border-radius: 8px;
  background: #fdfbf7;
}

.action-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.86rem;
}

.amt {
  color: #b91c1c;
}

.action-btns {
  display: flex;
  gap: 0.5rem;
}

.btn-approve {
  background: #1d4ed8;
  color: #ffffff;
  border: none;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-reject {
  background: #ffffff;
  color: #b91c1c;
  border: 1px solid #fecaca;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.empty-box {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
  font-size: 0.88rem;
}

.audit-table-wrap {
  overflow-x: auto;
  margin-top: 0.75rem;
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.83rem;
}

.audit-table th,
.audit-table td {
  text-align: left;
  padding: 0.55rem 0.65rem;
  border-bottom: 1px solid #e2e8f0;
}

.audit-table th {
  background: #fdfbf7;
  color: #475569;
  font-weight: 700;
}

.stage-pill {
  background: #eff6ff;
  color: #1d4ed8;
  padding: 0.12rem 0.45rem;
  border-radius: 4px;
  font-weight: 600;
}

@media (max-width: 960px) {
  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
