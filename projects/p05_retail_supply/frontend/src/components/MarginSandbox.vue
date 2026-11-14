<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  apiClient,
  type EOQOptimizeResponse,
  type MarginSimulateResponse,
  type SKUItem,
} from "../api/client";

const props = defineProps<{
  skus: SKUItem[];
}>();

const emit = defineEmits<{
  (e: "notify", type: "ok" | "err", text: string): void;
  (e: "refresh"): void;
}>();

// Interactive sliders
const globalDiscountPct = ref<number>(15);
const serviceLevelPct = ref<number>(95);
const orderingCost = ref<number>(85);
const holdingRatePct = ref<number>(24);
const promoLiftPct = ref<number>(20);

const simResult = ref<MarginSimulateResponse | null>(null);
const eoqResult = ref<EOQOptimizeResponse | null>(null);
const running = ref(false);

// Manual FDE Replenishment quick trigger
const replenishSku = ref("SKU-1001");
const replenishQty = ref<string>("");
const replenishPrice = ref<string>("");
const lastAction = ref<Record<string, unknown> | null>(null);

const blendedMarginPct = computed(() => {
  if (!simResult.value) return 0;
  return Number((simResult.value.blended_margin_pct * 100).toFixed(2));
});

const avgMarginFloorPct = computed(() => {
  if (!simResult.value || simResult.value.results.length === 0) return 20;
  const sum = simResult.value.results.reduce((acc, r) => acc + r.min_margin_pct * 100, 0);
  return Number((sum / simResult.value.results.length).toFixed(1));
});

// SVG Gauge math (semicircle 0%..60% margin mapped to -90deg..+90deg)
const gaugeDashOffset = computed(() => {
  const clamped = Math.max(0, Math.min(60, blendedMarginPct.value));
  const arcLen = 251.2; // pi * 80
  return arcLen - (clamped / 60) * arcLen;
});

const gaugeColor = computed(() => {
  if (!simResult.value) return "#4f46e5";
  if (!simResult.value.all_passed || blendedMarginPct.value < avgMarginFloorPct.value) {
    return "#ef4444";
  }
  if (blendedMarginPct.value < avgMarginFloorPct.value + 5) {
    return "#f59e0b";
  }
  return "#10b981";
});

async function runSandbox() {
  running.value = true;
  try {
    const [marginRes, eoqRes] = await Promise.all([
      apiClient.simulateMargin({
        global_discount_pct: globalDiscountPct.value / 100,
      }),
      apiClient.optimizeEOQ({
        ordering_cost: orderingCost.value,
        holding_cost_rate: holdingRatePct.value / 100,
        service_level: serviceLevelPct.value / 100,
        promo_lift_pct: promoLiftPct.value / 100,
      }),
    ]);
    simResult.value = marginRes;
    eoqResult.value = eoqRes;
  } catch (err) {
    emit("notify", "err", err instanceof Error ? err.message : String(err));
  } finally {
    running.value = false;
  }
}

async function triggerEOQOrder(skuId: string, qty: number) {
  try {
    const res = await apiClient.planReplenishment({
      sku_id: skuId,
      requested_qty: qty,
      actor: "eoq-sandbox",
    });
    lastAction.value = res.action as unknown as Record<string, unknown>;
    emit("notify", "ok", `EOQ 补货单 ${res.action.action_id} (${skuId} × ${qty}) -> ${res.action.status}`);
    emit("refresh");
  } catch (err) {
    emit("notify", "err", err instanceof Error ? err.message : String(err));
  }
}

async function submitManualReplenishment() {
  try {
    const payload: {
      sku_id: string;
      requested_qty?: number | null;
      proposed_price?: number | null;
    } = { sku_id: replenishSku.value };
    if (replenishQty.value.trim() !== "") {
      payload.requested_qty = Number(replenishQty.value);
    }
    if (replenishPrice.value.trim() !== "") {
      payload.proposed_price = Number(replenishPrice.value);
    }
    const res = await apiClient.planReplenishment(payload);
    lastAction.value = res.action as unknown as Record<string, unknown>;
    emit("notify", "ok", `FDE 决策 ${res.action.action_id} 状态: ${res.action.status}`);
    emit("refresh");
  } catch (err) {
    emit("notify", "err", err instanceof Error ? err.message : String(err));
  }
}

