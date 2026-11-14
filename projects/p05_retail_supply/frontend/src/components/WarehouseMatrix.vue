<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { apiClient, type RebalanceResponse } from "../api/client";

const emit = defineEmits<{
  (e: "notify", type: "ok" | "err", text: string): void;
}>();

const targetCoverDays = ref<number>(10);
const transferCostPerUnit = ref<number>(1.85);
const minTransferQty = ref<number>(5);
const loading = ref(false);
const plan = ref<RebalanceResponse | null>(null);

// Editable stock matrix: sku_id -> { warehouse_id: qty }
const editableMatrix = reactive<Record<string, Record<string, number>>>({});

const warehouseIds = computed(() => {
  if (!plan.value) return [];
  return plan.value.warehouse_summary.map((w) => w.warehouse_id);
});

const skuIds = computed(() => {
  if (!plan.value) return [];
  return Array.from(new Set(plan.value.matrix.map((c) => c.sku_id)));
});

function syncEditableFromPlan(res: RebalanceResponse) {
  for (const cell of res.matrix) {
    if (!editableMatrix[cell.sku_id]) {
      editableMatrix[cell.sku_id] = {};
    }
    editableMatrix[cell.sku_id][cell.warehouse_id] = cell.current_qty;
  }
}

function getCell(skuId: string, whId: string) {
  return plan.value?.matrix.find((c) => c.sku_id === skuId && c.warehouse_id === whId);
}

async function computeRebalance(useCustomMatrix = false) {
  loading.value = true;
  try {
    const payload: {
      stock_matrix?: Record<string, Record<string, number>> | null;
      target_cover_days: number;
      transfer_cost_per_unit: number;
      min_transfer_qty: number;
    } = {
      target_cover_days: targetCoverDays.value,
      transfer_cost_per_unit: transferCostPerUnit.value,
      min_transfer_qty: minTransferQty.value,
    };
    if (useCustomMatrix && Object.keys(editableMatrix).length > 0) {
      payload.stock_matrix = JSON.parse(JSON.stringify(editableMatrix));
    }
    const res = await apiClient.rebalanceWarehouses(payload);
    plan.value = res;
    if (!useCustomMatrix) {
      syncEditableFromPlan(res);
    }
  } catch (err) {
    emit("notify", "err", err instanceof Error ? err.message : String(err));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  computeRebalance(false);
});
</script>

