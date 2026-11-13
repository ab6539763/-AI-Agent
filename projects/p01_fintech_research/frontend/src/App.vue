<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  p01Api,
  type AuditLogEntry,
  type BatchScreenResponse,
  type ComplianceAction,
  type DashboardOverview,
  type OntologyGraphResponse,
  type ResearchQueryResponse,
  type WikiLintResponse,
  type WikiPageSummary,
} from "./api/client";

type TabKey = "workbench" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabKey>("workbench");
const loading = ref(false);
const bannerError = ref("");
const bannerSuccess = ref("");

const overview = ref<DashboardOverview>({
  total_issuers: 0,
  risk_signals: 0,
  wiki_pages_count: 0,
  pending_hitl_count: 0,
  audit_events_count: 0,
});

// Tab 1: Research & Batch Screen
const queryForm = reactive({
  issuer_id: "issuer_alpha",
  actor_role: "analyst",
  period: "2025-Q4",
  question: "评估 Alpha Fin 2025-Q4 杠杆率与偿债覆盖风险",
  total_debt: 320,
  shareholders_equity: 100,
  current_assets: 85,
  current_liabilities: 100,
  ebit: 12,
  interest_expense: 10,
  net_income: 8,
});
const queryResult = ref<ResearchQueryResponse | null>(null);
const batchResult = ref<BatchScreenResponse | null>(null);

// Tab 2: Ontology Graph
const graphIssuerFilter = ref("");
const graphMaxDepth = ref(2);
const graphData = ref<OntologyGraphResponse>({ nodes: [], edges: [] });

// Tab 3: LLM Wiki & Lint
const wikiPages = ref<WikiPageSummary[]>([]);
const lintResult = ref<WikiLintResponse | null>(null);
const ingestForm = reactive({
  doc_id: "doc_q4_alpha",
  title: "Alpha Fin 2025-Q4 财报摘要",
  content: "Alpha Fin 业务稳健，同业对标 [[issuer_beta]]。",
  entity_id: "issuer_alpha",
  entity_name: "Alpha Fin",
  ticker: "ALPH",
  sector: "Lending",
  credit_rating: "BBB",
  period: "2025-Q4",
  debt_to_equity: 2.1,
});

// Tab 4: HITL & Audit
const pendingActions = ref<ComplianceAction[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);
const hitlApprover = ref("cro.wang");
const hitlRole = ref("compliance_officer");
const hitlComment = ref("经风控委员会复核确认");

function clearAlerts() {
  bannerError.value = "";
  bannerSuccess.value = "";
}

async function refreshOverview() {
  overview.value = await p01Api.getDashboardOverview();
}

