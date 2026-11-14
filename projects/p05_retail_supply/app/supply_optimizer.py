"""Domain-native EOQ Replenishment & Multi-Warehouse Allocation Optimizer for P05."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from .ontology import DemandForecast, RetailOntologyRegistry, SKU, Supplier, Warehouse


class EOQTradeoffPoint(BaseModel):
    multiplier: float
    order_qty: int
    annual_ordering_cost: float
    annual_holding_cost: float
    annual_stockout_cost: float
    total_relevant_cost: float


class EOQResult(BaseModel):
    sku_id: str
    sku_name: str
    category: str
    supplier_id: str
    warehouse_id: str
    current_stock: int
    daily_demand: float
    annual_demand: float
    lead_time_days: int
    service_level: float
    z_score: float
    eoq_raw: int
    recommended_order_qty: int
    safety_stock: int
    reorder_point: int
    needs_replenishment: bool
    orders_per_year: float
    annual_ordering_cost: float
    annual_holding_cost: float
    annual_stockout_cost: float
    total_relevant_cost: float
    holding_vs_stockout_ratio: float
    tradeoff_curve: list[EOQTradeoffPoint]


class EOQBatchResult(BaseModel):
    items: list[EOQResult]
    total_skus: int
    skus_needing_replenishment: int
    total_annual_ordering_cost: float
    total_annual_holding_cost: float
    total_annual_stockout_cost: float
    total_relevant_cost: float


class TransferPlanItem(BaseModel):
    transfer_id: str
    sku_id: str
    sku_name: str
    from_warehouse: str
    to_warehouse: str
    quantity: int
    estimated_transfer_cost: float
    estimated_stockout_savings: float
    net_benefit: float
    reason: str


class WarehouseSKUCell(BaseModel):
    sku_id: str
    sku_name: str
    warehouse_id: str
    current_qty: int
    target_qty: int
    delta: int
    status: str  # SURPLUS | BALANCED | DEFICIT


class WarehouseSummary(BaseModel):
    warehouse_id: str
    name: str
    region: str
    capacity_units: int
    current_utilization_units: int
    utilization_pct: float
    total_sku_units: int
    surplus_units: int
    deficit_units: int


class RebalancePlanResult(BaseModel):
    transfers: list[TransferPlanItem]
    total_transfers: int
    total_units_rebalanced: int
    total_transfer_cost: float
    total_stockout_savings: float
    total_net_benefit: float
    warehouse_summary: list[WarehouseSummary]
    matrix: list[WarehouseSKUCell]


def _normal_ppf(p: float) -> float:
    """Deterministic Beasley-Springer-Moro approximation for standard normal inverse CDF."""
    p = min(max(p, 0.5), 0.999)
    lookup = {
        0.50: 0.0,
        0.80: 0.8416,
        0.85: 1.0364,
        0.90: 1.2816,
        0.95: 1.6449,
        0.975: 1.9600,
        0.98: 2.0537,
        0.99: 2.3263,
        0.995: 2.5758,
        0.999: 3.0902,
    }
    if p in lookup:
        return lookup[p]
    # Rational approximation (Abramowitz & Stegun 26.2.23) for p in (0.5, 1.0)
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    return round(z, 4)


class EOQOptimizer:
    """Deterministic Economic Order Quantity, Safety Stock, and Holding vs Stockout optimizer."""

    def optimize_sku(
        self,
        sku: SKU,
        supplier: Supplier | None = None,
        forecast: DemandForecast | None = None,
        *,
        ordering_cost: float = 85.0,
        holding_cost_rate: float = 0.24,
        service_level: float = 0.95,
        daily_demand_override: float | None = None,
        lead_time_override: int | None = None,
        promo_lift_pct: float = 0.0,
    ) -> EOQResult:
        base_daily = (
            daily_demand_override
            if daily_demand_override is not None
            else (forecast.effective_daily_demand() if forecast else 5.0)
        )
        effective_daily = round(max(base_daily * (1.0 + promo_lift_pct), 0.1), 2)
        annual_demand = round(effective_daily * 365.0, 2)

        lead_time_days = (
            lead_time_override
            if lead_time_override is not None
            else (supplier.lead_time_days if supplier else 7)
        )
        moq = supplier.moq if supplier else 50
        demand_std = (
            forecast.demand_std_dev * (1.0 + promo_lift_pct * 0.5)
            if forecast and forecast.demand_std_dev > 0
            else effective_daily * 0.2
        )

        holding_cost_per_unit = max(sku.unit_cost * holding_cost_rate, 0.01)
        z_score = _normal_ppf(service_level)

        eoq_raw = max(
            1,
            math.ceil(math.sqrt((2.0 * annual_demand * ordering_cost) / holding_cost_per_unit)),
        )
        recommended_order_qty = max(eoq_raw, moq)
        safety_stock = max(1, math.ceil(z_score * demand_std * math.sqrt(lead_time_days)))
        reorder_point = math.ceil(effective_daily * lead_time_days) + safety_stock

        unit_margin = max(sku.effective_price() - sku.unit_cost, 1.0)
        stockout_penalty_per_unit = unit_margin * 1.25

        def _costs_for_qty(qty: int) -> tuple[float, float, float, float]:
            q = max(qty, 1)
            orders = annual_demand / q
            ord_cost = round(orders * ordering_cost, 2)
            hold_cost = round(((q / 2.0) + safety_stock) * holding_cost_per_unit, 2)
            # Smaller order batches increase cycle exposure; higher service level mitigates it
            cycle_exposure = min(1.0, (moq / max(q, 1)) * 0.35 + 0.65)
            stk_cost = round(
                annual_demand * (1.0 - service_level) * stockout_penalty_per_unit * cycle_exposure,
                2,
            )
            total = round(ord_cost + hold_cost + stk_cost, 2)
            return ord_cost, hold_cost, stk_cost, total

        ord_cost, hold_cost, stk_cost, total_cost = _costs_for_qty(recommended_order_qty)
        orders_per_year = round(annual_demand / max(recommended_order_qty, 1), 2)
        ratio = round(hold_cost / max(stk_cost, 0.01), 2)

        multipliers = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        curve: list[EOQTradeoffPoint] = []
        for mult in multipliers:
            q_pt = max(1, math.ceil(recommended_order_qty * mult))
            c_ord, c_hold, c_stk, c_tot = _costs_for_qty(q_pt)
            curve.append(
                EOQTradeoffPoint(
                    multiplier=mult,
                    order_qty=q_pt,
                    annual_ordering_cost=c_ord,
                    annual_holding_cost=c_hold,
                    annual_stockout_cost=c_stk,
                    total_relevant_cost=c_tot,
                )
            )

        return EOQResult(
            sku_id=sku.sku_id,
            sku_name=sku.name,
            category=sku.category,
            supplier_id=sku.supplier_id,
            warehouse_id=sku.warehouse_id,
            current_stock=sku.current_stock,
            daily_demand=effective_daily,
            annual_demand=annual_demand,
            lead_time_days=lead_time_days,
            service_level=service_level,
            z_score=round(z_score, 4),
            eoq_raw=eoq_raw,
            recommended_order_qty=recommended_order_qty,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            needs_replenishment=sku.current_stock <= reorder_point,
            orders_per_year=orders_per_year,
            annual_ordering_cost=ord_cost,
            annual_holding_cost=hold_cost,
            annual_stockout_cost=stk_cost,
            total_relevant_cost=total_cost,
            holding_vs_stockout_ratio=ratio,
            tradeoff_curve=curve,
        )

    def optimize_registry(
        self,
        registry: RetailOntologyRegistry,
        *,
        sku_id: str | None = None,
        ordering_cost: float = 85.0,
        holding_cost_rate: float = 0.24,
        service_level: float = 0.95,
        daily_demand_override: float | None = None,
        lead_time_override: int | None = None,
        promo_lift_pct: float = 0.0,
    ) -> EOQBatchResult:
        if sku_id is not None:
            if sku_id not in registry.skus:
                raise KeyError(f"Unknown SKU: {sku_id}")
            target_skus = [registry.skus[sku_id]]
        else:
            target_skus = [registry.skus[sid] for sid in sorted(registry.skus)]

        results = [
            self.optimize_sku(
                sku=s,
                supplier=registry.suppliers.get(s.supplier_id),
                forecast=registry.forecasts.get(s.sku_id),
                ordering_cost=ordering_cost,
                holding_cost_rate=holding_cost_rate,
                service_level=service_level,
                daily_demand_override=daily_demand_override,
                lead_time_override=lead_time_override,
                promo_lift_pct=promo_lift_pct,
            )
            for s in target_skus
        ]

        return EOQBatchResult(
            items=results,
            total_skus=len(results),
            skus_needing_replenishment=sum(1 for r in results if r.needs_replenishment),
            total_annual_ordering_cost=round(sum(r.annual_ordering_cost for r in results), 2),
            total_annual_holding_cost=round(sum(r.annual_holding_cost for r in results), 2),
            total_annual_stockout_cost=round(sum(r.annual_stockout_cost for r in results), 2),
            total_relevant_cost=round(sum(r.total_relevant_cost for r in results), 2),
        )


class WarehouseAllocator:
    """Multi-warehouse inventory rebalancing allocator from surplus hubs to deficit hubs."""

    @staticmethod
    def build_default_stock_matrix(
        registry: RetailOntologyRegistry,
    ) -> dict[str, dict[str, int]]:
        """Build deterministic multi-warehouse stock snapshot for all SKUs & warehouses."""
        wh_ids = sorted(registry.warehouses.keys())
        matrix: dict[str, dict[str, int]] = {}
        for sku_id in sorted(registry.skus.keys()):
            sku = registry.skus[sku_id]
            row: dict[str, int] = {}
            for wh_id in wh_ids:
                if wh_id == sku.warehouse_id:
                    row[wh_id] = sku.current_stock
                else:
                    # Seed realistic secondary hub buffer for multi-hub rebalancing visibility
                    row[wh_id] = max(0, sku.safety_stock + 40 - (sku.current_stock // 4))
            matrix[sku_id] = row
        return matrix

    def plan_rebalance(
        self,
        registry: RetailOntologyRegistry,
        *,
        stock_matrix: dict[str, dict[str, int]] | None = None,
        sku_ids: list[str] | None = None,
        target_cover_days: float = 10.0,
        transfer_cost_per_unit: float = 1.85,
        min_transfer_qty: int = 5,
    ) -> RebalancePlanResult:
        if not registry.warehouses:
            raise ValueError("No warehouses registered in ontology.")

        resolved_matrix = (
            {k: dict(v) for k, v in stock_matrix.items()}
            if stock_matrix is not None
            else self.build_default_stock_matrix(registry)
        )

        target_sku_ids = (
            sku_ids if sku_ids is not None else sorted(registry.skus.keys())
        )
        for sid in target_sku_ids:
            if sid not in registry.skus:
                raise KeyError(f"Unknown SKU: {sid}")

        wh_ids = sorted(registry.warehouses.keys())
        for sid, wh_map in resolved_matrix.items():
            for wh_id in wh_map:
                if wh_id not in registry.warehouses:
                    raise KeyError(f"Unknown Warehouse: {wh_id}")

        # Track remaining capacity per warehouse
        remaining_cap: dict[str, int] = {
            wh_id: max(0, wh.capacity_units - wh.current_utilization_units)
            for wh_id, wh in registry.warehouses.items()
        }

        cells: list[WarehouseSKUCell] = []
        transfers: list[TransferPlanItem] = []
        wh_totals: dict[str, dict[str, int]] = {
            wh_id: {"total_sku_units": 0, "surplus_units": 0, "deficit_units": 0}
            for wh_id in wh_ids
        }

        transfer_counter = 1
        for sid in target_sku_ids:
            sku = registry.skus[sid]
            forecast = registry.forecasts.get(sid)
            daily_demand = forecast.effective_daily_demand() if forecast else 5.0
            per_hub_target = max(
                sku.safety_stock,
                math.ceil((daily_demand * target_cover_days) / max(len(wh_ids), 1)),
            )

            hub_stocks = resolved_matrix.get(sid, {})
            surpluses: list[tuple[str, int]] = []
            deficits: list[tuple[str, int]] = []

            for wh_id in wh_ids:
                qty = int(hub_stocks.get(wh_id, 0))
                delta = qty - per_hub_target
                if delta > 0:
                    status = "SURPLUS"
                    surpluses.append((wh_id, delta))
                    wh_totals[wh_id]["surplus_units"] += delta
                elif delta < 0:
                    status = "DEFICIT"
                    deficits.append((wh_id, -delta))
                    wh_totals[wh_id]["deficit_units"] += -delta
                else:
                    status = "BALANCED"

                wh_totals[wh_id]["total_sku_units"] += qty
                cells.append(
                    WarehouseSKUCell(
                        sku_id=sid,
                        sku_name=sku.name,
                        warehouse_id=wh_id,
                        current_qty=qty,
                        target_qty=per_hub_target,
                        delta=delta,
                        status=status,
                    )
                )

            # Greedy matching: largest surplus hub -> largest deficit hub
            surpluses.sort(key=lambda x: x[1], reverse=True)
            deficits.sort(key=lambda x: x[1], reverse=True)

            s_idx, d_idx = 0, 0
            surplus_rem = [x[1] for x in surpluses]
            deficit_rem = [x[1] for x in deficits]

            unit_margin = max(sku.effective_price() - sku.unit_cost, 1.0)
            while s_idx < len(surpluses) and d_idx < len(deficits):
                from_wh = surpluses[s_idx][0]
                to_wh = deficits[d_idx][0]
                avail = surplus_rem[s_idx]
                need = deficit_rem[d_idx]
                cap_ok = remaining_cap.get(to_wh, 0)
                move_qty = min(avail, need, cap_ok)

                if move_qty >= min_transfer_qty:
                    est_cost = round(move_qty * transfer_cost_per_unit, 2)
                    est_savings = round(move_qty * unit_margin * 0.45, 2)
                    net_ben = round(est_savings - est_cost, 2)
                    transfers.append(
                        TransferPlanItem(
                            transfer_id=f"TRF-{transfer_counter:03d}",
                            sku_id=sid,
                            sku_name=sku.name,
                            from_warehouse=from_wh,
                            to_warehouse=to_wh,
                            quantity=move_qty,
                            estimated_transfer_cost=est_cost,
                            estimated_stockout_savings=est_savings,
                            net_benefit=net_ben,
                            reason=(
                                f"Rebalance {move_qty} units of {sid} from surplus hub {from_wh} "
                                f"to cover deficit at {to_wh}"
                            ),
                        )
                    )
                    transfer_counter += 1
                    surplus_rem[s_idx] -= move_qty
                    deficit_rem[d_idx] -= move_qty
                    remaining_cap[to_wh] = max(0, remaining_cap[to_wh] - move_qty)
                else:
                    if cap_ok < min_transfer_qty or need < min_transfer_qty:
                        d_idx += 1
                    else:
                        s_idx += 1
                    continue

                if surplus_rem[s_idx] < min_transfer_qty:
                    s_idx += 1
                if deficit_rem[d_idx] < min_transfer_qty:
                    d_idx += 1

        summaries: list[WarehouseSummary] = []
        for wh_id in wh_ids:
            wh: Warehouse = registry.warehouses[wh_id]
            util_pct = round((wh.current_utilization_units / wh.capacity_units) * 100.0, 2)
            summaries.append(
                WarehouseSummary(
                    warehouse_id=wh.warehouse_id,
                    name=wh.name,
                    region=wh.region,
                    capacity_units=wh.capacity_units,
                    current_utilization_units=wh.current_utilization_units,
                    utilization_pct=util_pct,
                    total_sku_units=wh_totals[wh_id]["total_sku_units"],
                    surplus_units=wh_totals[wh_id]["surplus_units"],
                    deficit_units=wh_totals[wh_id]["deficit_units"],
                )
            )

        total_units = sum(t.quantity for t in transfers)
        total_cost = round(sum(t.estimated_transfer_cost for t in transfers), 2)
        total_savings = round(sum(t.estimated_stockout_savings for t in transfers), 2)
        total_net = round(total_savings - total_cost, 2)

        return RebalancePlanResult(
            transfers=transfers,
            total_transfers=len(transfers),
            total_units_rebalanced=total_units,
            total_transfer_cost=total_cost,
            total_stockout_savings=total_savings,
            total_net_benefit=total_net,
            warehouse_summary=summaries,
            matrix=cells,
        )
