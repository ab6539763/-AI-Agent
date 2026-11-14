<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  govtechApi,
  type DashboardOverview,
  type LintReport,
  type PolicyDiffResult,
  type WikiPageSummary,
} from '../api/client'

defineProps<{
  overview: DashboardOverview | null
  wikiPages: WikiPageSummary[]
}>()

const selectedPolicyId = ref<string>('POL-2026-TECH-01')
const diffResult = ref<PolicyDiffResult | null>(null)
const lintReport = ref<LintReport | null>(null)
const lintDate = ref<string>('2026-06-01')
const loadingDiff = ref(false)
const loadingLint = ref(false)
const errorMessage = ref<string | null>(null)

const gazettePolicies = [
  {
    policy_id: 'POL-2026-TECH-01',
    title: '高新技术企业研发创新补贴办法',
    department: '市科学技术局',
    status: 'active',
    version: '2026正式版',
  },
  {
    policy_id: 'POL-2026-HR-02',
    title: '青年人才安居与稳岗补贴实施细则',
    department: '市人力资源和社会保障局',
    status: 'active',
    version: '2026修订版',
  },
]

async function loadPolicyDiff(policyId: string) {
  selectedPolicyId.value = policyId
  loadingDiff.value = true
  errorMessage.value = null
  try {
    diffResult.value = await govtechApi.diffPolicyGazette({ policy_id: policyId })
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loadingDiff.value = false
  }
}

async function runGazetteLint() {
  loadingLint.value = true
  errorMessage.value = null
  try {
    lintReport.value = await govtechApi.lintWiki(lintDate.value)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loadingLint.value = false
  }
}

onMounted(() => {
  void loadPolicyDiff(selectedPolicyId.value)
})
</script>

