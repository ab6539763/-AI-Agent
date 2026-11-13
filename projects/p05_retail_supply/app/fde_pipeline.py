"""Retail FDE Pipeline: demand anomaly detection, Wiki+Ontology reasoning, margin guardrail, HITL & audit."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .llm_wiki import RetailLLMWiki
from .ontology import (
    ActionStatus,
    ActionType,
    RetailOntologyRegistry,
    SKU,
    SKUStatus,
    SupplyAction,
)


class RetailFDEPipeline:
    """Forward Deployed Engineering pipeline for retail replenishment and dynamic pricing."""

    def __init__(
        self,
        ontology: RetailOntologyRegistry,
        wiki: RetailLLMWiki,
        bulk_po_threshold_qty: int = 200,
        bulk_po_threshold_cost: float = 5000.0,
        max_price_change_pct: float = 0.15,
    ) -> None:
        self.ontology = ontology
        self.wiki = wiki
        self.bulk_po_threshold_qty = bulk_po_threshold_qty
        self.bulk_po_threshold_cost = bulk_po_threshold_cost
        self.max_price_change_pct = max_price_change_pct
        self.audit_trail: list[dict[str, Any]] = []

    def _record_audit(
        self,
        event: str,
        sku_id: str,
        actor: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        entry = {
            "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "sku_id": sku_id,
            "actor": actor,
            "details": details,
        }
        self.audit_trail.append(entry)
        return entry

    def seed_wiki_from_ontology(self) -> None:
        for wh in self.ontology.warehouses.values():
            self.wiki.ingest(
                doc_id=f"SEED-{wh.warehouse_id}",
                title=wh.name,
                content=(
                    f"Warehouse [[{wh.warehouse_id}]] in region {wh.region}, "
                    f"capacity {wh.capacity_units}, cold_chain={wh.is_cold_chain}."
                ),
                entity_id=wh.warehouse_id,
                entity_type="Warehouse",
                metadata={"region": wh.region, "capacity_units": wh.capacity_units},
            )
        for sup in self.ontology.suppliers.values():
            self.wiki.ingest(
                doc_id=f"SEED-{sup.supplier_id}",
                title=sup.name,
                content=(
                    f"Supplier [[{sup.supplier_id}]] with lead_time={sup.lead_time_days}d, "
                    f"MOQ={sup.moq}, reliability={sup.reliability_score}."
                ),
                entity_id=sup.supplier_id,
                entity_type="Supplier",
                metadata={"lead_time_days": sup.lead_time_days, "moq": sup.moq},
            )
        for sku in self.ontology.skus.values():
            self.wiki.ingest(
                doc_id=f"SEED-{sku.sku_id}",
                title=sku.name,
                content=(
                    f"SKU [[{sku.sku_id}]] stored at [[{sku.warehouse_id}]], "
                    f"supplied by [[{sku.supplier_id}]]. "
                    f"Current stock={sku.current_stock}, safety_stock={sku.safety_stock}, "
                    f"min_margin={sku.min_margin_pct:.0%}."
                ),
                entity_id=sku.sku_id,
                entity_type="SKU",
                links=[sku.warehouse_id, sku.supplier_id],
                metadata={
                    "category": sku.category,
                    "unit_cost": sku.unit_cost,
                    "list_price": sku.list_price,
                },
            )

    def analyze_demand_and_anomalies(self, sku_id: str) -> dict[str, Any]:
        safety_check = self.ontology.check_safety_stock(sku_id)
        forecast = self.ontology.forecasts.get(sku_id)
        wiki_ctx = self.wiki.query(sku_id, top_k=3)

        anomalies: list[str] = []
        if safety_check.below_safety_stock:
            anomalies.append("BELOW_SAFETY_STOCK")
        if safety_check.lead_time_breach:
            anomalies.append("SUPPLIER_LEAD_TIME_BREACH")
        if forecast and forecast.seasonality_factor >= 1.2:
            anomalies.append("SEASONAL_DEMAND_SPIKE")

        return {
            "sku_id": sku_id,
            "safety_check": safety_check.model_dump(),
            "forecast": forecast.model_dump() if forecast else None,
            "anomalies": anomalies,
            "wiki_context": wiki_ctx,
        }

    def evaluate_margin_guardrail(
        self, sku: SKU, proposed_price: float | None = None
    ) -> dict[str, Any]:
        margin = sku.gross_margin_pct(price_override=proposed_price)
        passed = margin >= sku.min_margin_pct
        target_price = proposed_price if proposed_price is not None else sku.effective_price()
        reason = (
            f"Margin {margin:.2%} meets floor {sku.min_margin_pct:.2%} at price ${target_price:.2f}"
            if passed
            else f"Margin {margin:.2%} violates floor {sku.min_margin_pct:.2%} at price ${target_price:.2f}"
        )
        return {
            "passed": passed,
            "gross_margin_pct": margin,
            "min_margin_pct": sku.min_margin_pct,
            "evaluated_price": target_price,
            "reason": reason,
        }

    def plan_replenishment(
        self,
        sku_id: str,
        requested_qty: int | None = None,
        proposed_price: float | None = None,
        actor: str = "fde-agent",
    ) -> dict[str, Any]:
        if sku_id not in self.ontology.skus:
            raise KeyError(f"Unknown SKU: {sku_id}")

        sku = self.ontology.skus[sku_id]
        analysis = self.analyze_demand_and_anomalies(sku_id)
        safety_check = analysis["safety_check"]

        # Margin guardrail check
        margin_eval = self.evaluate_margin_guardrail(sku, proposed_price=proposed_price)
        if not margin_eval["passed"]:
            action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
            blocked_action = SupplyAction(
                action_id=action_id,
                action_type=ActionType.ADJUST_DYNAMIC_PRICE,
                sku_id=sku_id,
                quantity=0,
                proposed_price=proposed_price,
                estimated_cost=0.0,
                requires_hitl=False,
                status=ActionStatus.BLOCKED,
                reason=margin_eval["reason"],
            )
            self.ontology.record_action(blocked_action)
            audit = self._record_audit(
                "MARGIN_GUARDRAIL_BLOCKED",
                sku_id,
                actor,
                {"action_id": action_id, "margin_eval": margin_eval},
            )
            self.wiki.append_log(
                "GUARDRAIL_BLOCK",
                f"[[{sku_id}]] action={action_id} blocked: {margin_eval['reason']}",
            )
            return {
                "action": blocked_action.model_dump(),
                "analysis": analysis,
                "margin_guardrail": margin_eval,
                "audit": audit,
            }

        order_qty = (
            requested_qty
            if requested_qty is not None
            else safety_check["recommended_order_qty"]
        )
        supplier = self.ontology.suppliers.get(sku.supplier_id)
        if order_qty > 0 and supplier and order_qty < supplier.moq:
            order_qty = supplier.moq

        estimated_cost = round(order_qty * sku.unit_cost, 2)
        action_type = (
            ActionType.ADJUST_DYNAMIC_PRICE
            if proposed_price is not None and order_qty == 0
            else ActionType.TRIGGER_REPLENISHMENT
        )

        # HITL gate for bulk PO or large price change
        hitl_reasons: list[str] = []
        if order_qty >= self.bulk_po_threshold_qty:
            hitl_reasons.append(
                f"bulk PO qty {order_qty} >= {self.bulk_po_threshold_qty}"
            )
        if estimated_cost >= self.bulk_po_threshold_cost:
            hitl_reasons.append(
                f"PO cost ${estimated_cost:.2f} >= ${self.bulk_po_threshold_cost:.2f}"
            )
        if proposed_price is not None:
            price_delta_pct = abs(proposed_price - sku.list_price) / sku.list_price
            if price_delta_pct > self.max_price_change_pct:
                hitl_reasons.append(
                    f"price change {price_delta_pct:.1%} > {self.max_price_change_pct:.1%}"
                )

        requires_hitl = len(hitl_reasons) > 0
        status = (
            ActionStatus.PENDING_APPROVAL if requires_hitl else ActionStatus.EXECUTED
        )
        reason_parts = [safety_check["message"]]
        if hitl_reasons:
            reason_parts.append("HITL required: " + "; ".join(hitl_reasons))

        action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
        action = SupplyAction(
            action_id=action_id,
            action_type=action_type,
            sku_id=sku_id,
            quantity=order_qty,
            proposed_price=proposed_price,
            estimated_cost=estimated_cost,
            requires_hitl=requires_hitl,
            status=status,
            reason=" | ".join(reason_parts),
            approved_by=None if requires_hitl else "auto-policy",
        )
        self.ontology.record_action(action)

        if not requires_hitl:
            self._apply_action_effects(sku, action)

        audit = self._record_audit(
            "REPLENISHMENT_PLANNED",
            sku_id,
            actor,
            {
                "action_id": action_id,
                "status": status.value,
                "requires_hitl": requires_hitl,
                "quantity": order_qty,
                "estimated_cost": estimated_cost,
                "proposed_price": proposed_price,
            },
        )
        self.wiki.append_log(
            "ACTION",
            f"[[{sku_id}]] {action_id} status={status.value} qty={order_qty} cost=${estimated_cost:.2f}",
        )
        return {
            "action": action.model_dump(),
            "analysis": analysis,
            "margin_guardrail": margin_eval,
            "audit": audit,
        }

    def _apply_action_effects(self, sku: SKU, action: SupplyAction) -> None:
        if action.quantity > 0:
            sku.current_stock += action.quantity
            if sku.current_stock > sku.safety_stock:
                sku.status = SKUStatus.ACTIVE
        if action.proposed_price is not None:
            sku.list_price = action.proposed_price

    def approve_action(
        self,
        action_id: str,
        approved: bool,
        approver: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if action_id not in self.ontology.actions:
            raise KeyError(f"Unknown action: {action_id}")

        action = self.ontology.actions[action_id]
        if action.status != ActionStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Action {action_id} is in status {action.status.value}, not PENDING_APPROVAL"
            )

        sku = self.ontology.skus[action.sku_id]
        if approved:
            action.status = ActionStatus.EXECUTED
            action.approved_by = approver
            self._apply_action_effects(sku, action)
        else:
            action.status = ActionStatus.REJECTED
            action.approved_by = approver

        audit = self._record_audit(
            "HITL_DECISION",
            action.sku_id,
            approver,
            {
                "action_id": action_id,
                "approved": approved,
                "new_status": action.status.value,
                "comment": comment,
            },
        )
        self.wiki.append_log(
            "HITL",
            f"[[{action.sku_id}]] {action_id} -> {action.status.value} by {approver}",
        )
        return {
            "action": action.model_dump(),
            "sku_stock_after": sku.current_stock,
            "sku_price_after": sku.list_price,
            "audit": audit,
        }