onMounted(() => {
  runSandbox();
});
</script>

<template>
  <div class="sandbox-wrap">
    <!-- Top Interactive Sliders + Live GMV / Margin-Floor Gauge -->
    <div class="hero-grid">
      <section class="card controls-card">
        <div class="card-head">
          <div>
            <span class="pill-indigo">GROWTH &amp; EOQ SANDBOX</span>
            <h2>促销毛利红线 &amp; EOQ 补货联动沙盘</h2>
          </div>
          <button class="btn-indigo" :disabled="running" @click="runSandbox">
            {{ running ? "测算中..." : "实时重算沙盘" }}
          </button>
        </div>

        <div class="slider-grid">
          <div class="slider-item">
            <div class="slider-head">
              <span>统一促销折扣 (Promo Discount)</span>
              <strong class="val-indigo">{{ globalDiscountPct }}%</strong>
            </div>
            <input
              v-model.number="globalDiscountPct"
              type="range"
              min="0"
              max="60"
              step="1"
              class="range-indigo"
              @change="runSandbox"
            />
            <div class="slider-scale"><span>0% 原价</span><span>30%</span><span>60% 清仓</span></div>
          </div>

          <div class="slider-item">
            <div class="slider-head">
              <span>目标现货服务水平 (Service Level)</span>
              <strong class="val-emerald">{{ serviceLevelPct }}%</strong>
            </div>
            <input
              v-model.number="serviceLevelPct"
              type="range"
              min="80"
              max="99"
              step="1"
              class="range-emerald"
              @change="runSandbox"
            />
            <div class="slider-scale"><span>80%</span><span>95% 标准</span><span>99% 极高</span></div>
          </div>

          <div class="slider-item">
            <div class="slider-head">
              <span>单次采购履约成本 (Ordering Cost)</span>
              <strong class="val-indigo">${{ orderingCost }}</strong>
            </div>
            <input
              v-model.number="orderingCost"
              type="range"
              min="40"
              max="200"
              step="5"
              class="range-indigo"
              @change="runSandbox"
            />
            <div class="slider-scale"><span>$40</span><span>$85 基准</span><span>$200</span></div>
          </div>

          <div class="slider-item">
            <div class="slider-head">
              <span>促销需求拉升 (Promo Lift)</span>
              <strong class="val-emerald">+{{ promoLiftPct }}%</strong>
            </div>
            <input
              v-model.number="promoLiftPct"
              type="range"
              min="0"
              max="100"
              step="5"
              class="range-emerald"
              @change="runSandbox"
            />
            <div class="slider-scale"><span>0% 常态</span><span>+50%</span><span>+100% 大促</span></div>
          </div>

          <div class="slider-item">
            <div class="slider-head">
              <span>年化仓储持有费率 (Holding Rate)</span>
              <strong class="val-indigo">{{ holdingRatePct }}%</strong>
            </div>
            <input
              v-model.number="holdingRatePct"
              type="range"
              min="10"
              max="40"
              step="2"
              class="range-indigo"
              @change="runSandbox"
            />
            <div class="slider-scale"><span>10%</span><span>24% 基准</span><span>40%</span></div>
          </div>
        </div>
      </section>

      <!-- Live GMV / Margin-Floor Gauge Card -->
      <section class="card gauge-card">
        <div class="pill-emerald">LIVE MARGIN-FLOOR GAUGE</div>
        <h2>综合毛利率 &amp; 红线护栏仪表盘</h2>
        <div class="gauge-box">
          <svg viewBox="0 0 200 115" class="gauge-svg">
            <path
              d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none"
              stroke="#e2e8f0"
              stroke-width="16"
              stroke-linecap="round"
            />
            <path
              d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none"
              :stroke="gaugeColor"
              stroke-width="16"
              stroke-linecap="round"
              stroke-dasharray="251.2"
              :stroke-dashoffset="gaugeDashOffset"
              style="transition: stroke-dashoffset 0.35s ease, stroke 0.35s ease"
            />
            <text x="100" y="82" text-anchor="middle" class="gauge-pct">
              {{ blendedMarginPct }}%
            </text>
            <text x="100" y="102" text-anchor="middle" class="gauge-sub">
              红线均值 {{ avgMarginFloorPct }}%
            </text>
          </svg>
        </div>

        <div v-if="simResult" class="gmv-metrics">
          <div class="gmv-tile">
            <span>预计 GMV 营收</span>
            <strong>${{ simResult.total_projected_revenue.toLocaleString() }}</strong>
          </div>
          <div class="gmv-tile">
            <span>预计毛利额</span>
            <strong class="val-emerald">${{ simResult.total_projected_profit.toLocaleString() }}</strong>
          </div>
          <div class="gmv-tile">
            <span>护栏通过率</span>
            <strong :class="simResult.all_passed ? 'val-emerald' : 'val-danger'">
              {{ simResult.guardrail_passed_count }} / {{ simResult.total_skus_simulated }}
            </strong>
          </div>
        </div>
      </section>
    </div>

    <!-- EOQ Replenishment & Holding vs Stockout Trade-off -->
    <section v-if="eoqResult" class="card">
      <div class="card-head">
        <div>
          <span class="pill-indigo">EOQ REPLENISHMENT ENGINE</span>
          <h2>经济订货批量 (EOQ) &amp; 持有/缺货成本权衡</h2>
        </div>
        <div class="cost-pills">
          <span class="cost-pill">
            年订货成本: <strong>${{ eoqResult.total_annual_ordering_cost.toLocaleString() }}</strong>
          </span>
          <span class="cost-pill">
            年持有成本: <strong>${{ eoqResult.total_annual_holding_cost.toLocaleString() }}</strong>
          </span>
          <span class="cost-pill warn">
            年缺货风险成本: <strong>${{ eoqResult.total_annual_stockout_cost.toLocaleString() }}</strong>
          </span>
          <span class="cost-pill total">
            总相关成本: <strong>${{ eoqResult.total_relevant_cost.toLocaleString() }}</strong>
          </span>
        </div>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>SKU / 供应商</th>
            <th>当前库存 / ROP</th>
            <th>安全库存 (SS)</th>
            <th>EOQ 推荐批量</th>
            <th>年订货次数</th>
            <th>持有 vs 缺货成本</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in eoqResult.items" :key="item.sku_id">
            <td>
              <strong>{{ item.sku_id }}</strong> · {{ item.sku_name }}
              <div class="sub">{{ item.supplier_id }} · 交期 {{ item.lead_time_days }}d · 日均 {{ item.daily_demand }} 件</div>
            </td>
            <td>
              <span :class="['stock-num', item.needs_replenishment ? 'danger' : 'ok']">
                {{ item.current_stock }}
              </span>
              <span class="sub"> / ROP {{ item.reorder_point }}</span>
            </td>
            <td>{{ item.safety_stock }} 件</td>
            <td>
              <strong class="val-indigo">{{ item.recommended_order_qty }} 件</strong>
              <div class="sub">理论 EOQ {{ item.eoq_raw }}</div>
            </td>
            <td>{{ item.orders_per_year }} 次/年</td>
            <td>
              <div class="sub">
                持有 ${{ item.annual_holding_cost.toLocaleString() }} | 缺货 ${{ item.annual_stockout_cost.toLocaleString() }}
              </div>
              <div class="tradeoff-bar">
                <div
                  class="bar-hold"
                  :style="{
                    width:
                      Math.min(
                        100,
                        (item.annual_holding_cost /
                          Math.max(item.annual_holding_cost + item.annual_stockout_cost, 1)) *
                          100
                      ) + '%',
                  }"
                />
              </div>
            </td>
            <td>
              <button
                class="btn-emerald-sm"
                @click="triggerEOQOrder(item.sku_id, item.recommended_order_qty)"
              >
                按 EOQ 下单
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Per-SKU Promo Guardrail Table -->
    <section v-if="simResult" class="card">
      <h2>SKU 促销毛利护栏明细</h2>
      <table class="data-table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>成本 / 目录价</th>
            <th>折后价</th>
            <th>测算毛利率</th>
            <th>毛利红线</th>
            <th>护栏状态</th>
            <th>预计利润</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in simResult.results" :key="r.sku_id">
            <td>
              <strong>{{ r.sku_id }}</strong>
              <div class="sub">{{ r.sku_name }}</div>
            </td>
            <td>${{ r.unit_cost }} / ${{ r.list_price }}</td>
            <td>${{ r.effective_price }} (-{{ (r.promo_discount_pct * 100).toFixed(0) }}%)</td>
            <td>{{ (r.gross_margin_pct * 100).toFixed(2) }}%</td>
            <td>{{ (r.min_margin_pct * 100).toFixed(0) }}%</td>
            <td>
              <span :class="['badge', r.guardrail_passed ? 'ok' : 'danger']">
                {{ r.guardrail_passed ? "PASSED" : "BLOCKED" }}
              </span>
            </td>
            <td>${{ r.projected_profit.toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Manual FDE Replenish / Price Trigger -->
    <section class="card">
      <h2>自定义 FDE 补货与调价触发</h2>
      <div class="form-row">
        <label>
          目标 SKU
          <select v-model="replenishSku">
            <option v-for="s in skus" :key="s.sku_id" :value="s.sku_id">
              {{ s.sku_id }} · {{ s.name }}
            </option>
          </select>
        </label>
        <label>
          采购数量 (留空自动推荐)
          <input v-model="replenishQty" type="number" min="0" placeholder="自动推荐" />
        </label>
        <label>
          拟议售价 $ (可选)
          <input v-model="replenishPrice" type="number" step="0.01" placeholder="按目录价" />
        </label>
        <button class="btn-indigo" @click="submitManualReplenishment">执行 FDE 决策</button>
      </div>
      <pre v-if="lastAction" class="json-box">{{ JSON.stringify(lastAction, null, 2) }}</pre>
    </section>
  </div>
</template>

<style scoped>
.sandbox-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.hero-grid {
  display: grid;
  grid-template-columns: 1.55fr 1fr;
  gap: 16px;
}
@media (max-width: 960px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }
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
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
h2 {
  margin: 4px 0 0;
  font-size: 16px;
  color: #0f172a;
}
.pill-indigo,
.pill-emerald {
  display: inline-block;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 999px;
}
.pill-indigo {
  background: #eef2ff;
  color: #4f46e5;
}
.pill-emerald {
  background: #ecfdf5;
  color: #059669;
}
.slider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.slider-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
}
.slider-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #475569;
  margin-bottom: 6px;
}
.val-indigo {
  color: #4f46e5;
}
.val-emerald {
  color: #10b981;
}
.val-danger {
  color: #ef4444;
}
.range-indigo,
.range-emerald {
  width: 100%;
  cursor: pointer;
}
.range-indigo {
  accent-color: #4f46e5;
}
.range-emerald {
  accent-color: #10b981;
}
.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 2px;
}
.gauge-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.gauge-box {
  display: flex;
  justify-content: center;
  margin: 6px 0;
}
.gauge-svg {
  width: 210px;
  height: 120px;
}
.gauge-pct {
  font-size: 24px;
  font-weight: 800;
  fill: #0f172a;
}
.gauge-sub {
  font-size: 11px;
  fill: #64748b;
}
.gmv-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.gmv-tile {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: #64748b;
}
.gmv-tile strong {
  font-size: 15px;
  color: #0f172a;
}
.cost-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cost-pill {
  background: #f1f5f9;
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 12px;
  color: #334155;
}
.cost-pill.warn {
  background: #fef3c7;
  color: #92400e;
}
.cost-pill.total {
  background: #eef2ff;
  color: #4338ca;
}
.tradeoff-bar {
  width: 140px;
  height: 6px;
  background: #fee2e2;
  border-radius: 999px;
  overflow: hidden;
  margin-top: 4px;
}
.bar-hold {
  height: 100%;
  background: #4f46e5;
}
.stock-num.danger {
  color: #dc2626;
  font-weight: 700;
}
.stock-num.ok {
  color: #059669;
  font-weight: 700;
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
.btn-indigo:hover {
  background: #4338ca;
}
.btn-emerald-sm {
  background: #10b981;
  color: #ffffff;
  border: none;
  padding: 5px 10px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.btn-emerald-sm:hover {
  background: #059669;
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
}
.badge.ok {
  background: #d1fae5;
  color: #065f46;
}
.badge.danger {
  background: #fee2e2;
  color: #991b1b;
}
.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-top: 10px;
}
.form-row label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #475569;
}
input,
select {
  padding: 7px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
}
.json-box {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
  margin-top: 12px;
  max-height: 220px;
}
</style>
