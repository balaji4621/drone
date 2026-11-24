"""
NESFIC-I-07: FastAPI Backend + WebSocket Telemetry Server
REST endpoints for mission control, WebSocket for real-time telemetry.
"""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import PORTS, GEOMETRY, SystemIDs, MissionState, DockState, MRL_RULEBOOK
from mavlink_fleet import FleetManager, get_fleet_manager, close_fleet_manager, Telemetry, Waypoint
from pest_detector import get_pest_service, InfestationHotspot
from dock_engine import get_dock_fsm, SmartDockFSM, TankMix


# =============================================================================
# Pydantic Models for API
# =============================================================================
class HealthResponse(BaseModel):
    status: str
    timestamp: float
    version: str = "1.0.0"
    mode: str


class ConfigResponse(BaseModel):
    ports: dict
    geometry: dict
    system_ids: dict


class TelemetryResponse(BaseModel):
    scout: Optional[dict] = None
    sprayer: Optional[dict] = None


class MissionStartRequest(BaseModel):
    days_to_harvest: int = 14


class DockProcessResponse(BaseModel):
    success: bool
    audit_record_id: str
    compliance_status: str
    hotspots_count: int
    tank_mix: Optional[dict] = None
    mrl_verification: dict


class AuditExportRequest(BaseModel):
    format: str = "json"  # json or csv


# =============================================================================
# WebSocket Connection Manager
# =============================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


# =============================================================================
# Global State
# =============================================================================
_fleet: Optional[FleetManager] = None
_dock_fsm: Optional[SmartDockFSM] = None
_use_mock = True  # Default to mock for Windows dev


# =============================================================================
# Lifespan
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _fleet, _dock_fsm
    _fleet = get_fleet_manager(use_mock=_use_mock)
    _dock_fsm = get_dock_fsm(days_to_harvest=14, audit_dir="audit_logs")

    # Subscribe to telemetry
    def on_telemetry(tel: Telemetry):
        asyncio.create_task(manager.broadcast({
            "type": "telemetry",
            "data": {
                "sysid": tel.sysid,
                "timestamp": tel.timestamp,
                "lat": tel.lat,
                "lon": tel.lon,
                "alt": tel.alt,
                "relative_alt": tel.relative_alt,
                "vx": tel.vx,
                "vy": tel.vy,
                "vz": tel.vz,
                "roll": tel.roll,
                "pitch": tel.pitch,
                "yaw": tel.yaw,
                "groundspeed": tel.groundspeed,
                "airspeed": tel.airspeed,
                "battery_voltage": tel.battery_voltage,
                "battery_current": tel.battery_current,
                "battery_remaining": tel.battery_remaining,
                "mode": tel.mode,
                "armed": tel.armed,
                "mission_state": tel.mission_state,
                "current_wp": tel.current_wp,
                "wp_total": tel.wp_total,
                "spray_active": tel.spray_active,
                "spray_servo_pwm": tel.spray_servo_pwm,
            }
        }))

    _fleet.subscribe(on_telemetry)

    # Connect to real SITL if not mock, or start mock loop
    if not _use_mock:
        await _fleet.connect()
    else:
        await _fleet.start_mock_loop()

    yield

    await close_fleet_manager()


# =============================================================================
# FastAPI App
# =============================================================================
app = FastAPI(
    title="NESFIC-I-07 Drone Telemetry API",
    description="Dual-UAV Scout + Sprayer control with Smart Dock integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REST Endpoints
# =============================================================================
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        timestamp=time.time(),
        mode="mock" if _use_mock else "sitl",
    )


@app.get("/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(
        ports={
            "scout_fdm_in": PORTS.SCOUT_FDM_PORT_IN,
            "sprayer_fdm_in": PORTS.SPRAYER_FDM_PORT_IN,
            "scout_mavlink_out": PORTS.SCOUT_MAVLINK_OUT,
            "sprayer_mavlink_out": PORTS.SPRAYER_MAVLINK_OUT,
            "backend_port": PORTS.BACKEND_PORT,
            "frontend_port": PORTS.FRONTEND_PORT,
        },
        geometry={
            "section_a14": {
                "min_x": GEOMETRY.MIN_X,
                "max_x": GEOMETRY.MAX_X,
                "min_y": GEOMETRY.MIN_Y,
                "max_y": GEOMETRY.MAX_Y,
            },
            "survey_altitude_m": GEOMETRY.SURVEY_ALTITUDE_M,
            "spray_altitude_m": GEOMETRY.SPRAY_ALTITUDE_M,
            "grid_spacing_m": GEOMETRY.GRID_SPACING_M,
            "tile_size_m": GEOMETRY.TILE_SIZE_M,
            "hover_dwell_s": GEOMETRY.HOVER_DWELL_S,
            "dock": {"x": GEOMETRY.DOCK_X, "y": GEOMETRY.DOCK_Y, "z": GEOMETRY.DOCK_Z},
        },
        system_ids={
            "scout_sysid": SystemIDs.SCOUT_SYSID,
            "sprayer_sysid": SystemIDs.SPRAYER_SYSID,
            "ground_station_sysid": SystemIDs.GROUND_STATION_SYSID,
        },
    )


@app.get("/telemetry/scout", response_model=TelemetryResponse)
async def get_scout_telemetry():
    tel = _fleet.get_scout_telemetry()
    return TelemetryResponse(scout=tel.__dict__ if tel else None)


@app.get("/telemetry/sprayer", response_model=TelemetryResponse)
async def get_sprayer_telemetry():
    tel = _fleet.get_sprayer_telemetry()
    return TelemetryResponse(sprayer=tel.__dict__ if tel else None)


