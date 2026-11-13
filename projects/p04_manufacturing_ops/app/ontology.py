"""Manufacturing Ontology for Smart Manufacturing & Equipment Operations.

Defines core domain models (Equipment, SensorAlert, FaultCode, MaintenanceSOP,
OpsLink, OpsAction) and the ManufacturingOntologyRegistry for deterministic
telemetry threshold evaluation and fault-to-SOP resolution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EquipmentStatus(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    SHUTDOWN = "SHUTDOWN"
    MAINTENANCE = "MAINTENANCE"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
    CREATE_WORK_ORDER = "CREATE_WORK_ORDER"
    INSPECT_EQUIPMENT = "INSPECT_EQUIPMENT"
    RESET_ALARM = "RESET_ALARM"


class ActionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class TelemetryThreshold(BaseModel):
    metric: str
    warn: float
    critical: float
    unit: str = ""
    fault_code_on_critical: str | None = None
    fault_code_on_warn: str | None = None


class Equipment(BaseModel):
    equipment_id: str
    name: str
    equipment_type: str
    line_id: str
    location: str
    status: EquipmentStatus = EquipmentStatus.OPERATIONAL
    thresholds: dict[str, TelemetryThreshold] = Field(default_factory=dict)
    sop_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: f"ALT-{uuid4().hex[:8].upper()}")
    equipment_id: str
    sensor_type: str
    value: float
    unit: str = ""
    threshold: float
    severity: Severity
    fault_code: str | None = None
    message: str = ""
    timestamp: str = Field(default_factory=_utc_now_iso)


class FaultCode(BaseModel):
    code: str
    title: str
    equipment_type: str
    severity: Severity
    root_cause: str
    recommended_sop_id: str | None = None
    requires_shutdown: bool = False


class MaintenanceSOP(BaseModel):
    sop_id: str
    title: str
    revision: str
    latest_revision: str = "v2.0"
    steps: list[str] = Field(default_factory=list)
    safety_precautions: list[str] = Field(default_factory=list)
    estimated_minutes: int = 30
    target_fault_codes: list[str] = Field(default_factory=list)

    @property
    def is_outdated(self) -> bool:
        return self.revision != self.latest_revision


class OpsLink(BaseModel):
    link_id: str = Field(default_factory=lambda: f"LNK-{uuid4().hex[:8].upper()}")
    source_type: str
    source_id: str
    relation: str
    target_type: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"ACT-{uuid4().hex[:8].upper()}")
    action_type: ActionType
    equipment_id: str
    fault_code: str | None = None
    sop_id: str | None = None
    status: ActionStatus = ActionStatus.PENDING_APPROVAL
    requires_hitl: bool = False
    requested_by: str = "fde-pipeline"
    approved_by: str | None = None
    decision_reason: str | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
    decided_at: str | None = None


class DiagnosisResult(BaseModel):
    equipment_id: str
    equipment_name: str
    equipment_status: EquipmentStatus
    alerts: list[SensorAlert] = Field(default_factory=list)
    fault_codes: list[FaultCode] = Field(default_factory=list)
    sops: list[MaintenanceSOP] = Field(default_factory=list)
    links: list[OpsLink] = Field(default_factory=list)
    requires_shutdown: bool = False
    highest_severity: Severity = Severity.INFO


class ManufacturingOntologyRegistry:
    """In-memory deterministic registry for Manufacturing Ontology entities & rules."""

    def __init__(self, seed_defaults: bool = True) -> None:
        self.equipment: dict[str, Equipment] = {}
        self.fault_codes: dict[str, FaultCode] = {}
        self.sops: dict[str, MaintenanceSOP] = {}
        self.links: list[OpsLink] = []
        self.alerts: list[SensorAlert] = []

        if seed_defaults:
            self._seed_default_ontology()

    def _seed_default_ontology(self) -> None:
        # SOPs
        sop_cnc_spindle = MaintenanceSOP(
            sop_id="SOP-CNC-001",
            title="CNC Spindle Overheat & Bearing Inspection",
            revision="v2.0",
            latest_revision="v2.0",
            steps=[
                "Verify emergency stop readiness and isolate main spindle drive.",
                "Allow spindle housing to cool below 45 C before physical inspection.",
                "Inspect coolant flow rate and clear clogged nozzles.",
                "Measure spindle bearing axial play and replace if > 0.02 mm.",
                "Run 5-minute no-load warm-up test and verify temperature < 65 C.",
            ],
            safety_precautions=[
                "Lockout/Tagout (LOTO) main 480V breaker before opening spindle shroud.",
                "Wear heat-resistant gloves and safety goggles.",
            ],
            estimated_minutes=45,
            target_fault_codes=["ERR-CNC-401", "ERR-CNC-402"],
        )
        sop_vib_balance = MaintenanceSOP(
            sop_id="SOP-VIB-002",
            title="High-Frequency Vibration & Rotor Re-balancing",
            revision="v2.0",
            latest_revision="v2.0",
            steps=[
                "Capture FFT vibration spectrum at 1000 RPM and 3000 RPM.",
                "Inspect tool holder taper and drawbar clamping force.",
                "Check anchor bolts and leveling pads on machine base.",
                "Perform dynamic trim balancing and verify RMS velocity < 2.8 mm/s.",
            ],
            safety_precautions=[
                "Stand clear of rotating chuck during diagnostic spin test.",
            ],
            estimated_minutes=60,
            target_fault_codes=["ERR-VIB-301"],
        )
        sop_hyd_press = MaintenanceSOP(
            sop_id="SOP-HYD-003",
            title="Hydraulic Pressure Surge & Relief Valve Calibration",
            revision="v2.0",
            latest_revision="v2.0",
            steps=[
                "Depressurize hydraulic accumulator via manual bleed valve.",
                "Inspect proportional relief valve for spool sticking or debris.",
                "Verify pressure transducer calibration against reference gauge.",
                "Test cycle at 50% and 100% nominal pressure.",
            ],
            safety_precautions=[
                "Confirm zero residual bar pressure on manifold gauge before loosening fittings.",
            ],
            estimated_minutes=40,
            target_fault_codes=["ERR-HYD-501"],
        )

        for sop in (sop_cnc_spindle, sop_vib_balance, sop_hyd_press):
            self.register_sop(sop)

        # Fault Codes
        fc_spindle_temp = FaultCode(
            code="ERR-CNC-401",
            title="CNC Spindle Critical Overtemperature",
            equipment_type="CNC_MILL",
            severity=Severity.CRITICAL,
            root_cause="Coolant starvation or front angular-contact bearing seizure",
            recommended_sop_id="SOP-CNC-001",
            requires_shutdown=True,
        )
        fc_spindle_warn = FaultCode(
            code="ERR-CNC-402",
            title="CNC Spindle Elevated Temperature Warning",
            equipment_type="CNC_MILL",
            severity=Severity.WARNING,
            root_cause="Reduced coolant flow or high ambient shop temperature",
            recommended_sop_id="SOP-CNC-001",
            requires_shutdown=False,
        )
        fc_vib_high = FaultCode(
            code="ERR-VIB-301",
            title="Excessive Spindle/Axis Vibration",
            equipment_type="CNC_MILL",
            severity=Severity.CRITICAL,
            root_cause="Tool imbalance, loose chuck, or worn spindle bearing",
            recommended_sop_id="SOP-VIB-002",
            requires_shutdown=True,
        )
        fc_hyd_surge = FaultCode(
            code="ERR-HYD-501",
            title="Hydraulic Manifold Overpressure",
            equipment_type="INJECTION_MOLDER",
            severity=Severity.CRITICAL,
            root_cause="Stuck proportional relief valve or blocked return line",
            recommended_sop_id="SOP-HYD-003",
            requires_shutdown=True,
        )

        for fc in (fc_spindle_temp, fc_spindle_warn, fc_vib_high, fc_hyd_surge):
            self.register_fault_code(fc)

        # Equipment
        cnc_01 = Equipment(
            equipment_id="CNC-LINE1-01",
            name="5-Axis CNC Machining Center #1",
            equipment_type="CNC_MILL",
            line_id="LINE-1",
            location="Bay A / Cell 01",
            status=EquipmentStatus.OPERATIONAL,
            sop_ids=["SOP-CNC-001", "SOP-VIB-002"],
            thresholds={
                "temperature_c": TelemetryThreshold(
                    metric="temperature_c",
                    warn=75.0,
                    critical=90.0,
                    unit="C",
                    fault_code_on_warn="ERR-CNC-402",
                    fault_code_on_critical="ERR-CNC-401",
                ),
                "vibration_mms": TelemetryThreshold(
                    metric="vibration_mms",
                    warn=4.5,
                    critical=7.1,
                    unit="mm/s",
                    fault_code_on_critical="ERR-VIB-301",
                ),
            },
        )
        mold_01 = Equipment(
            equipment_id="MOLD-LINE2-01",
            name="Hydraulic Injection Molder #1",
            equipment_type="INJECTION_MOLDER",
            line_id="LINE-2",
            location="Bay B / Cell 03",
            status=EquipmentStatus.OPERATIONAL,
            sop_ids=["SOP-HYD-003"],
            thresholds={
                "pressure_bar": TelemetryThreshold(
                    metric="pressure_bar",
                    warn=180.0,
                    critical=210.0,
                    unit="bar",
                    fault_code_on_critical="ERR-HYD-501",
                ),
                "temperature_c": TelemetryThreshold(
                    metric="temperature_c",
                    warn=65.0,
                    critical=80.0,
                    unit="C",
                ),
            },
        )

        self.register_equipment(cnc_01)
        self.register_equipment(mold_01)

        # OpsLinks
        self.add_link(
            OpsLink(
                source_type="Equipment",
                source_id="CNC-LINE1-01",
                relation="MITIGATED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-CNC-001",
            )
        )
        self.add_link(
            OpsLink(
                source_type="Equipment",
                source_id="CNC-LINE1-01",
                relation="MITIGATED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-VIB-002",
            )
        )
        self.add_link(
            OpsLink(
                source_type="Equipment",
                source_id="MOLD-LINE2-01",
                relation="MITIGATED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-HYD-003",
            )
        )
        self.add_link(
            OpsLink(
                source_type="FaultCode",
                source_id="ERR-CNC-401",
                relation="RESOLVED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-CNC-001",
            )
        )
        self.add_link(
            OpsLink(
                source_type="FaultCode",
                source_id="ERR-VIB-301",
                relation="RESOLVED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-VIB-002",
            )
        )
        self.add_link(
            OpsLink(
                source_type="FaultCode",
                source_id="ERR-HYD-501",
                relation="RESOLVED_BY",
                target_type="MaintenanceSOP",
                target_id="SOP-HYD-003",
            )
        )

    def register_equipment(self, equipment: Equipment) -> None:
        self.equipment[equipment.equipment_id] = equipment

    def register_fault_code(self, fault_code: FaultCode) -> None:
        self.fault_codes[fault_code.code] = fault_code

    def register_sop(self, sop: MaintenanceSOP) -> None:
        self.sops[sop.sop_id] = sop

    def add_link(self, link: OpsLink) -> None:
        self.links.append(link)

    def get_equipment(self, equipment_id: str) -> Equipment | None:
        return self.equipment.get(equipment_id)

    def get_fault_code(self, code: str) -> FaultCode | None:
        return self.fault_codes.get(code)

    def get_sop(self, sop_id: str) -> MaintenanceSOP | None:
        return self.sops.get(sop_id)

    def check_telemetry(
        self, equipment_id: str, readings: dict[str, float]
    ) -> list[SensorAlert]:
        eq = self.equipment.get(equipment_id)
        if eq is None:
            raise KeyError(f"Unknown equipment_id: {equipment_id}")

        emitted: list[SensorAlert] = []
        for metric, value in sorted(readings.items()):
            threshold = eq.thresholds.get(metric)
            if threshold is None:
                continue

            if value >= threshold.critical:
                alert = SensorAlert(
                    equipment_id=equipment_id,
                    sensor_type=metric,
                    value=value,
                    unit=threshold.unit,
                    threshold=threshold.critical,
                    severity=Severity.CRITICAL,
                    fault_code=threshold.fault_code_on_critical,
                    message=(
                        f"{metric}={value}{threshold.unit} exceeded critical "
                        f"threshold {threshold.critical}{threshold.unit}"
                    ),
                )
                emitted.append(alert)
                self.alerts.append(alert)
            elif value >= threshold.warn:
                alert = SensorAlert(
                    equipment_id=equipment_id,
                    sensor_type=metric,
                    value=value,
                    unit=threshold.unit,
                    threshold=threshold.warn,
                    severity=Severity.WARNING,
                    fault_code=threshold.fault_code_on_warn,
                    message=(
                        f"{metric}={value}{threshold.unit} exceeded warning "
                        f"threshold {threshold.warn}{threshold.unit}"
                    ),
                )
                emitted.append(alert)
                self.alerts.append(alert)

        return emitted

    def resolve_fault_to_sop(self, fault_code: str) -> dict[str, Any]:
        fc = self.fault_codes.get(fault_code)
        if fc is None:
            return {
                "fault_code": fault_code,
                "found": False,
                "fault": None,
                "sop": None,
                "requires_shutdown": False,
            }

        sop = self.sops.get(fc.recommended_sop_id) if fc.recommended_sop_id else None
        return {
            "fault_code": fault_code,
            "found": True,
            "fault": fc,
            "sop": sop,
            "requires_shutdown": fc.requires_shutdown,
        }

    def diagnose(
        self,
        equipment_id: str,
        readings: dict[str, float] | None = None,
        fault_code: str | None = None,
    ) -> DiagnosisResult:
        eq = self.equipment.get(equipment_id)
        if eq is None:
            raise KeyError(f"Unknown equipment_id: {equipment_id}")

        alerts = self.check_telemetry(equipment_id, readings or {})
        detected_codes: list[str] = []
        for alert in alerts:
            if alert.fault_code and alert.fault_code not in detected_codes:
                detected_codes.append(alert.fault_code)
        if fault_code and fault_code not in detected_codes:
            detected_codes.append(fault_code)

        faults: list[FaultCode] = []
        sops: list[MaintenanceSOP] = []
        seen_sops: set[str] = set()
        requires_shutdown = False

        for code in detected_codes:
            resolved = self.resolve_fault_to_sop(code)
            if resolved["found"] and resolved["fault"] is not None:
                fc: FaultCode = resolved["fault"]
                faults.append(fc)
                if fc.requires_shutdown:
                    requires_shutdown = True
                sop: MaintenanceSOP | None = resolved["sop"]
                if sop is not None and sop.sop_id not in seen_sops:
                    sops.append(sop)
                    seen_sops.add(sop.sop_id)

        severity_order = {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }
        highest = Severity.INFO
        for alert in alerts:
            if severity_order[alert.severity] > severity_order[highest]:
                highest = alert.severity
        for fc in faults:
            if severity_order[fc.severity] > severity_order[highest]:
                highest = fc.severity

        if highest == Severity.CRITICAL:
            eq.status = EquipmentStatus.FAULTED
        elif highest in (Severity.WARNING, Severity.HIGH) and eq.status == EquipmentStatus.OPERATIONAL:
            eq.status = EquipmentStatus.DEGRADED

        related_links = [
            lnk
            for lnk in self.links
            if lnk.source_id == equipment_id or lnk.source_id in detected_codes
        ]

        return DiagnosisResult(
            equipment_id=eq.equipment_id,
            equipment_name=eq.name,
            equipment_status=eq.status,
            alerts=alerts,
            fault_codes=faults,
            sops=sops,
            links=related_links,
            requires_shutdown=requires_shutdown,
            highest_severity=highest,
        )
