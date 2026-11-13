"""Retail & Supply Chain Ontology models and registry."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SKUStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LOW_STOCK = "LOW_STOCK"
    STOCKOUT = "STOCKOUT"
    DISCONTINUED = "DISCONTINUED"


class ActionType(str, Enum):
    TRIGGER_REPLENISHMENT = "TRIGGER_REPLENISHMENT"
    ADJUST_DYNAMIC_PRICE = "ADJUST_DYNAMIC_PRICE"
    REBALANCE_WAREHOUSE = "REBALANCE_WAREHOUSE"


class ActionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"


class SKU(BaseModel):
    sku_id: str
    name: str
    category: str
    unit_cost: float = Field(gt=0)
    list_price: float = Field(gt=0)
    current_stock: int = Field(ge=0)
    safety_stock: int = Field(ge=0)
    reorder_point: int = Field(ge=0)
    warehouse_id: str
    supplier_id: str
    min_margin_pct: float = Field(default=0.15, ge=0.0, le=0.95)
    promo_discount_pct: float = Field(default=0.0, ge=0.0, le=0.95)
    status: SKUStatus = SKUStatus.ACTIVE

    def effective_price(self) -> float:
        return round(self.list_price * (1.0 - self.promo_discount_pct), 2)

    def gross_margin_pct(self, price_override: float | None = None) -> float:
        price = price_override if price_override is not None else self.effective_price()
        if price <= 0:
            return -1.0
        return round((price - self.unit_cost) / price, 4)

    def is_below_safety_stock(self) -> bool:
        return self.current_stock <= self.safety_stock

    def is_below_reorder_point(self) -> bool:
        return self.current_stock <= self.reorder_point


class Warehouse(BaseModel):
    warehouse_id: str
    name: str
    region: str
    capacity_units: int = Field(gt=0)
    current_utilization_units: int = Field(default=0, ge=0)
    is_cold_chain: bool = False


class Supplier(BaseModel):
    supplier_id: str
    name: str
    lead_time_days: int = Field(ge=1)
    moq: int = Field(default=50, ge=1)
    reliability_score: float = Field(default=0.95, ge=0.0, le=1.0)
    on_time_rate: float = Field(default=0.96, ge=0.0, le=1.0)


class DemandForecast(BaseModel):
    forecast_id: str
    sku_id: str
    horizon_days: int = Field(default=14, ge=1)
    daily_demand_avg: float = Field(ge=0.0)
    demand_std_dev: float = Field(default=0.0, ge=0.0)
    seasonality_factor: float = Field(default=1.0, gt=0.0)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)

    def effective_daily_demand(self) -> float:
        return round(self.daily_demand_avg * self.seasonality_factor, 2)

    def projected_demand(self) -> float:
        return round(self.effective_daily_demand() * self.horizon_days, 2)


class SupplyLink(BaseModel):
    source_id: str
    target_id: str
    relation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupplyAction(BaseModel):
    action_id: str
    action_type: ActionType
    sku_id: str
    quantity: int = Field(default=0, ge=0)
    proposed_price: float | None = None
    estimated_cost: float = Field(default=0.0, ge=0.0)
    requires_hitl: bool = False
    status: ActionStatus = ActionStatus.PENDING_APPROVAL
    reason: str = ""
    approved_by: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SafetyStockCheckResult(BaseModel):
    sku_id: str
    sku_name: str
    warehouse_id: str
    supplier_id: str
    current_stock: int
    safety_stock: int
    reorder_point: int
    days_of_supply: float
    lead_time_days: int
    lead_time_breach: bool
    below_safety_stock: bool
    risk_level: str
    recommended_order_qty: int
    message: str


class RetailOntologyRegistry:
    """In-memory strongly-typed Retail & Supply Chain Ontology registry."""

    def __init__(self) -> None:
        self.skus: dict[str, SKU] = {}
        self.warehouses: dict[str, Warehouse] = {}
        self.suppliers: dict[str, Supplier] = {}
        self.forecasts: dict[str, DemandForecast] = {}
        self.links: list[SupplyLink] = []
        self.actions: dict[str, SupplyAction] = {}

    def register_warehouse(self, warehouse: Warehouse) -> Warehouse:
        self.warehouses[warehouse.warehouse_id] = warehouse
        return warehouse

    def register_supplier(self, supplier: Supplier) -> Supplier:
        self.suppliers[supplier.supplier_id] = supplier
        return supplier

    def register_sku(self, sku: SKU) -> SKU:
        self.skus[sku.sku_id] = sku
        self.add_link(
            SupplyLink(
                source_id=sku.sku_id,
                target_id=sku.warehouse_id,
                relation="STORED_AT",
            )
        )
        self.add_link(
            SupplyLink(
                source_id=sku.sku_id,
                target_id=sku.supplier_id,
                relation="SUPPLIED_BY",
            )
        )
        return sku

    def register_forecast(self, forecast: DemandForecast) -> DemandForecast:
        self.forecasts[forecast.sku_id] = forecast
        self.add_link(
            SupplyLink(
                source_id=forecast.forecast_id,
                target_id=forecast.sku_id,
                relation="FORECASTED_FOR",
            )
        )
        return forecast

    def add_link(self, link: SupplyLink) -> SupplyLink:
        for existing in self.links:
            if (
                existing.source_id == link.source_id
                and existing.target_id == link.target_id
                and existing.relation == link.relation
            ):
                return existing
        self.links.append(link)
        return link

    def record_action(self, action: SupplyAction) -> SupplyAction:
        self.actions[action.action_id] = action
        self.add_link(
            SupplyLink(
                source_id=action.action_id,
                target_id=action.sku_id,
                relation="TARGETS_SKU",
                metadata={"action_type": action.action_type.value},
            )
        )
        return action

    def get_neighbors(self, entity_id: str) -> list[SupplyLink]:
        return [
            link
            for link in self.links
            if link.source_id == entity_id or link.target_id == entity_id
        ]

    def check_safety_stock(self, sku_id: str) -> SafetyStockCheckResult:
        if sku_id not in self.skus:
            raise KeyError(f"Unknown SKU: {sku_id}")

        sku = self.skus[sku_id]
        supplier = self.suppliers.get(sku.supplier_id)
        lead_time_days = supplier.lead_time_days if supplier else 7
        moq = supplier.moq if supplier else 50

        forecast = self.forecasts.get(sku_id)
        daily_demand = forecast.effective_daily_demand() if forecast else 5.0
        effective_rate = max(daily_demand, 0.1)
        days_of_supply = round(sku.current_stock / effective_rate, 2)

        below_safety = sku.is_below_safety_stock()
        lead_time_breach = days_of_supply < float(lead_time_days)

        if sku.current_stock == 0 or (below_safety and lead_time_breach):
            risk_level = "CRITICAL"
        elif below_safety or lead_time_breach or sku.is_below_reorder_point():
            risk_level = "WARNING"
        else:
            risk_level = "HEALTHY"

        target_cover_days = lead_time_days + 7
        target_stock = int(round(effective_rate * target_cover_days)) + sku.safety_stock
        deficit = max(0, target_stock - sku.current_stock)
        if risk_level in {"CRITICAL", "WARNING"}:
            recommended_qty = max(moq, deficit) if deficit > 0 else moq
        else:
            recommended_qty = 0

        reasons: list[str] = []
        if below_safety:
            reasons.append(
                f"stock {sku.current_stock} <= safety_stock {sku.safety_stock}"
            )
        if lead_time_breach:
            reasons.append(
                f"days_of_supply {days_of_supply}d < lead_time {lead_time_days}d"
            )
        if not reasons:
            reasons.append("inventory within healthy thresholds")

        return SafetyStockCheckResult(
            sku_id=sku.sku_id,
            sku_name=sku.name,
            warehouse_id=sku.warehouse_id,
            supplier_id=sku.supplier_id,
            current_stock=sku.current_stock,
            safety_stock=sku.safety_stock,
            reorder_point=sku.reorder_point,
            days_of_supply=days_of_supply,
            lead_time_days=lead_time_days,
            lead_time_breach=lead_time_breach,
            below_safety_stock=below_safety,
            risk_level=risk_level,
            recommended_order_qty=recommended_qty,
            message="; ".join(reasons),
        )

    def check_all_inventory(self) -> list[SafetyStockCheckResult]:
        return [self.check_safety_stock(sku_id) for sku_id in sorted(self.skus)]

    def seed_demo_data(self) -> None:
        self.register_warehouse(
            Warehouse(
                warehouse_id="WH-EAST",
                name="East Coast Fulfillment Hub",
                region="US-EAST",
                capacity_units=50000,
                current_utilization_units=31200,
            )
        )
        self.register_warehouse(
            Warehouse(
                warehouse_id="WH-WEST",
                name="West Coast Cold & Dry Hub",
                region="US-WEST",
                capacity_units=35000,
                current_utilization_units=18400,
                is_cold_chain=True,
            )
        )
        self.register_supplier(
            Supplier(
                supplier_id="SUP-01",
                name="Shenzhen Smart Appliances Co.",
                lead_time_days=10,
                moq=50,
                reliability_score=0.94,
                on_time_rate=0.92,
            )
        )
        self.register_supplier(
            Supplier(
                supplier_id="SUP-02",
                name="Kyoto Botanicals Direct",
                lead_time_days=5,
                moq=40,
                reliability_score=0.98,
                on_time_rate=0.97,
            )
        )
        self.register_sku(
            SKU(
                sku_id="SKU-1001",
                name="Smart Espresso Maker Pro",
                category="Home Appliances",
                unit_cost=120.0,
                list_price=249.0,
                current_stock=35,
                safety_stock=60,
                reorder_point=90,
                warehouse_id="WH-EAST",
                supplier_id="SUP-01",
                min_margin_pct=0.20,
                status=SKUStatus.LOW_STOCK,
            )
        )
        self.register_sku(
            SKU(
                sku_id="SKU-1002",
                name="Ceremonial Matcha Tin 100g",
                category="Grocery",
                unit_cost=14.0,
                list_price=36.0,
                current_stock=220,
                safety_stock=80,
                reorder_point=120,
                warehouse_id="WH-WEST",
                supplier_id="SUP-02",
                min_margin_pct=0.25,
                status=SKUStatus.ACTIVE,
            )
        )
        self.register_sku(
            SKU(
                sku_id="SKU-1003",
                name="ANC Wireless Earbuds X2",
                category="Consumer Electronics",
                unit_cost=45.0,
                list_price=99.0,
                current_stock=70,
                safety_stock=75,
                reorder_point=110,
                warehouse_id="WH-EAST",
                supplier_id="SUP-01",
                min_margin_pct=0.18,
                status=SKUStatus.LOW_STOCK,
            )
        )
        self.register_forecast(
            DemandForecast(
                forecast_id="FC-1001",
                sku_id="SKU-1001",
                horizon_days=14,
                daily_demand_avg=12.0,
                demand_std_dev=2.5,
                seasonality_factor=1.25,
                confidence=0.91,
            )
        )
        self.register_forecast(
            DemandForecast(
                forecast_id="FC-1002",
                sku_id="SKU-1002",
                horizon_days=14,
                daily_demand_avg=15.0,
                demand_std_dev=3.0,
                seasonality_factor=1.0,
                confidence=0.94,
            )
        )
        self.register_forecast(
            DemandForecast(
                forecast_id="FC-1003",
                sku_id="SKU-1003",
                horizon_days=14,
                daily_demand_avg=10.0,
                demand_std_dev=2.0,
                seasonality_factor=1.1,
                confidence=0.89,
            )
        )
