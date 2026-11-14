"""IIoT Telemetry Ring Buffer (Z-Score Anomaly Detector) & LOTO Work-Order State Machine.

Provides deterministic, 100% offline streaming telemetry anomaly detection across
spindle temperature, vibration RMS, and hydraulic pressure, plus a strict
Lockout/Tagout (LOTO) maintenance work-order state machine:
OPEN -> ASSIGNED -> LOCKOUT_TAGOUT -> VERIFIED -> CLOSED.
"""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryMetricStats(BaseModel):
    metric: str
    latest_value: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    is_anomaly: bool
    sample_count: int
    history: list[float] = Field(default_factory=list)


class TelemetryAnomaly(BaseModel):
    equipment_id: str
    metric: str
    value: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    z_threshold: float
    timestamp: str


class TelemetryRingBuffer:
    """Sliding-window Z-score anomaly detector for industrial sensor streams."""

    def __init__(
        self,
        window_size: int = 30,
        z_threshold: float = 2.5,
        min_samples: int = 5,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        if z_threshold <= 0:
            raise ValueError("z_threshold must be > 0")
        if min_samples < 2:
            raise ValueError("min_samples must be >= 2")

        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        # (equipment_id, metric) -> deque[float]
        self._buffers: dict[tuple[str, str], deque[float]] = {}
        self._latest_stats: dict[tuple[str, str], TelemetryMetricStats] = {}
        self._anomalies: list[TelemetryAnomaly] = []

    def _compute_stats(self, values: deque[float]) -> tuple[float, float]:
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        return mean, math.sqrt(variance)

    def ingest_sample(
        self,
        equipment_id: str,
        readings: dict[str, float],
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        ts = timestamp or _utc_now_iso()
        metric_results: list[TelemetryMetricStats] = []
        sample_anomalies: list[TelemetryAnomaly] = []

        for metric, raw_val in sorted(readings.items()):
            value = float(raw_val)
            key = (equipment_id, metric)
            buf = self._buffers.get(key)
            if buf is None:
                buf = deque(maxlen=self.window_size)
                self._buffers[key] = buf

            prior_count = len(buf)
            if prior_count >= self.min_samples:
                mean, std = self._compute_stats(buf)
                effective_std = std if std > 1e-6 else max(abs(mean) * 0.01, 1e-3)
                z_score = (value - mean) / effective_std
                is_anomaly = abs(z_score) >= self.z_threshold
            elif prior_count > 0:
                mean, std = self._compute_stats(buf)
                z_score = 0.0
                is_anomaly = False
            else:
                mean, std = value, 0.0
                z_score = 0.0
                is_anomaly = False

            buf.append(value)
            new_mean, new_std = self._compute_stats(buf)

            stat = TelemetryMetricStats(
                metric=metric,
                latest_value=round(value, 4),
                rolling_mean=round(new_mean, 4),
                rolling_std=round(new_std, 4),
                z_score=round(z_score, 4),
                is_anomaly=is_anomaly,
                sample_count=len(buf),
                history=[round(v, 3) for v in buf],
            )
            self._latest_stats[key] = stat
            metric_results.append(stat)

            if is_anomaly:
                anomaly = TelemetryAnomaly(
                    equipment_id=equipment_id,
                    metric=metric,
                    value=round(value, 4),
                    rolling_mean=round(mean, 4),
                    rolling_std=round(std, 4),
                    z_score=round(z_score, 4),
                    z_threshold=self.z_threshold,
                    timestamp=ts,
                )
                sample_anomalies.append(anomaly)
                self._anomalies.append(anomaly)

        return {
            "equipment_id": equipment_id,
            "timestamp": ts,
            "metrics": [m.model_dump() for m in metric_results],
            "anomalies": [a.model_dump() for a in sample_anomalies],
            "anomaly_detected": len(sample_anomalies) > 0,
        }

    def ingest_batch(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        batch_anomalies: list[dict[str, Any]] = []

        for sample in samples:
            eq_id = str(sample["equipment_id"])
            readings = dict(sample.get("readings") or {})
            ts = sample.get("timestamp")
            res = self.ingest_sample(equipment_id=eq_id, readings=readings, timestamp=ts)
            results.append(res)
            batch_anomalies.extend(res["anomalies"])

        return {
            "ingested_count": len(results),
            "anomaly_count": len(batch_anomalies),
            "anomalies": batch_anomalies,
            "results": results,
            "equipment_snapshots": self.get_all_snapshots(),
        }

    def get_equipment_snapshot(self, equipment_id: str) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for (eq_id, metric), stat in sorted(self._latest_stats.items()):
            if eq_id == equipment_id:
                metrics[metric] = stat.model_dump()
        return metrics

    def get_all_snapshots(self) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}
        for (eq_id, metric), stat in sorted(self._latest_stats.items()):
            snapshots.setdefault(eq_id, {})[metric] = stat.model_dump()
        return snapshots

    def get_recent_anomalies(self, limit: int = 20) -> list[dict[str, Any]]:
        return [a.model_dump() for a in self._anomalies[-limit:]]


class WorkOrderStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    LOCKOUT_TAGOUT = "LOCKOUT_TAGOUT"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


ALLOWED_WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.OPEN: {WorkOrderStatus.ASSIGNED},
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.LOCKOUT_TAGOUT},
    WorkOrderStatus.LOCKOUT_TAGOUT: {WorkOrderStatus.VERIFIED},
    WorkOrderStatus.VERIFIED: {WorkOrderStatus.CLOSED},
    WorkOrderStatus.CLOSED: set(),
}


