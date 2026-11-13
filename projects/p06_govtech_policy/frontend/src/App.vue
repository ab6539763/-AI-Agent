<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  govtechApi,
  type AuditEvent,
  type BatchMatchResponse,
  type CitizenProfile,
  type DashboardOverview,
  type GovAction,
  type LintReport,
  type PolicyAskResponse,
  type WikiPageSummary,
} from './api/client'

type WorkbenchTab = 'match' | 'ontology' | 'wiki' | 'hitl'

const activeTab = ref<WorkbenchTab>('match')
const loading = ref(false)
const errorMessage = ref<string | null>(null)

const overview = ref<DashboardOverview | null>(null)
const wikiPages = ref<WikiPageSummary[]>([])
const pendingActions = ref<GovAction[]>([])
const auditLogs = ref<AuditEvent[]>([])
const lintReport = ref<LintReport | null>(null)

// Tab 1: Policy Ask & Batch Match
const askQuestion = ref(
  '我司（统一社会信用代码91310000MA1K3XYZ88，联系人手机13812345678）是否符合高新技术企业研发补贴？',
)
const applicantForm = reactive<CitizenProfile>({
  applicant_id: 'ENT-2026-001',
  applicant_type: 'enterprise',
  name: '星辰智能科技有限公司',
  identifier: '91310000MA1K3XYZ88',
  region: '浦东新区',
  annual_income_or_revenue: 3500000,
  employee_count: 42,
  industry: '人工智能',
  tags: ['高新技术', '专精特新'],
})
const tagsInput = ref('高新技术, 专精特新')
const selectedProgramId = ref<string>('')
const createHitlAction = ref(true)
const askResult = ref<PolicyAskResponse | null>(null)
const batchResult = ref<BatchMatchResponse | null>(null)

// Tab 3: Wiki Ingest Form
const ingestForm = reactive({
  doc_id: 'POL-2026-MFG-03',
  title: '专精特新制造业数字化转型补贴办法',
  department: '市工业和信息化局',
  content: '支持本市专精特新企业开展智能制造与数字化车间改造，按投入比例给予财政补贴。',
  effective_date: '2026-01-01',
  expiry_date: '2027-12-31',
  subsidy_threshold: 300000,
  clause_ref: '§第2条',
  clause_text: '对列入市级专精特新名单的制造业企业给予最高30万元改造补助。',
})
const lintReferenceDate = ref('2026-06-01')

// Tab 4: HITL Officer Sign-off
const officerId = ref('OFFICER-ZHANG-07')
const decisionNote = ref('材料齐全，符合条款规定，予以核准。')

const kpiCards = computed(() => {
  const ov = overview.value
  return [
    {
      label: '现行有效政策',
      value: ov ? `${ov.active_policies} / ${ov.total_policies}` : '-',
      accent: 'navy',
    },
    {
      label: '惠企便民项目',
      value: ov ? String(ov.benefit_programs) : '-',
      accent: 'teal',
    },
    {
      label: '法规 Wiki 词条',
      value: ov ? String(ov.wiki_pages) : '-',
      accent: 'indigo',
    },
    {
      label: '待经办人 HITL 复核',
      value: ov ? String(ov.pending_hitl_reviews) : '-',
      accent: 'amber',
    },
    {
      label: '脱敏审计日志',
      value: ov ? String(ov.audit_logs_count) : '-',
      accent: 'slate',
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
      govtechApi.getAuditLogs(100),
    ])
    overview.value = ov
    wikiPages.value = pages
    pendingActions.value = pending
    auditLogs.value = logs
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  }
}

