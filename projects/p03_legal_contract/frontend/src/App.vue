<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  legalApi,
  type AuditLogEntry,
  type ClauseItem,
  type ContractReviewResponse,
  type DashboardOverview,
  type LegalActionItem,
  type LegalLinkItem,
  type RedlineDiffResponse,
  type RegulationItem,
  type WikiLintResponse,
  type WikiPageItem,
} from "./api/client";

type TabKey = "review" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabKey>("review");
const apiOnline = ref<boolean>(false);
const loading = ref<boolean>(false);
const errorBanner = ref<string>("");

const overview = ref<DashboardOverview>({
  contracts_reviewed: 0,
  contracts_total: 0,
  clauses_total: 0,
  high_risk_clauses: 0,
  critical_risk_clauses: 0,
  active_regulations: 0,
  regulations_total: 0,
  pending_gc_approvals: 0,
  audit_logs_count: 0,
  pii_masked_total: 0,
  wiki_pages_count: 0,
  recent_contracts: [],
});

// Tab 1: Contract Review & Redline Diff
const reviewForm = reactive({
  contract_id: "ctr_enterprise_2026",
  title: "全球云服务主协议 (MSA)",
  counterparty: "Acme Cloud Corp.",
  jurisdiction: "EU / US-NY",
  liability_cap_usd: 500000,
  text: `1. Liability & Indemnification
Vendor shall have unlimited liability for all data breach and GDPR personal data claims. Legal notices to counsel@acme.com or +1-415-555-0199, SSN 123-45-6789.

2. Data Protection
Vendor may sell personal data without opt-out and transfer data under EU Directive 95/46/EC.

3. Confidentiality
Both parties shall maintain SOC2 encryption and confidential access controls.`,
});

const reviewResult = ref<ContractReviewResponse | null>(null);

const diffForm = reactive({
  contract_id: "ctr_diff_2026",
  title: "MSA v1 vs v2 Redline 对比",
  original_text: `1. Liability
Vendor shall have unlimited liability for all claims.

2. Privacy
Vendor may sell personal data without opt-out.`,
  revised_text: `1. Liability
Vendor total aggregate liability shall not exceed $500,000.

2. Privacy
Vendor shall process personal data strictly under GDPR Art.28.`,
});

const diffResult = ref<RedlineDiffResponse | null>(null);

// Tab 2: Ontology
const regulations = ref<RegulationItem[]>([]);
const ontologyLinks = ref<LegalLinkItem[]>([]);
const clauses = ref<ClauseItem[]>([]);
const riskFilter = ref<string>("");

// Tab 3: Wiki & Lint
const wikiPages = ref<WikiPageItem[]>([]);
const lintReport = ref<WikiLintResponse | null>(null);
const wikiIngestForm = reactive({
  doc_id: "reg_eu_ai_act_art50",
  title: "EU AI Act Article 50 Transparency",
  doc_type: "regulation" as "contract" | "clause" | "regulation",
  content: "Requires transparency obligations for AI-generated content and high-risk legal workflows.",
});
const wikiIngestMessage = ref<string>("");

// Tab 4: HITL & Audit
const pendingActions = ref<LegalActionItem[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);
const hitlApprover = ref<string>("gc_chief_counsel");
const hitlNotes = ref<string>("Reviewed by General Counsel.");

const filteredClauses = computed(() => {
  if (!riskFilter.value) return clauses.value;
  return clauses.value.filter((c) => c.risk_level === riskFilter.value);
});

function riskBadgeClass(level: string | null | undefined): string {
  switch (level) {
    case "critical":
      return "badge badge-critical";
    case "high":
      return "badge badge-high";
    case "medium":
      return "badge badge-medium";
    default:
      return "badge badge-low";
  }
}

async function refreshAll(): Promise<void> {
  errorBanner.value = "";
  try {
    await legalApi.health();
    apiOnline.value = true;
    const [ov, regs, cls, pages, pending, logs] = await Promise.all([
      legalApi.getOverview(),
      legalApi.listRegulations(),
      legalApi.listClauses(),
      legalApi.listWikiPages(),
      legalApi.listPendingActions(),
      legalApi.listAuditLogs(50),
    ]);
    overview.value = ov;
    regulations.value = regs.regulations;
    ontologyLinks.value = regs.links;
    clauses.value = cls.clauses;
    wikiPages.value = pages.pages;
    pendingActions.value = pending.actions;
    auditLogs.value = logs.logs;
  } catch (err) {
    apiOnline.value = false;
    errorBanner.value = err instanceof Error ? err.message : String(err);
  }
}