async function refreshAll() {
  clearAlerts();
  loading.value = true;
  try {
    await Promise.all([
      refreshOverview(),
      loadGraph(),
      loadWikiPages(),
      loadHitlAndAudit(),
    ]);
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function submitResearchQuery() {
  clearAlerts();
  loading.value = true;
  try {
    queryResult.value = await p01Api.runResearchQuery({
      question: queryForm.question,
      issuer_id: queryForm.issuer_id || undefined,
      actor_role: queryForm.actor_role,
      period: queryForm.period,
      financials: {
        total_debt: Number(queryForm.total_debt),
        shareholders_equity: Number(queryForm.shareholders_equity),
        current_assets: Number(queryForm.current_assets),
        current_liabilities: Number(queryForm.current_liabilities),
        ebit: Number(queryForm.ebit),
        interest_expense: Number(queryForm.interest_expense),
        net_income: Number(queryForm.net_income),
      },
    });
    await Promise.all([refreshOverview(), loadHitlAndAudit(), loadGraph()]);
    bannerSuccess.value =
      queryResult.value.status === "blocked"
        ? "合规护栏已拦截高风险查询并写入审计日志"
        : "投研分析与财务比率计算已完成";
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runDemoBatchScreen() {
  clearAlerts();
  loading.value = true;
  try {
    batchResult.value = await p01Api.runBatchScreen([
      {
        issuer_id: "issuer_alpha",
        name: "Alpha Fin",
        ticker: "ALPH",
        sector: "Lending",
        credit_rating: "BBB",
        period: "2025-Q4",
        financials: {
          total_debt: 320,
          shareholders_equity: 100,
          current_assets: 80,
          current_liabilities: 100,
          ebit: 10,
          interest_expense: 10,
          net_income: 5,
        },
      },
      {
        issuer_id: "issuer_beta",
        name: "Beta Pay",
        ticker: "BETA",
        sector: "Payments",
        credit_rating: "A",
        period: "2025-Q4",
        financials: {
          total_debt: 60,
          shareholders_equity: 120,
          current_assets: 180,
          current_liabilities: 100,
          ebit: 45,
          interest_expense: 5,
          net_income: 30,
        },
      },
    ]);
    await Promise.all([refreshOverview(), loadHitlAndAudit(), loadGraph()]);
    bannerSuccess.value = `批量风险筛查完成：共 ${batchResult.value.screened_count} 家发行人，高风险 ${batchResult.value.high_risk_count} 家`;
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function loadGraph() {
  graphData.value = await p01Api.getOntologyGraph(
    graphIssuerFilter.value.trim() || undefined,
    graphMaxDepth.value
  );
}

async function loadWikiPages() {
  const res = await p01Api.getWikiPages();
  wikiPages.value = res.pages;
}

async function submitWikiIngest() {
  clearAlerts();
  loading.value = true;
  try {
    await p01Api.ingestWiki({
      doc_id: ingestForm.doc_id,
      title: ingestForm.title,
      content: ingestForm.content,
      entities: [
        {
          id: ingestForm.entity_id,
          name: ingestForm.entity_name,
          type: "Issuer",
          ticker: ingestForm.ticker,
          sector: ingestForm.sector,
          credit_rating: ingestForm.credit_rating,
          period: ingestForm.period,
          metrics: { debt_to_equity: Number(ingestForm.debt_to_equity) },
        },
      ],
    });
    await Promise.all([refreshOverview(), loadWikiPages(), loadGraph(), loadHitlAndAudit()]);
    bannerSuccess.value = `文档 ${ingestForm.doc_id} 已编译入库至 LLM Wiki 与 Ontology`;
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runWikiLint() {
  clearAlerts();
  loading.value = true;
  try {
    lintResult.value = await p01Api.lintWiki(90);
    bannerSuccess.value = "LLM Wiki 知识库巡检完成";
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function loadHitlAndAudit() {
  const [actRes, logRes] = await Promise.all([
    p01Api.getPendingActions(),
    p01Api.getAuditLogs(50),
  ]);
  pendingActions.value = actRes.actions;
  auditLogs.value = logRes.logs;
}

async function decideAction(actionId: string, decision: "approve" | "reject") {
  clearAlerts();
  loading.value = true;
  try {
    const res = await p01Api.approveAction({
      action_id: actionId,
      decision,
      actor_role: hitlRole.value,
      approver: hitlApprover.value,
      comment: hitlComment.value,
    });
    await Promise.all([refreshOverview(), loadHitlAndAudit()]);
    bannerSuccess.value = res.message;
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
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
    <header class="top-bar">
      <div>
        <h1>P01 FinTech 投研与合规智能体工作台</h1>
        <p class="subtitle">
          Ontology 风险图谱 · LLM Wiki 知识库 · 财务比率引擎 · PII/MNPI 护栏 · HITL 审批审计
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="loading" @click="refreshAll">
        {{ loading ? "同步中..." : "刷新全局状态" }}
      </button>
    </header>

    <section class="kpi-grid">
      <div class="kpi-card">
        <span class="kpi-label">Ontology 发行人</span>
        <strong class="kpi-value">{{ overview.total_issuers }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">风险信号数</span>
        <strong class="kpi-value warn">{{ overview.risk_signals }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Wiki 实体页</span>
        <strong class="kpi-value">{{ overview.wiki_pages_count }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">待审批 HITL</span>
        <strong class="kpi-value danger">{{ overview.pending_hitl_count }}</strong>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">审计事件总数</span>
        <strong class="kpi-value">{{ overview.audit_events_count }}</strong>
      </div>
    </section>

    <div v-if="bannerError" class="alert alert-error">{{ bannerError }}</div>
    <div v-if="bannerSuccess" class="alert alert-success">{{ bannerSuccess }}</div>

    <nav class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'workbench' }]"
        @click="activeTab = 'workbench'"
      >
        投研合规工作台
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        Ontology 风险图谱
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        LLM Wiki 知识库与巡检
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        HITL 审批与审计中心
      </button>
    </nav>

    <!-- Tab 1: 投研合规工作台 -->
    <main v-if="activeTab === 'workbench'" class="panel-grid">
      <section class="card">
        <h2>单发行人投研查询与财务比率风控</h2>
        <div class="form-row">
          <label>
            发行人 ID
            <input v-model="queryForm.issuer_id" placeholder="issuer_alpha" />
          </label>
          <label>
            角色
            <input v-model="queryForm.actor_role" placeholder="analyst" />
          </label>
          <label>
            报告期
            <input v-model="queryForm.period" placeholder="2025-Q4" />
          </label>
        </div>
        <label class="full-width">
          投研问题 (内置 PII 脱敏与 MNPI 内幕交易拦截)
          <textarea v-model="queryForm.question" rows="2"></textarea>
        </label>
        <div class="form-row">
          <label>总负债 <input v-model.number="queryForm.total_debt" type="number" /></label>
          <label>股东权益 <input v-model.number="queryForm.shareholders_equity" type="number" /></label>
          <label>流动资产 <input v-model.number="queryForm.current_assets" type="number" /></label>
          <label>流动负债 <input v-model.number="queryForm.current_liabilities" type="number" /></label>
          <label>EBIT <input v-model.number="queryForm.ebit" type="number" /></label>
          <label>利息费用 <input v-model.number="queryForm.interest_expense" type="number" /></label>
        </div>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitResearchQuery">
            执行投研分析
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="runDemoBatchScreen">
            运行多发行人批量风险筛查
          </button>
        </div>

        <div v-if="queryResult" class="result-box">
          <h3>分析结果 ({{ queryResult.status }})</h3>
          <p v-if="queryResult.reason" class="text-danger">{{ queryResult.reason }}</p>
          <p v-if="queryResult.question"><strong>脱敏后问题：</strong>{{ queryResult.question }}</p>
          <p v-if="queryResult.guardrail?.findings?.length">
            <strong>护栏命中：</strong>{{ queryResult.guardrail.findings.join(", ") }}
          </p>
          <div v-if="queryResult.ratios">
            <strong>财务比率：</strong>
            <code>{{ JSON.stringify(queryResult.ratios.ratios) }}</code>
            <ul v-if="queryResult.ratios.triggered_risks.length">
              <li v-for="(r, idx) in queryResult.ratios.triggered_risks" :key="idx">
                [{{ r.severity }}] {{ r.category }}: {{ r.description }}
              </li>
            </ul>
          </div>
          <p v-if="queryResult.hitl_pending_action" class="text-warn">
            已自动触发 HITL 审批动作：{{ queryResult.hitl_pending_action.action_id }}
            ({{ queryResult.hitl_pending_action.action_type }})
          </p>
        </div>
      </section>

      <section v-if="batchResult" class="card">
        <h2>批量风险筛查结果 ({{ batchResult.screened_count }} 家)</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>发行人</th>
              <th>风险等级</th>
              <th>核心比率</th>
              <th>HITL 动作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in batchResult.results" :key="item.issuer_id">
              <td>{{ item.name }} ({{ item.issuer_id }})</td>
              <td>
                <span :class="['badge', item.risk_level.toLowerCase()]">{{ item.risk_level }}</span>
              </td>
              <td><code>{{ JSON.stringify(item.ratios) }}</code></td>
              <td>
                {{ item.hitl_pending_action ? item.hitl_pending_action.action_type : "无需审批" }}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>

    <!-- Tab 2: Ontology 风险图谱 -->
    <main v-if="activeTab === 'ontology'" class="card">
      <h2>Ontology 实体与风险传导图谱</h2>
      <div class="form-row">
        <label>
          按发行人过滤 (留空查看全图)
          <input v-model="graphIssuerFilter" placeholder="issuer_alpha" />
        </label>
        <label>
          遍历深度
          <input v-model.number="graphMaxDepth" type="number" min="1" max="5" />
        </label>
        <div class="align-end">
          <button class="btn btn-primary" :disabled="loading" @click="loadGraph">查询图谱</button>
        </div>
      </div>

      <div class="split-grid">
        <div>
          <h3>节点 ({{ graphData.nodes.length }})</h3>
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>类型</th>
                <th>名称/属性</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="node in graphData.nodes" :key="node.id">
                <td><code>{{ node.id }}</code></td>
                <td>{{ node.type || "-" }}</td>
                <td>{{ node.name || node.action_type || node.category || "-" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>关系边 ({{ graphData.edges.length }})</h3>
          <table class="data-table">
            <thead>
              <tr>
                <th>源节点</th>
                <th>关系</th>
                <th>目标节点</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(edge, idx) in graphData.edges" :key="idx">
                <td><code>{{ edge.source_id }}</code></td>
                <td><span class="badge">{{ edge.relation }}</span></td>
                <td><code>{{ edge.target_id }}</code></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>

    <!-- Tab 3: LLM Wiki 知识库与巡检 -->
    <main v-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <h2>文档入库与 Wiki 编译</h2>
        <div class="form-row">
          <label>文档 ID <input v-model="ingestForm.doc_id" /></label>
          <label>标题 <input v-model="ingestForm.title" /></label>
          <label>实体 ID <input v-model="ingestForm.entity_id" /></label>
          <label>实体名称 <input v-model="ingestForm.entity_name" /></label>
        </div>
        <label class="full-width">
          文档正文 (支持 [[wiki_link]] 双向链接)
          <textarea v-model="ingestForm.content" rows="2"></textarea>
        </label>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitWikiIngest">
            入库并编译 Wiki
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="runWikiLint">
            运行知识库 Lint 巡检
          </button>
        </div>

        <div v-if="lintResult" class="result-box">
          <h3>Lint 巡检报告 ({{ lintResult.status }})</h3>
          <p>
            总页数: {{ lintResult.total_pages }} · 孤立页: {{ lintResult.orphan_pages.length }} ·
            断链: {{ lintResult.broken_links.length }} · 指标冲突:
            {{ lintResult.conflicting_metrics.length }} · 过期条目:
            {{ lintResult.stale_entries.length }}
          </p>
        </div>
      </section>

      <section class="card">
        <h2>已编译 Wiki 页面 ({{ wikiPages.length }})</h2>
        <div v-if="wikiPages.length === 0" class="empty-state">暂无 Wiki 页面，请先入库文档。</div>
        <div v-for="page in wikiPages" :key="page.id" class="wiki-item">
          <div class="wiki-header">
            <strong>{{ page.title }}</strong>
            <code>{{ page.path }}</code>
          </div>
          <p class="wiki-preview">{{ page.preview }}</p>
        </div>
      </section>
    </main>

    <!-- Tab 4: HITL 审批与审计中心 -->
    <main v-if="activeTab === 'hitl'" class="panel-grid">
      <section class="card">
        <h2>待审批 HITL 合规动作 ({{ pendingActions.length }})</h2>
        <div class="form-row">
          <label>审批人 <input v-model="hitlApprover" /></label>
          <label>审批角色 <input v-model="hitlRole" /></label>
          <label>审批意见 <input v-model="hitlComment" /></label>
        </div>

        <div v-if="pendingActions.length === 0" class="empty-state">当前无待审批 HITL 动作。</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Action ID</th>
              <th>发行人</th>
              <th>动作类型</th>
              <th>依据</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="act in pendingActions" :key="act.action_id">
              <td><code>{{ act.action_id }}</code></td>
              <td>{{ act.issuer_id }}</td>
              <td><span class="badge high">{{ act.action_type }}</span></td>
              <td>{{ act.rationale }}</td>
              <td class="actions-cell">
                <button class="btn btn-primary btn-sm" @click="decideAction(act.action_id, 'approve')">
                  批准
                </button>
                <button class="btn btn-danger btn-sm" @click="decideAction(act.action_id, 'reject')">
                  驳回
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>JSONL 不可篡改审计日志 (最近 {{ auditLogs.length }} 条)</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>事件类型</th>
              <th>事件 ID</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.event_id">
              <td>{{ log.timestamp }}</td>
              <td><span class="badge">{{ log.event_type }}</span></td>
              <td><code>{{ log.event_id }}</code></td>
              <td><code>{{ JSON.stringify(log) }}</code></td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f4f6f9;
  color: #1e293b;
}
.app-shell {
  max-width: 1240px;
  margin: 0 auto;
  padding: 20px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}
h1 {
  margin: 0;
  font-size: 1.5rem;
}
.subtitle {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 0.9rem;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.kpi-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kpi-label {
  font-size: 0.82rem;
  color: #64748b;
}
.kpi-value {
  font-size: 1.5rem;
  color: #0f172a;
}
.kpi-value.warn { color: #d97706; }
.kpi-value.danger { color: #dc2626; }
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.tab-btn {
  padding: 9px 16px;
  border: 1px solid #cbd5e1;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  color: #334155;
}
.tab-btn.active {
  background: #1d4ed8;
  color: #fff;
  border-color: #1d4ed8;
}
.panel-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.split-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
}
.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 18px;
}
.card h2 {
  margin: 0 0 14px;
  font-size: 1.15rem;
}
.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
  color: #475569;
}
.full-width {
  margin-bottom: 12px;
}
input, textarea {
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.9rem;
}
.actions-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.align-end {
  display: flex;
  align-items: flex-end;
}
.btn {
  padding: 8px 14px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-weight: 600;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-primary { background: #1d4ed8; color: #fff; }
.btn-secondary { background: #e2e8f0; color: #1e293b; }
.btn-danger { background: #dc2626; color: #fff; }
.btn-sm { padding: 5px 10px; font-size: 0.8rem; }
.actions-cell {
  display: flex;
  gap: 6px;
}
.alert {
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 0.9rem;
}
.alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.alert-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
.result-box {
  margin-top: 14px;
  padding: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.data-table th, .data-table td {
  border-bottom: 1px solid #e2e8f0;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
.data-table th {
  background: #f8fafc;
  color: #475569;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: #e2e8f0;
  color: #334155;
}
.badge.low { background: #dcfce7; color: #166534; }
.badge.high { background: #fef3c7; color: #92400e; }
.badge.critical { background: #fee2e2; color: #991b1b; }
.wiki-item {
  padding: 10px 0;
  border-bottom: 1px solid #e2e8f0;
}
.wiki-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.wiki-preview {
  margin: 6px 0 0;
  font-size: 0.85rem;
  color: #475569;
}
.empty-state {
  color: #64748b;
  font-size: 0.9rem;
  padding: 12px 0;
}
.text-danger { color: #dc2626; }
.text-warn { color: #d97706; font-weight: 600; }
</style>