async function handlePolicyAsk() {
  loading.value = true
  errorMessage.value = null
  try {
    applicantForm.tags = tagsInput.value
      .split(/[,，]/)
      .map((t) => t.trim())
      .filter(Boolean)

    askResult.value = await govtechApi.askPolicy({
      question: askQuestion.value,
      profile: { ...applicantForm },
      program_id: selectedProgramId.value || null,
      create_hitl_action: createHitlAction.value,
    })
    await refreshAll()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function handleBatchMatchDemo() {
  loading.value = true
  errorMessage.value = null
  try {
    applicantForm.tags = tagsInput.value
      .split(/[,，]/)
      .map((t) => t.trim())
      .filter(Boolean)

    const sampleProfiles: CitizenProfile[] = [
      { ...applicantForm },
      {
        applicant_id: 'CIT-2026-088',
        applicant_type: 'citizen',
        name: '李明',
        identifier: '310101199505051234',
        region: '静安区',
        annual_income_or_revenue: 180000,
        employee_count: 0,
        industry: '集成电路',
        tags: ['青年人才'],
      },
      {
        applicant_id: 'ENT-2026-099',
        applicant_type: 'enterprise',
        name: '微光初创工作室',
        identifier: '91310000MA1K9ABC12',
        region: '徐汇区',
        annual_income_or_revenue: 200000,
        employee_count: 3,
        industry: '软件服务',
        tags: ['高新技术'],
      },
    ]

    batchResult.value = await govtechApi.batchMatch({ profiles: sampleProfiles })
    await refreshAll()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function handleWikiIngest() {
  loading.value = true
  errorMessage.value = null
  try {
    await govtechApi.ingestWiki({
      doc_id: ingestForm.doc_id,
      title: ingestForm.title,
      content: ingestForm.content,
      department: ingestForm.department,
      effective_date: ingestForm.effective_date,
      expiry_date: ingestForm.expiry_date || null,
      subsidy_threshold: ingestForm.subsidy_threshold,
      clauses: {
        [ingestForm.clause_ref]: ingestForm.clause_text,
      },
    })
    await refreshAll()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function handleWikiLint() {
  loading.value = true
  errorMessage.value = null
  try {
    lintReport.value = await govtechApi.lintWiki(lintReferenceDate.value || undefined)
    await refreshAll()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
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
  <div class="gov-shell">
    <header class="gov-header">
      <div class="gov-brand">
        <span class="gov-badge">P06 GOVTECH</span>
        <div>
          <h1>政务服务与企业政策通智能体工作台</h1>
          <p>本体规则核验 · PII 自动脱敏 · 法规 LLM Wiki · 经办人 HITL 合规复核</p>
        </div>
      </div>
      <button class="btn-outline" :disabled="loading" @click="refreshAll">
        刷新数据
      </button>
    </header>

    <section class="kpi-grid">
      <div v-for="card in kpiCards" :key="card.label" :class="['kpi-card', card.accent]">
        <div class="kpi-label">{{ card.label }}</div>
        <div class="kpi-value">{{ card.value }}</div>
      </div>
    </section>

    <nav class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'match' }]"
        @click="activeTab = 'match'"
      >
        1. 政策智配与资格核验
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        2. 政策本体图谱
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        3. 法规 LLM Wiki
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        4. 经办人 HITL 复核与审计
        <span v-if="pendingActions.length" class="pill-count">{{ pendingActions.length }}</span>
      </button>
    </nav>

    <div v-if="errorMessage" class="alert-error">
      请求异常：{{ errorMessage }}
    </div>

    <!-- Tab 1: 政策智配与资格核验 -->
    <main v-if="activeTab === 'match'" class="panel-grid">
      <section class="card">
        <h2>智能政策问答与资格核验</h2>
        <div class="form-group">
          <label>咨询问题（支持身份证 / 统一社会信用代码 / 手机号自动脱敏）</label>
          <textarea v-model="askQuestion" rows="3" />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>主体类型</label>
            <select v-model="applicantForm.applicant_type">
              <option value="enterprise">企业法人 (enterprise)</option>
              <option value="citizen">自然人 (citizen)</option>
            </select>
          </div>
          <div class="form-group">
            <label>申请人 / 企业名称</label>
            <input v-model="applicantForm.name" />
          </div>
          <div class="form-group">
            <label>证件号 / 信用代码</label>
            <input v-model="applicantForm.identifier" />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>年营收 / 年收入 (CNY)</label>
            <input v-model.number="applicantForm.annual_income_or_revenue" type="number" />
          </div>
          <div class="form-group">
            <label>员工人数</label>
            <input v-model.number="applicantForm.employee_count" type="number" />
          </div>
          <div class="form-group">
            <label>资质标签（逗号分隔）</label>
            <input v-model="tagsInput" />
          </div>
        </div>

        <div class="form-row align-center">
          <div class="form-group">
            <label>指定补贴项目（可选）</label>
            <select v-model="selectedProgramId">
              <option value="">自动匹配全部项目</option>
              <option
                v-for="prog in overview?.programs || []"
                :key="prog.program_id"
                :value="prog.program_id"
              >
                {{ prog.name }} ({{ prog.program_id }})
              </option>
            </select>
          </div>
          <label class="checkbox-label">
            <input v-model="createHitlAction" type="checkbox" />
            生成经办人 HITL 待复核工单
          </label>
        </div>

        <div class="actions-row">
          <button class="btn-primary" :disabled="loading" @click="handlePolicyAsk">
            执行政策智配与资格核验
          </button>
          <button class="btn-secondary" :disabled="loading" @click="handleBatchMatchDemo">
            批量政策匹配矩阵 (3 类主体示例)
          </button>
        </div>

        <div v-if="askResult" class="result-box">
          <div class="result-header">
            <span :class="['status-badge', askResult.status]">
              {{ askResult.status === 'answered' ? '已依据条款答复' : '无依据拒绝承诺' }}
            </span>
            <span>责任部门：<strong>{{ askResult.department }}</strong></span>
            <span>请求号：<code>{{ askResult.request_id }}</code></span>
          </div>
          <p class="masked-line">
            <strong>脱敏后问题：</strong>{{ askResult.masked_question }}
            <span v-if="askResult.masked_pii_types.length" class="tag-chip">
              已脱敏: {{ askResult.masked_pii_types.join(', ') }}
            </span>
          </p>
          <p class="answer-text">{{ askResult.answer }}</p>
          <div v-if="askResult.clause_citations.length" class="citations">
            <strong>引用政策条款：</strong>
            <span v-for="c in askResult.clause_citations" :key="c" class="tag-chip">{{ c }}</span>
          </div>
          <div v-if="askResult.pending_action" class="hitl-banner">
            已创建 HITL 审批单：<code>{{ askResult.pending_action.action_id }}</code>
            （状态：{{ askResult.pending_action.status }}，补贴金额：¥{{
              askResult.pending_action.amount.toLocaleString()
            }}）
          </div>
        </div>
      </section>

      <section v-if="batchResult" class="card">
        <h2>多项目批量政策匹配矩阵 ({{ batchResult.batch_id }})</h2>
        <p class="sub-info">
          共评估 {{ batchResult.total_applicants }} 个主体 × {{ batchResult.total_programs_evaluated }}
          个项目 · 符合条件主体 {{ batchResult.eligible_applicants }} 个 · 潜在补贴总额
          <strong>¥{{ batchResult.total_potential_subsidy.toLocaleString() }}</strong>
        </p>
        <table class="data-table">
          <thead>
            <tr>
              <th>主体</th>
              <th>类型</th>
              <th>脱敏证件号</th>
              <th>所属区域</th>
              <th>匹配项目数</th>
              <th>预计补贴 (CNY)</th>
              <th>主责部门</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in batchResult.matrix" :key="row.applicant_id">
              <td>{{ row.applicant_name }} ({{ row.applicant_id }})</td>
              <td>{{ row.applicant_type }}</td>
              <td><code>{{ row.masked_identifier }}</code></td>
              <td>{{ row.region }}</td>
              <td>{{ row.eligible_count }} / {{ row.evaluations.length }}</td>
              <td>¥{{ row.total_estimated_subsidy.toLocaleString() }}</td>
              <td>{{ row.recommended_department }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>

    <!-- Tab 2: 政策本体图谱 -->
    <main v-if="activeTab === 'ontology'" class="panel-grid">
      <section class="card">
        <h2>政策与惠企项目本体清单</h2>
        <div class="two-col">
          <div>
            <h3>现行政策文件 ({{ overview?.policies.length || 0 }})</h3>
            <div v-for="p in overview?.policies || []" :key="p.policy_id" class="entity-card">
              <div class="entity-title">
                <code>{{ p.policy_id }}</code> {{ p.title }}
              </div>
              <div class="entity-meta">
                部门：{{ p.department }} · 状态：{{ p.status }} · 有效期：{{ p.effective_date }} ~
                {{ p.expiry_date || '长期' }}
              </div>
            </div>
          </div>
          <div>
            <h3>补贴项目与 HITL 阈值 ({{ overview?.programs.length || 0 }})</h3>
            <div v-for="prog in overview?.programs || []" :key="prog.program_id" class="entity-card">
              <div class="entity-title">
                <code>{{ prog.program_id }}</code> {{ prog.name }}
              </div>
              <div class="entity-meta">
                部门：{{ prog.department }} · 最高补贴：¥{{ prog.max_subsidy_amount.toLocaleString() }} ·
                HITL 阈值：¥{{ prog.hitl_threshold_amount.toLocaleString() }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>本体语义关系图谱 ({{ overview?.ontology_links.length || 0 }} 条关系)</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>源实体 (Source)</th>
              <th>语义关系 (Relation)</th>
              <th>目标实体 (Target)</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(lnk, idx) in overview?.ontology_links || []"
              :key="`${lnk.source_id}-${lnk.target_id}-${idx}`"
            >
              <td><code>{{ lnk.source_id }}</code></td>
              <td><span class="tag-chip">{{ lnk.relation_type }}</span></td>
              <td><code>{{ lnk.target_id }}</code></td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>

    <!-- Tab 3: 法规 LLM Wiki -->
    <main v-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <div class="section-header">
          <h2>法规 LLM Wiki 知识库 ({{ wikiPages.length }} 词条)</h2>
          <div class="inline-controls">
            <input v-model="lintReferenceDate" placeholder="基准日期 YYYY-MM-DD" />
            <button class="btn-primary" :disabled="loading" @click="handleWikiLint">
              运行合规体检 (Lint)
            </button>
          </div>
        </div>

        <div v-if="lintReport" class="result-box">
          <div class="result-header">
            <span :class="['status-badge', lintReport.healthy ? 'answered' : 'refused']">
              {{ lintReport.healthy ? '知识库健康 (0 异常)' : `发现 ${lintReport.issues.length} 项异常` }}
            </span>
            <span>基准日：{{ lintReport.reference_date }}</span>
            <span>扫描词条：{{ lintReport.total_entities }}</span>
          </div>
          <ul v-if="lintReport.issues.length" class="issue-list">
            <li v-for="(iss, idx) in lintReport.issues" :key="idx">
              [{{ iss.severity }} / {{ iss.issue_type }}] {{ iss.message }}
            </li>
          </ul>
        </div>

        <div class="wiki-list">
          <div v-for="page in wikiPages" :key="page.id" class="entity-card">
            <div class="entity-title">
              <code>{{ page.id }}</code> {{ page.title }}
            </div>
            <div class="entity-meta">
              {{ page.department }} · {{ page.entity_type }} · 路径：<code>{{ page.path }}</code>
            </div>
            <p class="wiki-preview">{{ page.preview }}</p>
            <div v-if="page.wiki_links.length" class="citations">
              <span v-for="lnk in page.wiki_links" :key="lnk" class="tag-chip">[[{{ lnk }}]]</span>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>新增 / 更新政策 Wiki 词条</h2>
        <div class="form-row">
          <div class="form-group">
            <label>文档编号 (doc_id)</label>
            <input v-model="ingestForm.doc_id" />
          </div>
          <div class="form-group">
            <label>政策标题</label>
            <input v-model="ingestForm.title" />
          </div>
          <div class="form-group">
            <label>责任部门</label>
            <input v-model="ingestForm.department" />
          </div>
        </div>
        <div class="form-group">
          <label>政策正文摘要</label>
          <textarea v-model="ingestForm.content" rows="2" />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>生效日期</label>
            <input v-model="ingestForm.effective_date" />
          </div>
          <div class="form-group">
            <label>失效日期</label>
            <input v-model="ingestForm.expiry_date" />
          </div>
          <div class="form-group">
            <label>条款编号 & 内容</label>
            <input v-model="ingestForm.clause_text" />
          </div>
        </div>
        <button class="btn-primary" :disabled="loading" @click="handleWikiIngest">
          入库至 LLM Wiki
        </button>
      </section>
    </main>

    <!-- Tab 4: 经办人 HITL 复核与审计 -->
    <main v-if="activeTab === 'hitl'" class="panel-grid">
      <section class="card">
        <h2>待经办人复核工单 (HITL Queue)</h2>
        <div class="form-row">
          <div class="form-group">
            <label>经办人编号 (Officer ID)</label>
            <input v-model="officerId" />
          </div>
          <div class="form-group">
            <label>审批意见备注</label>
            <input v-model="decisionNote" />
          </div>
        </div>

        <div v-if="!pendingActions.length" class="empty-state">
          当前暂无待复核 HITL 工单。可在「1. 政策智配与资格核验」中提交申请生成。
        </div>

        <table v-else class="data-table">
          <thead>
            <tr>
              <th>工单号</th>
              <th>申请人</th>
              <th>项目</th>
              <th>部门</th>
              <th>补贴金额</th>
              <th>引用条款</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="act in pendingActions" :key="act.action_id">
              <td><code>{{ act.action_id }}</code></td>
              <td>{{ act.applicant_id }}</td>
              <td>{{ act.program_id }}</td>
              <td>{{ act.department }}</td>
              <td>¥{{ act.amount.toLocaleString() }}</td>
              <td>{{ act.clause_citations.join('; ') }}</td>
              <td class="action-btns">
                <button
                  class="btn-approve"
                  :disabled="loading"
                  @click="handleApproveAction(act.action_id, true)"
                >
                  核准
                </button>
                <button
                  class="btn-reject"
                  :disabled="loading"
                  @click="handleApproveAction(act.action_id, false)"
                >
                  驳回
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>PII 脱敏不可篡改审计日志 ({{ auditLogs.length }})</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>时间 (UTC)</th>
              <th>阶段</th>
              <th>主体</th>
              <th>已脱敏字段</th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ev in auditLogs" :key="ev.event_id">
              <td><code>{{ ev.timestamp.slice(0, 19) }}</code></td>
              <td><span class="tag-chip">{{ ev.stage }}</span></td>
              <td>{{ ev.actor }}</td>
              <td>{{ ev.masked_pii_types.join(', ') || '-' }}</td>
              <td>{{ ev.summary }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<style scoped>
.gov-shell {
  min-height: 100vh;
  background: #f3f6fb;
  color: #162235;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  padding: 20px 28px 48px;
}

.gov-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #0f2a52 0%, #1b437d 100%);
  color: #ffffff;
  padding: 18px 24px;
  border-radius: 12px;
  margin-bottom: 18px;
  box-shadow: 0 6px 18px rgba(15, 42, 82, 0.16);
}

.gov-brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.gov-brand h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.gov-brand p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #cfe0f7;
}

.gov-badge {
  background: #f59e0b;
  color: #0f2a52;
  font-weight: 800;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 6px;
  letter-spacing: 0.5px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.kpi-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 14px 16px;
  border-left: 4px solid #1b437d;
  box-shadow: 0 2px 8px rgba(15, 42, 82, 0.06);
}

.kpi-card.teal { border-left-color: #0d9488; }
.kpi-card.indigo { border-left-color: #4f46e5; }
.kpi-card.amber { border-left-color: #d97706; }
.kpi-card.slate { border-left-color: #475569; }

.kpi-label {
  font-size: 12px;
  color: #5b6b82;
}

.kpi-value {
  font-size: 24px;
  font-weight: 700;
  margin-top: 4px;
}

.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.tab-btn {
  background: #ffffff;
  border: 1px solid #d5dfec;
  color: #31435c;
  padding: 10px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tab-btn.active {
  background: #1b437d;
  color: #ffffff;
  border-color: #1b437d;
}

.pill-count {
  background: #ef4444;
  color: #ffffff;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 12px;
}

.panel-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background: #ffffff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(15, 42, 82, 0.06);
}

.card h2 {
  margin: 0 0 14px;
  font-size: 17px;
  color: #0f2a52;
}

.card h3 {
  margin: 0 0 10px;
  font-size: 15px;
  color: #1b437d;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  flex: 1;
}

.form-group label {
  font-size: 12px;
  font-weight: 600;
  color: #4b5c74;
}

.form-group input,
.form-group select,
.form-group textarea {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 14px;
  font-family: inherit;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 12px;
}

.align-center {
  align-items: center;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1e3a5f;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
}

.btn-primary,
.btn-secondary,
.btn-outline,
.btn-approve,
.btn-reject {
  border: none;
  border-radius: 6px;
  padding: 9px 16px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary {
  background: #1b437d;
  color: #ffffff;
}

.btn-secondary {
  background: #0d9488;
  color: #ffffff;
}

.btn-outline {
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.35);
}

.btn-approve {
  background: #16a34a;
  color: #ffffff;
  padding: 5px 10px;
  font-size: 12px;
}

.btn-reject {
  background: #dc2626;
  color: #ffffff;
  padding: 5px 10px;
  font-size: 12px;
}

.result-box {
  margin-top: 16px;
  background: #f8fafc;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  padding: 14px;
}

.result-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.status-badge {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.status-badge.answered {
  background: #dcfce7;
  color: #166534;
}

.status-badge.refused {
  background: #fee2e2;
  color: #991b1b;
}

.tag-chip {
  display: inline-block;
  background: #e2e8f0;
  color: #1e293b;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  margin-right: 6px;
}

.hitl-banner {
  margin-top: 10px;
  padding: 8px 12px;
  background: #fef3c7;
  color: #92400e;
  border-radius: 6px;
  font-size: 13px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid #e2e8f0;
}

.data-table th {
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
}

.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.entity-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fcfdff;
}

.entity-title {
  font-weight: 700;
  margin-bottom: 4px;
}

.entity-meta {
  font-size: 12px;
  color: #64748b;
}

.wiki-preview {
  font-size: 13px;
  color: #334155;
  margin: 8px 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.inline-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.inline-controls input {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 13px;
}

.action-btns {
  display: flex;
  gap: 6px;
}

.alert-error {
  background: #fee2e2;
  color: #991b1b;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 14px;
  font-size: 14px;
}

.empty-state {
  padding: 18px;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border-radius: 8px;
}
</style>