class WorkOrder(BaseModel):
    work_order_id: str = Field(default_factory=lambda: f"WO-{uuid4().hex[:6].upper()}")
    equipment_id: str
    title: str
    fault_code: str | None = None
    sop_id: str | None = None
    priority: str = "HIGH"
    status: WorkOrderStatus = WorkOrderStatus.OPEN
    assigned_to: str | None = None
    loto_tag_id: str | None = None
    verified_by: str | None = None
    notes: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    history: list[dict[str, Any]] = Field(default_factory=list)


class WorkOrderStateMachine:
    """Deterministic LOTO Maintenance Work-Order State Machine."""

    def __init__(self, seed_defaults: bool = True) -> None:
        self.work_orders: dict[str, WorkOrder] = {}
        if seed_defaults:
            self._seed_default_work_orders()

    def _seed_default_work_orders(self) -> None:
        now = _utc_now_iso()
        defaults = [
            WorkOrder(
                work_order_id="WO-LOTO-101",
                equipment_id="CNC-LINE1-01",
                title="Spindle Coolant Flow & Bearing Thermal Inspection",
                fault_code="ERR-CNC-401",
                sop_id="SOP-CNC-001",
                priority="CRITICAL",
                status=WorkOrderStatus.OPEN,
                notes="Triggered by thermal drift watch on Bay A Cell 01.",
                created_at=now,
                updated_at=now,
                history=[
                    {
                        "from_status": None,
                        "to_status": WorkOrderStatus.OPEN.value,
                        "actor": "scada-monitor",
                        "timestamp": now,
                        "notes": "Work order initialized.",
                    }
                ],
            ),
            WorkOrder(
                work_order_id="WO-LOTO-102",
                equipment_id="MOLD-LINE2-01",
                title="Hydraulic Proportional Relief Valve Calibration",
                fault_code="ERR-HYD-501",
                sop_id="SOP-HYD-003",
                priority="HIGH",
                status=WorkOrderStatus.ASSIGNED,
                assigned_to="tech-chen",
                notes="Assigned to hydraulic specialist for manifold bleed check.",
                created_at=now,
                updated_at=now,
                history=[
                    {
                        "from_status": None,
                        "to_status": WorkOrderStatus.OPEN.value,
                        "actor": "scada-monitor",
                        "timestamp": now,
                        "notes": "Work order initialized.",
                    },
                    {
                        "from_status": WorkOrderStatus.OPEN.value,
                        "to_status": WorkOrderStatus.ASSIGNED.value,
                        "actor": "shift-lead",
                        "timestamp": now,
                        "notes": "Dispatched to tech-chen.",
                    },
                ],
            ),
            WorkOrder(
                work_order_id="WO-LOTO-103",
                equipment_id="CNC-LINE1-01",
                title="Rotor Dynamic Trim Balancing & Drawbar Check",
                fault_code="ERR-VIB-301",
                sop_id="SOP-VIB-002",
                priority="CRITICAL",
                status=WorkOrderStatus.LOCKOUT_TAGOUT,
                assigned_to="tech-li",
                loto_tag_id="LOTO-BAYA-04",
                notes="480V main breaker locked and tagged out; awaiting FFT check.",
                created_at=now,
                updated_at=now,
                history=[
                    {
                        "from_status": None,
                        "to_status": WorkOrderStatus.OPEN.value,
                        "actor": "scada-monitor",
                        "timestamp": now,
                        "notes": "Work order initialized.",
                    },
                    {
                        "from_status": WorkOrderStatus.OPEN.value,
                        "to_status": WorkOrderStatus.ASSIGNED.value,
                        "actor": "shift-lead",
                        "timestamp": now,
                        "notes": "Dispatched to tech-li.",
                    },
                    {
                        "from_status": WorkOrderStatus.ASSIGNED.value,
                        "to_status": WorkOrderStatus.LOCKOUT_TAGOUT.value,
                        "actor": "tech-li",
                        "timestamp": now,
                        "notes": "Applied LOTO tag LOTO-BAYA-04.",
                    },
                ],
            ),
        ]
        for wo in defaults:
            self.work_orders[wo.work_order_id] = wo

    def create_work_order(
        self,
        equipment_id: str,
        title: str,
        fault_code: str | None = None,
        sop_id: str | None = None,
        priority: str = "HIGH",
        actor: str = "scada-monitor",
        notes: str = "",
    ) -> WorkOrder:
        now = _utc_now_iso()
        wo = WorkOrder(
            equipment_id=equipment_id,
            title=title,
            fault_code=fault_code,
            sop_id=sop_id,
            priority=priority,
            status=WorkOrderStatus.OPEN,
            notes=notes,
            created_at=now,
            updated_at=now,
            history=[
                {
                    "from_status": None,
                    "to_status": WorkOrderStatus.OPEN.value,
                    "actor": actor,
                    "timestamp": now,
                    "notes": notes or "Work order created.",
                }
            ],
        )
        self.work_orders[wo.work_order_id] = wo
        return wo

    def get_work_order(self, work_order_id: str) -> WorkOrder | None:
        return self.work_orders.get(work_order_id)

    def list_work_orders(self) -> list[WorkOrder]:
        return list(self.work_orders.values())

    def transition(
        self,
        work_order_id: str,
        target_status: WorkOrderStatus | str,
        actor: str = "scada-operator",
        assigned_to: str | None = None,
        loto_tag_id: str | None = None,
        notes: str = "",
    ) -> WorkOrder:
        wo = self.work_orders.get(work_order_id)
        if wo is None:
            raise KeyError(f"Unknown work_order_id: {work_order_id}")

        try:
            target = (
                target_status
                if isinstance(target_status, WorkOrderStatus)
                else WorkOrderStatus(str(target_status).upper())
            )
        except ValueError as exc:
            raise ValueError(f"Invalid work order status: {target_status}") from exc

        allowed = ALLOWED_WORK_ORDER_TRANSITIONS[wo.status]
        if target not in allowed:
            allowed_names = sorted(s.value for s in allowed)
            raise ValueError(
                f"Invalid transition {wo.status.value} -> {target.value} for {work_order_id}. "
                f"Allowed: {allowed_names}"
            )

        prev_status = wo.status
        now = _utc_now_iso()
        wo.status = target
        wo.updated_at = now

        if target == WorkOrderStatus.ASSIGNED:
            wo.assigned_to = assigned_to or wo.assigned_to or actor
        elif target == WorkOrderStatus.LOCKOUT_TAGOUT:
            wo.loto_tag_id = loto_tag_id or wo.loto_tag_id or f"LOTO-{wo.equipment_id}"
        elif target == WorkOrderStatus.VERIFIED:
            wo.verified_by = actor

        if notes:
            wo.notes = notes

        wo.history.append(
            {
                "from_status": prev_status.value,
                "to_status": target.value,
                "actor": actor,
                "timestamp": now,
                "notes": notes or f"Transitioned {prev_status.value} -> {target.value}",
            }
        )
        return wo
