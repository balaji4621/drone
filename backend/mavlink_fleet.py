"""
NESFIC-I-07: Dual-UAV MAVLink Fleet Controller
Supports both real ArduPilot SITL (via UDP) and deterministic 10Hz physics mock fallback.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

from config import (
    PORTS,
    GEOMETRY,
    SystemIDs,
    StreamRates,
    MissionState,
)


# =============================================================================
# Data Structures
# =============================================================================
@dataclass
class Telemetry:
    sysid: int
    timestamp: float
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0  # AMSL
    relative_alt: float = 0.0  # AGL
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    groundspeed: float = 0.0
    airspeed: float = 0.0
    battery_voltage: float = 0.0
    battery_current: float = 0.0
    battery_remaining: float = 100.0
    mode: str = "UNKNOWN"
    armed: bool = False
    mission_state: str = MissionState.IDLE
    current_wp: int = -1
    wp_total: int = 0
    # Sprayer-specific
    spray_active: bool = False
    spray_servo_pwm: int = 1100


@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: float  # AMSL
    hold_time: float = 0.0  # seconds
    spray_at_wp: bool = False


class UAVType(Enum):
    SCOUT = "scout"
    SPRAYER = "sprayer"


# =============================================================================
# Mock Physics Engine (10Hz deterministic fallback)
# =============================================================================
class MockPhysics:
    """
    Deterministic physics simulation for Windows development / CI.
    Simulates quadcopter dynamics at 10Hz with simple kinematics.
    """

    def __init__(self, uav_type: UAVType, home_lat: float, home_lon: float, home_alt: float):
        self.uav_type = uav_type
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt = home_alt  # AMSL

        # State
        self.x = 0.0  # North (m)
        self.y = 0.0  # East (m)
        self.z = 0.0  # Down (m, positive down) -> AGL = -z
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.armed = False
        self.mode = "INIT"
        self.mission_state = MissionState.IDLE
        self.target_wp: Optional[Waypoint] = None
        self.waypoints: list[Waypoint] = []
        self.current_wp_idx = -1
        self.spray_active = False
        self.spray_servo_pwm = 1100

        # Physics constants
        self.max_speed = 8.0  # m/s
        self.max_climb = 3.0  # m/s
        self.max_descent = 2.0  # m/s
        self.hover_threshold = 0.5  # m
        self.dt = 0.1  # 10Hz

        # Battery simulation
        self.battery_voltage = 22.2  # 6S LiPo
        self.battery_current = 0.0
        self.battery_capacity_mah = 10000
        self.battery_used_mah = 0.0
        self.battery_remaining = 100.0

        # Random seed for deterministic noise
        self._rng = random.Random(42 if uav_type == UAVType.SCOUT else 43)

    def _ned_to_latlon(self, north: float, east: float) -> tuple[float, float]:
        """Convert local NED to lat/lon (approximate, valid for small areas)."""
        # 1 deg lat ≈ 111,111 m, 1 deg lon ≈ 111,111 * cos(lat) m
        lat = self.home_lat + (north / 111111.0)
        lon = self.home_lon + (east / (111111.0 * math.cos(math.radians(self.home_lat))))
        return lat, lon

    def _latlon_to_ned(self, lat: float, lon: float) -> tuple[float, float]:
        north = (lat - self.home_lat) * 111111.0
        east = (lon - self.home_lon) * 111111.0 * math.cos(math.radians(self.home_lat))
        return north, east

    def set_waypoints(self, waypoints: list[Waypoint]):
        self.waypoints = waypoints
        self.current_wp_idx = 0
        if waypoints:
            self.target_wp = waypoints[0]
            self.mission_state = MissionState.TAKING_OFF if self.armed else MissionState.IDLE

    def arm(self):
        self.armed = True
        self.mode = "GUIDED"
        self.mission_state = MissionState.ARMING

    def disarm(self):
        self.armed = False
        self.mode = "INIT"
        self.mission_state = MissionState.IDLE

    def set_mode(self, mode: str):
        self.mode = mode

    def update(self):
        """Step physics by dt (10Hz)."""
        if not self.armed:
            self.battery_current = 0.1
            return

        # Battery drain based on throttle
        throttle = 0.5 + abs(self.vz) * 0.1 + math.hypot(self.vx, self.vy) * 0.05
        self.battery_current = 10.0 * throttle  # Amps
        self.battery_used_mah += self.battery_current * (self.dt / 3600.0) * 1000
        self.battery_voltage = 22.2 - (self.battery_used_mah / self.battery_capacity_mah) * 3.0
        self.battery_remaining = max(0.0, 100.0 - (self.battery_used_mah / self.battery_capacity_mah) * 100)

        if self.target_wp is None:
            # Loiter at current position
            self._loiter()
            return

        # Navigate to target waypoint
        target_north, target_east = self._latlon_to_ned(self.target_wp.lat, self.target_wp.lon)
        target_down = self.home_alt - self.target_wp.alt  # Positive down

        dx = target_north - self.x
        dy = target_east - self.y
        dz = target_down - self.z
        dist_xy = math.hypot(dx, dy)
        dist_3d = math.hypot(dist_xy, dz)

        if dist_3d < self.hover_threshold:
            # Reached waypoint
            self.vx = self.vy = self.vz = 0.0
            if self.target_wp.hold_time > 0:
                self.target_wp.hold_time -= self.dt
                self.mission_state = MissionState.SPRAYING if self.target_wp.spray_at_wp else MissionState.SURVEYING
                if self.target_wp.spray_at_wp:
                    self.spray_active = True
                    self.spray_servo_pwm = 1900
                else:
                    self.spray_active = False
                    self.spray_servo_pwm = 1100
            else:
                self._advance_waypoint()
        else:
            # Move toward waypoint
            speed = min(self.max_speed, dist_xy * 0.5)
            if dist_xy > 0:
                self.vx = speed * dx / dist_xy
                self.vy = speed * dy / dist_xy
            else:
                self.vx = self.vy = 0.0

            # Vertical
            if abs(dz) > 0.2:
                climb_rate = self.max_climb if dz > 0 else -self.max_descent
                self.vz = max(-self.max_descent, min(self.max_climb, climb_rate))
            else:
                self.vz = 0.0

            self.x += self.vx * self.dt
            self.y += self.vy * self.dt
            self.z += self.vz * self.dt

            # Attitude from velocity
            self.pitch = math.atan2(-self.vx, 9.81) if abs(self.vx) > 0.1 else 0.0
            self.roll = math.atan2(self.vy, 9.81) if abs(self.vy) > 0.1 else 0.0
            self.yaw = math.atan2(dy, dx) if dist_xy > 0.1 else self.yaw

            self.mission_state = MissionState.SPRAYING if self.target_wp.spray_at_wp else MissionState.SURVEYING

        # Sprayer pulse logic (4s on/off cycle during hold)
        if self.spray_active and self.target_wp and self.target_wp.spray_at_wp:
            cycle = math.sin(time.time() * 2 * math.pi / 1.0)  # 1Hz pulse
            self.spray_servo_pwm = 1900 if cycle > 0 else 1100

    def _loiter(self):
        self.vx = self.vy = self.vz = 0.0
        self.pitch = self.roll = 0.0

    def _advance_waypoint(self):
        self.current_wp_idx += 1
        if self.current_wp_idx < len(self.waypoints):
            self.target_wp = self.waypoints[self.current_wp_idx]
        else:
            self.target_wp = None
            self.mission_state = MissionState.RETURNING
            # Auto-RTL to dock
            self.target_wp = Waypoint(
                lat=self.home_lat,
                lon=self.home_lon,
                alt=self.home_alt,
            )

    def get_telemetry(self) -> Telemetry:
        lat, lon = self._ned_to_latlon(self.x, self.y)
        return Telemetry(
            sysid=SystemIDs.SCOUT_SYSID if self.uav_type == UAVType.SCOUT else SystemIDs.SPRAYER_SYSID,
            timestamp=time.time(),
            lat=lat,
            lon=lon,
            alt=self.home_alt - self.z,  # AMSL
            relative_alt=-self.z,  # AGL
            vx=self.vx,
            vy=self.vy,
            vz=-self.vz,  # NED vz is positive down
            roll=self.roll,
            pitch=self.pitch,
            yaw=self.yaw,
            groundspeed=math.hypot(self.vx, self.vy),
            airspeed=math.hypot(self.vx, self.vy) + self._rng.uniform(-0.2, 0.2),
            battery_voltage=self.battery_voltage,
            battery_current=self.battery_current,
            battery_remaining=self.battery_remaining,
            mode=self.mode,
            armed=self.armed,
            mission_state=self.mission_state,
            current_wp=self.current_wp_idx,
            wp_total=len(self.waypoints),
            spray_active=self.spray_active,
            spray_servo_pwm=self.spray_servo_pwm,
        )


# =============================================================================
# MAVLink Connection Manager (Real SITL)
# =============================================================================
class MAVLinkConnection:
    """
    Manages UDP MAVLink connection to ArduPilot SITL instance.
    Handles heartbeat, stream requests, command sending, and telemetry parsing.
    """

    def __init__(self, sysid: int, mavlink_uri: str, source_system: int = SystemIDs.GROUND_STATION_SYSID):
        self.sysid = sysid
        self.mavlink_uri = mavlink_uri
        self.source_system = source_system
        self.master: Optional[mavutil.mavlink_connection] = None
        self._running = False
        self._telemetry_callbacks: list[Callable[[Telemetry], None]] = []
        self._latest_telemetry: Optional[Telemetry] = None
        self._mode_mapping: dict[str, int] = {}

    async def connect(self) -> bool:
        try:
            self.master = mavutil.mavlink_connection(
                self.mavlink_uri,
                source_system=self.source_system,
                source_component=mavlink2.MAV_COMP_ID_MISSIONPLANNER,
                autoreconnect=True,
            )
            # Wait for heartbeat
            self.master.wait_heartbeat(timeout=10)
            self._mode_mapping = self.master.mode_mapping() or {}
            self._running = True
            asyncio.create_task(self._recv_loop())
            await self._request_streams()
            return True
        except Exception as e:
            print(f"[MAVLink sysid={self.sysid}] Connection failed: {e}")
            return False

    async def _request_streams(self):
        """Request standard telemetry streams at configured rates."""
        streams = [
            (mavlink2.MAV_DATA_STREAM_ATTITUDE, StreamRates.ATTITUDE),
            (mavlink2.MAV_DATA_STREAM_POSITION, StreamRates.GLOBAL_POSITION_INT),
            (mavlink2.MAV_DATA_STREAM_EXTRA1, StreamRates.VFR_HUD),
            (mavlink2.MAV_DATA_STREAM_EXTRA2, StreamRates.BATTERY_STATUS),
            (mavlink2.MAV_DATA_STREAM_EXTRA3, StreamRates.SYS_STATUS),
        ]
        for stream_id, rate in streams:
            self.master.mav.request_data_stream_send(
                self.sysid, 1, stream_id, rate, 1
            )
            await asyncio.sleep(0.05)

    async def _recv_loop(self):
        while self._running and self.master:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1.0)
                if msg is None:
                    continue
                self._parse_message(msg)
            except Exception as e:
                print(f"[MAVLink sysid={self.sysid}] Recv error: {e}")
                await asyncio.sleep(0.5)

    def _parse_message(self, msg):
        msg_type = msg.get_type()
        tel = Telemetry(sysid=self.sysid, timestamp=time.time())

        if msg_type == "HEARTBEAT":
            tel.mode = mavutil.mode_string_v10(msg)
            tel.armed = (msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED) != 0
        elif msg_type == "GLOBAL_POSITION_INT":
            tel.lat = msg.lat / 1e7
            tel.lon = msg.lon / 1e7
            tel.alt = msg.alt / 1000.0
            tel.relative_alt = msg.relative_alt / 1000.0
            tel.vx = msg.vx / 100.0
            tel.vy = msg.vy / 100.0
            tel.vz = msg.vz / 100.0
        elif msg_type == "LOCAL_POSITION_NED":
            tel.vx = msg.vx
            tel.vy = msg.vy
            tel.vz = msg.vz
        elif msg_type == "ATTITUDE":
            tel.roll = msg.roll
            tel.pitch = msg.pitch
            tel.yaw = msg.yaw
        elif msg_type == "VFR_HUD":
            tel.groundspeed = msg.groundspeed
            tel.airspeed = msg.airspeed
            tel.alt = msg.alt
        elif msg_type == "SYS_STATUS":
            tel.battery_voltage = msg.voltage_battery / 1000.0
            tel.battery_current = msg.current_battery / 100.0
            tel.battery_remaining = msg.battery_remaining
        elif msg_type == "BATTERY_STATUS":
            if msg.voltages:
                tel.battery_voltage = msg.voltages[0] / 1000.0
            tel.battery_current = msg.current_battery / 100.0
            tel.battery_remaining = msg.battery_remaining
        elif msg_type == "MISSION_CURRENT":
            tel.current_wp = msg.seq
        elif msg_type == "MISSION_COUNT":
            tel.wp_total = msg.count

        # Merge with existing
        if self._latest_telemetry:
            for field_name in tel.__dataclass_fields__:
                val = getattr(tel, field_name)
                if val != 0.0 and val != "" and val is not False:
                    setattr(self._latest_telemetry, field_name, val)
        else:
            self._latest_telemetry = tel

        for cb in self._telemetry_callbacks:
            cb(self._latest_telemetry)

    def on_telemetry(self, callback: Callable[[Telemetry], None]):
        self._telemetry_callbacks.append(callback)

    def get_latest(self) -> Optional[Telemetry]:
        return self._latest_telemetry

    # ---- Command Sending ----
    def arm(self):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0
        )

    def disarm(self):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            0, 0, 0, 0, 0, 0, 0
        )

    def set_mode(self, mode: str):
        if mode not in self._mode_mapping:
            raise ValueError(f"Unknown mode: {mode}. Available: {list(self._mode_mapping.keys())}")
        mode_id = self._mode_mapping[mode]
        self.master.mav.set_mode_send(
            self.sysid,
            mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

    def takeoff(self, altitude: float):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, altitude
        )

    def upload_mission(self, waypoints: list[Waypoint]):
        """Upload mission (simple waypoint list)."""
        self.master.mav.mission_count_send(self.sysid, 1, len(waypoints), 0)
        for i, wp in enumerate(waypoints):
            self.master.mav.mission_item_int_send(
                self.sysid, 1, i,
                mavlink2.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavlink2.MAV_CMD_NAV_WAYPOINT,
                0, 1,  # current, autocontinue
                0, 0, 0, 0,  # params 1-4 (hold, radius, etc.)
                int(wp.lat * 1e7), int(wp.lon * 1e7), int(wp.alt * 1000),
                0  # mission_type
            )

    def start_mission(self):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_MISSION_START, 0,
            0, 0, 0, 0, 0, 0, 0
        )

    def set_servo(self, channel: int, pwm: int):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_DO_SET_SERVO, 0,
            channel, pwm, 0, 0, 0, 0, 0
        )

    def rtl(self):
        self.master.mav.command_long_send(
            self.sysid, 1,
            mavlink2.MAV_CMD_NAV_RETURN_TO_LAUNCH, 0,
            0, 0, 0, 0, 0, 0, 0
        )

    async def close(self):
        self._running = False
        if self.master:
            self.master.close()


# =============================================================================
# Fleet Manager (High-level API)
# =============================================================================
class FleetManager:
    """
    Manages both UAVs. Auto-detects real SITL connections; falls back to mock physics.
    """

    def __init__(self, use_mock: bool = False, home_lat: float = 26.7300, home_lon: float = 94.2300, home_alt: float = 100.0):
        self.use_mock = use_mock
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt = home_alt

        self.scout: MAVLinkConnection | MockPhysics
        self.sprayer: MAVLinkConnection | MockPhysics

        self._telemetry_subscribers: list[Callable[[Telemetry], None]] = []

        if use_mock:
            self._init_mock()
        else:
            self._init_real()

    def _init_mock(self):
        self.scout = MockPhysics(UAVType.SCOUT, self.home_lat, self.home_lon, self.home_alt)
        self.sprayer = MockPhysics(UAVType.SPRAYER, self.home_lat, self.home_lon, self.home_alt)
        # Mock loop will be started by the FastAPI lifespan or explicitly via start_mock_loop()
        self._mock_task: Optional[asyncio.Task] = None

    async def start_mock_loop(self):
        """Start the mock physics loop (must be called from async context)."""
        if self.use_mock and self._mock_task is None:
            self._mock_task = asyncio.create_task(self._mock_loop())

    def _init_real(self):
        self.scout = MAVLinkConnection(SystemIDs.SCOUT_SYSID, PORTS.SCOUT_MAVLINK_OUT)
        self.sprayer = MAVLinkConnection(SystemIDs.SPRAYER_SYSID, PORTS.SPRAYER_MAVLINK_OUT)
        self.scout.on_telemetry(self._on_telemetry)
        self.sprayer.on_telemetry(self._on_telemetry)

    async def connect(self) -> tuple[bool, bool]:
        if self.use_mock:
            return True, True
        scout_ok = await self.scout.connect()
        sprayer_ok = await self.sprayer.connect()
        return scout_ok, sprayer_ok

    def _on_telemetry(self, tel: Telemetry):
        for cb in self._telemetry_subscribers:
            cb(tel)

    def subscribe(self, callback: Callable[[Telemetry], None]):
        self._telemetry_subscribers.append(callback)

    async def _mock_loop(self):
        while True:
            self.scout.update()
            self.sprayer.update()
            self._on_telemetry(self.scout.get_telemetry())
            self._on_telemetry(self.sprayer.get_telemetry())
            await asyncio.sleep(0.1)  # 10Hz

    # ---- High-level Mission Commands ----
    def generate_scout_survey(self) -> list[Waypoint]:
        """Generate lawnmower survey waypoints for Section A-14 at 12m AGL."""
        wps = []
        spacing = GEOMETRY.GRID_SPACING_M
        alt = GEOMETRY.SURVEY_ALTITUDE_M

        # Convert local grid to lat/lon
        # Section A-14: x in [-30, 30], y in [-30, 30]
        # Lawnmower along X (North-South), stepping in Y (East-West)
        y = GEOMETRY.MIN_Y
        toggle = True
        while y <= GEOMETRY.MAX_Y:
            x_start = GEOMETRY.MIN_X if toggle else GEOMETRY.MAX_X
            x_end = GEOMETRY.MAX_X if toggle else GEOMETRY.MIN_X

            # Add waypoint at start of leg
            lat, lon = self._local_to_latlon(x_start, y)
            wps.append(Waypoint(lat=lat, lon=lon, alt=self.home_alt + alt))

            # Add waypoint at end of leg
            lat, lon = self._local_to_latlon(x_end, y)
            wps.append(Waypoint(lat=lat, lon=lon, alt=self.home_alt + alt))

            y += spacing
            toggle = not toggle

        return wps

    def generate_sprayer_sortie(self, hotspots: list[tuple[float, float]]) -> list[Waypoint]:
        """Generate spot-spray waypoints: dock -> hotspot1 -> hotspot2 -> ... -> dock."""
        wps = []
        alt = GEOMETRY.SPRAY_ALTITUDE_M

        # Start from dock
        wps.append(Waypoint(
            lat=self.home_lat, lon=self.home_lon, alt=self.home_alt + alt
        ))

        for hx, hy in hotspots:
            lat, lon = self._local_to_latlon(hx, hy)
            wps.append(Waypoint(
                lat=lat, lon=lon, alt=self.home_alt + alt,
                hold_time=GEOMETRY.HOVER_DWELL_S,
                spray_at_wp=True
            ))

        # Return to dock
        wps.append(Waypoint(
            lat=self.home_lat, lon=self.home_lon, alt=self.home_alt + alt
        ))

        return wps

    def _local_to_latlon(self, north: float, east: float) -> tuple[float, float]:
        lat = self.home_lat + (north / 111111.0)
        lon = self.home_lon + (east / (111111.0 * math.cos(math.radians(self.home_lat))))
        return lat, lon

    # ---- Scout Commands ----
    async def scout_arm_takeoff_survey(self):
        if self.use_mock:
            self.scout.arm()
            self.scout.set_mode("GUIDED")
            wps = self.generate_scout_survey()
            self.scout.set_waypoints(wps)
        else:
            await asyncio.get_event_loop().run_in_executor(None, self.scout.arm)
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.scout.set_mode, "GUIDED")
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.scout.takeoff, GEOMETRY.SURVEY_ALTITUDE_M)
            await asyncio.sleep(5)
            wps = self.generate_scout_survey()
            await asyncio.get_event_loop().run_in_executor(None, self.scout.upload_mission, wps)
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.scout.start_mission)

    async def scout_rtl(self):
        if self.use_mock:
            # Mock auto-RTL handled in physics
            pass
        else:
            await asyncio.get_event_loop().run_in_executor(None, self.scout.rtl)

    # ---- Sprayer Commands ----
    async def sprayer_arm_takeoff_spray(self, hotspots: list[tuple[float, float]]):
        if self.use_mock:
            self.sprayer.arm()
            self.sprayer.set_mode("GUIDED")
            wps = self.generate_sprayer_sortie(hotspots)
            self.sprayer.set_waypoints(wps)
        else:
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.arm)
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.set_mode, "GUIDED")
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.takeoff, GEOMETRY.SPRAY_ALTITUDE_M)
            await asyncio.sleep(5)
            wps = self.generate_sprayer_sortie(hotspots)
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.upload_mission, wps)
            await asyncio.sleep(1)
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.start_mission)

    async def sprayer_rtl(self):
        if self.use_mock:
            pass
        else:
            await asyncio.get_event_loop().run_in_executor(None, self.sprayer.rtl)

    def get_scout_telemetry(self) -> Optional[Telemetry]:
        if self.use_mock:
            return self.scout.get_telemetry()
        return self.scout.get_latest()

    def get_sprayer_telemetry(self) -> Optional[Telemetry]:
        if self.use_mock:
            return self.sprayer.get_telemetry()
        return self.sprayer.get_latest()

    async def close(self):
        if not self.use_mock:
            await self.scout.close()
            await self.sprayer.close()


# =============================================================================
# Singleton Instance (lazy initialization)
# =============================================================================
_fleet_manager: Optional[FleetManager] = None


def get_fleet_manager(use_mock: bool = False) -> FleetManager:
    global _fleet_manager
    if _fleet_manager is None:
        _fleet_manager = FleetManager(use_mock=use_mock)
    return _fleet_manager


async def close_fleet_manager():
    global _fleet_manager
    if _fleet_manager:
        await _fleet_manager.close()
        _fleet_manager = None