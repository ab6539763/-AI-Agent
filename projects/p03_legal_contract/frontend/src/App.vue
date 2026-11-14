<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import ClauseNavigator from "./components/ClauseNavigator.vue";
import RedlineDiffViewer from "./components/RedlineDiffViewer.vue";
import {
  legalApi,
  type AuditLogEntry,
  type ClauseItem,
  type ContractReviewResponse,
  type DashboardOverview,
  type LegalActionItem,
  type LegalLinkItem,
  type ObligationTimelineResponse,
  type PlaybookClauseEntry,
  type RedlineDiffResponse,
  type RegulationItem,
  type WikiLintResponse,
  type WikiPageItem,
} from "./api/client";

type TabKey = "studio" | "diff" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabKey>("studio");
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

const reviewForm = reactive({
  contract_id: "ctr_enterprise_2026",
  title: "Master Cloud Services Agreement (MSA)",
  counterparty: "Acme Cloud Corp.",
  jurisdiction: "EU / US-NY",
  effective_date: "2026-01-15",
  liability_cap_usd: 500000,
  text: `1. Limitation of Liability
Vendor shall have unlimited liability for all data breach and GDPR personal data claims. Legal notices to counsel@acme.com or +1-415-555-0199, SSN 123-45-6789.

2. Indemnification & Breach Notice
Vendor shall notify Customer within 48 hours of any security incident and indemnify Customer for third-party IP claims.

3. Service Levels & Termination
Vendor shall maintain 99.9% uptime SLA. This Agreement shall auto-renew annually unless Customer provides 30 days prior written notice.

4. Intellectual Property
Vendor shall assign all pre-existing IP and deliverables upon execution.`,
});

const reviewResult = ref<ContractReviewResponse | null>(null);
const obligationTimeline = ref<ObligationTimelineResponse | null>(null);
const playbookEntries = ref<PlaybookClauseEntry[]>([]);
const selectedClauseId = ref<string | null>(null);
const clauseDecisions = reactive<Record<string, "accepted" | "rejected" | "pending">>({});

const diffForm = reactive({
  contract_id: "ctr_diff_2026",
  title: "MSA v1 vs v2 Redline Comparison",
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

const regulations = ref<RegulationItem[]>([]);
const ontologyLinks = ref<LegalLinkItem[]>([]);
const clauses = ref<ClauseItem[]>([]);
const riskFilter = ref<string>("");

const wikiPages = ref<WikiPageItem[]>([]);
const lintReport = ref<WikiLintResponse | null>(null);
const wikiIngestForm = reactive({
  doc_id: "reg_eu_ai_act_art50",
  title: "EU AI Act Article 50 Transparency",
  doc_type: "regulation" as "contract" | "clause" | "regulation",
  content: "Requires transparency obligations for AI-generated content and high-risk legal workflows.",
});
const wikiIngestMessage = ref<string>("");

const pendingActions = ref<LegalActionItem[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);
const hitlApprover = ref<string>("gc_chief_counsel");
const hitlNotes = ref<string>("Reviewed by General Counsel.");

const activeClauses = computed(() => reviewResult.value?.clauses ?? []);

const selectedClause = computed<ClauseItem | null>(() => {
  if (!activeClauses.value.length) return null;
  return (
    activeClauses.value.find((c) => c.id === selectedClauseId.value) ??
    activeClauses.value[0]
  );
});

const matchingPlaybookEntry = computed<PlaybookClauseEntry | null>(() => {
  if (!selectedClause.value) return null;
  return (
    playbookEntries.value.find(
      (entry) => entry.clause_type === selectedClause.value?.clause_type
    ) ?? null
  );
});

const filteredClauses = computed(() => {
  if (!riskFilter.value) return clauses.value;
  return clauses.value.filter((c) => c.risk_level === riskFilter.value);
});

const acceptedCount = computed(
  () => Object.values(clauseDecisions).filter((v) => v === "accepted").length
);

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
    const [ov, regs, cls, pages, pending, logs, pb] = await Promise.all([
      legalApi.getOverview(),
      legalApi.listRegulations(),
      legalApi.listClauses(),
      legalApi.listWikiPages(),
      legalApi.listPendingActions(),
      legalApi.listAuditLogs(50),
      legalApi.getPlaybook(),
    ]);
    overview.value = ov;
    regulations.value = regs.regulations;
    ontologyLinks.value = regs.links;
    clauses.value = cls.clauses;
    wikiPages.value = pages.pages;
    pendingActions.value = pending.actions;
    auditLogs.value = logs.logs;
    playbookEntries.value = pb.entries;
  } catch (err) {
    apiOnline.value = false;
    errorBanner.value = err instanceof Error ? err.message : String(err);
  }
}

