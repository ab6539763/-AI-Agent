<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  apiClient,
  type AuditLogEntry,
  type ClinicalAction,
  type ClinicalTriageResponse,
  type DashboardOverview,
  type DischargeSummaryResponse,
  type InteractionCheckResult,
  type OntologyCatalog,
  type WikiLintResponse,
  type WikiPageItem,
} from "./api/client";

type TabId = "triage" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabId>("triage");
const loading = ref(false);
const errorMsg = ref("");

const overview = ref<DashboardOverview | null>(null);
const catalog = ref<OntologyCatalog | null>(null);
const wikiPages = ref<WikiPageItem[]>([]);
const wikiLintResult = ref<WikiLintResponse | null>(null);
const pendingActions = ref<ClinicalAction[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);

// Tab 1: Triage & Discharge Summary
const triageForm = reactive({
  case_id: "case-er-2026",
  age: 64,
  sex: "M" as "M" | "F" | "O" | "U",
  chief_complaint:
    "Patient: Zhang Wei (MRN-882190) presents with acute substernal chest pain, phone 555-222-3333",
  symptom_id: "chest_pain",
  symptom_name: "Chest Pain",
  symptom_severity: "critical" as "mild" | "moderate" | "severe" | "critical",
  is_red_flag: true,
  spo2: 88,
  hr: 118,
  sbp: 105,
  active_medications: "warfarin",
  allergies: "",
  conditions: "hypertension",
  proposed_med_ids: "aspirin",
  raw_notes: "DOB 1962-04-11, SSN 123-45-6789, Email zhang.wei@example.com",
});
const triageResult = ref<ClinicalTriageResponse | null>(null);

const dischargeForm = reactive({
  case_id: "case-dc-2026",
  diagnosis: "Hypertension and atrial fibrillation",
  raw_notes:
    "Patient: Li Ming, MRN-778899, SSN 123-45-6789, DOB 1965-03-21, Phone 555-123-9876, Email li.ming@example.com. Discharged stable on Warfarin and Lisinopril.",
  conditions: "hypertension",
  medications: "warfarin, lisinopril",
  follow_up_days: 7,
});
const dischargeResult = ref<DischargeSummaryResponse | null>(null);

// Tab 2: Ontology Checker
const ontologyForm = reactive({
  proposed_med_ids: "ibuprofen",
  active_med_ids: "warfarin",
  allergies: "penicillin",
  conditions: "",
});
const interactionResult = ref<InteractionCheckResult | null>(null);

// Tab 3: Wiki Ingest
const wikiForm = reactive({
  doc_id: "gl_acs_aspirin",
  title: "ACS Aspirin Loading Protocol",
  content:
    "Administer Aspirin 325 mg chewed immediately for suspected acute coronary syndrome unless active hemorrhage is present.",
  entity_type: "guideline",
  condition: "acute_coronary_syndrome",
  medication: "aspirin",
  dose_mg: 325,
  citation: "AHA/ACC Chest Pain Guideline 2021",
  related_ids: "chest_pain",
});

// Tab 4: HITL Sign-off
const hitlPhysicianId = ref("dr-lin-01");
const hitlNotes = ref("Reviewed ontology constraints and clinical presentation.");

