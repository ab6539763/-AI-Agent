<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  govtechApi,
  type CitizenProfile,
  type EligibilityEvaluation,
  type PolicyAskResponse,
  type WorkflowRouteResult,
} from '../api/client'

const emit = defineEmits<{
  (e: 'refresh-overview'): void
}>()

const currentStep = ref<1 | 2 | 3 | 4>(1)
const loading = ref(false)
const errorMessage = ref<string | null>(null)

const profile = reactive<CitizenProfile>({
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
const questionText = ref(
  '我司（统一社会信用代码91310000MA1K3XYZ88，联系人手机13812345678）申请高新技术企业研发补贴，请核验资格并生成跨部门办理流转单。',
)
const createHitlAction = ref(true)

const askResult = ref<PolicyAskResponse | null>(null)
const selectedProgramId = ref<string>('')
const workflowResult = ref<WorkflowRouteResult | null>(null)
const checkedDocs = ref<Record<string, boolean>>({})
const simulatedBureauStep = ref<number>(1)

const wizardSteps = [
  { step: 1 as const, label: '1. 填报画像', desc: '企业/个人主体信息' },
  { step: 2 as const, label: '2. 智能匹配', desc: '本体规则与条款核验' },
  { step: 3 as const, label: '3. 材料清单', desc: '申报材料核对确认' },
  { step: 4 as const, label: '4. 跨部门流转进度条', desc: '人社局 → 科技局 → 财政局' },
]

function applyEnterprisePreset() {
  profile.applicant_id = 'ENT-2026-001'
  profile.applicant_type = 'enterprise'
  profile.name = '星辰智能科技有限公司'
  profile.identifier = '91310000MA1K3XYZ88'
  profile.region = '浦东新区'
  profile.annual_income_or_revenue = 3500000
  profile.employee_count = 42
  profile.industry = '人工智能'
  tagsInput.value = '高新技术, 专精特新'
  questionText.value =
    '我司（统一社会信用代码91310000MA1K3XYZ88，联系人手机13812345678）申请高新技术企业研发补贴，请核验资格。'
}

function applyCitizenPreset() {
  profile.applicant_id = 'CIT-2026-088'
  profile.applicant_type = 'citizen'
  profile.name = '林晓'
  profile.identifier = '310101199808081234'
  profile.region = '徐汇区'
  profile.annual_income_or_revenue = 190000
  profile.employee_count = 0
  profile.industry = '集成电路'
  tagsInput.value = '青年人才'
  questionText.value =
    '本人（身份证310101199808081234，手机13900001111）符合青年人才安居补贴条件吗？'
}

const selectedEvaluation = computed<EligibilityEvaluation | null>(() => {
  if (!askResult.value?.eligibility_evaluations.length) return null
  return (
    askResult.value.eligibility_evaluations.find(
      (ev) => ev.program_id === selectedProgramId.value,
    ) || askResult.value.eligibility_evaluations[0]
  )
})

const allDocsChecked = computed(() => {
  const docs = workflowResult.value?.consolidated_documents || []
  if (!docs.length) return true
  return docs.every((doc) => Boolean(checkedDocs.value[doc]))
})

async function runStep1Match() {
  loading.value = true
  errorMessage.value = null
  try {
    profile.tags = tagsInput.value
      .split(/[,，]/)
      .map((t) => t.trim())
      .filter(Boolean)

    const res = await govtechApi.askPolicy({
      question: questionText.value,
      profile: { ...profile },
      create_hitl_action: createHitlAction.value,
    })
    askResult.value = res
    const firstEligible =
      res.eligibility_evaluations.find((e) => e.eligible) ||
      res.eligibility_evaluations[0]
    selectedProgramId.value = firstEligible ? firstEligible.program_id : 'PROG-TECH-RD-500K'
    currentStep.value = 2
    emit('refresh-overview')
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function prepareChecklistAndRoute(targetStep: 3 | 4, stepProgress = 1) {
  loading.value = true
  errorMessage.value = null
  try {
    const ev = selectedEvaluation.value
    const routeRes = await govtechApi.routeCase({
      applicant_id: profile.applicant_id,
      applicant_type: profile.applicant_type,
      program_id: ev?.program_id || selectedProgramId.value || 'PROG-TECH-RD-500K',
      program_name: ev?.program_name || '高新技术企业研发补贴',
      amount: ev?.estimated_subsidy || 500000,
      approved: true,
      tags: profile.tags,
      current_step: stepProgress,
    })
    workflowResult.value = routeRes
    simulatedBureauStep.value = stepProgress
    if (targetStep === 3) {
      const nextChecked: Record<string, boolean> = {}
      for (const doc of routeRes.consolidated_documents) {
        nextChecked[doc] = checkedDocs.value[doc] ?? true
      }
      checkedDocs.value = nextChecked
    }
    currentStep.value = targetStep
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function advanceBureauStage(step: number) {
  await prepareChecklistAndRoute(4, step)
}
</script>

<template>
  <section class="wizard-shell">
    <!-- 4-Step Progress Stepper -->
    <div class="stepper-bar" role="tablist" aria-label="一网通办四步向导">
      <button
        v-for="item in wizardSteps"
        :key="item.step"
        type="button"
        class="stepper-node"
        :class="{
          active: currentStep === item.step,
          done: currentStep > item.step,
        }"
        @click="currentStep = item.step"
      >
        <span class="step-badge">{{ currentStep > item.step ? '✓' : item.step }}</span>
        <span class="step-meta">
          <strong>{{ item.label }}</strong>
          <small>{{ item.desc }}</small>
        </span>
      </button>
    </div>

    <div v-if="errorMessage" class="wizard-alert">
      {{ errorMessage }}
    </div>

    <!-- Step 1: 填报画像 -->
    <div v-if="currentStep === 1" class="wizard-card">
      <div class="card-head">
        <div>
          <h2>第一步：填报申请人画像（自动 PII 脱敏保护）</h2>
          <p class="sub">
            支持法人企业与个人青年人才两类主体，身份证号、统一社会信用代码与手机号在审计链路自动脱敏。
          </p>
        </div>
        <div class="preset-group">
          <button type="button" class="btn-outline" @click="applyEnterprisePreset">
            示例：高新技术企业
          </button>
          <button type="button" class="btn-outline" @click="applyCitizenPreset">
            示例：青年人才个人
          </button>
        </div>
      </div>

      <div class="form-grid">
        <label class="field">
          <span>主体类型</span>
          <select v-model="profile.applicant_type">
            <option value="enterprise">企业法人 (Enterprise)</option>
            <option value="citizen">个人市民 (Citizen)</option>
          </select>
        </label>
        <label class="field">
          <span>名称 / 姓名</span>
          <input v-model="profile.name" type="text" placeholder="企业全称或个人姓名" />
        </label>
        <label class="field">
          <span>统一社会信用代码 / 身份证号</span>
          <input v-model="profile.identifier" type="text" />
        </label>
        <label class="field">
          <span>所在行政区</span>
          <input v-model="profile.region" type="text" />
        </label>
        <label class="field">
          <span>年营收 / 年收入（元）</span>
          <input v-model.number="profile.annual_income_or_revenue" type="number" min="0" />
        </label>
        <label class="field">
          <span>参保员工人数</span>
          <input v-model.number="profile.employee_count" type="number" min="0" />
        </label>
        <label class="field">
          <span>所属重点产业</span>
          <input v-model="profile.industry" type="text" />
        </label>
        <label class="field">
          <span>政策资质标签（逗号分隔）</span>
          <input v-model="tagsInput" type="text" placeholder="高新技术, 专精特新" />
        </label>
      </div>

      <label class="field full-width">
        <span>政策诉求描述（含敏感信息测试）</span>
        <textarea v-model="questionText" rows="2"></textarea>
      </label>

      <div class="card-footer">
        <label class="checkbox-inline">
          <input v-model="createHitlAction" type="checkbox" />
          <span>命中条款后同步生成待经办人 HITL 复核工单</span>
        </label>
        <button
          type="button"
          class="btn-primary"
          :disabled="loading"
          @click="runStep1Match"
        >
          {{ loading ? '正在核验政策本体...' : '下一步：智能匹配政策 →' }}
        </button>
      </div>
    </div>

    <!-- Step 2: 智能匹配 -->
    <div v-else-if="currentStep === 2" class="wizard-card">
      <div class="card-head">
        <div>
          <h2>第二步：政策本体智能匹配与条款溯源</h2>
          <p class="sub">
            基于确定性规则引擎逐条核验，零幻觉输出可点击条款编号。
          </p>
        </div>
        <button type="button" class="btn-outline" @click="currentStep = 1">
          ← 返回修改画像
        </button>
      </div>

      <div v-if="askResult" class="match-summary-box">
        <div class="pii-banner">
          <span class="tag-red">PII 已脱敏</span>
          <span>脱敏字段：{{ askResult.masked_pii_types.join('、') || '无' }}</span>
          <span class="muted">｜ 脱敏问题：{{ askResult.masked_question }}</span>
        </div>
        <p class="answer-text">{{ askResult.answer }}</p>
      </div>

      <div v-if="askResult?.eligibility_evaluations.length" class="eval-grid">
        <div
          v-for="ev in askResult.eligibility_evaluations"
          :key="ev.program_id"
          class="eval-card"
          :class="{
            eligible: ev.eligible,
            selected: selectedProgramId === ev.program_id,
          }"
          @click="selectedProgramId = ev.program_id"
        >
          <div class="eval-top">
            <span class="status-pill" :class="ev.eligible ? 'pill-pass' : 'pill-fail'">
              {{ ev.eligible ? '符合申报条件' : '暂不满足条件' }}
            </span>
            <span class="dept-badge">{{ ev.department }}</span>
          </div>
          <h3>{{ ev.program_name }}</h3>
          <div class="subsidy-num">
            预估可享补贴：<strong>¥{{ ev.estimated_subsidy.toLocaleString() }}</strong>
          </div>
          <ul class="rule-list">
            <li v-for="r in ev.matched_rules" :key="r.rule_id" class="rule-pass">
              ✓ {{ r.description || r.field }} <small>({{ r.clause_ref }})</small>
            </li>
            <li v-for="r in ev.failed_rules" :key="r.rule_id" class="rule-fail">
              ✕ {{ r.description || r.field }} <small>({{ r.clause_ref }})</small>
            </li>
          </ul>
        </div>
      </div>

      <div v-else class="empty-note">
        请先在第一步提交画像以获取智能匹配结果。
      </div>

      <div class="card-footer">
        <span class="muted">
          已选项目：<strong>{{ selectedEvaluation?.program_name || selectedProgramId || '未选择' }}</strong>
        </span>
        <button
          type="button"
          class="btn-primary"
          :disabled="loading || !askResult"
          @click="prepareChecklistAndRoute(3, 1)"
        >
          {{ loading ? '生成材料清单...' : '下一步：确认材料清单 →' }}
        </button>
      </div>
    </div>

    <!-- Step 3: 材料清单 -->
    <div v-else-if="currentStep === 3" class="wizard-card">
      <div class="card-head">
        <div>
          <h2>第三步：跨部门联办申报材料清单</h2>
          <p class="sub">
            系统已根据所选项目自动汇总人社、科技、财政三部门所需电子证照与纸质材料。
          </p>
        </div>
        <button type="button" class="btn-outline" @click="currentStep = 2">
          ← 返回重选项目
        </button>
      </div>

      <div v-if="workflowResult" class="checklist-panel">
        <div class="checklist-meta">
          <span>流转路径：<strong>{{ workflowResult.route_summary }}</strong></span>
          <span>承诺总时限：<strong>{{ workflowResult.total_sla_days }} 个工作日</strong></span>
          <span v-if="workflowResult.fast_track" class="tag-blue">绿色快办通道</span>
        </div>

        <div class="doc-list">
          <label
            v-for="doc in workflowResult.consolidated_documents"
            :key="doc"
            class="doc-item"
          >
            <input v-model="checkedDocs[doc]" type="checkbox" />
            <span>{{ doc }}</span>
            <small class="doc-badge">已校验</small>
          </label>
        </div>
      </div>

      <div class="card-footer">
        <span class="muted">
          {{ allDocsChecked ? '全部申报材料已确认齐全，可发起跨部门流转' : '请勾选确认全部必需材料' }}
        </span>
        <button
          type="button"
          class="btn-crimson"
          :disabled="loading || !allDocsChecked"
          @click="prepareChecklistAndRoute(4, 2)"
        >
          {{ loading ? '正在路由至各局...' : '提交并启动跨部门流转 →' }}
        </button>
      </div>
    </div>

    <!-- Step 4: 跨部门流转进度条 -->
    <div v-else class="wizard-card">
      <div class="card-head">
        <div>
          <h2>第四步：跨部门联合审批流转进度条</h2>
          <p class="sub">
            案件编号：<strong>{{ workflowResult?.case_id || '-' }}</strong> ｜ 协同模式：
            <strong>{{
              workflowResult?.workflow_pattern === 'hybrid_parallel'
                ? '并联初审 + 串联拨付'
                : '全流程串联核验'
            }}</strong>
          </p>
        </div>
        <div class="preset-group">
          <button type="button" class="btn-outline" @click="advanceBureauStage(1)">
            阶段1：初审受理
          </button>
          <button type="button" class="btn-outline" @click="advanceBureauStage(2)">
            阶段2：科技核定
          </button>
          <button type="button" class="btn-outline" @click="advanceBureauStage(4)">
            阶段3：财政已拨付
          </button>
        </div>
      </div>

      <div v-if="workflowResult" class="workflow-track">
        <div
          v-for="(stage, idx) in workflowResult.stages"
          :key="stage.stage_id"
          class="bureau-node"
          :class="stage.status"
        >
          <div class="bureau-header">
            <span class="bureau-step">第 {{ stage.step_order }} 序位</span>
            <span class="mode-pill" :class="stage.execution_mode">
              {{ stage.execution_mode === 'parallel' ? '并联协审' : '串联审批' }}
            </span>
          </div>
          <div class="bureau-title">
            <span class="bureau-dot"></span>
            <div>
              <h3>{{ stage.bureau_short }}</h3>
              <small>{{ stage.bureau }}</small>
            </div>
          </div>
          <p class="bureau-resp">{{ stage.responsibility }}</p>
          <div class="bureau-sla">
            <span>承诺办理 SLA：<strong>{{ stage.sla_days }} 个工作日</strong></span>
            <span class="status-text">
              {{
                stage.status === 'completed'
                  ? '✓ 已办结'
                  : stage.status === 'in_progress'
                    ? '● 办理中'
                    : '○ 待流转'
              }}
            </span>
          </div>
          <ul class="bureau-docs">
            <li v-for="d in stage.required_documents" :key="d">{{ d }}</li>
          </ul>
          <div v-if="idx < workflowResult.stages.length - 1" class="arrow-connector">→</div>
        </div>
      </div>

      <div class="card-footer">
        <span class="muted">
          汇总时限：<strong>{{ workflowResult?.total_sla_days || 0 }} 个工作日</strong>（含并联压减）
        </span>
        <button type="button" class="btn-outline" @click="currentStep = 1">
          发起新申报
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.wizard-shell {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.stepper-bar {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}

.stepper-node {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 1rem;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: all 0.18s ease;
}

.stepper-node.active {
  border-color: #1d4ed8;
  background: #eff6ff;
  box-shadow: 0 2px 10px rgba(29, 78, 216, 0.12);
}

.stepper-node.done {
  border-color: #b91c1c;
  background: #fef2f2;
}

.step-badge {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.85rem;
  background: #e2e8f0;
  color: #1e293b;
  flex-shrink: 0;
}

.stepper-node.active .step-badge {
  background: #1d4ed8;
  color: #ffffff;
}

.stepper-node.done .step-badge {
  background: #b91c1c;
  color: #ffffff;
}

.step-meta {
  display: flex;
  flex-direction: column;
}

.step-meta strong {
  font-size: 0.9rem;
  color: #0f172a;
}

.step-meta small {
  font-size: 0.75rem;
  color: #64748b;
}

.wizard-alert {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-weight: 500;
}

.wizard-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-top: 3px solid #1d4ed8;
  border-radius: 10px;
  padding: 1.25rem 1.4rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.card-head h2 {
  margin: 0;
  font-size: 1.1rem;
  color: #0f172a;
}

.sub {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  color: #475569;
}

.preset-group {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.82rem;
  color: #334155;
  font-weight: 600;
}

.field input,
.field select,
.field textarea {
  padding: 0.55rem 0.7rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.88rem;
  background: #fdfbf7;
  color: #0f172a;
}

.full-width {
  width: 100%;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f5f9;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.checkbox-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.85rem;
  color: #334155;
}

.btn-primary {
  background: #1d4ed8;
  color: #ffffff;
  border: none;
  padding: 0.6rem 1.2rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-crimson {
  background: #b91c1c;
  color: #ffffff;
  border: none;
  padding: 0.6rem 1.25rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.btn-outline {
  background: #fdfbf7;
  color: #1e293b;
  border: 1px solid #cbd5e1;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:disabled,
.btn-crimson:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.match-summary-box {
  background: #fdfbf7;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #b91c1c;
  border-radius: 8px;
  padding: 0.85rem 1rem;
}

.pii-banner {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-size: 0.82rem;
  margin-bottom: 0.45rem;
}

.tag-red {
  background: #b91c1c;
  color: #ffffff;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
}

.tag-blue {
  background: #1d4ed8;
  color: #ffffff;
  padding: 0.15rem 0.55rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.answer-text {
  margin: 0;
  font-size: 0.9rem;
  color: #1e293b;
  line-height: 1.5;
}

.eval-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}

.eval-card {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 0.95rem 1rem;
  cursor: pointer;
  background: #ffffff;
  transition: border-color 0.15s ease;
}

.eval-card.selected {
  border: 2px solid #1d4ed8;
  background: #eff6ff;
}

.eval-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.4rem;
}

.status-pill {
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
}

.pill-pass {
  background: #dcfce7;
  color: #166534;
}

.pill-fail {
  background: #fee2e2;
  color: #991b1b;
}

.dept-badge {
  font-size: 0.78rem;
  color: #1d4ed8;
  font-weight: 600;
}

.eval-card h3 {
  margin: 0.2rem 0 0.4rem;
  font-size: 1rem;
}

.subsidy-num {
  font-size: 0.88rem;
  color: #334155;
  margin-bottom: 0.5rem;
}

.subsidy-num strong {
  color: #b91c1c;
  font-size: 1.05rem;
}

.rule-list {
  margin: 0;
  padding-left: 1rem;
  font-size: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.rule-pass {
  color: #166534;
}

.rule-fail {
  color: #991b1b;
}

.checklist-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.checklist-meta {
  display: flex;
  gap: 1.25rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0.75rem 1rem;
  background: #fdfbf7;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.88rem;
}

.doc-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.65rem 0.85rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
  font-size: 0.86rem;
}

.doc-badge {
  margin-left: auto;
  color: #1d4ed8;
  font-weight: 600;
}

.workflow-track {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.bureau-node {
  position: relative;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 1rem;
  background: #fdfbf7;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.bureau-node.completed {
  border-color: #16a34a;
  background: #f0fdf4;
}

.bureau-node.in_progress {
  border-color: #1d4ed8;
  border-width: 2px;
  background: #eff6ff;
}

.bureau-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.76rem;
}

.bureau-step {
  font-weight: 700;
  color: #475569;
}

.mode-pill {
  padding: 0.12rem 0.45rem;
  border-radius: 4px;
  font-weight: 600;
}

.mode-pill.parallel {
  background: #dbeafe;
  color: #1d4ed8;
}

.mode-pill.sequential {
  background: #fee2e2;
  color: #b91c1c;
}

.bureau-title {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.bureau-title h3 {
  margin: 0;
  font-size: 1.05rem;
  color: #0f172a;
}

.bureau-title small {
  color: #64748b;
  font-size: 0.76rem;
}

.bureau-dot {
  width: 11px;
  height: 11px;
  border-radius: 999px;
  background: #94a3b8;
  flex-shrink: 0;
}

.bureau-node.completed .bureau-dot {
  background: #16a34a;
}

.bureau-node.in_progress .bureau-dot {
  background: #1d4ed8;
}

.bureau-resp {
  margin: 0;
  font-size: 0.82rem;
  color: #334155;
  line-height: 1.45;
}

.bureau-sla {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8rem;
  padding-top: 0.35rem;
  border-top: 1px dashed #cbd5e1;
}

.status-text {
  font-weight: 700;
  color: #1d4ed8;
}

.bureau-node.completed .status-text {
  color: #166534;
}

.bureau-docs {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.77rem;
  color: #475569;
}

.arrow-connector {
  display: none;
}

.muted {
  color: #64748b;
  font-size: 0.84rem;
}

.empty-note {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
}

@media (max-width: 960px) {
  .stepper-bar,
  .form-grid,
  .eval-grid,
  .doc-list,
  .workflow-track {
    grid-template-columns: 1fr;
  }
}
</style>