async function submitContractReview(): Promise<void> {
  loading.value = true;
  errorBanner.value = "";
  try {
    const [rev, obl] = await Promise.all([
      legalApi.reviewContract({
        contract_id: reviewForm.contract_id,
        title: reviewForm.title,
        counterparty: reviewForm.counterparty,
        jurisdiction: reviewForm.jurisdiction,
        liability_cap_usd: reviewForm.liability_cap_usd || null,
        text: reviewForm.text,
      }),
      legalApi.extractObligations({
        contract_id: reviewForm.contract_id,
        title: reviewForm.title,
        text: reviewForm.text,
        effective_date: reviewForm.effective_date,
      }),
    ]);
    reviewResult.value = rev;
    obligationTimeline.value = obl;
    if (rev.clauses.length > 0) {
      selectedClauseId.value = rev.clauses[0].id;
      for (const cl of rev.clauses) {
        if (!clauseDecisions[cl.id]) {
          clauseDecisions[cl.id] = "pending";
        }
      }
    }
    await refreshAll();
  } catch (err) {
    errorBanner.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function handleAcceptRedline(clauseId: string, _tier: "standard" | "fallback"): void {
  clauseDecisions[clauseId] = "accepted";
}

function handleRejectRedline(clauseId: string): void {
  clauseDecisions[clauseId] = "rejected";
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
    wikiIngestMessage.value = `Indexed Entities: ${res.entities.join(", ")}`;
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
  <div class="law-shell">
    <header class="masthead">
      <div class="brand-lockup">
        <div class="firm-seal">§</div>
        <div>
          <span class="firm-kicker">P03 LEGAL COUNSEL WORKBENCH</span>
          <h1>Law Firm Document Review &amp; Redline Studio</h1>
          <p class="subtitle">
            Split-Pane Redline Playbook · Obligation Calendar · Regulatory Ontology · GC HITL
          </p>
        </div>
      </div>
      <div class="masthead-actions">
        <span :class="['status-pill', apiOnline ? 'online' : 'offline']">
          {{ apiOnline ? "Counsel API Online" : "API Offline" }}
        </span>
        <button class="btn btn-secondary" @click="refreshAll">Sync Workspace</button>
      </div>
    </header>

    <div v-if="errorBanner" class="error-banner">
      <strong>System Notice:</strong> {{ errorBanner }}
    </div>

    <section class="kpi-ribbon">
      <div class="kpi-card">
        <span class="kpi-label">Matters Reviewed</span>
        <strong class="kpi-value">{{ overview.contracts_reviewed }}</strong>
        <span class="kpi-sub">Total Dockets: {{ overview.contracts_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">High / Critical Clauses</span>
        <strong class="kpi-value burgundy">{{ overview.high_risk_clauses }}</strong>
        <span class="kpi-sub">Total Clauses: {{ overview.clauses_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Active Regulations</span>
        <strong class="kpi-value">{{ overview.active_regulations }}</strong>
        <span class="kpi-sub">Ontology Rules: {{ overview.regulations_total }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Pending GC Sign-Off</span>
        <strong class="kpi-value amber">{{ overview.pending_gc_approvals }}</strong>
        <span class="kpi-sub">Accepted Redlines: {{ acceptedCount }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">PII Redactions</span>
        <strong class="kpi-value">{{ overview.pii_masked_total }}</strong>
        <span class="kpi-sub">Wiki Pages: {{ overview.wiki_pages_count }}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Audit Trail Events</span>
        <strong class="kpi-value">{{ overview.audit_logs_count }}</strong>
        <span class="kpi-sub">Immutable Ledger</span>
      </div>
    </section>

    <nav class="studio-tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'studio' }]"
        @click="activeTab = 'studio'"
      >
        Split-Pane Redline &amp; Obligations
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'diff' }]"
        @click="activeTab = 'diff'"
      >
        Version Diff Comparison
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        Regulatory Ontology
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        Compliance Wiki &amp; Lint
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        GC HITL &amp; Audit
        <span v-if="pendingActions.length" class="tab-count">{{ pendingActions.length }}</span>
      </button>
    </nav>

    <!-- TAB 1: SPLIT-PANE REDLINE & OBLIGATION STUDIO -->
    <main v-if="activeTab === 'studio'" class="studio-container">
      <section class="intake-bar card">
        <div class="intake-head">
          <div>
            <span class="section-eyebrow">MATTER INTAKE &amp; EXTRACTION</span>
            <h2>Contract Redline &amp; Obligation Calendar Analysis</h2>
          </div>
          <button class="btn btn-primary" :disabled="loading" @click="submitContractReview">
            {{ loading ? "Analyzing..." : "Analyze & Redline" }}
          </button>
        </div>

        <div class="form-row">
          <label>
            Matter / Contract ID
            <input v-model="reviewForm.contract_id" type="text" />
          </label>
          <label>
            Agreement Title
            <input v-model="reviewForm.title" type="text" />
          </label>
          <label>
            Counterparty
            <input v-model="reviewForm.counterparty" type="text" />
          </label>
          <label>
            Jurisdiction
            <input v-model="reviewForm.jurisdiction" type="text" />
          </label>
          <label>
            Effective Date
            <input v-model="reviewForm.effective_date" type="date" />
          </label>
          <label>
            Liability Cap (USD)
            <input v-model.number="reviewForm.liability_cap_usd" type="number" />
          </label>
        </div>

        <label class="full-width">
          Agreement Draft Text (PII auto-redacted prior to analysis)
          <textarea v-model="reviewForm.text" rows="5"></textarea>
        </label>

        <div v-if="reviewResult" class="intake-summary">
          <span :class="riskBadgeClass(reviewResult.overall_risk_level)">
            Overall Risk: {{ reviewResult.overall_risk_level.toUpperCase() }} ({{ reviewResult.overall_risk_score }})
          </span>
          <span class="meta-chip">PII Masked: {{ reviewResult.pii_masked_count }}</span>
          <span class="meta-chip">
            GC Escalation: {{ reviewResult.requires_hitl ? "Required" : "Not Required" }}
          </span>
          <span v-if="obligationTimeline" class="meta-chip">
            Obligations Extracted: {{ obligationTimeline.total_obligations }}
          </span>
        </div>
      </section>

      <!-- SPLIT PANE WORKSPACE -->
      <div class="split-workspace">
        <ClauseNavigator
          :clauses="activeClauses"
          :obligations="obligationTimeline?.obligations ?? []"
          :selected-clause-id="selectedClause?.id ?? null"
          :decisions="clauseDecisions"
          @select-clause="(id) => (selectedClauseId = id)"
        />

        <RedlineDiffViewer
          :clause="selectedClause"
          :playbook-entry="matchingPlaybookEntry"
          :diff-item="null"
          :decision="selectedClause ? (clauseDecisions[selectedClause.id] ?? 'pending') : 'pending'"
          :obligations="obligationTimeline?.obligations ?? []"
          @accept-redline="handleAcceptRedline"
          @reject-redline="handleRejectRedline"
        />
      </div>

      <!-- OBLIGATION CALENDAR TIMELINE -->
      <section class="card">
        <div class="section-head">
          <div>
            <span class="section-eyebrow">POST-EXECUTION COMPLIANCE</span>
            <h2>Obligation &amp; Renewal Calendar</h2>
          </div>
          <span v-if="obligationTimeline" class="meta-chip">
            Effective Date: {{ obligationTimeline.effective_date }} · {{ obligationTimeline.total_obligations }} Deadlines
          </span>
        </div>

        <div v-if="!obligationTimeline || obligationTimeline.obligations.length === 0" class="empty-state">
          Run <strong>Analyze &amp; Redline</strong> to extract SLA, breach notification, notice, and renewal deadlines.
        </div>

        <div v-else class="timeline-grid">
          <div
            v-for="obl in obligationTimeline.obligations"
            :key="obl.id"
            class="timeline-card"
          >
            <div class="timeline-top">
              <span class="deadline-pill">{{ obl.deadline_label }}</span>
              <span :class="riskBadgeClass(obl.severity)">{{ obl.severity }}</span>
            </div>
            <h4>{{ obl.clause_title }}</h4>
            <p class="timeline-summary">{{ obl.summary }}</p>
            <div class="timeline-foot">
              <span>Category: <strong>{{ obl.category.replace("_", " ") }}</strong></span>
              <span>Party: <strong>{{ obl.party }}</strong></span>
              <span>Due: <strong>{{ obl.due_date_iso ?? "Ongoing" }}</strong></span>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- TAB 2: VERSION DIFF -->
    <main v-if="activeTab === 'diff'" class="panel-grid">
      <section class="card">
        <span class="section-eyebrow">COUNTERPARTY MARKUP COMPARISON</span>
        <h2>Contract Version Redline Diff (v1 vs v2)</h2>
        <div class="form-row">
          <label>
            Comparison ID
            <input v-model="diffForm.contract_id" type="text" />
          </label>
          <label>
            Comparison Title
            <input v-model="diffForm.title" type="text" />
          </label>
        </div>
        <div class="form-row">
          <label>
            Original Draft (v1)
            <textarea v-model="diffForm.original_text" rows="6"></textarea>
          </label>
          <label>
            Revised Markup (v2)
            <textarea v-model="diffForm.revised_text" rows="6"></textarea>
          </label>
        </div>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitRedlineDiff">
            Compute Risk Delta &amp; Diff
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
              <span class="meta-chip">Risk Delta: {{ cd.risk_delta > 0 ? "+" : "" }}{{ cd.risk_delta }}</span>
            </div>
            <p v-if="cd.redline_recommendation" class="redline-box">{{ cd.redline_recommendation }}</p>
            <pre v-if="cd.diff_lines.length" class="diff-pre">{{ cd.diff_lines.join("\n") }}</pre>
          </div>
        </div>
      </section>

      <section class="card">
        <span class="section-eyebrow">FIRM STANDARD LIBRARY</span>
        <h2>Redline Playbook Positions ({{ playbookEntries.length }})</h2>
        <div v-for="entry in playbookEntries" :key="entry.id" class="clause-item">
          <div class="clause-top">
            <strong>{{ entry.title }}</strong>
            <span class="meta-chip">{{ entry.clause_type }}</span>
          </div>
          <p class="muted"><strong>Trigger:</strong> {{ entry.risk_trigger }}</p>
          <p class="playbook-pos"><strong>Standard:</strong> {{ entry.standard_position }}</p>
          <p class="playbook-pos"><strong>Fallback:</strong> {{ entry.fallback_position }}</p>
        </div>
      </section>
    </main>

    <!-- TAB 3: ONTOLOGY -->
    <main v-if="activeTab === 'ontology'" class="panel-grid">
      <section class="card">
        <h2>Regulatory Ontology Registry ({{ regulations.length }})</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Title</th>
              <th>Jurisdiction</th>
              <th>Status</th>
              <th>Keywords</th>
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
          <h2>Clause Risk &amp; Regulation Mapping ({{ filteredClauses.length }})</h2>
          <select v-model="riskFilter">
            <option value="">All Risk Levels</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </div>
        <div v-if="filteredClauses.length === 0" class="empty-state">
          No clauses registered yet. Analyze a contract in the Studio tab.
        </div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Clause ID</th>
              <th>Type</th>
              <th>Risk</th>
              <th>Mapped Regulations</th>
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

        <h3 class="sub-heading">Knowledge Graph Edges ({{ ontologyLinks.length }})</h3>
        <div class="link-pills">
          <span v-for="lnk in ontologyLinks.slice(0, 20)" :key="lnk.id" class="meta-chip">
            {{ lnk.source_id }} —[{{ lnk.relation }}]→ {{ lnk.target_id }}
          </span>
        </div>
      </section>
    </main>

    <!-- TAB 4: WIKI & LINT -->
    <main v-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <h2>Compliance Markdown Wiki Ingest &amp; Lint</h2>
        <div class="form-row">
          <label>
            Document ID
            <input v-model="wikiIngestForm.doc_id" type="text" />
          </label>
          <label>
            Document Type
            <select v-model="wikiIngestForm.doc_type">
              <option value="regulation">regulation</option>
              <option value="contract">contract</option>
              <option value="clause">clause</option>
            </select>
          </label>
        </div>
        <label class="full-width">
          Title
          <input v-model="wikiIngestForm.title" type="text" />
        </label>
        <label class="full-width">
          Content
          <textarea v-model="wikiIngestForm.content" rows="4"></textarea>
        </label>
        <div class="actions-row">
          <button class="btn btn-primary" :disabled="loading" @click="submitWikiIngest">
            Ingest to Wiki
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="runWikiLint">
            Run Compliance Lint
          </button>
        </div>
        <p v-if="wikiIngestMessage" class="success-msg">{{ wikiIngestMessage }}</p>

        <div v-if="lintReport" class="result-box">
          <h3>Lint Report · Total Issues: {{ lintReport.total_issues }}</h3>
          <ul>
            <li>Superseded Regulations: {{ lintReport.superseded_regulations.length }}</li>
            <li>Unlinked Clauses: {{ lintReport.unlinked_clauses.length }}</li>
            <li>Conflicting Liability Caps: {{ lintReport.conflicting_liability_caps.length }}</li>
          </ul>
          <pre v-if="lintReport.total_issues > 0" class="diff-pre">{{ JSON.stringify(lintReport, null, 2) }}</pre>
        </div>
      </section>

      <section class="card">
        <h2>Wiki Knowledge Pages ({{ wikiPages.length }})</h2>
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

    <!-- TAB 5: HITL & AUDIT -->
    <main v-if="activeTab === 'hitl'" class="panel-grid">
      <section class="card">
        <h2>General Counsel HITL Approval Queue ({{ pendingActions.length }})</h2>
        <div class="form-row">
          <label>
            Approver (General Counsel)
            <input v-model="hitlApprover" type="text" />
          </label>
          <label>
            Decision Notes
            <input v-model="hitlNotes" type="text" />
          </label>
        </div>
        <div v-if="pendingActions.length === 0" class="empty-state">
          No pending high-risk clauses awaiting General Counsel sign-off.
        </div>
        <div v-for="act in pendingActions" :key="act.id" class="clause-item">
          <div class="clause-top">
            <strong>{{ act.id }} · Matter {{ act.contract_id }}</strong>
            <span :class="riskBadgeClass(act.risk_level)">{{ act.risk_level }}</span>
          </div>
          <p class="muted">Clause: {{ act.clause_id || "-" }} · Requested by: {{ act.requested_by }}</p>
          <div class="actions-row">
            <button class="btn btn-primary" :disabled="loading" @click="decideAction(act.id, 'approved')">
              Approve Exception
            </button>
            <button class="btn btn-danger" :disabled="loading" @click="decideAction(act.id, 'rejected')">
              Reject &amp; Require Redline
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>Immutable Compliance Audit Log ({{ auditLogs.length }})</h2>
        <div v-if="auditLogs.length === 0" class="empty-state">No audit events recorded yet.</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Event</th>
              <th>Actor</th>
              <th>Target</th>
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
.law-shell {
  min-height: 100vh;
  background: #faf8f5;
  color: #1e293b;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding: 20px 28px 48px;
}

.masthead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 2px solid #1e293b;
  padding-bottom: 16px;
  margin-bottom: 18px;
  gap: 16px;
  flex-wrap: wrap;
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: 14px;
}

.firm-seal {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: #991b1b;
  color: #faf8f5;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 24px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.firm-kicker {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #991b1b;
}

.masthead h1 {
  margin: 2px 0 0;
  font-size: 22px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.subtitle {
  margin: 3px 0 0;
  font-size: 12px;
  color: #475569;
}

.masthead-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-pill {
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  font-weight: 600;
}

.status-pill.online {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #86efac;
}

.status-pill.offline {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #991b1b;
  color: #7f1d1d;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
}

.kpi-ribbon {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.kpi-card {
  background: #ffffff;
  border: 1px solid #e2ddd2;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.kpi-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
}

.kpi-value {
  font-size: 24px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.kpi-value.burgundy {
  color: #991b1b;
}

.kpi-value.amber {
  color: #b45309;
}

.kpi-sub {
  font-size: 11px;
  color: #64748b;
}

.studio-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.tab-btn {
  background: #f5f2eb;
  color: #1e293b;
  border: 1px solid #d6cfc2;
  padding: 9px 15px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tab-btn.active {
  background: #1e293b;
  color: #faf8f5;
  border-color: #1e293b;
}

.tab-count {
  background: #991b1b;
  color: #ffffff;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 700;
}

.studio-container {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.split-workspace {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 18px;
  align-items: stretch;
}

@media (max-width: 960px) {
  .split-workspace {
    grid-template-columns: 1fr;
  }
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 18px;
}

.card {
  background: #ffffff;
  border: 1px solid #e2ddd2;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(30, 41, 59, 0.04);
}

.section-eyebrow {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #991b1b;
  margin-bottom: 2px;
}

.card h2 {
  margin: 0 0 12px;
  font-size: 17px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.intake-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.intake-head h2 {
  margin: 0;
}

.intake-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #ece7dc;
}

.timeline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.timeline-card {
  background: #faf8f5;
  border: 1px solid #e2ddd2;
  border-left: 4px solid #991b1b;
  border-radius: 8px;
  padding: 12px 14px;
}

.timeline-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.deadline-pill {
  font-size: 12px;
  font-weight: 700;
  color: #991b1b;
}

.timeline-card h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #1e293b;
}

.timeline-summary {
  margin: 0 0 8px;
  font-size: 12px;
  color: #475569;
  line-height: 1.45;
}

.timeline-foot {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #64748b;
  gap: 8px;
  flex-wrap: wrap;
}

.sub-heading {
  margin: 18px 0 10px;
  font-size: 14px;
  color: #1e293b;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
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
  font-weight: 600;
  color: #475569;
}

.full-width {
  margin-bottom: 10px;
}

input,
textarea,
select {
  background: #faf8f5;
  color: #1e293b;
  border: 1px solid #d6cfc2;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
}

input:focus,
textarea:focus,
select:focus {
  outline: 2px solid rgba(153, 27, 27, 0.25);
  border-color: #991b1b;
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
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #991b1b;
  color: #ffffff;
}

.btn-primary:hover:not(:disabled) {
  background: #7f1d1d;
}

.btn-secondary {
  background: #f5f2eb;
  color: #1e293b;
  border: 1px solid #d6cfc2;
}

.btn-danger {
  background: #1e293b;
  color: #ffffff;
}

.result-box {
  margin-top: 14px;
  border-top: 1px solid #e2ddd2;
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
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
}

.badge-high {
  background: #ffedd5;
  color: #9a3412;
  border: 1px solid #fdba74;
}

.badge-medium {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}

.badge-low {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #86efac;
}

.meta-chip {
  background: #f5f2eb;
  color: #1e293b;
  border: 1px solid #e2ddd2;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
}

.diff-pre {
  background: #faf8f5;
  border: 1px solid #e2ddd2;
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1e293b;
}

.clause-item,
.wiki-card {
  background: #faf8f5;
  border: 1px solid #e2ddd2;
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

.redline-box {
  margin: 6px 0 0;
  padding: 6px 8px;
  background: #fef2f2;
  border-left: 3px solid #991b1b;
  font-size: 12px;
  color: #7f1d1d;
}

.playbook-pos {
  margin: 4px 0;
  font-size: 12px;
  line-height: 1.5;
  color: #1e293b;
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
  border-bottom: 1px solid #e7e2d8;
}

.data-table th {
  color: #475569;
  font-weight: 700;
}

.muted {
  color: #64748b;
  font-size: 12px;
}

.empty-state {
  padding: 20px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}

.success-msg {
  color: #166534;
  font-size: 13px;
  font-weight: 600;
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
