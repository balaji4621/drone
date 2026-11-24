"""
NESFIC-I-07: Smart Dock Engine
- Deterministic FSM for Dock operations
- Chemical mixing mathematics with TRA-approved actives
- EU & Japan MRL compliance verification
- Tamper-evident audit logging (JSON + CSV)
"""
from __future__ import annotations

import csv
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from config import (
    TRA_CHEMICALS,
    CARRIER_SPECS,
    MRL_RULEBOOK,
    MRLRulebook,
    ChemicalSpec,
    DockState,
    GEOMETRY,
)
from pest_detector import InfestationHotspot, get_pest_service


# =============================================================================
# Data Structures
# =============================================================================
@dataclass
class TankMix:
    """Represents a formulated tank mix ready for loading onto Sprayer."""
    batch_id: str
    chemicals: dict[str, float]  # chemical_key -> volume_ml
    carrier_water_ml: float
    surfactant_ml: float
    total_volume_ml: float
    target_hotspots: list[str]  # hotspot IDs
    mixed_at: float = field(default_factory=time.time)
    phi_compliant_eu: bool = False
    phi_compliant_japan: bool = False
    mrl_verified: bool = False
    days_to_harvest: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DockAuditRecord:
    """Immutable audit record for section-wise compliance."""
    record_id: str
    section_id: str
    timestamp: str  # ISO 8601
    dock_state: str
    survey_data: dict
    hotspots: list[dict]
    tank_mix: Optional[dict]
    mrl_verification: dict
    compliance_status: str  # COMPLIANT | NON_COMPLIANT | PENDING
    operator_id: str = "AUTO"
    signature: str = ""  # Hash for tamper evidence

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_csv_row(self) -> list[str]:
        return [
            self.record_id,
            self.section_id,
            self.timestamp,
            self.dock_state,
            json.dumps(self.survey_data),
            json.dumps(self.hotspots),
            json.dumps(self.tank_mix) if self.tank_mix else "",
            json.dumps(self.mrl_verification),
            self.compliance_status,
            self.operator_id,
            self.signature,
        ]


