<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  apiClient,
  type AuditLogItem,
  type DashboardOverview,
  type SafetyCheckItem,
  type SKUItem,
  type SupplierItem,
  type SupplyActionItem,
  type WarehouseItem,
  type WikiPageItem,
} from "./api/client";
import MarginSandbox from "./components/MarginSandbox.vue";
import WarehouseMatrix from "./components/WarehouseMatrix.vue";

type TabId = "sandbox" | "matrix" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabId>("sandbox");
const loading = ref(false);
const banner = ref<{ type: "ok" | "err"; text: string } | null>(null);

const overview = ref<DashboardOverview | null>(null);
const inventoryChecks = ref<SafetyCheckItem[]>([]);
const skus = ref<SKUItem[]>([]);
const warehouses = ref<WarehouseItem[]>([]);
const suppliers = ref<SupplierItem[]>([]);
const wikiPages = ref<WikiPageItem[]>([]);
const actions = ref<SupplyActionItem[]>([]);
const auditLogs = ref<AuditLogItem[]>([]);

// Wiki search, lint, ingest
const wikiSearchQuery = ref("");
const wikiSearchAnswer = ref("");
const wikiLintResult = ref<Record<string, unknown> | null>(null);
const selectedWikiPage = ref<WikiPageItem | null>(null);
const ingestDocId = ref("SOP-PROMO-01");
const ingestTitle = ref("Q4 Promo Policy");
const ingestEntityId = ref("SKU-1002");
const ingestContent = ref("Apply 10% off on [[SKU-1002]] fulfilled from [[WH-WEST]].");

// HITL approval
const approverName = ref("merchandiser-lead");
const approvalComment = ref("Approved via P05 Retail BI Workbench");

function notify(type: "ok" | "err", text: string) {
  banner.value = { type, text };
}

async function refreshAll() {
  loading.value = true;
  try {
    const [ov, inv, pages, acts, logs] = await Promise.all([
      apiClient.getOverview(),
      apiClient.getInventory(),
      apiClient.getWikiPages(),
      apiClient.getActions(true),
      apiClient.getAuditLogs(),
    ]);
    overview.value = ov;
    inventoryChecks.value = inv.items;
    skus.value = inv.skus || [];
    warehouses.value = inv.warehouses || [];
    suppliers.value = inv.suppliers || [];
    wikiPages.value = pages.items;
    if (!selectedWikiPage.value && pages.items.length > 0) {
      selectedWikiPage.value = pages.items[0];
    }
    actions.value = acts.items;
    auditLogs.value = logs.items;
  } catch (err) {
    notify("err", err instanceof Error ? err.message : String(err));
  } finally {
    loading.value = false;
  }
}

async function runWikiQuery() {
  if (!wikiSearchQuery.value.trim()) return;
  try {
    const res = await apiClient.queryWiki(wikiSearchQuery.value.trim());
    wikiSearchAnswer.value = res.answer;
  } catch (err) {
    notify("err", err instanceof Error ? err.message : String(err));
  }
}

async function runWikiLint() {
  try {
    wikiLintResult.value = await apiClient.lintWiki();
    notify("ok", `Wiki Lint 完成: ${wikiLintResult.value.status}`);
  } catch (err) {
    notify("err", err instanceof Error ? err.message : String(err));
  }
}

async function submitWikiIngest() {
  try {
    await apiClient.ingestWiki({
      doc_id: ingestDocId.value,
      title: ingestTitle.value,
      entity_id: ingestEntityId.value,
      entity_type: "SKU",
      content: ingestContent.value,
    });
    notify("ok", `已编译写入 Wiki 词条 [[${ingestEntityId.value}]]`);
    await refreshAll();
  } catch (err) {
    notify("err", err instanceof Error ? err.message : String(err));
  }
}

async function decideAction(actionId: string, approved: boolean) {
  try {
    const res = await apiClient.approveAction({
      action_id: actionId,
      approved,
      approver: approverName.value || "merchandiser-lead",
      comment: approvalComment.value,
    });
    notify("ok", `动作 ${actionId} 已${approved ? "批准" : "驳回"} -> ${res.action.status}`);
    await refreshAll();
  } catch (err) {
    notify("err", err instanceof Error ? err.message : String(err));
  }
}

