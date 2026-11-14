<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import {
  p01Api,
  type AuditLogEntry,
  type ComplianceAction,
  type CreditScoreResponse,
  type DashboardOverview,
  type OntologyGraphResponse,
  type ResearchQueryResponse,
  type WikiLintResponse,
  type WikiPageSummary,
} from "./api/client";
import TickerWatchlist, { type WatchlistIssuer } from "./components/TickerWatchlist.vue";
import ComplianceBlotter from "./components/ComplianceBlotter.vue";

const loading = ref(false);
const bannerError = ref("");
const bannerSuccess = ref("");
const drawerOpen = ref(false);
const drawerTab = ref<"ontology" | "wiki">("ontology");

const overview = ref<DashboardOverview>({
  total_issuers: 0,
  risk_signals: 0,
  wiki_pages_count: 0,
  pending_hitl_count: 0,
  audit_events_count: 0,
  ontology_links_count: 0,
});

// Seeded + dynamic Bloomberg/Wind-style watchlist
const watchlist = ref<WatchlistIssuer[]>([
  {
    issuer_id: "issuer_alpha",
    ticker: "ALPH",
    name: "Alpha FinTech Holdings",
    sector: "Lending",
    credit_rating: "BBB",
    risk_level: "HIGH",
    financials: {
      total_debt: 320,
      shareholders_equity: 100,
      current_assets: 85,
      current_liabilities: 100,
      ebit: 12,
      interest_expense: 10,
      net_income: 8,
    },
  },
  {
    issuer_id: "issuer_beta",
    ticker: "BETA",
    name: "Beta Cross-Border Pay",
    sector: "Payments",
    credit_rating: "AA",
    risk_level: "SAFE",
    financials: {
      total_debt: 60,
      shareholders_equity: 180,
      current_assets: 210,
      current_liabilities: 95,
      ebit: 64,
      interest_expense: 5,
      net_income: 46,
    },
  },
  {
    issuer_id: "issuer_gamma",
    ticker: "GAMM",
    name: "Gamma Consumer Credit",
    sector: "Credit",
    credit_rating: "BB",
    risk_level: "CRITICAL",
    financials: {
      total_debt: 360,
      shareholders_equity: 90,
      current_assets: 70,
      current_liabilities: 125,
      ebit: 11,
      interest_expense: 14,
      net_income: -4,
    },
  },
]);

const queryForm = reactive({
  issuer_id: "issuer_alpha",
  actor_role: "analyst",
  period: "2025-Q4",
  question: "Assess Alpha FinTech leverage, Altman Z-Score, and DCF sensitivity",
  total_debt: 320,
  shareholders_equity: 100,
  current_assets: 85,
  current_liabilities: 100,
  ebit: 12,
  interest_expense: 10,
  net_income: 8,
  wacc: 0.09,
  terminal_growth: 0.025,
});

const creditScore = ref<CreditScoreResponse | null>(null);
const queryResult = ref<ResearchQueryResponse | null>(null);

// SSE Streaming state
const streamStatus = ref<"idle" | "streaming" | "completed" | "blocked" | "error">("idle");
const streamOutput = ref("");
const streamStages = ref<Array<Record<string, unknown>>>([]);
let closeStreamFn: (() => void) | null = null;

// Right Blotter state
const pendingActions = ref<ComplianceAction[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);

// Drawer: Ontology & Wiki
const graphIssuerFilter = ref("");
const graphMaxDepth = ref(2);
const graphData = ref<OntologyGraphResponse>({ nodes: [], edges: [] });
const wikiPages = ref<WikiPageSummary[]>([]);
const lintResult = ref<WikiLintResponse | null>(null);
const ingestForm = reactive({
  doc_id: "doc_q4_alpha",
  title: "Alpha FinTech 2025-Q4 Filing",
  content: "Alpha FinTech exposure and liquidity review; peer [[issuer_beta]].",
  entity_id: "issuer_alpha",
  entity_name: "Alpha FinTech Holdings",
  ticker: "ALPH",
  sector: "Lending",
  credit_rating: "BBB",
  period: "2025-Q4",
  debt_to_equity: 3.2,
});