# =============================================================================
# Chemical Mixing Engine
# =============================================================================
class ChemicalMixer:
    """
    Computes precise tank mix formulation from hotspots.
    Enforces TRA label limits, compatibility, and carrier constraints.
    """

    MAX_TANK_VOLUME_ML = CARRIER_SPECS["water_l_per_tank"] * 1000  # 10,000 ml
    SURFACTANT_PCT_MIN = CARRIER_SPECS["surfactant_pct_vv_min"]
    SURFACTANT_PCT_MAX = CARRIER_SPECS["surfactant_pct_vv_max"]

    def __init__(self, days_to_harvest: int = 0):
        self.days_to_harvest = days_to_harvest

    def formulate(self, hotspots: list[InfestationHotspot]) -> TankMix:
        """
        Create tank mix from hotspot recommendations.
        Aggregates chemical needs, checks compatibility, computes carrier volumes.
        """
        if not hotspots:
            raise ValueError("No hotspots provided for formulation")

        # Aggregate chemical requirements
        chem_volumes: dict[str, float] = {}  # chemical_key -> total_ml
        target_hotspot_ids = [hs.id for hs in hotspots]

        for hs in hotspots:
            chem_key = hs.recommended_chemical
            # Volume needed = application_rate_ml_per_l * (hotspot_area / 10000) * spray_coverage_factor
            # Simplified: each hotspot gets 1L equivalent spray volume
            vol_ml = hs.application_rate_ml_per_l * 1.0  # 1L per hotspot
            chem_volumes[chem_key] = chem_volumes.get(chem_key, 0.0) + vol_ml

        # Verify label limits
        for chem_key, vol_ml in chem_volumes.items():
            spec = TRA_CHEMICALS[chem_key]
            max_allowed_ml = spec.max_concentration_g_per_l * (self.MAX_TANK_VOLUME_ML / 1000.0)
            if vol_ml > max_allowed_ml:
                raise ValueError(
                    f"Chemical {spec.name} exceeds label max: {vol_ml:.1f}ml > {max_allowed_ml:.1f}ml"
                )

        # Verify tank-mix compatibility
        chemical_specs = [TRA_CHEMICALS[k] for k in chem_volumes.keys()]
        compatible, violations = MRL_RULEBOOK.validate_tank_mix(chemical_specs)
        if not compatible:
            raise ValueError(f"Tank-mix incompatibility: {'; '.join(violations)}")

        # Compute carrier volumes
        total_chem_ml = sum(chem_volumes.values())
        carrier_water_ml = self.MAX_TANK_VOLUME_ML - total_chem_ml

        # Surfactant: max of required percentages across chemicals
        max_surfactant_pct = max(
            TRA_CHEMICALS[k].surfactant_required_pct_vv for k in chem_volumes.keys()
        )
        surfactant_ml = carrier_water_ml * max_surfactant_pct
        carrier_water_ml -= surfactant_ml

        # Final volume check
        final_volume = total_chem_ml + carrier_water_ml + surfactant_ml
        if final_volume > self.MAX_TANK_VOLUME_ML * 1.01:  # 1% tolerance
            raise ValueError(f"Formulation exceeds tank capacity: {final_volume:.0f}ml > {self.MAX_TANK_VOLUME_ML}ml")

        batch_id = f"MIX-{uuid.uuid4().hex[:8].upper()}"

        return TankMix(
            batch_id=batch_id,
            chemicals=chem_volumes,
            carrier_water_ml=carrier_water_ml,
            surfactant_ml=surfactant_ml,
            total_volume_ml=final_volume,
            target_hotspots=target_hotspot_ids,
            days_to_harvest=self.days_to_harvest,
        )

    def verify_mrl(self, tank_mix: TankMix) -> tuple[bool, dict]:
        """
        Runs MRL compliance check for EU & Japan.
        Returns (compliant, verification_details).
        """
        chemical_specs = [TRA_CHEMICALS[k] for k in tank_mix.chemicals.keys()]

        # PHI check
        phi_eu_ok = all(self.days_to_harvest >= spec.phi_days_eu for spec in chemical_specs)
        phi_japan_ok = all(self.days_to_harvest >= spec.phi_days_japan for spec in chemical_specs)

        # MRL check (simplified - real implementation needs dissipation modeling)
        mrl_details = {}
        for spec in chemical_specs:
            mrl_details[spec.active_ingredient] = {
                "eu_mrl_mg_per_kg": spec.mrl_eu_mg_per_kg,
                "japan_mrl_mg_per_kg": spec.mrl_japan_mg_per_kg,
                "phi_eu_days": spec.phi_days_eu,
                "phi_japan_days": spec.phi_days_japan,
                "days_to_harvest": self.days_to_harvest,
                "phi_eu_ok": self.days_to_harvest >= spec.phi_days_eu,
                "phi_japan_ok": self.days_to_harvest >= spec.phi_days_japan,
            }

        compliant = phi_eu_ok and phi_japan_ok

        verification = {
            "phi_compliant_eu": phi_eu_ok,
            "phi_compliant_japan": phi_japan_ok,
            "mrl_details": mrl_details,
            "overall_compliant": compliant,
            "checked_at": time.time(),
        }

        return compliant, verification