<template>
  <section class="gazette-shell">
    <!-- Official Gazette Masthead -->
    <div class="gazette-masthead">
      <div class="masthead-seal">政</div>
      <div class="masthead-title">
        <div class="masthead-kicker">MUNICIPAL POLICY GAZETTE · 市政府政策公报与修订比对中心</div>
        <h2>现行政策公报、生效状态与条款修订对照</h2>
      </div>
      <div class="masthead-actions">
        <input v-model="lintDate" type="date" class="date-input" />
        <button
          type="button"
          class="btn-blue"
          :disabled="loadingLint"
          @click="runGazetteLint"
        >
          {{ loadingLint ? '巡检中...' : '公报效力巡检 (Lint)' }}
        </button>
      </div>
    </div>

    <div v-if="errorMessage" class="gazette-alert">{{ errorMessage }}</div>

    <div v-if="lintReport" class="lint-banner" :class="{ healthy: lintReport.healthy }">
      <strong>
        {{ lintReport.healthy ? '✓ 公报知识库效力健康' : '⚠ 发现公报效力异常' }}
      </strong>
      <span>
        基准日 {{ lintReport.reference_date }} · 过期政策 {{ lintReport.expired_policies.length }} 项 ·
        阈值冲突 {{ lintReport.conflicting_thresholds.length }} 项 · 孤立规则 {{ lintReport.orphan_rules.length }} 项
      </span>
    </div>

    <div class="gazette-layout">
      <!-- Left: Policy Selector & Effective Status -->
      <aside class="gazette-sidebar">
        <h3>公报目录（点击比对修订）</h3>
        <button
          v-for="pol in gazettePolicies"
          :key="pol.policy_id"
          type="button"
          class="policy-item"
          :class="{ active: selectedPolicyId === pol.policy_id }"
          @click="loadPolicyDiff(pol.policy_id)"
        >
          <div class="policy-item-top">
            <span class="pol-id">{{ pol.policy_id }}</span>
            <span class="eff-badge" :class="pol.status">
              {{ pol.status === 'active' ? '现行有效' : '已废止' }}
            </span>
          </div>
          <strong>{{ pol.title }}</strong>
          <small>{{ pol.department }} · {{ pol.version }}</small>
        </button>

        <div v-if="overview?.policies.length" class="registry-list">
          <h4>本体在库政策效力一览</h4>
          <div
            v-for="p in overview.policies"
            :key="p.policy_id"
            class="mini-pol-row"
          >
            <span>{{ p.policy_id }}</span>
            <span class="mini-status" :class="p.status">{{ p.status }}</span>
          </div>
        </div>
      </aside>

      <!-- Right: Diff Viewer -->
      <div class="gazette-viewer">
        <div v-if="loadingDiff" class="loading-box">正在比对政策修订条款...</div>

        <template v-else-if="diffResult">
          <div class="diff-header">
            <div>
              <div class="version-pills">
                <span class="ver-old">{{ diffResult.old_version }} ({{ diffResult.old_status }})</span>
                <span class="ver-arrow">→</span>
                <span class="ver-new">{{ diffResult.new_version }} ({{ diffResult.new_status }})</span>
              </div>
              <h3>{{ diffResult.title }}</h3>
              <p class="diff-summary">{{ diffResult.summary }}</p>
            </div>
            <div class="cap-delta-box" :class="{ positive: diffResult.subsidy_cap_delta > 0 }">
              <small>最高补贴上限变动</small>
              <strong>
                {{ diffResult.subsidy_cap_delta >= 0 ? '+' : '' }}¥{{
                  diffResult.subsidy_cap_delta.toLocaleString()
                }}
              </strong>
            </div>
          </div>

          <!-- Threshold Changes -->
          <div class="threshold-grid">
            <div
              v-for="tc in diffResult.threshold_changes"
              :key="tc.field"
              class="threshold-card"
              :class="tc.change_type"
            >
              <div class="tc-label">{{ tc.label }}</div>
              <div class="tc-values">
                <span class="old-val">{{ tc.old_value }}</span>
                <span class="tc-arrow">→</span>
                <span class="new-val">{{ tc.new_value }}</span>
              </div>
            </div>
          </div>

          <!-- Clause-by-Clause Diff -->
          <div class="clause-diff-list">
            <h4>条款逐条修订对照</h4>
            <div
              v-for="cd in diffResult.clause_diffs"
              :key="cd.clause_ref"
              class="clause-row"
              :class="cd.change_type"
            >
              <div class="clause-ref-col">
                <strong>{{ cd.clause_ref }}</strong>
                <span class="diff-tag" :class="cd.change_type">
                  {{
                    cd.change_type === 'added'
                      ? '新增'
                      : cd.change_type === 'removed'
                        ? '废止'
                        : cd.change_type === 'modified'
                          ? '修订'
                          : '不变'
                  }}
                </span>
              </div>
              <div class="clause-body-col">
                <div v-if="cd.old_text" class="text-old">
                  <small>原条款：</small>{{ cd.old_text }}
                </div>
                <div v-if="cd.new_text" class="text-new">
                  <small>现条款：</small>{{ cd.new_text }}
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Wiki Pages Reference -->
    <div v-if="wikiPages.length" class="wiki-strip">
      <h4>法规知识库已收录公报条目 ({{ wikiPages.length }})</h4>
      <div class="wiki-chips">
        <span v-for="w in wikiPages" :key="w.id" class="wiki-chip">
          [[{{ w.id }}]] {{ w.title }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.gazette-shell {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.gazette-masthead {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-top: 4px solid #b91c1c;
  border-radius: 10px;
  flex-wrap: wrap;
}

.masthead-seal {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: #b91c1c;
  color: #ffffff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 1.35rem;
  flex-shrink: 0;
}

.masthead-title {
  flex: 1;
}

.masthead-kicker {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  color: #b91c1c;
  font-weight: 700;
}

.masthead-title h2 {
  margin: 0.15rem 0 0;
  font-size: 1.15rem;
  color: #0f172a;
}

.masthead-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.date-input {
  padding: 0.45rem 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fdfbf7;
  font-size: 0.85rem;
}

.btn-blue {
  background: #1d4ed8;
  color: #ffffff;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.gazette-alert {
  padding: 0.7rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 8px;
}

.lint-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.7rem 1rem;
  border-radius: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 0.85rem;
}

.lint-banner.healthy {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.gazette-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 1rem;
}

.gazette-sidebar {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.gazette-sidebar h3 {
  margin: 0;
  font-size: 0.95rem;
  color: #0f172a;
}

.policy-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: left;
  padding: 0.75rem 0.85rem;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fdfbf7;
  cursor: pointer;
}

.policy-item.active {
  border-color: #b91c1c;
  background: #fef2f2;
}

.policy-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pol-id {
  font-size: 0.74rem;
  font-weight: 700;
  color: #1d4ed8;
}

.eff-badge {
  font-size: 0.7rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  font-weight: 700;
}

.eff-badge.active {
  background: #dcfce7;
  color: #166534;
}

.policy-item strong {
  font-size: 0.88rem;
  color: #0f172a;
}

.policy-item small {
  font-size: 0.75rem;
  color: #64748b;
}

.registry-list {
  margin-top: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f5f9;
}

.registry-list h4 {
  margin: 0 0 0.4rem;
  font-size: 0.82rem;
  color: #475569;
}

.mini-pol-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.78rem;
  padding: 0.25rem 0;
}