const sensitivityHeaders = computed(() => {
  const mat = creditScore.value?.dcf_valuation.sensitivity_matrix;
  if (!mat || mat.length === 0) return [];
  return Object.keys(mat[0].equity_values_by_terminal_growth);
});

function clearAlerts() {
  bannerError.value = "";
  bannerSuccess.value = "";
}

function selectWatchlistIssuer(item: WatchlistIssuer) {
  queryForm.issuer_id = item.issuer_id;
  if (item.financials) {
    queryForm.total_debt = item.financials.total_debt ?? queryForm.total_debt;
    queryForm.shareholders_equity =
      item.financials.shareholders_equity ?? queryForm.shareholders_equity;
    queryForm.current_assets = item.financials.current_assets ?? queryForm.current_assets;
    queryForm.current_liabilities =
      item.financials.current_liabilities ?? queryForm.current_liabilities;
    queryForm.ebit = item.financials.ebit ?? queryForm.ebit;
    queryForm.interest_expense =
      item.financials.interest_expense ?? queryForm.interest_expense;
    queryForm.net_income = item.financials.net_income ?? queryForm.net_income;
  }
  queryForm.question = `Assess ${item.name} (${item.ticker}) credit quality, Z-Score & DCF valuation`;
  runCreditScoring();
}

async function refreshOverview() {
  overview.value = await p01Api.getDashboardOverview();
}