@app.get("/telemetry", response_model=TelemetryResponse)
async def get_all_telemetry():
    return TelemetryResponse(
        scout=_fleet.get_scout_telemetry().__dict__ if _fleet.get_scout_telemetry() else None,
        sprayer=_fleet.get_sprayer_telemetry().__dict__ if _fleet.get_sprayer_telemetry() else None,
    )


@app.post("/mission/scout/start")
async def start_scout_mission():
    """Launch Scout lawnmower survey over Section A-14."""
    if _fleet is None:
        raise HTTPException(503, "Fleet not initialized")
    await _fleet.scout_arm_takeoff_survey()
    return {"status": "started", "mission": "scout_survey", "target_altitude": GEOMETRY.SURVEY_ALTITUDE_M}


@app.post("/mission/scout/rtl")
async def scout_rtl():
    """Command Scout to return to launch."""
    await _fleet.scout_rtl()
    return {"status": "rtl_commanded"}


@app.post("/dock/process", response_model=DockProcessResponse)
async def process_dock(request: MissionStartRequest):
    """
    Trigger Smart Dock full pipeline:
    AI inference -> Chemical mixing -> Line flush -> MRL verification.
    Returns audit record. If compliant, Sprayer can be launched.
    """
    global _dock_fsm
    _dock_fsm = get_dock_fsm(days_to_harvest=request.days_to_harvest, audit_dir="audit_logs")

    audit = _dock_fsm.process_mission()

    return DockProcessResponse(
        success=audit.compliance_status == "COMPLIANT",
        audit_record_id=audit.record_id,
        compliance_status=audit.compliance_status,
        hotspots_count=len(audit.hotspots),
        tank_mix=audit.tank_mix,
        mrl_verification=audit.mrl_verification,
    )


@app.post("/mission/sprayer/start")
async def start_sprayer_mission():
    """Launch Sprayer spot-spray sortie (only after Dock READY_FOR_SORTIE)."""
    if _dock_fsm is None or not _dock_fsm.is_ready_for_sortie():
        raise HTTPException(400, "Dock not ready. Run /dock/process first.")

    hotspots = _dock_fsm.get_hotspots()
    if not hotspots:
        raise HTTPException(400, "No hotspots to spray")

    # Convert to (lat, lon) for fleet manager
    waypoints = _dock_fsm.get_sprayer_waypoints(26.7300, 94.2300)  # Tocklai approx
    await _fleet.sprayer_arm_takeoff_spray([(lat, lon) for lat, lon in waypoints[1:-1]])

    return {
        "status": "started",
        "mission": "spot_spray",
        "hotspots": len(hotspots),
        "waypoints": len(waypoints),
        "tank_mix_batch": _dock_fsm.get_tank_mix().batch_id if _dock_fsm.get_tank_mix() else None,
    }


@app.post("/mission/sprayer/rtl")
async def sprayer_rtl():
    await _fleet.sprayer_rtl()
    return {"status": "rtl_commanded"}


@app.get("/audit/latest")
async def get_latest_audit():
    """Get most recent audit record."""
    audit_dir = Path("audit_logs")
    if not audit_dir.exists():
        raise HTTPException(404, "No audit logs found")

    json_files = list(audit_dir.glob("AUDIT-*.json"))
    if not json_files:
        raise HTTPException(404, "No audit records found")

    latest = max(json_files, key=lambda f: f.stat().st_mtime)
    return json.loads(latest.read_text())


@app.get("/audit/export")
async def export_audit(format: str = Query("json", pattern="^(json|csv)$")):
    """Export all audit records."""
    audit_dir = Path("audit_logs")
    if not audit_dir.exists():
        raise HTTPException(404, "No audit logs found")

    if format == "json":
        records = []
        for f in sorted(audit_dir.glob("AUDIT-*.json")):
            records.append(json.loads(f.read_text()))
        return records
    else:
        csv_path = audit_dir / "audit_log.csv"
        if not csv_path.exists():
            raise HTTPException(404, "CSV audit log not found")
        return FileResponse(csv_path, media_type="text/csv", filename="audit_log.csv")


@app.get("/audit/list")
async def list_audits():
    audit_dir = Path("audit_logs")
    if not audit_dir.exists():
        return []

    files = sorted(audit_dir.glob("AUDIT-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "file": f.name,
            "record_id": f.stem,
            "timestamp": f.stat().st_mtime,
        }
        for f in files
    ]


# =============================================================================
# WebSocket Telemetry Endpoint
# =============================================================================
@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        scout_tel = _fleet.get_scout_telemetry()
        sprayer_tel = _fleet.get_sprayer_telemetry()
        await websocket.send_json({
            "type": "initial_state",
            "scout": scout_tel.__dict__ if scout_tel else None,
            "sprayer": sprayer_tel.__dict__ if sprayer_tel else None,
            "dock_state": _dock_fsm.state if _dock_fsm else DockState.IDLE,
            "timestamp": time.time(),
        })

        # Keep alive - client can send ping/pong or commands
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Handle client commands (optional)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# Development Helper: Toggle Mock Mode
# =============================================================================
@app.post("/dev/set_mode")
async def set_mode(use_mock: bool):
    global _use_mock, _fleet, _dock_fsm
    if _fleet:
        await close_fleet_manager()
    _use_mock = use_mock
    _fleet = get_fleet_manager(use_mock=_use_mock)
    _dock_fsm = get_dock_fsm(days_to_harvest=14, audit_dir="audit_logs")

    def on_telemetry(tel: Telemetry):
        asyncio.create_task(manager.broadcast({
            "type": "telemetry",
            "data": tel.__dict__
        }))
    _fleet.subscribe(on_telemetry)

    if not _use_mock:
        await _fleet.connect()

    return {"mode": "mock" if _use_mock else "sitl", "status": "restarted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)