<template>
  <div class="matrix-wrap">
    <!-- Controls & Summary -->
    <section class="card">
      <div class="card-head">
        <div>
          <span class="pill-emerald">MULTI-WAREHOUSE ALLOCATOR</span>
          <h2>多仓联动库存矩阵 &amp; 调拨平衡引擎</h2>
        </div>
        <div class="controls-row">
          <label class="ctrl">
            目标备货天数: <strong>{{ targetCoverDays }} 天</strong>
            <input
              v-model.number="targetCoverDays"
              type="range"
              min="5"
              max="21"
              step="1"
              class="range-emerald"
              @change="computeRebalance(true)"
            />
          </label>
          <label class="ctrl">
            单件调拨运费 ($)
            <input
              v-model.number="transferCostPerUnit"
              type="number"
              step="0.1"
              min="0"
              class="num-input"
            />
          </label>
          <button class="btn-indigo" :disabled="loading" @click="computeRebalance(true)">
            {{ loading ? "计算中..." : "重算调拨方案" }}
          </button>
          <button class="btn-outline" :disabled="loading" @click="computeRebalance(false)">
            重置默认分布
          </button>
        </div>
      </div>

      <!-- Warehouse Capacity Summary Cards -->
      <div v-if="plan" class="wh-cards">
        <div v-for="wh in plan.warehouse_summary" :key="wh.warehouse_id" class="wh-card">
          <div class="wh-top">
            <div>
              <strong>{{ wh.warehouse_id }}</strong>
              <span class="sub"> · {{ wh.region }}</span>
              <div class="wh-name">{{ wh.name }}</div>
            </div>
            <span class="util-badge">{{ wh.utilization_pct }}% 库容</span>
          </div>
          <div class="util-bar">
            <div class="util-fill" :style="{ width: Math.min(100, wh.utilization_pct) + '%' }" />
          </div>
          <div class="wh-stats">
            <span>在库: <strong>{{ wh.total_sku_units }}</strong></span>
            <span class="surplus-txt">盈余: +{{ wh.surplus_units }}</span>
            <span class="deficit-txt">缺口: -{{ wh.deficit_units }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- SKU x Warehouse Allocation Matrix -->
    <section v-if="plan" class="card">
      <h2>SKU × 仓库库存盈亏矩阵 (可直接修改库存模拟)</h2>
      <table class="data-table">
        <thead>
          <tr>
            <th>SKU</th>
            <th v-for="whId in warehouseIds" :key="whId">{{ whId }} (当前 / 目标)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sid in skuIds" :key="sid">
            <td>
              <strong>{{ sid }}</strong>
              <div class="sub">{{ getCell(sid, warehouseIds[0])?.sku_name }}</div>
            </td>
            <td v-for="whId in warehouseIds" :key="whId">
              <div
                v-if="getCell(sid, whId)"
                :class="['cell-box', getCell(sid, whId)!.status.toLowerCase()]"
              >
                <div class="cell-edit">
                  <input
                    v-model.number="editableMatrix[sid][whId]"
                    type="number"
                    min="0"
                    class="cell-input"
                  />
                  <span class="sub">/ {{ getCell(sid, whId)!.target_qty }}</span>
                </div>
                <span class="delta-tag">
                  {{ getCell(sid, whId)!.delta >= 0 ? "+" : "" }}{{ getCell(sid, whId)!.delta }}
                  ({{ getCell(sid, whId)!.status }})
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Recommended Transfer Plan -->
    <section v-if="plan" class="card">
      <div class="card-head">
        <h2>智能调拨执行计划 ({{ plan.total_transfers }} 条路径)</h2>
        <div class="benefit-pills">
          <span class="bpill">总调拨件数: <strong>{{ plan.total_units_rebalanced }}</strong></span>
          <span class="bpill">调拨运费: <strong>${{ plan.total_transfer_cost.toLocaleString() }}</strong></span>
          <span class="bpill ok">
            预计净收益: <strong>+${{ plan.total_net_benefit.toLocaleString() }}</strong>
          </span>
        </div>
      </div>

      <div v-if="plan.transfers.length === 0" class="empty-state">
        当前各仓库库存均已满足安全备货目标，无需跨仓调拨。
      </div>

      <table v-else class="data-table">
        <thead>
          <tr>
            <th>调拨单号</th>
            <th>SKU</th>
            <th>调拨路径</th>
            <th>调拨数量</th>
            <th>运费成本</th>
            <th>避免缺货收益</th>
            <th>净收益</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in plan.transfers" :key="t.transfer_id">
            <td><strong>{{ t.transfer_id }}</strong></td>
            <td>
              <strong>{{ t.sku_id }}</strong>
              <div class="sub">{{ t.sku_name }}</div>
            </td>
            <td>
              <span class="route-pill">
                {{ t.from_warehouse }} → {{ t.to_warehouse }}
              </span>
            </td>
            <td><strong>{{ t.quantity }} 件</strong></td>
            <td>${{ t.estimated_transfer_cost.toLocaleString() }}</td>
            <td class="surplus-txt">+${{ t.estimated_stockout_savings.toLocaleString() }}</td>
            <td><strong class="surplus-txt">+${{ t.net_benefit.toLocaleString() }}</strong></td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.matrix-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
h2 {
  margin: 4px 0 0;
  font-size: 16px;
  color: #0f172a;
}
.pill-emerald {
  display: inline-block;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #059669;
}
.controls-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.ctrl {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: #475569;
}
.range-emerald {
  accent-color: #10b981;
  cursor: pointer;
}
.num-input {
  width: 84px;
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
}
.btn-indigo {
  background: #4f46e5;
  color: #ffffff;
  border: none;
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.btn-outline {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #cbd5e1;
  padding: 8px 12px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.wh-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}
.wh-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
}
.wh-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.wh-name {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}
.util-badge {
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
}
.util-bar {
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 8px;
}
.util-fill {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5, #10b981);
}
.wh-stats {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.surplus-txt {
  color: #059669;
  font-weight: 600;
}
.deficit-txt {
  color: #dc2626;
  font-weight: 600;
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
  vertical-align: middle;
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
.cell-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.cell-box.surplus {
  background: #ecfdf5;
  border-color: #a7f3d0;
}
.cell-box.deficit {
  background: #fef2f2;
  border-color: #fecaca;
}
.cell-box.balanced {
  background: #f8fafc;
}
.cell-edit {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cell-input {
  width: 68px;
  padding: 4px 6px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  font-size: 13px;
  font-weight: 700;
}
.delta-tag {
  font-size: 11px;
  font-weight: 700;
  color: #334155;
}
.benefit-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.bpill {
  background: #f1f5f9;
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 12px;
}
.bpill.ok {
  background: #d1fae5;
  color: #065f46;
}
.route-pill {
  background: #eef2ff;
  color: #4338ca;
  padding: 3px 9px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 12px;
}
.empty-state {
  padding: 18px;
  text-align: center;
  color: #64748b;
  background: #f8fafc;
  border-radius: 8px;
  font-size: 13px;
}
</style>