onMounted(async () => {
  await refreshAll();
});
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="eyebrow">P05 NEW RETAIL BI · GROWTH &amp; EOQ REPLENISHMENT</div>
        <h1>新零售增长毛利沙盘与 EOQ 智能补货中台</h1>
      </div>
      <div class="top-actions">
        <span class="live-chip">● 离线确定性引擎就绪</span>
        <button class="btn-outline" :disabled="loading" @click="refreshAll">
          {{ loading ? "同步中..." : "刷新全局数据" }}
        </button>
      </div>
    </header>

    <div v-if="banner" :class="['banner', banner.type]">
      <span>{{ banner.text }}</span>
      <button class="close-btn" @click="banner = null">×</button>
    </div>

    <section v-if="overview" class="kpi-grid">
      <div class="kpi-card indigo">
        <div class="kpi-label">在管 SKU 总数</div>
        <div class="kpi-value">{{ overview.total_skus }}</div>
      </div>
      <div class="kpi-card warn">
        <div class="kpi-label">缺货 / 交期预警</div>
        <div class="kpi-value">{{ overview.stockout_alerts }}</div>
      </div>
      <div class="kpi-card indigo">
        <div class="kpi-label">待采销 HITL 审批</div>
        <div class="kpi-value">{{ overview.pending_hitl_pos }}</div>
      </div>
      <div class="kpi-card emerald">
        <div class="kpi-label">库存总成本 ($)</div>
        <div class="kpi-value">${{ overview.total_inventory_value.toLocaleString() }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">LLM Wiki 词条</div>
        <div class="kpi-value">{{ overview.wiki_pages }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">审计轨迹条数</div>
        <div class="kpi-value">{{ overview.audit_logs }}</div>
      </div>
    </section>

    <nav class="tabs">
      <button
        :class="['tab', { active: activeTab === 'sandbox' }]"
        @click="activeTab = 'sandbox'"
      >
        促销毛利与 EOQ 沙盘
      </button>
      <button
        :class="['tab', { active: activeTab === 'matrix' }]"
        @click="activeTab = 'matrix'"
      >
        多仓库存与调拨矩阵
      </button>
      <button
        :class="['tab', { active: activeTab === 'ontology' }]"
        @click="activeTab = 'ontology'"
      >
        供应链本体台账
      </button>
      <button
        :class="['tab', { active: activeTab === 'wiki' }]"
        @click="activeTab = 'wiki'"
      >
        运营 LLM Wiki
      </button>
      <button
        :class="['tab', { active: activeTab === 'hitl' }]"
        @click="activeTab = 'hitl'"
      >
        采销 HITL 审批与审计
      </button>
    </nav>

    <!-- Tab 1: Margin & EOQ Sandbox -->
    <main v-if="activeTab === 'sandbox'">
      <MarginSandbox :skus="skus" @notify="notify" @refresh="refreshAll" />
    </main>

    <!-- Tab 2: Multi-Warehouse Allocation Matrix -->
    <main v-if="activeTab === 'matrix'">
      <WarehouseMatrix @notify="notify" />
    </main>

    <!-- Tab 3: Ontology Ledger -->
    <main v-if="activeTab === 'ontology'" class="panel-grid">
      <section class="card">
        <h2>SKU 安全库存与交期风险监测</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>仓库 / 供应商</th>
              <th>当前 / 安全库存</th>
              <th>可售天数 / 交期</th>
              <th>风险等级</th>
              <th>建议补货量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in inventoryChecks" :key="item.sku_id">
              <td>
                <strong>{{ item.sku_id }}</strong>
                <div class="sub">{{ item.sku_name }}</div>
              </td>
              <td>{{ item.warehouse_id }} ← {{ item.supplier_id }}</td>
              <td>{{ item.current_stock }} / {{ item.safety_stock }}</td>
              <td>{{ item.days_of_supply }}d / {{ item.lead_time_days }}d</td>
              <td>
                <span
                  :class="[
                    'badge',
                    item.risk_level === 'CRITICAL'
                      ? 'danger'
                      : item.risk_level === 'WARNING'
                        ? 'warn'
                        : 'ok',
                  ]"
                >
                  {{ item.risk_level }}
                </span>
              </td>
              <td>{{ item.recommended_order_qty }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <div class="two-col">
        <section class="card">
          <h2>履约仓库节点 ({{ warehouses.length }})</h2>
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称 / 区域</th>
                <th>库容利用率</th>
                <th>冷链</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in warehouses" :key="w.warehouse_id">
                <td><strong>{{ w.warehouse_id }}</strong></td>
                <td>{{ w.name }} ({{ w.region }})</td>
                <td>{{ w.current_utilization_units }} / {{ w.capacity_units }}</td>
                <td>{{ w.is_cold_chain ? "是" : "否" }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="card">
          <h2>核心供应商 ({{ suppliers.length }})</h2>
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>交期 / MOQ</th>
                <th>准时率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sup in suppliers" :key="sup.supplier_id">
                <td><strong>{{ sup.supplier_id }}</strong></td>
                <td>{{ sup.name }}</td>
                <td>{{ sup.lead_time_days }}d / {{ sup.moq }}</td>
                <td>{{ (sup.on_time_rate * 100).toFixed(0) }}%</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </main>

    <!-- Tab 4: Operational LLM Wiki -->
    <main v-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <div class="card-head">
          <h2>Wiki 语义检索与一致性巡检 (Lint)</h2>
          <div class="inline-controls">
            <input
              v-model="wikiSearchQuery"
              type="text"
              placeholder="输入关键词检索，如 Espresso / SUP-01"
              @keyup.enter="runWikiQuery"
            />
            <button class="btn-primary" @click="runWikiQuery">检索 Wiki</button>
            <button class="btn-outline" @click="runWikiLint">运行 Wiki Lint</button>
          </div>
        </div>
        <div v-if="wikiSearchAnswer" class="info-box">{{ wikiSearchAnswer }}</div>
        <pre v-if="wikiLintResult" class="json-box">{{
          JSON.stringify(wikiLintResult, null, 2)
        }}</pre>
      </section>

      <div class="two-col">
        <section class="card">
          <h2>已编译 Wiki 词条 ({{ wikiPages.length }})</h2>
          <ul class="wiki-list">
            <li
              v-for="p in wikiPages"
              :key="p.id"
              :class="{ selected: selectedWikiPage?.id === p.id }"
              @click="selectedWikiPage = p"
            >
              <div class="wiki-title">
                <strong>[[{{ p.id }}]]</strong> {{ p.title }}
                <span class="badge">{{ p.entity_type }}</span>
              </div>
              <div class="sub">{{ p.preview }}</div>
            </li>
          </ul>
        </section>

        <section class="card">
          <h2>词条内容预览 &amp; 增量编译录入</h2>
          <pre v-if="selectedWikiPage" class="md-box">{{ selectedWikiPage.content }}</pre>
          <hr class="divider" />
          <div class="form-col">
            <input v-model="ingestDocId" placeholder="Doc ID" />
            <input v-model="ingestEntityId" placeholder="Entity ID (e.g. SKU-1002)" />
            <input v-model="ingestTitle" placeholder="规则标题" />
            <textarea v-model="ingestContent" rows="2" placeholder="规则正文 (支持 [[WikiLink]])" />
            <button class="btn-primary" @click="submitWikiIngest">编译写入 Wiki</button>
          </div>
        </section>
      </div>
    </main>

    <!-- Tab 5: HITL Approval & Audit -->
    <main v-if="activeTab === 'hitl'" class="panel-grid">
      <section class="card">
        <div class="card-head">
          <h2>采销经理 HITL 审批队列</h2>
          <div class="inline-controls">
            <input v-model="approverName" placeholder="审批人" />
            <input v-model="approvalComment" placeholder="审批意见" />
          </div>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Action ID</th>
              <th>SKU / 类型</th>
              <th>数量 / 金额</th>
              <th>状态</th>
              <th>触发原因</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="act in actions" :key="act.action_id">
              <td><strong>{{ act.action_id }}</strong></td>
              <td>
                {{ act.sku_id }}
                <div class="sub">{{ act.action_type }}</div>
              </td>
              <td>{{ act.quantity }} 件 / ${{ act.estimated_cost.toLocaleString() }}</td>
              <td>
                <span
                  :class="[
                    'badge',
                    act.status === 'EXECUTED'
                      ? 'ok'
                      : act.status === 'PENDING_APPROVAL'
                        ? 'warn'
                        : 'danger',
                  ]"
                >
                  {{ act.status }}
                </span>
              </td>
              <td class="sub">{{ act.reason }}</td>
              <td>
                <div v-if="act.status === 'PENDING_APPROVAL'" class="inline-controls">
                  <button class="btn-emerald" @click="decideAction(act.action_id, true)">
                    批准
                  </button>
                  <button class="btn-danger" @click="decideAction(act.action_id, false)">
                    驳回
                  </button>
                </div>
                <span v-else class="sub">{{ act.approved_by || "-" }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>不可篡改操作审计日志 ({{ auditLogs.length }})</h2>
        <table class="data-table">
          <thead>
            <tr>
              <th>Audit ID</th>
              <th>时间</th>
              <th>事件</th>
              <th>SKU</th>
              <th>操作者</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.audit_id">
              <td><strong>{{ log.audit_id }}</strong></td>
              <td class="sub">{{ log.timestamp }}</td>
              <td><span class="badge">{{ log.event }}</span></td>
              <td>{{ log.sku_id }}</td>
              <td>{{ log.actor }}</td>
              <td class="sub">{{ JSON.stringify(log.details) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<style scoped>
:root {
  color-scheme: light;
}
.shell {
  max-width: 1320px;
  margin: 0 auto;
  padding: 24px;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #0f172a;
  background: #f8fafc;
  min-height: 100vh;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #ffffff 0%, #eef2ff 65%, #ecfdf5 100%);
  border: 1px solid #e2e8f0;
  border-radius: 14px;
}
.eyebrow {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: #4f46e5;
}
h1 {
  margin: 4px 0 0;
  font-size: 22px;
  color: #0f172a;
}
h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.live-chip {
  font-size: 12px;
  font-weight: 700;
  color: #059669;
  background: #d1fae5;
  padding: 5px 10px;
  border-radius: 999px;
}
.banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}
.banner.ok {
  background: #d1fae5;
  color: #065f46;
}
.banner.err {
  background: #fee2e2;
  color: #991b1b;
}
.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.kpi-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.kpi-card.indigo {
  border-left: 4px solid #4f46e5;
}
.kpi-card.emerald {
  border-left: 4px solid #10b981;
}
.kpi-card.warn {
  border-left: 4px solid #f59e0b;
}
.kpi-label {
  font-size: 12px;
  color: #64748b;
}
.kpi-value {
  font-size: 24px;
  font-weight: 800;
  margin-top: 4px;
  color: #0f172a;
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  border-bottom: 2px solid #e2e8f0;
  margin-bottom: 18px;
}
.tab {
  background: transparent;
  border: none;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}
.tab.active {
  color: #4f46e5;
  border-bottom-color: #4f46e5;
}
.panel-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.form-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
input,
select,
textarea {
  padding: 7px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
}
.inline-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.btn-primary {
  background: #4f46e5;
  color: #ffffff;
  border: none;
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
.btn-emerald {
  background: #10b981;
  color: #ffffff;
  border: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}
.btn-outline {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #cbd5e1;
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
.btn-danger {
  background: #dc2626;
  color: #ffffff;
  border: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
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
  vertical-align: top;
}
.data-table th {
  font-size: 12px;
  color: #64748b;
  background: #f8fafc;
}
.sub {
  font-size: 12px;
  color: #64748b;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: #e2e8f0;
  color: #334155;
}
.badge.ok {
  background: #d1fae5;
  color: #065f46;
}
.badge.warn {
  background: #fef3c7;
  color: #92400e;
}
.badge.danger {
  background: #fee2e2;
  color: #991b1b;
}
.json-box,
.md-box {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
  margin-top: 12px;
  max-height: 260px;
}
.info-box {
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  color: #3730a3;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.wiki-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wiki-list li {
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
}
.wiki-list li.selected {
  border-color: #4f46e5;
  background: #eef2ff;
}
.wiki-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.divider {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 14px 0;
}
</style>