.mini-status {
  font-weight: 700;
  color: #166534;
}

.mini-status.expired {
  color: #b91c1c;
}

.gazette-viewer {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid #e2e8f0;
}

.version-pills {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.78rem;
  margin-bottom: 0.35rem;
}

.ver-old {
  background: #fee2e2;
  color: #991b1b;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
}

.ver-new {
  background: #dbeafe;
  color: #1d4ed8;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 700;
}

.diff-header h3 {
  margin: 0;
  font-size: 1.1rem;
}

.diff-summary {
  margin: 0.3rem 0 0;
  font-size: 0.86rem;
  color: #475569;
}

.cap-delta-box {
  padding: 0.65rem 1rem;
  border-radius: 8px;
  background: #fdfbf7;
  border: 1px solid #cbd5e1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.cap-delta-box.positive {
  background: #eff6ff;
  border-color: #93c5fd;
}

.cap-delta-box small {
  font-size: 0.74rem;
  color: #64748b;
}

.cap-delta-box strong {
  font-size: 1.15rem;
  color: #b91c1c;
}

.threshold-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.threshold-card {
  padding: 0.75rem;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fdfbf7;
}

.threshold-card.increased,
.threshold-card.modified {
  border-left: 3px solid #1d4ed8;
}

.tc-label {
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 0.3rem;
}

.tc-values {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  font-size: 0.84rem;
}

.old-val {
  color: #991b1b;
  text-decoration: line-through;
}

.new-val {
  color: #1d4ed8;
  font-weight: 700;
}

.clause-diff-list h4 {
  margin: 0 0 0.6rem;
  font-size: 0.95rem;
}

.clause-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  margin-bottom: 0.55rem;
  background: #fdfbf7;
}

.clause-row.added {
  border-left: 4px solid #1d4ed8;
  background: #eff6ff;
}

.clause-row.modified {
  border-left: 4px solid #b91c1c;
}

.clause-ref-col {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.diff-tag {
  display: inline-block;
  width: fit-content;
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-weight: 700;
  background: #e2e8f0;
  color: #334155;
}

.diff-tag.added {
  background: #1d4ed8;
  color: #ffffff;
}

.diff-tag.modified {
  background: #b91c1c;
  color: #ffffff;
}

.text-old {
  font-size: 0.83rem;
  color: #991b1b;
  background: #fef2f2;
  padding: 0.35rem 0.55rem;
  border-radius: 4px;
  margin-bottom: 0.3rem;
}

.text-new {
  font-size: 0.85rem;
  color: #0f172a;
  background: #ffffff;
  padding: 0.35rem 0.55rem;
  border-radius: 4px;
  border: 1px solid #dbeafe;
}

.wiki-strip {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.9rem 1.1rem;
}

.wiki-strip h4 {
  margin: 0 0 0.5rem;
  font-size: 0.88rem;
}

.wiki-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.wiki-chip {
  background: #fdfbf7;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0.25rem 0.6rem;
  font-size: 0.78rem;
  color: #1e293b;
}

.loading-box {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

@media (max-width: 960px) {
  .gazette-layout,
  .threshold-grid,
  .clause-row {
    grid-template-columns: 1fr;
  }
}
</style>
