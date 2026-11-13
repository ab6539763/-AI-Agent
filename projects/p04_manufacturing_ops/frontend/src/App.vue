<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  apiClient,
  type AuditLogEntry,
  type DashboardOverview,
  type DiagnosisResult,
  type IncidentResponse,
  type OpsActionItem,
  type PredictiveMaintenanceResponse,
  type WikiLintReport,
  type WikiPageItem,
} from "./api/client";

type TabKey = "telemetry" | "ontology" | "wiki" | "hitl";

const activeTab = ref<TabKey>("telemetry");
const loading = ref(false);
const errorMsg = ref("");
const toastMsg = ref("");

const overview = ref<DashboardOverview | null>(null);
const wikiPages = ref<WikiPageItem[]>([]);
const selectedWikiPage = ref<WikiPageItem | null>(null);
const wikiSearch = ref("");
const lintReport = ref<WikiLintReport | null>(null);

const pendingActions = ref<OpsActionItem[]>([]);
const auditLogs = ref<AuditLogEntry[]>([]);

// Telemetry & Diagnosis form state
const selectedEquipmentId = ref("CNC-LINE1-01");
const sensorTemp = ref(82);
const sensorVib = ref(4.2);
const sensorPressure = ref(140);
const operatingHours = ref(650);
const diagnosisResult = ref<DiagnosisResult | null>(null);
const incidentResult = ref<IncidentResponse | null>(null);
const predictiveResult = ref<PredictiveMaintenanceResponse | null>(null);

// Wiki ingest form state
const ingestId = ref("SOP-CUSTOM-01");
const ingestType = ref("MaintenanceSOP");
const ingestTitle = ref("Custom Spindle Thermal Check");
const ingestContent = ref("Verify coolant chiller flow and spindle bearing temperature.");
const ingestLinks = ref("CNC-LINE1-01,ERR-CNC-401");

// HITL form state
const safetyOfficer = ref("officer-zhang");
const decisionReason = ref("Verified sensor telemetry and thermal imaging.");

const selectedEquipment = computed(() => {
  return (
    overview.value?.equipment.find((e) => e.equipment_id === selectedEquipmentId.value) ??
    overview.value?.equipment[0] ??
    null
  );
});

const filteredWikiPages = computed(() => {
  const q = wikiSearch.value.trim().toLowerCase();
  if (!q) return wikiPages.value;
  return wikiPages.value.filter(
    (p) =>
      p.id.toLowerCase().includes(q) ||
      p.title.toLowerCase().includes(q) ||
      p.entity_type.toLowerCase().includes(q) ||
      p.preview.toLowerCase().includes(q)
  );
});

function showToast(msg: string) {
  toastMsg.value = msg;
  setTimeout(() => {
    if (toastMsg.value === msg) toastMsg.value = "";
  }, 3500);
}

async function refreshAll() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const [ov, wp, pa, al] = await Promise.all([
      apiClient.getDashboardOverview(),
      apiClient.getWikiPages(),
      apiClient.getPendingActions(),
      apiClient.getAuditLogs(),
    ]);
    overview.value = ov;
    wikiPages.value = wp.pages;
    if (!selectedWikiPage.value && wp.pages.length > 0) {
      selectedWikiPage.value = wp.pages[0];
    }
    pendingActions.value = pa.actions;
    auditLogs.value = al.logs;
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function buildReadings(): Record<string, number> {
  if (selectedEquipmentId.value === "MOLD-LINE2-01") {
    return {
      pressure_bar: Number(sensorPressure.value),
      temperature_c: Number(sensorTemp.value),
    };
  }
  return {
    temperature_c: Number(sensorTemp.value),
    vibration_mms: Number(sensorVib.value),
  };
}