async function loadHitlAndAudit() {
  const [p, l] = await Promise.all([
    p01Api.getPendingActions(),
    p01Api.getAuditLogs(40),
  ]);
  pendingActions.value = p.actions;
  auditLogs.value = l.logs;
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

async function refreshAll() {
  clearAlerts();
  loading.value = true;
  try {
    await Promise.all([refreshOverview(), loadHitlAndAudit(), loadGraph(), loadWikiPages()]);
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function runCreditScoring() {
  clearAlerts();
  loading.value = true;
  try {
    const res = await p01Api.scoreCredit({
      issuer_id: queryForm.issuer_id,
      period: queryForm.period,
      total_debt: Number(queryForm.total_debt),
      shareholders_equity: Number(queryForm.shareholders_equity),
      current_assets: Number(queryForm.current_assets),
      current_liabilities: Number(queryForm.current_liabilities),
      ebit: Number(queryForm.ebit),
      interest_expense: Number(queryForm.interest_expense),
      net_income: Number(queryForm.net_income),
      wacc: Number(queryForm.wacc),
      terminal_growth: Number(queryForm.terminal_growth),
    });
    creditScore.value = res;
    const target = watchlist.value.find((w) => w.issuer_id === res.issuer_id);
    if (target) {
      target.credit_rating = res.credit_rating;
      target.risk_level = res.altman_z_score.zone;
      target.z_score = res.altman_z_score.score;
      target.composite_score = res.composite_score;
    }
    await Promise.all([refreshOverview(), loadHitlAndAudit()]);
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
    if (queryResult.value.status === "blocked") {
      bannerError.value = queryResult.value.reason || "Blocked by compliance guardrail";
    } else {
      bannerSuccess.value = `Compliance query completed (audit ${queryResult.value.audit_event_id.slice(0, 8)})`;
    }
    await Promise.all([refreshOverview(), loadHitlAndAudit(), loadGraph()]);
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function startResearchStream() {
  clearAlerts();
  if (closeStreamFn) {
    closeStreamFn();
    closeStreamFn = null;
  }
  streamOutput.value = "";
  streamStages.value = [];
  streamStatus.value = "streaming";

  closeStreamFn = p01Api.streamResearchMemo(
    {
      issuer_id: queryForm.issuer_id || undefined,
      question: queryForm.question,
      period: queryForm.period,
      total_debt: Number(queryForm.total_debt),
      shareholders_equity: Number(queryForm.shareholders_equity),
      current_assets: Number(queryForm.current_assets),
      current_liabilities: Number(queryForm.current_liabilities),
      ebit: Number(queryForm.ebit),
      interest_expense: Number(queryForm.interest_expense),
      net_income: Number(queryForm.net_income),
    },
    {
      onStage: (data) => {
        streamStages.value.push(data);
      },
      onToken: (data) => {
        streamOutput.value += data.text;
      },
      onBlocked: (data) => {
        streamStatus.value = "blocked";
        streamOutput.value = `[GUARDRAIL BLOCKED] ${String(data.reason || "Compliance violation")}`;
        bannerError.value = "Research stream blocked by MNPI/compliance guardrail.";
        void Promise.all([refreshOverview(), loadHitlAndAudit()]);
      },
      onDone: () => {
        if (streamStatus.value !== "blocked") {
          streamStatus.value = "completed";
        }
        void Promise.all([refreshOverview(), loadHitlAndAudit()]);
      },
      onError: () => {
        if (streamStatus.value === "streaming") {
          streamStatus.value = "error";
        }
      },
    }
  );
}

async function runBatchScreenAll() {
  clearAlerts();
  loading.value = true;
  try {
    const items = watchlist.value.map((w) => ({
      issuer_id: w.issuer_id,
      name: w.name,
      ticker: w.ticker,
      sector: w.sector,
      credit_rating: w.credit_rating,
      period: queryForm.period,
      financials: w.financials || {},
    }));
    const res = await p01Api.runBatchScreen(items, queryForm.actor_role);
    for (const r of res.results) {
      const target = watchlist.value.find((w) => w.issuer_id === r.issuer_id);
      if (target) {
        target.risk_level = r.risk_level;
      }
    }
    bannerSuccess.value = `Batch screened ${res.screened_count} issuers (${res.high_risk_count} high/critical risk).`;
    await Promise.all([refreshOverview(), loadHitlAndAudit(), loadGraph()]);
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function handleHitlDecision(payload: {
  action_id: string;
  decision: "approve" | "reject";
  actor_role: string;
  approver: string;
  comment: string;
}) {
  clearAlerts();
  loading.value = true;
  try {
    const res = await p01Api.approveAction(payload);
    bannerSuccess.value = res.message;
    await Promise.all([refreshOverview(), loadHitlAndAudit()]);
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
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
    bannerSuccess.value = `Ingested ${ingestForm.doc_id} into Wiki & Ontology.`;
    await Promise.all([refreshOverview(), loadWikiPages(), loadGraph(), loadHitlAndAudit()]);
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
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshAll();
  void runCreditScoring();
});

onBeforeUnmount(() => {
  if (closeStreamFn) closeStreamFn();
});
</script>

<template>
  <div class="terminal-shell">
    <!-- Top Bloomberg/Wind Terminal Bar -->
    <header class="terminal-topbar">
      <div class="brand-block">
        <span class="brand-badge">P01</span>
        <div>
          <h1>QUANTITATIVE CREDIT &amp; COMPLIANCE TERMINAL</h1>
          <p class="brand-sub">OFFLINE DETERMINISTIC ENGINE · ONTOLOGY · LLM WIKI · HITL</p>
        </div>
      </div>

      <div class="kpi-strip">
        <div class="kpi-chip">
          <span class="kpi-label">ISSUERS</span>
          <span class="kpi-val">{{ overview.total_issuers }}</span>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">SIGNALS</span>
          <span class="kpi-val amber">{{ overview.risk_signals }}</span>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">WIKI</span>
          <span class="kpi-val">{{ overview.wiki_pages_count }}</span>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">PENDING HITL</span>
          <span class="kpi-val" :class="overview.pending_hitl_count > 0 ? 'red' : 'green'">
            {{ overview.pending_hitl_count }}
          </span>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">AUDIT</span>
          <span class="kpi-val">{{ overview.audit_events_count }}</span>
        </div>
      </div>

      <div class="topbar-actions">
        <button class="btn-amber-outline" @click="drawerOpen = !drawerOpen">
          {{ drawerOpen ? "CLOSE DRAWER" : "ONTOLOGY & WIKI" }}
        </button>
        <button class="btn-amber" :disabled="loading" @click="refreshAll">
          {{ loading ? "SYNCING..." : "SYNC ALL" }}
        </button>
      </div>
    </header>

    <!-- Alert Banner -->
    <div v-if="bannerError" class="alert-bar alert-error">
      <span>[ALERT] {{ bannerError }}</span>
      <button class="btn-mini" @click="bannerError = ''">DISMISS</button>
    </div>
    <div v-if="bannerSuccess" class="alert-bar alert-success">
      <span>[OK] {{ bannerSuccess }}</span>
      <button class="btn-mini" @click="bannerSuccess = ''">DISMISS</button>
    </div>

    <!-- 3-Column Quantitative Terminal Grid -->
    <main class="terminal-grid">
      <!-- Left: Issuer Watchlist -->
      <TickerWatchlist
        :issuers="watchlist"
        :selected-issuer-id="queryForm.issuer_id"
        :loading="loading"
        @select-issuer="selectWatchlistIssuer"
        @run-batch-screen="runBatchScreenAll"
      />

      <!-- Center: Quant Credit & Streaming Research -->
      <section class="terminal-panel center-workspace">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-dot"></span>
            <h2>QUANT CREDIT &amp; STREAMING RESEARCH</h2>
          </div>
          <span class="mono-tag">{{ queryForm.issuer_id.toUpperCase() }} // {{ queryForm.period }}</span>
        </div>

        <!-- Financial Parameters & Query Bar -->
        <div class="workspace-controls">
          <div class="params-grid">
            <label class="param-field">
              <span>ISSUER ID</span>
              <input v-model="queryForm.issuer_id" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>PERIOD</span>
              <input v-model="queryForm.period" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>TOTAL DEBT</span>
              <input v-model.number="queryForm.total_debt" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>EQUITY</span>
              <input v-model.number="queryForm.shareholders_equity" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>CURR ASSETS</span>
              <input v-model.number="queryForm.current_assets" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>CURR LIAB</span>
              <input v-model.number="queryForm.current_liabilities" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>EBIT</span>
              <input v-model.number="queryForm.ebit" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>INTEREST EXP</span>
              <input v-model.number="queryForm.interest_expense" type="number" class="terminal-input" />
            </label>
            <label class="param-field">
              <span>NET INCOME</span>
              <input v-model.number="queryForm.net_income" type="number" class="terminal-input" />
            </label>
          </div>

          <div class="query-bar">
            <input
              v-model="queryForm.question"
              class="terminal-input query-input"
              placeholder="Enter research or compliance prompt..."
            />
            <button class="btn-amber" :disabled="loading" @click="runCreditScoring">
              SCORE CREDIT
            </button>
            <button class="btn-cyan" @click="startResearchStream">
              STREAM MEMO (SSE)
            </button>
            <button class="btn-amber-outline" :disabled="loading" @click="submitResearchQuery">
              COMPLIANCE QUERY
            </button>
          </div>
        </div>

        <!-- Quant Engine Results -->
        <div class="workspace-scroll">
          <div v-if="creditScore" class="quant-cards-grid">
            <!-- Credit Tier Card -->
            <div class="quant-card highlight-card">
              <div class="card-label">IMPLIED CREDIT TIER</div>
              <div class="rating-hero">
                <span class="rating-grade">{{ creditScore.credit_rating }}</span>
                <div class="rating-meta">
                  <div>COMPOSITE: <strong>{{ creditScore.composite_score }}/100</strong></div>
                  <div>OAS SPREAD: <strong>{{ creditScore.implied_spread_bps }} bps</strong></div>
                  <div>1Y PD: <strong>{{ creditScore.probability_of_default_1y_pct }}%</strong></div>
                </div>
              </div>
            </div>

            <!-- Altman Z-Score -->
            <div class="quant-card">
              <div class="card-label">ALTMAN Z-SCORE</div>
              <div class="metric-hero">
                <span class="metric-num">{{ creditScore.altman_z_score.score }}</span>
                <span class="zone-pill" :class="`zone-${creditScore.altman_z_score.zone.toLowerCase()}`">
                  {{ creditScore.altman_z_score.zone }}
                </span>
              </div>
              <div class="sub-metrics">
                <span>LEV SCORE: {{ creditScore.sub_scores.leverage_score }}</span>
                <span>LIQ SCORE: {{ creditScore.sub_scores.liquidity_score }}</span>
              </div>
            </div>

            <!-- Piotroski F-Score -->
            <div class="quant-card">
              <div class="card-label">PIOTROSKI F-SCORE</div>
              <div class="metric-hero">
                <span class="metric-num">
                  {{ creditScore.piotroski_f_score.score }} / {{ creditScore.piotroski_f_score.max_score }}
                </span>
              </div>
              <div class="criteria-pills">
                <span
                  v-for="(ok, key) in creditScore.piotroski_f_score.criteria"
                  :key="key"
                  class="crit-pill"
                  :class="ok ? 'crit-pass' : 'crit-fail'"
                  :title="String(key)"
                >
                  {{ ok ? "✓" : "✕" }} {{ String(key).replace(/_/g, " ") }}
                </span>
              </div>
            </div>
          </div>

          <!-- DCF Valuation Sensitivity Matrix -->
          <div v-if="creditScore" class="dcf-panel">
            <div class="dcf-header">
              <span>DCF VALUATION &amp; SENSITIVITY MATRIX (WACC vs TERMINAL GROWTH)</span>
              <span class="mono-tag">
                BASE EV: {{ creditScore.dcf_valuation.enterprise_value }} · EQ VAL:
                {{ creditScore.dcf_valuation.implied_equity_value }}
              </span>
            </div>
            <table class="dcf-table">
              <thead>
                <tr>
                  <th>WACC \ g</th>
                  <th v-for="g in sensitivityHeaders" :key="g">{{ g }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in creditScore.dcf_valuation.sensitivity_matrix" :key="row.wacc">
                  <td class="wacc-col">{{ row.wacc }}</td>
                  <td v-for="g in sensitivityHeaders" :key="g">
                    {{ row.equity_values_by_terminal_growth[g] }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- SSE Streaming Research Console -->
          <div class="stream-console">
            <div class="stream-header">
              <span>LIVE RESEARCH STREAM (SSE)</span>
              <span class="stream-status" :class="`st-${streamStatus}`">
                {{ streamStatus.toUpperCase() }}
              </span>
            </div>
            <div v-if="streamStages.length > 0" class="stage-strip">
              <span v-for="(st, idx) in streamStages" :key="idx" class="stage-pill">
                {{ String(st.stage || "stage") }}: {{ String(st.status || st.credit_rating || "ok") }}
              </span>
            </div>
            <pre class="stream-body">{{ streamOutput || "Click 'STREAM MEMO (SSE)' to stream deterministic research & compliance analysis..." }}</pre>
          </div>
        </div>
      </section>

      <!-- Right: Compliance Blotter & Audit Stream -->
      <ComplianceBlotter
        :pending-actions="pendingActions"
        :audit-logs="auditLogs"
        :loading="loading"
        @decide-action="handleHitlDecision"
        @refresh-blotter="loadHitlAndAudit"
      />
    </main>

    <!-- Slide-over Ontology & Wiki Drawer -->
    <div v-if="drawerOpen" class="drawer-backdrop" @click.self="drawerOpen = false">
      <div class="terminal-drawer">
        <div class="panel-header">
          <div class="panel-title-group">
            <span class="panel-dot"></span>
            <h2>ONTOLOGY &amp; LLM WIKI DRAWER</h2>
          </div>
          <div class="drawer-tabs">
            <button
              class="btn-mini"
              :class="{ active: drawerTab === 'ontology' }"
              @click="drawerTab = 'ontology'"
            >
              ONTOLOGY GRAPH
            </button>
            <button
              class="btn-mini"
              :class="{ active: drawerTab === 'wiki' }"
              @click="drawerTab = 'wiki'"
            >
              LLM WIKI &amp; LINT
            </button>
            <button class="btn-mini" @click="drawerOpen = false">CLOSE</button>
          </div>
        </div>

        <div v-if="drawerTab === 'ontology'" class="drawer-body">
          <div class="drawer-toolbar">
            <input
              v-model="graphIssuerFilter"
              class="terminal-input"
              placeholder="Filter root issuer_id..."
            />
            <input
              v-model.number="graphMaxDepth"
              type="number"
              min="1"
              max="5"
              class="terminal-input depth-input"
            />
            <button class="btn-amber" @click="loadGraph">TRAVERSE</button>
          </div>
          <div class="drawer-split">
            <div class="drawer-box">
              <h3>NODES ({{ graphData.nodes.length }})</h3>
              <div v-for="n in graphData.nodes" :key="n.id" class="graph-item">
                <span class="mono-gold">{{ n.id }}</span>
                <span class="graph-type">{{ n.type || "Node" }}</span>
              </div>
            </div>
            <div class="drawer-box">
              <h3>EDGES ({{ graphData.edges.length }})</h3>
              <div
                v-for="(e, i) in graphData.edges"
                :key="`${e.source_id}-${e.target_id}-${i}`"
                class="graph-item"
              >
                <span>{{ e.source_id }}</span>
                <span class="mono-gold">--[{{ e.relation }}]--&gt;</span>
                <span>{{ e.target_id }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="drawer-body">
          <div class="drawer-split">
            <div class="drawer-box">
              <h3>INGEST DOCUMENT TO WIKI</h3>
              <div class="ingest-grid">
                <input v-model="ingestForm.doc_id" class="terminal-input" placeholder="doc_id" />
                <input v-model="ingestForm.title" class="terminal-input" placeholder="title" />
                <input v-model="ingestForm.entity_id" class="terminal-input" placeholder="entity_id" />
                <input v-model="ingestForm.entity_name" class="terminal-input" placeholder="entity_name" />
                <textarea v-model="ingestForm.content" class="terminal-input" rows="3"></textarea>
                <div class="drawer-toolbar">
                  <button class="btn-amber" :disabled="loading" @click="submitWikiIngest">
                    INGEST TO WIKI
                  </button>
                  <button class="btn-amber-outline" :disabled="loading" @click="runWikiLint">
                    RUN LINT
                  </button>
                </div>
              </div>
              <pre v-if="lintResult" class="lint-pre">{{ JSON.stringify(lintResult, null, 2) }}</pre>
            </div>
            <div class="drawer-box">
              <h3>WIKI ENTITY PAGES ({{ wikiPages.length }})</h3>
              <div v-for="p in wikiPages" :key="p.id" class="wiki-item">
                <div class="mono-gold">{{ p.title }} ({{ p.id }})</div>
                <div class="wiki-preview">{{ p.preview }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
:root {
  color-scheme: dark;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #0a0e17;
  color: #e2e8f0;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.terminal-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #0a0e17;
  color: #e2e8f0;
  overflow: hidden;
}

.terminal-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 16px;
  background: #070a11;
  border-bottom: 1px solid #1e293b;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-badge {
  font-family: "JetBrains Mono", monospace;
  font-weight: 800;
  font-size: 13px;
  background: #f59e0b;
  color: #0a0e17;
  padding: 4px 8px;
  border-radius: 3px;
}

.brand-block h1 {
  margin: 0;
  font-size: 14px;
  letter-spacing: 0.08em;
  color: #f8fafc;
}

.brand-sub {
  margin: 2px 0 0;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #64748b;
}

.kpi-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.kpi-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #0f1624;
  border: 1px solid #1e293b;
  padding: 4px 9px;
  border-radius: 3px;
  font-family: "JetBrains Mono", monospace;
}

.kpi-label {
  font-size: 10px;
  color: #64748b;
}

.kpi-val {
  font-size: 12px;
  font-weight: 700;
  color: #f8fafc;
}

.kpi-val.amber {
  color: #f59e0b;
}
.kpi-val.red {
  color: #f87171;
}
.kpi-val.green {
  color: #34d399;
}

.topbar-actions {
  display: flex;
  gap: 8px;
}

.alert-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}

.alert-error {
  background: rgba(239, 68, 68, 0.14);
  color: #fca5a5;
  border-bottom: 1px solid rgba(239, 68, 68, 0.4);
}

.alert-success {
  background: rgba(16, 185, 129, 0.14);
  color: #6ee7b7;
  border-bottom: 1px solid rgba(16, 185, 129, 0.4);
}

.terminal-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 270px 1fr 330px;
  gap: 8px;
  padding: 8px;
  background: #05080f;
}

.terminal-panel {
  background: #0a0e17;
  border: 1px solid #1e293b;
  border-radius: 4px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #0d1320;
  border-bottom: 1px solid #1e293b;
}

.panel-title-group {
  display: flex;
  align-items: center;
  gap: 7px;
}

.panel-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
}

.panel-header h2 {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #e2e8f0;
}

.count-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  background: #172033;
  color: #f59e0b;
  border: 1px solid #263147;
}

.terminal-input {
  width: 100%;
  background: #070b12;
  border: 1px solid #263147;
  border-radius: 3px;
  color: #f8fafc;
  padding: 6px 8px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  outline: none;
}

.terminal-input:focus {
  border-color: #f59e0b;
}

.btn-amber {
  background: #f59e0b;
  color: #0a0e17;
  border: none;
  border-radius: 3px;
  padding: 6px 12px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.btn-amber:hover:not(:disabled) {
  background: #fbbf24;
}

.btn-amber-outline {
  background: transparent;
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.5);
  border-radius: 3px;
  padding: 6px 10px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.btn-amber-outline:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.12);
}

.btn-cyan {
  background: rgba(56, 189, 248, 0.16);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.45);
  border-radius: 3px;
  padding: 6px 12px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.btn-cyan:hover {
  background: rgba(56, 189, 248, 0.25);
}

.btn-mini {
  background: #131c2e;
  color: #cbd5e1;
  border: 1px solid #263147;
  border-radius: 3px;
  padding: 3px 8px;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  cursor: pointer;
}

.btn-mini.active {
  border-color: #f59e0b;
  color: #f59e0b;
}

.empty-state {
  padding: 18px;
  text-align: center;
  font-size: 11px;
  color: #64748b;
}

/* Center Workspace */
.center-workspace {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.mono-tag {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #f59e0b;
}

.workspace-controls {
  padding: 10px 12px;
  border-bottom: 1px solid #1e293b;
  background: #080c14;
}

.params-grid {
  display: grid;
  grid-template-columns: repeat(9, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}

.param-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #64748b;
}

.query-bar {
  display: flex;
  gap: 6px;
}

.query-input {
  flex: 1;
}

.workspace-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.quant-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.quant-card {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
}

.highlight-card {
  border-color: rgba(245, 158, 11, 0.45);
}

.card-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #94a3b8;
  margin-bottom: 6px;
}

.rating-hero {
  display: flex;
  align-items: center;
  gap: 12px;
}

.rating-grade {
  font-family: "JetBrains Mono", monospace;
  font-size: 28px;
  font-weight: 800;
  color: #f59e0b;
}

.rating-meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: #cbd5e1;
  line-height: 1.5;
}

.metric-hero {
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-num {
  font-family: "JetBrains Mono", monospace;
  font-size: 24px;
  font-weight: 800;
  color: #f8fafc;
}

.zone-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 3px;
}

.zone-safe {
  background: rgba(16, 185, 129, 0.16);
  color: #34d399;
}
.zone-grey {
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
}
.zone-distress {
  background: rgba(239, 68, 68, 0.18);
  color: #f87171;
}

.sub-metrics {
  display: flex;
  justify-content: space-between;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 8px;
}

.criteria-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.crit-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 2px;
}

.crit-pass {
  background: rgba(16, 185, 129, 0.14);
  color: #34d399;
}

.crit-fail {
  background: rgba(239, 68, 68, 0.14);
  color: #f87171;
}

.dcf-panel {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
}

.dcf-header {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #94a3b8;
  margin-bottom: 8px;
}

.dcf-table {
  width: 100%;
  border-collapse: collapse;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}

.dcf-table th,
.dcf-table td {
  border: 1px solid #1e293b;
  padding: 5px 8px;
  text-align: right;
}

.dcf-table th {
  background: #070b12;
  color: #f59e0b;
}

.wacc-col {
  text-align: left !important;
  color: #94a3b8;
  font-weight: 700;
}

.stream-console {
  flex: 1;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  background: #060910;
  border: 1px solid #1e293b;
  border-radius: 4px;
  overflow: hidden;
}

.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: #0d1320;
  border-bottom: 1px solid #1e293b;
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
}

.stream-status {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
}

.st-streaming {
  background: rgba(56, 189, 248, 0.2);
  color: #38bdf8;
}
.st-completed {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}
.st-blocked,
.st-error {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}
.st-idle {
  background: #1e293b;
  color: #94a3b8;
}

.stage-strip {
  display: flex;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid #131c2e;
  flex-wrap: wrap;
}

.stage-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
  padding: 1px 6px;
  border-radius: 2px;
}

