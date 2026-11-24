"""
NESFIC-I-07: Central Configuration Module
Port definitions, tea block coordinates, TRA chemical & EU/Japan MRL rulebook.
All values are validated at import time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# PORT CONTRACT (STRICT - must match architecture spec exactly)
# =============================================================================
class PortConfig(BaseModel):
    # Gazebo FDM ports (input to Gazebo from SITL)
    SCOUT_FDM_PORT_IN: int = Field(default=9002, description="Scout UAV Gazebo FDM input port")
    SPRAYER_FDM_PORT_IN: int = Field(default=9012, description="Sprayer UAV Gazebo FDM input port")

    # MAVLink telemetry output ports (UDP from SITL to backend)
    SCOUT_MAVLINK_OUT: str = Field(default="udp:127.0.0.1:14550", description="Scout MAVLink telemetry output")
    SPRAYER_MAVLINK_OUT: str = Field(default="udp:127.0.0.1:14560", description="Sprayer MAVLink telemetry output")

    # Backend API
    BACKEND_HOST: str = Field(default="0.0.0.0", description="Backend bind host")
    BACKEND_PORT: int = Field(default=8000, description="Backend REST + WebSocket port")

    # Frontend
    FRONTEND_PORT: int = Field(default=3000, description="Next.js dev server port")

    @field_validator("SCOUT_FDM_PORT_IN", "SPRAYER_FDM_PORT_IN", "BACKEND_PORT", "FRONTEND_PORT")
    @classmethod
    def validate_port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"Port {v} out of valid range 1-65535")
        return v

    @field_validator("SCOUT_MAVLINK_OUT", "SPRAYER_MAVLINK_OUT")
    @classmethod
    def validate_mavlink_uri(cls, v: str) -> str:
        if not v.startswith("udp:"):
            raise ValueError(f"MAVLink URI must be udp://, got {v}")
        return v


PORTS = PortConfig()


# =============================================================================
# TEA ESTATE GEOMETRY (Section A-14: 60m x 60m block)
# =============================================================================
@dataclass(frozen=True)
class TeaBlockGeometry:
    # Section A-14 bounds (local NED frame, origin at Smart Dock (0,0,0))
    # Dock is at southwest corner of the 100m x 100m estate
    # Section A-14 occupies [-30, -30] to [30, 30] in local frame
    MIN_X: float = -30.0
    MAX_X: float = 30.0
    MIN_Y: float = -30.0
    MAX_Y: float = 30.0

    # Survey parameters for Scout
    SURVEY_ALTITUDE_M: float = 12.0  # AGL
    GRID_SPACING_M: float = 5.0  # Lawnmower track spacing
    TILE_SIZE_M: float = 5.0  # Pest detection tile resolution

    # Sprayer parameters
    SPRAY_ALTITUDE_M: float = 6.0  # AGL
    HOVER_DWELL_S: float = 4.0  # Seconds at each hotspot
    SPRAY_SERVO_CHANNEL: int = 9  # MAV_CMD_DO_SET_SERVO channel
    SPRAY_PWM_ON: int = 1900
    SPRAY_PWM_OFF: int = 1100

    # Smart Dock position (local origin)
    DOCK_X: float = 0.0
    DOCK_Y: float = 0.0
    DOCK_Z: float = 0.05  # Pad height

    # Infested patch ground truth (from SDF world) - center coordinates
    INFESTED_PATCHES: tuple[tuple[float, float, float], ...] = (
        (-10.0, -10.0, 5.0),   # Patch 1: center (-10,-10), radius 5m
        (15.0, 20.0, 4.0),     # Patch 2: center (15,20), radius 4m
        (40.0, -20.0, 6.0),    # Patch 3: center (40,-20), radius 6m (partially outside A-14)
    )


GEOMETRY = TeaBlockGeometry()


# =============================================================================
# TRA CHEMICAL RULEBOOK (Approved actives for Assam/Dooars tea)
# =============================================================================
@dataclass(frozen=True)
class ChemicalSpec:
    name: str
    active_ingredient: str
    max_concentration_g_per_l: float  # Label max concentration
    phi_days_eu: int  # Pre-harvest interval (EU)
    phi_days_japan: int  # Pre-harvest interval (Japan)
    mrl_eu_mg_per_kg: float  # EU MRL (mg/kg)
    mrl_japan_mg_per_kg: float  # Japan MRL (mg/kg)
    compatible_with: tuple[str, ...]  # Tank-mix compatible actives
    target_pests: tuple[str, ...]
    surfactant_required_pct_vv: float = 0.05  # 0.05% v/v default


# Pre-loaded TRA-approved chemicals for tea pest management
TRA_CHEMICALS: Final[dict[str, ChemicalSpec]] = {
    "deltamethrin_ec": ChemicalSpec(
        name="Deltamethrin 2.8% EC",
        active_ingredient="deltamethrin",
        max_concentration_g_per_l=28.0,
        phi_days_eu=7,
        phi_days_japan=14,
        mrl_eu_mg_per_kg=0.05,
        mrl_japan_mg_per_kg=0.01,
        compatible_with=("tebuconazole", "hexythiazox"),
        target_pests=("tea_mosquito_bug", "thrips", "leaf_roller"),
        surfactant_required_pct_vv=0.05,
    ),
    "thiamethoxam_wg": ChemicalSpec(
        name="Thiamethoxam 25% WG",
        active_ingredient="thiamethoxam",
        max_concentration_g_per_l=250.0,
        phi_days_eu=10,
        phi_days_japan=14,
        mrl_eu_mg_per_kg=0.1,
        mrl_japan_mg_per_kg=0.02,
        compatible_with=("deltamethrin", "hexythiazox"),
        target_pests=("tea_mosquito_bug", "aphids", "jassids"),
        surfactant_required_pct_vv=0.05,
    ),
    "hexythiazox_wp": ChemicalSpec(
        name="Hexythiazox 5.45% WP",
        active_ingredient="hexythiazox",
        max_concentration_g_per_l=54.5,
        phi_days_eu=14,
        phi_days_japan=21,
        mrl_eu_mg_per_kg=0.5,
        mrl_japan_mg_per_kg=0.1,
        compatible_with=("deltamethrin", "thiamethoxam", "tebuconazole"),
        target_pests=("red_spider_mite", "yellow_mite"),
        surfactant_required_pct_vv=0.08,
    ),
    "tebuconazole_ec": ChemicalSpec(
        name="Tebuconazole 25.9% EC",
        active_ingredient="tebuconazole",
        max_concentration_g_per_l=259.0,
        phi_days_eu=7,
        phi_days_japan=14,
        mrl_eu_mg_per_kg=0.1,
        mrl_japan_mg_per_kg=0.05,
        compatible_with=("deltamethrin", "hexythiazox"),
        target_pests=("blister_blight", "grey_blight"),
        surfactant_required_pct_vv=0.05,
    ),
    "spirotetramat_sc": ChemicalSpec(
        name="Spirotetramat 11.01% SC",
        active_ingredient="spirotetramat",
        max_concentration_g_per_l=110.1,
        phi_days_eu=7,
        phi_days_japan=14,
        mrl_eu_mg_per_kg=0.2,
        mrl_japan_mg_per_kg=0.05,
        compatible_with=("deltamethrin",),
        target_pests=("tea_mosquito_bug", "aphids", "whitefly"),
        surfactant_required_pct_vv=0.05,
    ),
}

# Carrier fluid (water + surfactant)
CARRIER_SPECS = {
    "water_l_per_tank": 10.0,  # Max tank volume 10L
    "surfactant_pct_vv_min": 0.05,
    "surfactant_pct_vv_max": 0.10,
    "surfactant_name": "Non-ionic agricultural surfactant",
}


# =============================================================================
# MRL COMPLIANCE RULEBOOK
# =============================================================================
class MRLRulebook(BaseModel):
    """
    EU Regulation 396/2005 & Japan Positive List System compliance.
    """
    # Default MRL for unlisted substances (Japan)
    JAPAN_DEFAULT_MRL_MG_PER_KG: float = 0.01

    # Minimum PHI enforcement (days before harvest)
    MIN_PHI_DAYS_EU: int = 7
    MIN_PHI_DAYS_JAPAN: int = 14

    # Maximum residue calculation safety factor
    SAFETY_FACTOR: float = 1.5

    def validate_chemical(self, chem: ChemicalSpec, days_to_harvest: int) -> tuple[bool, list[str]]:
        """
        Returns (compliant, [violations]).
        """
        violations = []

        # PHI check
        if days_to_harvest < chem.phi_days_eu:
            violations.append(f"EU PHI violation: {days_to_harvest}d < {chem.phi_days_eu}d required for {chem.active_ingredient}")
        if days_to_harvest < chem.phi_days_japan:
            violations.append(f"Japan PHI violation: {days_to_harvest}d < {chem.phi_days_japan}d required for {chem.active_ingredient}")

        # MRL sanity check (would need application rate + dissipation model for real calc)
        # Here we just verify MRL values are set
        if chem.mrl_eu_mg_per_kg <= 0:
            violations.append(f"EU MRL not set for {chem.active_ingredient}")
        if chem.mrl_japan_mg_per_kg <= 0:
            violations.append(f"Japan MRL not set for {chem.active_ingredient}")

        return len(violations) == 0, violations

    def validate_tank_mix(self, chemicals: list[ChemicalSpec]) -> tuple[bool, list[str]]:
        """
        Validates tank-mix compatibility.
        """
        violations = []
        actives = [c.active_ingredient for c in chemicals]

        for i, chem in enumerate(chemicals):
            for other_active in actives[:i] + actives[i+1:]:
                if other_active not in chem.compatible_with:
                    violations.append(f"Tank-mix incompatibility: {chem.active_ingredient} + {other_active}")

        # Volume check
        total_volume = sum(c.max_concentration_g_per_l for c in chemicals)  # Proxy
        if total_volume > CARRIER_SPECS["water_l_per_tank"] * 100:  # Rough heuristic
            violations.append("Estimated total concentrate volume may exceed 10L tank capacity")

        return len(violations) == 0, violations


MRL_RULEBOOK = MRLRulebook()


# =============================================================================
# MAVLink SYSTEM IDs (STRICT)
# =============================================================================
class SystemIDs:
    SCOUT_SYSID: Final[int] = 1
    SPRAYER_SYSID: Final[int] = 2
    GROUND_STATION_SYSID: Final[int] = 255
    COMP_ID_AUTOPILOT: Final[int] = 1
    COMP_ID_CAMERA: Final[int] = 100
    COMP_ID_SPRAYER: Final[int] = 200


# =============================================================================
# MAVLink MESSAGE RATES (Hz)
# =============================================================================
class StreamRates:
    HEARTBEAT: Final[int] = 1
    ATTITUDE: Final[int] = 10
    GLOBAL_POSITION_INT: Final[int] = 10
    LOCAL_POSITION_NED: Final[int] = 10
    VFR_HUD: Final[int] = 5
    BATTERY_STATUS: Final[int] = 2
    SYS_STATUS: Final[int] = 1
    MISSION_CURRENT: Final[int] = 2
    NAV_CONTROLLER_OUTPUT: Final[int] = 5


# =============================================================================
# MISSION STATES
# =============================================================================
class MissionState:
    IDLE = "IDLE"
    ARMING = "ARMING"
    TAKING_OFF = "TAKING_OFF"
    SURVEYING = "SURVEYING"
    SPRAYING = "SPRAYING"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    DOCKED = "DOCKED"
    ERROR = "ERROR"


# =============================================================================
# DOCK FSM STATES
# =============================================================================
class DockState:
    IDLE = "IDLE"
    CHARGING = "CHARGING"
    AI_INFERENCE = "AI_INFERENCE"
    CHEMICAL_MIXING = "CHEMICAL_MIXING"
    LINE_FLUSH = "LINE_FLUSH"
    MRL_VERIFICATION = "MRL_VERIFICATION"
    READY_FOR_SORTIE = "READY_FOR_SORTIE"
    ERROR = "ERROR"


# Export all config as a single namespace
__all__ = [
    "PORTS",
    "GEOMETRY",
    "TRA_CHEMICALS",
    "CARRIER_SPECS",
    "MRL_RULEBOOK",
    "SystemIDs",
    "StreamRates",
    "MissionState",
    "DockState",
    "ChemicalSpec",
    "TeaBlockGeometry",
    "PortConfig",
    "MRLRulebook",
]