async function runDiagnose() {
  errorMsg.value = "";
  try {
    diagnosisResult.value = await apiClient.diagnoseOntology({
      equipment_id: selectedEquipmentId.value,
      readings: buildReadings(),
    });
    showToast(`已完成 ${selectedEquipmentId.value} 本体诊断`);
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function runIncident() {
  errorMsg.value = "";
  try {
    incidentResult.value = await apiClient.triggerIncident({
      equipment_id: selectedEquipmentId.value,
      sensor_readings: buildReadings(),
      reporter: "workbench-operator",
    });
    showToast(
      incidentResult.value.hitl_required
        ? "已触发安全官 HITL 紧急停机审批！"
        : `事件 ${incidentResult.value.incident_id} 已记录并同步至 Wiki`
    );
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function runPredictiveBatch() {
  errorMsg.value = "";
  try {
    const samples = (overview.value?.equipment ?? []).map((eq) => {
      if (eq.equipment_id === selectedEquipmentId.value) {
        return {
          equipment_id: eq.equipment_id,
          readings: buildReadings(),
          operating_hours: Number(operatingHours.value),
        };
      }
      return {
        equipment_id: eq.equipment_id,
        readings:
          eq.equipment_id === "MOLD-LINE2-01"
            ? { pressure_bar: 145, temperature_c: 62 }
            : { temperature_c: 64, vibration_mms: 2.1 },
        operating_hours: 320,
      };
    });
    predictiveResult.value = await apiClient.runPredictiveMaintenance(samples);
    showToast("批量预测性维保与 MTBF 排程已生成");
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function runWikiLint() {
  errorMsg.value = "";
  try {
    lintReport.value = await apiClient.lintWiki();
    showToast(lintReport.value.healthy ? "Wiki 知识图谱健康" : "检测到 Wiki 知识库异常");
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function submitWikiIngest() {
  errorMsg.value = "";
  try {
    const links = ingestLinks.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await apiClient.ingestWikiPage({
      entity_id: ingestId.value.trim(),
      entity_type: ingestType.value.trim(),
      title: ingestTitle.value.trim(),
      content: ingestContent.value.trim(),
      links,
    });
    showToast(`Wiki 实体 ${ingestId.value} 已入库`);
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

async function decideAction(actionId: string, approved: boolean) {
  errorMsg.value = "";
  try {
    const res = await apiClient.approveAction({
      action_id: actionId,
      approved,
      safety_officer: safetyOfficer.value.trim() || "safety-officer",
      reason: decisionReason.value.trim(),
    });
    showToast(
      `审批完成: ${res.action.action_id} -> ${res.action.status} (设备状态: ${res.equipment_status ?? "N/A"})`
    );
    await refreshAll();
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : String(err);
  }
}

function statusBadgeClass(status: string): string {
  const s = status.toUpperCase();
  if (s === "OPERATIONAL" || s === "HEALTHY" || s === "APPROVED" || s === "INFO") {
    return "badge badge-ok";
  }
  if (s === "DEGRADED" || s === "WARNING" || s === "WATCH" || s === "PENDING_APPROVAL") {
    return "badge badge-warn";
  }
  return "badge badge-crit";
}

onMounted(() => {
  void refreshAll();
});
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div>
        <div class="eyebrow">PROJECT P04 · ENTERPRISE MANUFACTURING OPS</div>
        <h1>智能制造设备运维与本体决策工作台</h1>
      </div>
      <div class="topbar-actions">
        <span v-if="toastMsg" class="toast">{{ toastMsg }}</span>
        <button class="btn btn-secondary" :disabled="loading" @click="refreshAll">
          {{ loading ? "同步中..." : "刷新全厂状态" }}
        </button>
      </div>
    </header>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- Plant KPI Strip -->
    <section v-if="overview" class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">接入设备数</div>
        <div class="kpi-val">{{ overview.equipment_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">本体故障码</div>
        <div class="kpi-val">{{ overview.fault_codes_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">标准作业程序 (SOP)</div>
        <div class="kpi-val">{{ overview.sops_count }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">LLM Wiki 页面</div>
        <div class="kpi-val">{{ overview.wiki_pages_count }}</div>
      </div>
      <div class="kpi-card" :class="{ 'kpi-alert': overview.pending_hitl_shutdowns > 0 }">
        <div class="kpi-label">待审批 HITL 停机</div>
        <div class="kpi-val">{{ overview.pending_hitl_shutdowns }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">不可变审计日志</div>
        <div class="kpi-val">{{ overview.audit_logs_count }}</div>
      </div>
    </section>

    <!-- 4-Tab Workbench Navigation -->
    <nav class="tabs">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'telemetry' }"
        @click="activeTab = 'telemetry'"
      >
        设备遥测诊断与预测维保
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'ontology' }"
        @click="activeTab = 'ontology'"
      >
        故障-SOP 本体图谱
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'wiki' }"
        @click="activeTab = 'wiki'"
      >
        运维 LLM Wiki
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'hitl' }"
        @click="activeTab = 'hitl'"
      >
        安全官 HITL 审批与审计
        <span v-if="pendingActions.length > 0" class="tab-pill">{{ pendingActions.length }}</span>
      </button>
    </nav>

    <!-- Tab 1: Telemetry Diagnosis & Predictive Maintenance -->
    <main v-if="activeTab === 'telemetry'" class="panel-grid">
      <section class="card">
        <h2>实时遥测注入与本体诊断</h2>
        <div class="form-grid">
          <label>
            <span>目标设备</span>
            <select v-model="selectedEquipmentId">
              <option
                v-for="eq in overview?.equipment ?? []"
                :key="eq.equipment_id"
                :value="eq.equipment_id"
              >
                {{ eq.equipment_id }} — {{ eq.name }} ({{ eq.status }})
              </option>
            </select>
          </label>
          <label>
            <span>主轴/模腔温度 (°C)</span>
            <input v-model.number="sensorTemp" type="number" step="0.5" />
          </label>
          <label v-if="selectedEquipmentId !== 'MOLD-LINE2-01'">
            <span>振动速度 RMS (mm/s)</span>
            <input v-model.number="sensorVib" type="number" step="0.1" />
          </label>
          <label v-else>
            <span>液压歧管压力 (bar)</span>
            <input v-model.number="sensorPressure" type="number" step="1" />
          </label>
          <label>
            <span>累计运行时长 (h)</span>
            <input v-model.number="operatingHours" type="number" step="10" />
          </label>
        </div>

        <div v-if="selectedEquipment" class="threshold-hint">
          <span>产线: {{ selectedEquipment.line_id }} · 位置: {{ selectedEquipment.location }}</span>
          <span :class="statusBadgeClass(selectedEquipment.status)">
            {{ selectedEquipment.status }}
          </span>
        </div>

        <div class="btn-row">
          <button class="btn btn-primary" @click="runDiagnose">即时本体诊断</button>
          <button class="btn btn-danger" @click="runIncident">上报事件 (触发 FDE / HITL)</button>
          <button class="btn btn-secondary" @click="runPredictiveBatch">
            批量预测性维保 & MTBF 排程
          </button>
        </div>

        <div v-if="diagnosisResult" class="sub-box">
          <div class="sub-head">
            <strong>诊断结论: {{ diagnosisResult.equipment_id }}</strong>
            <span :class="statusBadgeClass(diagnosisResult.highest_severity)">
              {{ diagnosisResult.highest_severity }} · 停机建议:
              {{ diagnosisResult.requires_shutdown ? "YES" : "NO" }}
            </span>
          </div>
          <ul v-if="diagnosisResult.alerts.length > 0" class="list-clean">
            <li v-for="al in diagnosisResult.alerts" :key="al.alert_id">
              [{{ al.severity }}] {{ al.message }}
              <code v-if="al.fault_code">{{ al.fault_code }}</code>
            </li>
          </ul>
          <p v-else class="muted">当前遥测指标处于安全阈值内。</p>
          <div v-if="diagnosisResult.sops.length > 0" class="chip-row">
            <span v-for="sop in diagnosisResult.sops" :key="sop.sop_id" class="chip">
              推荐 SOP: {{ sop.sop_id }} ({{ sop.title }})
            </span>
          </div>
        </div>

        <div v-if="incidentResult" class="sub-box">
          <div class="sub-head">
            <strong>FDE 事件单: {{ incidentResult.incident_id }}</strong>
            <span :class="incidentResult.hitl_required ? 'badge badge-warn' : 'badge badge-ok'">
              {{ incidentResult.hitl_required ? "等待安全官 HITL 审批" : "已自动闭环" }}
            </span>
          </div>
          <p v-if="incidentResult.action" class="muted">
            Action ID: <code>{{ incidentResult.action.action_id }}</code> · 类型:
            {{ incidentResult.action.action_type }} · 状态: {{ incidentResult.action.status }}
          </p>
        </div>
      </section>

      <section class="card">
        <h2>预测性维保健康评分与 MTBF 排程</h2>
        <p v-if="!predictiveResult" class="muted">
          点击左侧「批量预测性维保 & MTBF 排程」按钮，基于设备遥测与运行时长生成离线确定性健康评分与维保窗口。
        </p>
        <div v-else>
          <div class="pm-summary">
            <span>评估设备: {{ predictiveResult.equipment_evaluated }}</span>
            <span>平均健康分: {{ predictiveResult.average_health_score }}</span>
            <span>高危设备: {{ predictiveResult.critical_count }}</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>设备</th>
                  <th>健康分</th>
                  <th>风险等级</th>
                  <th>优先级</th>
                  <th>建议窗口</th>
                  <th>预估 MTBF</th>
                  <th>关联 SOP</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in predictiveResult.schedules" :key="item.equipment_id">
                  <td>
                    <strong>{{ item.equipment_id }}</strong>
                    <div class="muted small">{{ item.equipment_name }}</div>
                  </td>
                  <td>
                    <div class="score-bar">
                      <div class="score-fill" :style="{ width: item.health_score + '%' }"></div>
                    </div>
                    <span class="mono">{{ item.health_score }}</span>
                  </td>
                  <td>
                    <span :class="statusBadgeClass(item.risk_tier)">{{ item.risk_tier }}</span>
                  </td>
                  <td class="mono">{{ item.priority }}</td>
                  <td>{{ item.recommended_window_hours }}h</td>
                  <td class="mono">{{ item.estimated_mtbf_hours }}h</td>
                  <td>
                    <span v-for="sid in item.recommended_sops" :key="sid" class="chip">
                      {{ sid }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>

    <!-- Tab 2: Fault-SOP Ontology Graph -->
    <main v-else-if="activeTab === 'ontology'" class="panel-grid">
      <section class="card">
        <h2>故障码本体库 (FaultCodes)</h2>
        <div class="stack">
          <div v-for="fc in overview?.fault_codes ?? []" :key="fc.code" class="entity-card">
            <div class="sub-head">
              <strong>{{ fc.code }} · {{ fc.title }}</strong>
              <span :class="statusBadgeClass(fc.severity)">{{ fc.severity }}</span>
            </div>
            <p class="muted">根因: {{ fc.root_cause }}</p>
            <div class="chip-row">
              <span class="chip">设备类型: {{ fc.equipment_type }}</span>
              <span v-if="fc.recommended_sop_id" class="chip">
                映射 SOP: {{ fc.recommended_sop_id }}
              </span>
              <span v-if="fc.requires_shutdown" class="badge badge-crit">需紧急停机</span>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>标准作业程序与本体关系链 (SOP & Links)</h2>
        <div class="stack">
          <div v-for="sop in overview?.sops ?? []" :key="sop.sop_id" class="entity-card">
            <div class="sub-head">
              <strong>{{ sop.sop_id }} · {{ sop.title }}</strong>
              <span class="chip">{{ sop.revision }} · {{ sop.estimated_minutes }} min</span>
            </div>
            <ol class="steps">
              <li v-for="(st, idx) in sop.steps" :key="idx">{{ st }}</li>
            </ol>
            <div v-if="sop.safety_precautions.length > 0" class="safety-box">
              <strong>安全警示:</strong> {{ sop.safety_precautions.join("；") }}
            </div>
          </div>
        </div>

        <h3 style="margin-top: 1.25rem">本体拓扑边 ({{ overview?.links.length ?? 0 }})</h3>
        <div class="chip-row">
          <span v-for="lnk in overview?.links ?? []" :key="lnk.link_id" class="chip mono">
            {{ lnk.source_id }} —[{{ lnk.relation }}]→ {{ lnk.target_id }}
          </span>
        </div>
      </section>
    </main>

    <!-- Tab 3: Operations LLM Wiki -->
    <main v-else-if="activeTab === 'wiki'" class="panel-grid">
      <section class="card">
        <div class="sub-head">
          <h2>运维 LLM Wiki 知识库 ({{ filteredWikiPages.length }})</h2>
          <button class="btn btn-secondary" @click="runWikiLint">执行 Wiki Lint 检查</button>
        </div>
        <input
          v-model="wikiSearch"
          class="search-input"
          placeholder="搜索实体 ID、标题或内容..."
        />

        <div v-if="lintReport" class="sub-box">
          <div class="sub-head">
            <strong>Wiki Lint 报告</strong>
            <span :class="lintReport.healthy ? 'badge badge-ok' : 'badge badge-warn'">
              {{ lintReport.healthy ? "HEALTHY" : "ISSUES DETECTED" }}
            </span>
          </div>
          <p class="muted small">
            总页数: {{ lintReport.total_pages }} · 未映射故障:
            {{ lintReport.unmapped_fault_codes.length }} · 过期 SOP:
            {{ lintReport.outdated_sops.length }} · 孤立设备:
            {{ lintReport.orphan_equipment.length }}
          </p>
        </div>

        <div class="wiki-list">
          <button
            v-for="page in filteredWikiPages"
            :key="page.id"
            class="wiki-item"
            :class="{ selected: selectedWikiPage?.id === page.id }"
            @click="selectedWikiPage = page"
          >
            <div class="sub-head">
              <strong>{{ page.id }}</strong>
              <span class="chip">{{ page.entity_type }}</span>
            </div>
            <div class="small">{{ page.title }}</div>
            <div class="muted small">{{ page.preview }}</div>
          </button>
        </div>
      </section>

      <section class="card">
        <h2>页面详情与知识注入</h2>
        <div v-if="selectedWikiPage" class="sub-box">
          <div class="sub-head">
            <strong>{{ selectedWikiPage.title }} ({{ selectedWikiPage.id }})</strong>
            <span class="chip">{{ selectedWikiPage.entity_type }}</span>
          </div>
          <div class="muted small" style="margin-bottom: 0.5rem">
            路径: <code>{{ selectedWikiPage.path }}</code>
          </div>
          <pre class="wiki-body">{{ selectedWikiPage.content }}</pre>
          <div v-if="selectedWikiPage.wiki_links.length > 0" class="chip-row">
            <span v-for="lnk in selectedWikiPage.wiki_links" :key="lnk" class="chip">
              [[{{ lnk }}]]
            </span>
          </div>
        </div>

        <h3 style="margin-top: 1.25rem">注入新 Wiki 实体</h3>
        <div class="form-grid">
          <label>
            <span>实体 ID</span>
            <input v-model="ingestId" />
          </label>
          <label>
            <span>实体类型</span>
            <input v-model="ingestType" />
          </label>
          <label class="full-span">
            <span>标题</span>
            <input v-model="ingestTitle" />
          </label>
          <label class="full-span">
            <span>关联 Wiki Links (逗号分隔)</span>
            <input v-model="ingestLinks" />
          </label>
          <label class="full-span">
            <span>Markdown 正文</span>
            <textarea v-model="ingestContent" rows="3"></textarea>
          </label>
        </div>
        <button class="btn btn-primary" style="margin-top: 0.75rem" @click="submitWikiIngest">
          写入知识图谱
        </button>
      </section>
    </main>

    <!-- Tab 4: Safety Officer HITL & Audit -->
    <main v-else class="panel-grid">
      <section class="card">
        <h2>待审批 HITL 安全动作队列 ({{ pendingActions.length }})</h2>
        <div class="form-grid" style="margin-bottom: 0.75rem">
          <label>
            <span>安全官工号</span>
            <input v-model="safetyOfficer" />
          </label>
          <label>
            <span>审批意见</span>
            <input v-model="decisionReason" />
          </label>
        </div>

        <p v-if="pendingActions.length === 0" class="muted">
          当前无待审批的紧急停机或高危工单。可在「设备遥测诊断与预测维保」页签触发高危事件。
        </p>
        <div v-else class="stack">
          <div v-for="act in pendingActions" :key="act.action_id" class="entity-card">
            <div class="sub-head">
              <strong>{{ act.action_id }} · {{ act.action_type }}</strong>
              <span class="badge badge-warn">{{ act.status }}</span>
            </div>
            <p class="muted small">
              设备: <code>{{ act.equipment_id }}</code> · 故障码:
              <code>{{ act.fault_code ?? "N/A" }}</code> · SOP:
              <code>{{ act.sop_id ?? "N/A" }}</code> · 上报方: {{ act.requested_by }}
            </p>
            <div class="btn-row">
              <button class="btn btn-danger" @click="decideAction(act.action_id, true)">
                批准紧急停机 (Approve)
              </button>
              <button class="btn btn-secondary" @click="decideAction(act.action_id, false)">
                驳回停机 (Reject)
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>不可变操作审计追踪 ({{ auditLogs.length }})</h2>
        <p v-if="auditLogs.length === 0" class="muted">暂无审计事件记录。</p>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>审计 ID</th>
                <th>事件类型</th>
                <th>设备</th>
                <th>操作者</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="log in [...auditLogs].reverse()" :key="log.audit_id">
                <td class="mono">{{ log.audit_id }}</td>
                <td><span class="chip">{{ log.event_type }}</span></td>
                <td class="mono">{{ log.equipment_id }}</td>
                <td>{{ log.actor }}</td>
                <td class="mono small">{{ log.timestamp.slice(0, 19).replace("T", " ") }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #0b1120;
  color: #e2e8f0;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.shell {
  max-width: 1380px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 3rem;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 1rem;
  margin-bottom: 1.25rem;
}

.eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: #38bdf8;
  font-weight: 700;
}

h1 {
  margin: 0.25rem 0 0;
  font-size: 1.45rem;
  font-weight: 700;
}

h2 {
  margin: 0 0 0.85rem;
  font-size: 1.05rem;
  color: #f8fafc;
}

h3 {
  margin: 0 0 0.6rem;
  font-size: 0.92rem;
  color: #cbd5e1;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toast {
  background: #065f46;
  color: #d1fae5;
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  font-size: 0.82rem;
}

.error-banner {
  background: #7f1d1d;
  color: #fecaca;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.88rem;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.kpi-card {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 10px;
  padding: 0.85rem 1rem;
}

.kpi-alert {
  border-color: #f59e0b;
  background: #1c1917;
}

.kpi-label {
  font-size: 0.76rem;
  color: #94a3b8;
}

.kpi-val {
  font-size: 1.5rem;
  font-weight: 700;
  margin-top: 0.25rem;
  font-variant-numeric: tabular-nums;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}

.tab-btn {
  background: #111827;
  color: #94a3b8;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 0.55rem 1rem;
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.tab-btn.active {
  background: #0284c7;
  color: #ffffff;
  border-color: #38bdf8;
}

.tab-pill {
  background: #dc2626;
  color: #fff;
  border-radius: 999px;
  padding: 0.1rem 0.45rem;
  font-size: 0.72rem;
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 1rem;
}

.card {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 1.15rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.full-span {
  grid-column: 1 / -1;
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: #94a3b8;
}

input,
select,
textarea {
  background: #0f172a;
  color: #f1f5f9;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 0.45rem 0.6rem;
  font-size: 0.88rem;
}

.search-input {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 0.75rem;
}

.threshold-hint {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #0f172a;
  border-radius: 6px;
  font-size: 0.8rem;
  color: #cbd5e1;
}

.btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.85rem;
}

.btn {
  border: none;
  border-radius: 6px;
  padding: 0.5rem 0.9rem;
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary {
  background: #0284c7;
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

.sub-box,
.entity-card {
  margin-top: 0.85rem;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 0.75rem;
}

.sub-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.badge-ok {
  background: #064e3b;
  color: #6ee7b7;
}

.badge-warn {
  background: #78350f;
  color: #fcd34d;
}

.badge-crit {
  background: #7f1d1d;
  color: #fca5a5;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.5rem;
}

.chip {
  background: #1e293b;
  color: #93c5fd;
  padding: 0.18rem 0.5rem;
  border-radius: 5px;
  font-size: 0.75rem;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.steps {
  margin: 0.5rem 0;
  padding-left: 1.2rem;
  font-size: 0.84rem;
  color: #cbd5e1;
}

.safety-box {
  background: #451a03;
  color: #fde68a;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.78rem;
}

.pm-summary {
  display: flex;
  gap: 1rem;
  font-size: 0.84rem;
  color: #93c5fd;
  margin-bottom: 0.75rem;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

th,
td {
  text-align: left;
  padding: 0.5rem 0.45rem;
  border-bottom: 1px solid #1e293b;
}

th {
  color: #94a3b8;
  font-weight: 600;
}

.score-bar {
  width: 72px;
  height: 6px;
  background: #1e293b;
  border-radius: 999px;
  overflow: hidden;
  display: inline-block;
  margin-right: 0.4rem;
  vertical-align: middle;
}

.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #ef4444, #f59e0b, #10b981);
}

.wiki-list {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  max-height: 440px;
  overflow-y: auto;
}

.wiki-item {
  text-align: left;
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  cursor: pointer;
}

.wiki-item.selected {
  border-color: #38bdf8;
  background: #0c4a6e33;
}

.wiki-body {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.78rem;
  background: #020617;
  padding: 0.75rem;
  border-radius: 6px;
  max-height: 260px;
  overflow-y: auto;
}

.list-clean {
  margin: 0.5rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.84rem;
}

.muted {
  color: #94a3b8;
}

.small {
  font-size: 0.76rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