.stream-body {
  margin: 0;
  padding: 10px;
  flex: 1;
  overflow-y: auto;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  line-height: 1.55;
  color: #cbd5e1;
  white-space: pre-wrap;
}

/* Drawer */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 14, 0.72);
  display: flex;
  justify-content: flex-end;
  z-index: 40;
}

.terminal-drawer {
  width: min(820px, 92vw);
  height: 100%;
  background: #0a0e17;
  border-left: 1px solid #f59e0b;
  display: flex;
  flex-direction: column;
}

.drawer-tabs {
  display: flex;
  gap: 6px;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drawer-toolbar {
  display: flex;
  gap: 8px;
}

.depth-input {
  width: 72px;
}

.drawer-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.drawer-box {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
}

.drawer-box h3 {
  margin: 0 0 8px;
  font-size: 11px;
  color: #94a3b8;
  letter-spacing: 0.06em;
}

.graph-item,
.wiki-item {
  padding: 5px 0;
  border-bottom: 1px solid #162033;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.wiki-item {
  flex-direction: column;
}

.wiki-preview {
  font-size: 10px;
  color: #94a3b8;
}

.mono-gold {
  color: #f59e0b;
}

.ingest-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lint-pre {
  margin-top: 8px;
  background: #070b12;
  padding: 8px;
  border-radius: 3px;
  font-size: 10px;
  overflow-x: auto;
}

@media (max-width: 1180px) {
  .terminal-grid {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
  .params-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .quant-cards-grid {
    grid-template-columns: 1fr;
  }
}
</style>