function splitCsv(val: string): string[] {
  return val
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function refreshDashboard() {
  try {
    overview.value = await apiClient.getDashboardOverview();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function refreshAll() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const [ov, cat, pages, pending, logs] = await Promise.all([
      apiClient.getDashboardOverview(),
      apiClient.getOntologyCatalog(),
      apiClient.getWikiPages(),
      apiClient.getPendingActions(),
      apiClient.getAuditLogs(),
    ]);
    overview.value = ov;
    catalog.value = cat;
    wikiPages.value = pages.pages;
    pendingActions.value = pending.actions;
    auditLogs.value = logs.logs;
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runTriage() {
  loading.value = true;
  errorMsg.value = "";
  try {
    triageResult.value = await apiClient.clinicalTriage({
      patient_case: {
        case_id: triageForm.case_id,
        age: triageForm.age,
        sex: triageForm.sex,
        chief_complaint: triageForm.chief_complaint,
        symptoms: [
          {
            symptom_id: triageForm.symptom_id,
            name: triageForm.symptom_name,
            severity: triageForm.symptom_severity,
            is_red_flag: triageForm.is_red_flag,
          },
        ],
        active_medications: splitCsv(triageForm.active_medications),
        allergies: splitCsv(triageForm.allergies),
        conditions: splitCsv(triageForm.conditions),
        vital_signs: {
          spo2: triageForm.spo2,
          hr: triageForm.hr,
          sbp: triageForm.sbp,
        },
      },
      proposed_med_ids: splitCsv(triageForm.proposed_med_ids),
      raw_notes: triageForm.raw_notes,
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runDischargeSummary() {
  loading.value = true;
  errorMsg.value = "";
  try {
    dischargeResult.value = await apiClient.generateDischargeSummary({
      case_id: dischargeForm.case_id,
      raw_notes: dischargeForm.raw_notes,
      diagnosis: dischargeForm.diagnosis,
      conditions: splitCsv(dischargeForm.conditions),
      medications: splitCsv(dischargeForm.medications),
      follow_up_days: dischargeForm.follow_up_days,
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runInteractionCheck() {
  loading.value = true;
  errorMsg.value = "";
  try {
    interactionResult.value = await apiClient.checkInteraction({
      proposed_med_ids: splitCsv(ontologyForm.proposed_med_ids),
      active_med_ids: splitCsv(ontologyForm.active_med_ids),
      allergies: splitCsv(ontologyForm.allergies),
      conditions: splitCsv(ontologyForm.conditions),
    });
    await refreshDashboard();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiIngest() {
  loading.value = true;
  errorMsg.value = "";
  try {
    await apiClient.ingestWikiPage({
      doc_id: wikiForm.doc_id,
      title: wikiForm.title,
      content: wikiForm.content,
      entity_type: wikiForm.entity_type,
      condition: wikiForm.condition || null,
      medication: wikiForm.medication || null,
      dose_mg: wikiForm.dose_mg,
      citation: wikiForm.citation || null,
      related_ids: splitCsv(wikiForm.related_ids),
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiLint() {
  loading.value = true;
  errorMsg.value = "";
  try {
    wikiLintResult.value = await apiClient.lintWiki();
    await refreshDashboard();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function handleHitlDecision(
  actionId: string,
  decision: "approved" | "rejected"
) {
  loading.value = true;
  errorMsg.value = "";
  try {
    await apiClient.approveAction({
      action_id: actionId,
      physician_id: hitlPhysicianId.value,
      decision,
      notes: hitlNotes.value,
    });
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshAll();
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <div class="brand">P02 Healthcare Clinical Decision Copilot</div>
        <div class="subtitle">
          Offline Deterministic Clinical Ontology · LLM Wiki · HIPAA PHI Guardrail · Physician HITL
        </div>
      </div>
      <button class="btn btn-secondary" :disabled="loading" @click="refreshAll">
        {{ loading ? "刷新中..." : "刷新数据" }}
      </button>
    </header>

    <section v-if="overview" class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">临床指南 (Guidelines)</div>
        <div class="kpi-value">{{ overview.guidelines_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">药物本体 (Medications)</div>
        <div class="kpi-value">{{ overview.medications_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Wiki 知识页</div>
        <div class="kpi-value">{{ overview.wiki_pages_count }}</div>
      </div>
      <div class="kpi-card warn">
        <div class="kpi-label">待医师 HITL 签核</div>
        <div class="kpi-value">{{ overview.pending_hitl_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">PHI-Safe 审计日志</div>
        <div class="kpi-value">{{ overview.audit_logs_count }}</div>
      </div>
    </section>

    <div v-if="errorMsg" class="alert alert-error">
      {{ errorMsg }}
    </div>

    <nav class="tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'triage' }]"
        @click="activeTab = 'triage'"
      >
        临床分诊与出院脱敏
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        用药禁忌 Ontology
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        临床指南 LLM Wiki
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        医师 HITL 签核与审计
      </button>
    </nav>

    <!-- Tab 1: Clinical Triage & Discharge De-identification -->
    <main v-if="activeTab === 'triage'" class="two-col">
      <section class="panel">
        <h2>急诊红旗分诊与 PHI 脱敏</h2>
        <div class="form-grid">
          <label>
            Case ID
            <input v-model="triageForm.case_id" />
          </label>
          <label>
            年龄 / 性别
            <div class="inline-row">
              <input v-model.number="triageForm.age" type="number" min="0" max="130" />
              <select v-model="triageForm.sex">
                <option value="M">M</option>
                <option value="F">F</option>
                <option value="O">O</option>
                <option value="U">U</option>
              </select>
            </div>
          </label>
          <label class="full">
            主诉 (支持自动脱敏姓名/MRN/电话/SSN/邮箱)
            <textarea v-model="triageForm.chief_complaint" rows="2" />
          </label>
          <label>
            症状 ID / 名称
            <div class="inline-row">
              <input v-model="triageForm.symptom_id" />
              <input v-model="triageForm.symptom_name" />
            </div>
          </label>
          <label>
            严重程度 & 红旗
            <div class="inline-row">
              <select v-model="triageForm.symptom_severity">
                <option value="mild">mild</option>
                <option value="moderate">moderate</option>
                <option value="severe">severe</option>
                <option value="critical">critical</option>
              </select>
              <label class="checkbox-inline">
                <input v-model="triageForm.is_red_flag" type="checkbox" />
                Red Flag
              </label>
            </div>
          </label>
          <label>
            生命体征 (SpO2 / HR / SBP)
            <div class="inline-row">
              <input v-model.number="triageForm.spo2" type="number" placeholder="SpO2" />
              <input v-model.number="triageForm.hr" type="number" placeholder="HR" />
              <input v-model.number="triageForm.sbp" type="number" placeholder="SBP" />
            </div>
          </label>
          <label>
            拟用药物 (逗号分隔)
            <input v-model="triageForm.proposed_med_ids" />
          </label>
          <label>
            在用药物 (逗号分隔)
            <input v-model="triageForm.active_medications" />
          </label>
          <label>
            既往疾病 / 过敏史
            <div class="inline-row">
              <input v-model="triageForm.conditions" placeholder="conditions" />
              <input v-model="triageForm.allergies" placeholder="allergies" />
            </div>
          </label>
          <label class="full">
            原始病历备注
            <textarea v-model="triageForm.raw_notes" rows="2" />
          </label>
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="runTriage">
          执行临床分诊与 Guardrail 检查
        </button>

        <div v-if="triageResult" class="result-box">
          <div class="badge-row">
            <span :class="['badge', triageResult.triage_level]">
              Triage: {{ triageResult.triage_level.toUpperCase() }}
            </span>
            <span
              :class="[
                'badge',
                triageResult.interaction_check.blocked ? 'critical' : 'ok',
              ]"
            >
              {{ triageResult.proposed_action.status }}
            </span>
          </div>
          <p><strong>脱敏主诉:</strong> {{ triageResult.deidentified_complaint }}</p>
          <p><strong>脱敏备注:</strong> {{ triageResult.deidentified_notes }}</p>
          <p>
            <strong>已拦截 PHI 类型:</strong>
            {{ triageResult.redacted_phi_types.join(", ") || "无" }}
          </p>
          <p><strong>红旗指标:</strong> {{ triageResult.red_flags.join(", ") || "无" }}</p>
          <p><strong>用药约束摘要:</strong> {{ triageResult.interaction_check.summary }}</p>
        </div>
      </section>

      <section class="panel">
        <h2>出院小结脱敏与随访清单生成</h2>
        <div class="form-grid">
          <label>
            Case ID
            <input v-model="dischargeForm.case_id" />
          </label>
          <label>
            随访天数
            <input v-model.number="dischargeForm.follow_up_days" type="number" min="1" max="90" />
          </label>
          <label class="full">
            出院诊断
            <input v-model="dischargeForm.diagnosis" />
          </label>
          <label>
            基础疾病 (逗号分隔)
            <input v-model="dischargeForm.conditions" />
          </label>
          <label>
            带药清单 (逗号分隔)
            <input v-model="dischargeForm.medications" />
          </label>
          <label class="full">
            原始出院记录 (含 PHI)
            <textarea v-model="dischargeForm.raw_notes" rows="3" />
          </label>
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="runDischargeSummary">
          生成脱敏出院小结与随访清单
        </button>

        <div v-if="dischargeResult" class="result-box">
          <p><strong>脱敏后出院记录:</strong> {{ dischargeResult.deidentified_note }}</p>
          <p>
            <strong>已脱敏 PHI:</strong>
            {{ dischargeResult.redacted_phi_types.join(", ") || "无" }}
          </p>
          <p><strong>带药安全检查:</strong> {{ dischargeResult.interaction_check.summary }}</p>
          <h3>随访核查清单 ({{ dischargeResult.follow_up_checklist.length }})</h3>
          <ul class="checklist">
            <li v-for="item in dischargeResult.follow_up_checklist" :key="item.step_id">
              <span class="tag">{{ item.timeframe }}</span>
              <strong>[{{ item.category }}]</strong> {{ item.task }}
            </li>
          </ul>
        </div>
      </section>
    </main>

    <!-- Tab 2: Medication Contraindication Ontology -->
    <main v-if="activeTab === 'ontology'" class="two-col">
      <section class="panel">
        <h2>用药禁忌与过敏交叉检查</h2>
        <div class="form-grid">
          <label class="full">
            拟开具药物 (如: ibuprofen, amoxicillin, aspirin)
            <input v-model="ontologyForm.proposed_med_ids" />
          </label>
          <label class="full">
            当前在用药物 (如: warfarin, lisinopril)
            <input v-model="ontologyForm.active_med_ids" />
          </label>
          <label class="full">
            过敏史 (如: penicillin, nsaid)
            <input v-model="ontologyForm.allergies" />
          </label>
          <label class="full">
            禁忌症疾病 (如: active_hemorrhage, severe_renal_failure)
            <input v-model="ontologyForm.conditions" />
          </label>
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="runInteractionCheck">
          执行 Ontology 约束检查
        </button>

        <div v-if="interactionResult" class="result-box">
          <div class="badge-row">
            <span :class="['badge', interactionResult.blocked ? 'critical' : 'ok']">
              {{ interactionResult.blocked ? "BLOCKED (阻断)" : "ALLOWED / CAUTION" }}
            </span>
          </div>
          <p><strong>摘要:</strong> {{ interactionResult.summary }}</p>
          <div v-if="interactionResult.drug_interactions.length">
            <h4>药物相互作用 (DDI)</h4>
            <ul>
              <li v-for="(d, idx) in interactionResult.drug_interactions" :key="idx">
                <strong>{{ d.med_a }} + {{ d.med_b }}</strong> ({{ d.severity }}): {{ d.mechanism }} — <em>{{ d.recommendation }}</em>
              </li>
            </ul>
          </div>
          <div v-if="interactionResult.allergy_conflicts.length">
            <h4>过敏冲突</h4>
            <ul>
              <li v-for="(a, idx) in interactionResult.allergy_conflicts" :key="idx">
                <strong>{{ a.med_id }}</strong> ({{ a.matched_allergies }}): {{ a.recommendation }}
              </li>
            </ul>
          </div>
          <div v-if="interactionResult.condition_conflicts.length">
            <h4>疾病禁忌</h4>
            <ul>
              <li v-for="(c, idx) in interactionResult.condition_conflicts" :key="idx">
                <strong>{{ c.med_id }}</strong> ({{ c.matched_conditions }}): {{ c.recommendation }}
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>临床药物本体目录 ({{ catalog?.medications.length ?? 0 }})</h2>
        <div v-if="catalog" class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>分类</th>
                <th>标准/最大剂量(mg)</th>
                <th>禁忌疾病</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="med in catalog.medications" :key="med.med_id">
                <td><code>{{ med.med_id }}</code></td>
                <td>{{ med.name }}</td>
                <td>{{ med.drug_class }}</td>
                <td>{{ med.standard_dose_mg }} / {{ med.max_daily_dose_mg }}</td>
                <td>{{ med.contraindicated_conditions.join(", ") || "-" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>

    <!-- Tab 3: Clinical Guidelines LLM Wiki -->
    <main v-if="activeTab === 'wiki'" class="two-col">
      <section class="panel">
        <h2>写入临床指南实体 (Wiki Ingest)</h2>
        <div class="form-grid">
          <label>
            Doc ID
            <input v-model="wikiForm.doc_id" />
          </label>
          <label>
            实体类型
            <select v-model="wikiForm.entity_type">
              <option value="guideline">guideline</option>
              <option value="protocol">protocol</option>
              <option value="condition">condition</option>
            </select>
          </label>
          <label class="full">
            标题
            <input v-model="wikiForm.title" />
          </label>
          <label>
            关联疾病
            <input v-model="wikiForm.condition" />
          </label>
          <label>
            关联药物 / 剂量 (mg)
            <div class="inline-row">
              <input v-model="wikiForm.medication" />
              <input v-model.number="wikiForm.dose_mg" type="number" />
            </div>
          </label>
          <label class="full">
            循证文献引用 (Citation)
            <input v-model="wikiForm.citation" />
          </label>
          <label class="full">
            正文内容
            <textarea v-model="wikiForm.content" rows="3" />
          </label>
        </div>
        <div class="btn-row">
          <button class="btn btn-primary" :disabled="loading" @click="runWikiIngest">
            写入 Wiki 页面
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="runWikiLint">
            运行 Wiki 冲突与引用 Linter
          </button>
        </div>

        <div v-if="wikiLintResult" class="result-box">
          <p>
            <strong>Lint 状态:</strong> {{ wikiLintResult.status }} (共 {{ wikiLintResult.total_entities }} 实体, {{ wikiLintResult.total_issues }} 问题)
          </p>
          <ul v-if="wikiLintResult.issues.length">
            <li v-for="(iss, idx) in wikiLintResult.issues" :key="idx">
              [{{ iss.issue_type }}] {{ iss.message }}
            </li>
          </ul>
        </div>
      </section>

      <section class="panel">
        <h2>临床指南 Wiki 页面列表 ({{ wikiPages.length }})</h2>
        <div v-if="wikiPages.length === 0" class="empty-state">
          暂无 Wiki 页面，请在左侧写入指南实体。
        </div>
        <div v-else class="card-list">
          <article v-for="page in wikiPages" :key="page.id" class="list-card">
            <div class="list-card-head">
              <strong>{{ page.title }}</strong>
              <code>{{ page.id }}</code>
            </div>
            <p class="preview">{{ page.preview }}</p>
            <div class="meta-line">
              <span>类型: {{ page.entity_type }}</span>
              <span>引用: {{ page.citation || "缺失" }}</span>
              <span>路径: {{ page.path }}</span>
            </div>
          </article>
        </div>
      </section>
    </main>

    <!-- Tab 4: Physician HITL Sign-off & Audit -->
    <main v-if="activeTab === 'hitl'" class="two-col">
      <section class="panel">
        <h2>待医师 HITL 签核队列 ({{ pendingActions.length }})</h2>
        <div class="form-grid compact">
          <label>
            签核医师 ID
            <input v-model="hitlPhysicianId" />
          </label>
          <label>
            签核意见
            <input v-model="hitlNotes" />
          </label>
        </div>
        <div v-if="pendingActions.length === 0" class="empty-state">
          当前无待签核的临床动作。可在“临床分诊与出院脱敏”中触发分诊生成待签核队列。
        </div>
        <div v-else class="card-list">
          <article v-for="act in pendingActions" :key="act.action_id" class="list-card">
            <div class="list-card-head">
              <strong>{{ act.action_type }} ({{ act.case_id }})</strong>
              <span :class="['badge', act.risk_level]">{{ act.risk_level }}</span>
            </div>
            <p>{{ act.rationale }}</p>
            <div class="meta-line">
              <span>Action ID: <code>{{ act.action_id }}</code></span>
              <span>拟用药物: {{ act.proposed_med_ids.join(", ") || "无" }}</span>
            </div>
            <div class="btn-row">
              <button
                class="btn btn-primary"
                :disabled="loading"
                @click="handleHitlDecision(act.action_id, 'approved')"
              >
                批准 (Approve)
              </button>
              <button
                class="btn btn-danger"
                :disabled="loading"
                @click="handleHitlDecision(act.action_id, 'rejected')"
              >
                驳回 (Reject)
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="panel">
        <h2>PHI-Safe 审计轨迹 ({{ auditLogs.length }})</h2>
        <div v-if="auditLogs.length === 0" class="empty-state">
          暂无审计记录。
        </div>
        <div v-else class="card-list">
          <article v-for="(log, idx) in auditLogs" :key="idx" class="list-card">
            <div class="list-card-head">
              <strong>{{ log.event_type }}</strong>
              <code>{{ log.case_id }}</code>
            </div>
            <div class="meta-line">
              <span>{{ log.timestamp }}</span>
              <span v-if="log.action_id">Action: {{ log.action_id }}</span>
            </div>
            <pre class="json-pre">{{ JSON.stringify(log.details, null, 2) }}</pre>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f1f5f9;
  color: #0f172a;
}

.app-shell {
  max-width: 1320px;
  margin: 0 auto;
  padding: 20px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #0f172a;
  color: #f8fafc;
  padding: 16px 22px;
  border-radius: 12px;
  margin-bottom: 16px;
}

.brand {
  font-size: 1.25rem;
  font-weight: 700;
}

.subtitle {
  font-size: 0.85rem;
  color: #94a3b8;
  margin-top: 4px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.kpi-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
}

.kpi-card.warn {
  border-left: 4px solid #d97706;
}

.kpi-label {
  font-size: 0.8rem;
  color: #64748b;
}

.kpi-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: #0f766e;
  margin-top: 4px;
}

.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.tab-btn {
  padding: 10px 16px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  color: #334155;
}

.tab-btn.active {
  background: #0f766e;
  color: #ffffff;
  border-color: #0f766e;
}

.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 16px;
}

.panel {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px;
}

.panel h2 {
  margin-top: 0;
  font-size: 1.1rem;
  color: #0f172a;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.form-grid.compact {
  margin-bottom: 12px;
}

.form-grid label {
  display: flex;
  flex-direction: column;
  font-size: 0.82rem;
  font-weight: 600;
  color: #334155;
  gap: 4px;
}

.form-grid label.full {
  grid-column: 1 / -1;
}

.inline-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.checkbox-inline {
  flex-direction: row !important;
  align-items: center;
  gap: 6px !important;
}

input,
select,
textarea {
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.88rem;
  width: 100%;
  box-sizing: border-box;
}

.btn-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn {
  padding: 9px 14px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.88rem;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #0f766e;
  color: #ffffff;
}

.btn-secondary {
  background: #e2e8f0;
  color: #0f172a;
}

.btn-danger {
  background: #dc2626;
  color: #ffffff;
}

.result-box {
  margin-top: 14px;
  padding: 12px;
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.88rem;
}

.badge-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  background: #e2e8f0;
}

.badge.emergency,
.badge.critical {
  background: #fee2e2;
  color: #b91c1c;
}

.badge.urgent,
.badge.high {
  background: #fef3c7;
  color: #b45309;
}

.badge.ok,
.badge.low,
.badge.routine {
  background: #dcfce7;
  color: #15803d;
}

.checklist {
  padding-left: 18px;
  margin: 8px 0 0;
}

.checklist li {
  margin-bottom: 6px;
}

.tag {
  background: #e0f2fe;
  color: #0369a1;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-right: 6px;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

th,
td {
  text-align: left;
  padding: 8px;
  border-bottom: 1px solid #e2e8f0;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.list-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  background: #f8fafc;
}

.list-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.preview {
  margin: 4px 0 8px;
  font-size: 0.86rem;
  color: #334155;
}

.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 0.78rem;
  color: #64748b;
}

.json-pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 8px;
  border-radius: 6px;
  font-size: 0.76rem;
  overflow-x: auto;
  margin: 8px 0 0;
}

.alert-error {
  background: #fee2e2;
  color: #b91c1c;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 14px;
}

.empty-state {
  padding: 20px;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border-radius: 8px;
}
</style>