async function submitContractReview(): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  try {
    reviewResult.value = await legalApi.reviewContract({
      contract_id: reviewForm.contract_id,
      title: reviewForm.title,
      counterparty: reviewForm.counterparty,
      jurisdiction: reviewForm.jurisdiction,
      liability_cap_usd: reviewForm.liability_cap_usd || null,
      text: reviewForm.text,
    });
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function submitRedlineDiff(): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  try {
    diffResult.value = await legalApi.redlineDiff({
      contract_id: diffForm.contract_id,
      title: diffForm.title,
      original_text: diffForm.original_text,
      revised_text: diffForm.revised_text,
    });
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function submitWikiIngest(): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  wikiIngestMessage.value = "";
  try {
    const res = await legalApi.ingestWiki({
      doc_id: wikiIngestForm.doc_id,
      title: wikiIngestForm.title,
      doc_type: wikiIngestForm.doc_type,
      content: wikiIngestForm.content,
    });
    wikiIngestMessage.value = `已入库实体: ${res.entities.join(", ")}`;
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiLint(): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  try {
    lintReport.value = await legalApi.lintWiki();
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function decideAction(actionId: string, decision: "approved" | "rejected"): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  try {
    await legalApi.approveAction({
      action_id: actionId,
      decision,
      approver: hitlApprover.value || "gc_chief",
      notes: hitlNotes.value,
    });
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshAll();
});
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-badge">P03</div>
        <div>
          <h1>企业级法务合规与合同审查工作台</h1>
          <p class="subtitle">Legal Ontology · LLM Wiki · FDE Redline · General Counsel HITL</p>
        </div>
      </div>
      <div class="topbar-actions">
        <span :class="['status-pill', apiOnline ? 'online' : 'offline']">
          {{ apiOnline ? "FastAPI 后端在线" : "后端离线" }}
        </span>
        <button class="btn btn-secondary" @click="refreshAll">刷新数据</button>
      </div>
    </header>

    <div v-if="errorBanner" class="error-banner">
      <strong>请求异常:</strong> {{ errorBanner }}
    </div>

    <section class="kpi-grid">
      <div class="kpi-card">
        <span class="kpi-label">已审查合同</span>
        <strong class="kpi-value">{{ overview.contracts_reviewed }}</strong>
        <span class="kpi-sub">总合同数 {{ overview.contracts_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">高/极高风险条款</span>
        <strong class="kpi-value warn">{{ overview.high_risk_clauses }}</strong>
        <span class="kpi-sub">总条款 {{ overview.clauses_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">现行法规本体</span>
        <strong class="kpi-value">{{ overview.active_regulations }}</strong>
        <span class="kpi-sub">总法规 {{ overview.regulations_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">待法务总监审批</span>
        <strong class="kpi-value accent">{{ overview.pending_gc_approvals }}</strong>
        <span class="kpi-sub">HITL 队列</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">PII 自动脱敏</span>
        <strong class="kpi-value">{{ overview.pii_masked_total }}</strong>
        <span class="kpi-sub">Wiki 页面 {{ overview.wiki_pages_count }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">合规审计日志</span>
        <strong class="kpi-value">{{ overview.audit_logs_count }}</strong>
        <span class="kpi-sub">不可篡改追踪</span>
      </div>
    </section>

    <nav class="tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'review' }]"
        @click="activeTab = 'review'"
      >
        合同审查与 Redline 对比
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        法规本体图谱
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        法规 LLM Wiki 与巡检
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        法务总监 HITL 审批与审计
        <span v-if="pendingActions.length" class="tab-count">{{ pendingActions.length }}</span>
      </button>
    </nav>

    <!-- Tab 1: Contract Review & Redline Diff -->
    <main v-if="activeTab === 'review'" class="panel-grid">
      <section class="card">
        <h2>1. FDE 合同审查流水线 (PII 脱敏 + 风险分类 + Redline)</h2>
        <div class="form-row">
          <label>
            合同 ID
            <input v-model="reviewForm.contract_id" type="text" />
          </label>
          <label>
            合同标题
            <input v-model="reviewForm.title" type="text" />
          </label>
        </div>
        <div class="form-row">
          <label>
            相对方
            <input v-model="reviewForm.counterparty" type="text" />
          </label>
          <label>
            管辖法域
            <input v-model="reviewForm.jurisdiction" type="text" />
          </label>
          <label>
            责任上限 (USD)
            <input v-model.number="reviewForm.liability_cap_usd" type="number" />
          </label>
        </div>
        <label class="full-width">
          合同文本
          <textarea v-model="reviewForm.text" rows="6"></textarea>
        </label>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitContractReview">
            执行智能审查
          </button>
        </div>

        <div v-if="reviewResult" class="result-box">
          <div class="result-header">
            <span :class="riskBadgeClass(reviewResult.overall_risk_level)">
              综合风险: {{ reviewResult.overall_risk_level.toUpperCase() }} ({{ reviewResult.overall_risk_score }})
            </span>
            <span class="meta-chip">PII 脱敏: {{ reviewResult.pii_masked_count }} 处</span>
            <span class="meta-chip">
              HITL 状态: {{ reviewResult.requires_hitl ? "需法务总监审批" : "自动通过" }}
            </span>
          </div>
          <div class="masked-preview">
            <strong>脱敏后文本:</strong>
            <pre>{{ reviewResult.masked_text }}</pre>
          </div>
          <div class="clause-list">
            <div v-for="cl in reviewResult.clauses" :key="cl.id" class="clause-item">
              <div class="clause-top">
                <strong>{{ cl.title }}</strong>
                <span :class="riskBadgeClass(cl.risk_level)">{{ cl.risk_level }} ({{ cl.risk_score }})</span>
              </div>
              <p class="clause-type">类型: {{ cl.clause_type }} · 关联法规: {{ cl.matched_regulations.join(", ") || "无" }}</p>
              <p v-if="cl.redline_suggestion" class="redline-box">{{ cl.redline_suggestion }}</p>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>2. 合同版本 Redline 对比 (Clause Risk Delta)</h2>
        <div class="form-row">
          <label>
            对比 ID
            <input v-model="diffForm.contract_id" type="text" />
          </label>
          <label>
            对比标题
            <input v-model="diffForm.title" type="text" />
          </label>
        </div>
        <div class="form-row">
          <label>
            原始版本 (v1)
            <textarea v-model="diffForm.original_text" rows="6"></textarea>
          </label>
          <label>
            修订版本 (v2)
            <textarea v-model="diffForm.revised_text" rows="6"></textarea>
          </label>
        </div>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitRedlineDiff">
            计算风险 Delta 与 Redline 建议
          </button>
        </div>

        <div v-if="diffResult" class="result-box">
          <div class="result-header">
            <span :class="riskBadgeClass(diffResult.original_risk_level)">
              v1: {{ diffResult.original_risk_level }} ({{ diffResult.original_risk_score }})
            </span>
            <span>→</span>
            <span :class="riskBadgeClass(diffResult.revised_risk_level)">
              v2: {{ diffResult.revised_risk_level }} ({{ diffResult.revised_risk_score }})
            </span>
            <span class="meta-chip">
              Delta: {{ diffResult.risk_score_delta > 0 ? "+" : "" }}{{ diffResult.risk_score_delta }}
              ({{ diffResult.risk_trend }})
            </span>
          </div>
          <div v-for="cd in diffResult.clause_diffs" :key="cd.index" class="clause-item">
            <div class="clause-top">
              <strong>#{{ cd.index }} {{ cd.title }} [{{ cd.status }}]</strong>
              <span class="meta-chip">风险变化: {{ cd.risk_delta > 0 ? "+" : "" }}{{ cd.risk_delta }}</span>
            </div>
            <p v-if="cd.redline_recommendation" class="redline-box">{{ cd.redline_recommendation }}</p>
            <pre v-if="cd.diff_lines.length" class="diff-pre">{{ cd.diff_lines.join("\n") }}</pre>
          </div>
        </div>
      </section>
    </main>

    <!-- Tab 2: Legal Ontology Graph -->
    <main v-if="activeTab === 'ontology'" class="panel-grid">
      <section class="card">
        <h2>法规本体库 ({{ regulations.length }})</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>法规代码</th>
              <th>名称</th>
              <th>法域</th>
              <th>状态</th>
              <th>关键词</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="reg in regulations" :key="reg.id">
              <td><code>{{ reg.code }}</code></td>
              <td>{{ reg.title }}</td>
              <td>{{ reg.jurisdiction }}</td>
              <td>
                <span :class="['badge', reg.status === 'superseded' ? 'badge-high' : 'badge-low']">
                  {{ reg.status }}
                </span>
              </td>
              <td class="muted">{{ reg.keywords.join(", ") }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="section-head">
          <h2>条款本体与风险映射 ({{ filteredClauses.length }})</h2>
          <select v-model="riskFilter">
            <option value="">全部风险等级</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </div>
        <div v-if="filteredClauses.length === 0" class="empty-state">
          暂无已注册条款，请先在「合同审查」或「Wiki 入库」提交合同。
        </div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>条款 ID</th>
              <th>类型</th>
              <th>风险</th>
              <th>匹配法规</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cl in filteredClauses" :key="cl.id">
              <td><code>{{ cl.id }}</code></td>
              <td>{{ cl.clause_type }}</td>
              <td><span :class="riskBadgeClass(cl.risk_level)">{{ cl.risk_level }}</span></td>
              <td>{{ cl.matched_regulations.join(", ") || "-" }}</td>
            </tr>
          </tbody>
        </table>

        <h3 class="sub-heading">本体关系边 ({{ ontologyLinks.length }})</h3>
        <div class="link-pills">
          <span v-for="lnk in ontologyLinks.slice(0, 20)" :key="lnk.id" class="meta-chip">
            {{ lnk.source_id }} —[{{ lnk.relation }}]→ {{ lnk.target_id }}
          </span>
        </div>
      </section>
    </main>

    <!-- Tab 3: LLM Wiki & Lint -->
    <main v-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <h2>法规 / 合同 Markdown Wiki 入库</h2>
        <div class="form-row">
          <label>
            文档 ID
            <input v-model="wikiIngestForm.doc_id" type="text" />
          </label>
          <label>
            类型
            <select v-model="wikiIngestForm.doc_type">
              <option value="regulation">regulation</option>
              <option value="contract">contract</option>
              <option value="clause">clause</option>
            </select>
          </label>
        </div>
        <label class="full-width">
          标题
          <input v-model="wikiIngestForm.title" type="text" />
        </label>
        <label class="full-width">
          正文内容
          <textarea v-model="wikiIngestForm.content" rows="4"></textarea>
        </label>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitWikiIngest">
            写入 Wiki 知识库
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="runWikiLint">
            执行 Wiki 合规巡检 (Lint)
          </button>
        </div>
        <p v-if="wikiIngestMessage" class="success-msg">{{ wikiIngestMessage }}</p>

        <div v-if="lintReport" class="result-box">
          <h3>巡检报告 · 发现问题总数: {{ lintReport.total_issues }}</h3>
          <ul>
            <li>引用已废止法规: {{ lintReport.superseded_regulations.length }}</li>
            <li>未关联法规孤立条款: {{ lintReport.unlinked_clauses.length }}</li>
            <li>责任上限冲突: {{ lintReport.conflicting_liability_caps.length }}</li>
          </ul>
          <pre v-if="lintReport.total_issues > 0" class="diff-pre">{{ JSON.stringify(lintReport, null, 2) }}</pre>
        </div>
      </section>

      <section class="card">
        <h2>Wiki 知识库页面列表 ({{ wikiPages.length }})</h2>
        <div class="wiki-list">
          <div v-for="page in wikiPages" :key="page.id" class="wiki-card">
            <div class="clause-top">
              <strong>{{ page.title }}</strong>
              <code>{{ page.path }}</code>
            </div>
            <p class="muted">{{ page.preview }}</p>
          </div>
        </div>
      </section>
    </main>

    <!-- Tab 4: HITL Approval & Audit -->
    <main v-if="activeTab === 'hitl'" class="panel-grid">
      <section class="card">
        <h2>法务总监 HITL 待审批队列 ({{ pendingActions.length }})</h2>
        <div class="form-row">
          <label>
            审批人 (General Counsel)
            <input v-model="hitlApprover" type="text" />
          </label>
          <label>
            审批意见备注
            <input v-model="hitlNotes" type="text" />
          </label>
        </div>
        <div v-if="pendingActions.length === 0" class="empty-state">
          当前无待审批的高风险条款。
        </div>
        <div v-for="act in pendingActions" :key="act.id" class="clause-item">
          <div class="clause-top">
            <strong>{{ act.id }} · 合同 {{ act.contract_id }}</strong>
            <span :class="riskBadgeClass(act.risk_level)">{{ act.risk_level }}</span>
          </div>
          <p class="muted">条款: {{ act.clause_id || "-" }} · 发起人: {{ act.requested_by }}</p>
          <div class="actions-row">
            <button class="btn btn-primary" :disabled="loading" @click="decideAction(act.id, 'approved')">
              批准例外 (Approve)
            </button>
            <button class="btn btn-danger" :disabled="loading" @click="decideAction(act.id, 'rejected')">
              驳回并要求 Redline (Reject)
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>合规审计日志 ({{ auditLogs.length }})</h2>
        <div v-if="auditLogs.length === 0" class="empty-state">暂无审计记录。</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>事件类型</th>
              <th>操作人</th>
              <th>目标对象</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(log, idx) in auditLogs" :key="idx">
              <td class="muted">{{ log.timestamp.slice(0, 19).replace("T", " ") }}</td>
              <td><code>{{ log.event_type }}</code></td>
              <td>{{ log.actor }}</td>
              <td><code>{{ log.target_id }}</code></td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<style scoped>
:root {
  color-scheme: dark;
}

.shell {
  min-height: 100vh;
  background: #0b1120;
  color: #e2e8f0;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding: 20px 28px 40px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 16px;
  margin-bottom: 20px;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-badge {
  background: linear-gradient(135deg, #3b82f6, #1d4ed8);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  padding: 10px 14px;
  border-radius: 10px;
}

.brand h1 {
  margin: 0;
  font-size: 20px;
  color: #f8fafc;
}

.subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: #94a3b8;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-pill {
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  font-weight: 600;
}

.status-pill.online {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(52, 211, 153, 0.35);
}

.status-pill.offline {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.35);
}

.error-banner {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid #ef4444;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.kpi-card {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-label {
  font-size: 12px;
  color: #94a3b8;
}

.kpi-value {
  font-size: 24px;
  color: #f8fafc;
}

.kpi-value.warn {
  color: #f87171;
}

.kpi-value.accent {
  color: #fbbf24;
}

.kpi-sub {
  font-size: 11px;
  color: #64748b;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.tab-btn {
  background: #111827;
  color: #cbd5e1;
  border: 1px solid #1e293b;
  padding: 10px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tab-btn.active {
  background: #1d4ed8;
  color: #ffffff;
  border-color: #3b82f6;
}

.tab-count {
  background: #ef4444;
  color: #fff;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 700;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 18px;
}

.card {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 18px;
}

.card h2 {
  margin: 0 0 14px;
  font-size: 16px;
  color: #f1f5f9;
}

.sub-heading {
  margin: 18px 0 10px;
  font-size: 14px;
  color: #cbd5e1;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: #94a3b8;
}

.full-width {
  margin-bottom: 10px;
}

input,
textarea,
select {
  background: #0f172a;
  color: #f8fafc;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
}

.actions-row {
  display: flex;
  gap: 10px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.btn {
  border: none;
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #2563eb;
  color: #fff;
}

.btn-secondary {
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
}

.btn-danger {
  background: #dc2626;
  color: #fff;
}

.result-box {
  margin-top: 14px;
  border-top: 1px solid #1e293b;
  padding-top: 12px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.badge-critical {
  background: rgba(220, 38, 38, 0.25);
  color: #fca5a5;
  border: 1px solid #dc2626;
}

.badge-high {
  background: rgba(249, 115, 22, 0.2);
  color: #fdba74;
  border: 1px solid #f97316;
}

.badge-medium {
  background: rgba(234, 179, 8, 0.2);
  color: #fde047;
  border: 1px solid #eab308;
}

.badge-low {
  background: rgba(16, 185, 129, 0.2);
  color: #6ee7b7;
  border: 1px solid #10b981;
}

.meta-chip {
  background: #1e293b;
  color: #cbd5e1;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
}

.masked-preview pre,
.diff-pre {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #cbd5e1;
}

.clause-item,
.wiki-card {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 10px 12px;
  margin-top: 8px;
}

.clause-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.clause-type {
  margin: 4px 0;
  font-size: 12px;
  color: #94a3b8;
}

.redline-box {
  margin: 6px 0 0;
  padding: 6px 8px;
  background: rgba(245, 158, 11, 0.12);
  border-left: 3px solid #f59e0b;
  font-size: 12px;
  color: #fde68a;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.data-table th,
.data-table td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid #1e293b;
}

.data-table th {
  color: #94a3b8;
  font-weight: 600;
}

.muted {
  color: #94a3b8;
  font-size: 12px;
}

.empty-state {
  padding: 20px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}

.success-msg {
  color: #34d399;
  font-size: 13px;
  margin-top: 8px;
}

.link-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wiki-list {
  max-height: 520px;
  overflow-y: auto;
}
</style>