# =============================================================================
# Line Flush System
# =============================================================================
class LineFlush:
    """
    Simulates inter-batch line flush procedure.
    In real hardware: pumps carrier fluid through lines, verifies clear.
    """

    FLUSH_VOLUME_ML = 500.0  # ml of carrier to flush
    FLUSH_DURATION_S = 30.0  # seconds

    def __init__(self):
        self.last_flush_at: Optional[float] = None
        self.last_flush_batch: Optional[str] = None

    def execute(self, next_batch_id: str) -> dict:
        """Execute flush sequence. Returns flush record."""
        start = time.time()
        # Simulate flush
        time.sleep(0.01)  # Minimal delay for simulation

        record = {
            "flush_id": f"FLUSH-{uuid.uuid4().hex[:8].upper()}",
            "previous_batch": self.last_flush_batch,
            "next_batch": next_batch_id,
            "volume_ml": self.FLUSH_VOLUME_ML,
            "duration_s": self.FLUSH_DURATION_S,
            "started_at": start,
            "completed_at": time.time(),
            "status": "COMPLETED",
        }

        self.last_flush_at = record["completed_at"]
        self.last_flush_batch = next_batch_id
        return record


# =============================================================================
# Smart Dock FSM
# =============================================================================
class SmartDockFSM:
    """
    Deterministic Finite State Machine for Smart Dock operations.
    States: IDLE -> CHARGING -> AI_INFERENCE -> CHEMICAL_MIXING -> LINE_FLUSH -> MRL_VERIFICATION -> READY_FOR_SORTIE
    """

    def __init__(self, days_to_harvest: int = 14, audit_dir: str = "audit_logs"):
        self.state = DockState.IDLE
        self.days_to_harvest = days_to_harvest
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self.mixer = ChemicalMixer(days_to_harvest)
        self.line_flush = LineFlush()
        self.pest_service = get_pest_service()

        self._current_tank_mix: Optional[TankMix] = None
        self._current_hotspots: list[InfestationHotspot] = []
        self._survey_data: dict = {}
        self._state_history: list[tuple[str, float]] = [(DockState.IDLE, time.time())]

    def _transition(self, new_state: str):
        if new_state not in [
            DockState.IDLE, DockState.CHARGING, DockState.AI_INFERENCE,
            DockState.CHEMICAL_MIXING, DockState.LINE_FLUSH,
            DockState.MRL_VERIFICATION, DockState.READY_FOR_SORTIE, DockState.ERROR
        ]:
            raise ValueError(f"Invalid state: {new_state}")
        self.state = new_state
        self._state_history.append((new_state, time.time()))

    def process_mission(self, scout_tiles: Optional[list] = None) -> DockAuditRecord:
        """
        Full Dock processing pipeline:
        1. CHARGING (simulated)
        2. AI_INFERENCE (pest detection on Scout tiles)
        3. CHEMICAL_MIXING (formulate tank mix)
        4. LINE_FLUSH (inter-batch flush)
        5. MRL_VERIFICATION (EU & Japan compliance)
        6. READY_FOR_SORTIE
        """
        try:
            # 1. CHARGING
            self._transition(DockState.CHARGING)
            time.sleep(0.01)  # Simulate charging

            # 2. AI_INFERENCE
            self._transition(DockState.AI_INFERENCE)
            self.pest_service.process_scout_survey(scout_tiles)
            self._survey_data = self.pest_service.export_audit_record("A-14")
            self._current_hotspots = self.pest_service.cluster_hotspots()

            # 3. CHEMICAL_MIXING
            self._transition(DockState.CHEMICAL_MIXING)
            if self._current_hotspots:
                self._current_tank_mix = self.mixer.formulate(self._current_hotspots)
            else:
                # No hotspots - empty mix (just carrier)
                self._current_tank_mix = TankMix(
                    batch_id=f"MIX-EMPTY-{uuid.uuid4().hex[:8].upper()}",
                    chemicals={},
                    carrier_water_ml=CARRIER_SPECS["water_l_per_tank"] * 1000,
                    surfactant_ml=0,
                    total_volume_ml=CARRIER_SPECS["water_l_per_tank"] * 1000,
                    target_hotspots=[],
                    days_to_harvest=self.days_to_harvest,
                )

            # 4. LINE_FLUSH
            self._transition(DockState.LINE_FLUSH)
            flush_record = self.line_flush.execute(self._current_tank_mix.batch_id)

            # 5. MRL_VERIFICATION
            self._transition(DockState.MRL_VERIFICATION)
            mrl_compliant, mrl_verification = self.mixer.verify_mrl(self._current_tank_mix)
            self._current_tank_mix.phi_compliant_eu = mrl_verification["phi_compliant_eu"]
            self._current_tank_mix.phi_compliant_japan = mrl_verification["phi_compliant_japan"]
            self._current_tank_mix.mrl_verified = mrl_compliant

            if not mrl_compliant:
                self._transition(DockState.ERROR)
                raise ValueError("MRL verification failed: PHI not met for target harvest date")

            # 6. READY_FOR_SORTIE
            self._transition(DockState.READY_FOR_SORTIE)

            return self._create_audit_record(
                compliance_status="COMPLIANT",
                mrl_verification=mrl_verification,
            )

        except Exception as e:
            self._transition(DockState.ERROR)
            return self._create_audit_record(
                compliance_status="NON_COMPLIANT",
                mrl_verification={"error": str(e)},
            )

    def _create_audit_record(self, compliance_status: str, mrl_verification: dict) -> DockAuditRecord:
        record = DockAuditRecord(
            record_id=f"AUDIT-{uuid.uuid4().hex[:12].upper()}",
            section_id="A-14",
            timestamp=datetime.now(timezone.utc).isoformat(),
            dock_state=self.state,
            survey_data=self._survey_data,
            hotspots=[hs.to_dict(26.7300, 94.2300) for hs in self._current_hotspots],
            tank_mix=self._current_tank_mix.to_dict() if self._current_tank_mix else None,
            mrl_verification=mrl_verification,
            compliance_status=compliance_status,
            operator_id="AUTO",
            signature=self._compute_signature(compliance_status, mrl_verification),
        )
        self._persist_audit(record)
        return record

    def _compute_signature(self, compliance_status: str, mrl_verification: dict) -> str:
        """Simple tamper-evident hash (in production: use HMAC with secret key)."""
        import hashlib
        data = f"{self._survey_data}{self._current_hotspots}{compliance_status}{mrl_verification}{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _persist_audit(self, record: DockAuditRecord):
        """Write audit record as JSON and append to CSV."""
        # JSON
        json_path = self.audit_dir / f"{record.record_id}.json"
        json_path.write_text(record.to_json())

        # CSV
        csv_path = self.audit_dir / "audit_log.csv"
        file_exists = csv_path.exists()
        with csv_path.open("a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "record_id", "section_id", "timestamp", "dock_state",
                    "survey_data", "hotspots", "tank_mix",
                    "mrl_verification", "compliance_status",
                    "operator_id", "signature"
                ])
            writer.writerow(record.to_csv_row())

    def get_tank_mix(self) -> Optional[TankMix]:
        return self._current_tank_mix

    def get_hotspots(self) -> list[InfestationHotspot]:
        return self._current_hotspots

    def get_sprayer_waypoints(self, home_lat: float, home_lon: float) -> list[tuple[float, float]]:
        return self.pest_service.get_sprayer_waypoints(home_lat, home_lon)

    def is_ready_for_sortie(self) -> bool:
        return self.state == DockState.READY_FOR_SORTIE

    def reset(self):
        self._transition(DockState.IDLE)
        self._current_tank_mix = None
        self._current_hotspots = []
        self._survey_data = {}


# =============================================================================
# Singleton Instance
# =============================================================================
_dock_fsm: Optional[SmartDockFSM] = None


def get_dock_fsm(days_to_harvest: int = 14, audit_dir: str = "audit_logs") -> SmartDockFSM:
    global _dock_fsm
    if _dock_fsm is None:
        _dock_fsm = SmartDockFSM(days_to_harvest=days_to_harvest, audit_dir=audit_dir)
    return _dock_fsm