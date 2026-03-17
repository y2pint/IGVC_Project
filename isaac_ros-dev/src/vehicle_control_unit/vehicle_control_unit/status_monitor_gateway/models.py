from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TopicFreshness:
    present: bool = False
    stamp_unix: float = 0.0
    msg_count: int = 0
    ema_hz: float = 0.0
    age_sec: Optional[float] = None
    _last_rx_unix: float = 0.0

    def touch(self, now_unix: float) -> None:
        self.msg_count += 1
        if self.present and self._last_rx_unix > 0.0:
            dt = now_unix - self._last_rx_unix
            if dt > 1e-4:
                hz = 1.0 / dt
                alpha = 0.2
                self.ema_hz = hz if self.ema_hz <= 0.0 else (1 - alpha) * self.ema_hz + alpha * hz
        self.present = True
        self._last_rx_unix = now_unix
        self.stamp_unix = now_unix

    def update_age(self, now_unix: float) -> None:
        self.age_sec = None if not self.present else max(0.0, now_unix - self.stamp_unix)


@dataclass
class VescSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    input_voltage_v: Optional[float] = None
    input_current_a: Optional[float] = None
    motor_current_a: Optional[float] = None
    erpm: Optional[float] = None
    duty: Optional[float] = None
    fault_code: Optional[int] = None
    temp_fet_c: Optional[float] = None
    temp_motor_c: Optional[float] = None


@dataclass
class GPSSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_m: Optional[float] = None
    status: Optional[int] = None
    service: Optional[int] = None
    cov_xx: Optional[float] = None
    cov_yy: Optional[float] = None
    cov_zz: Optional[float] = None


@dataclass
class SatSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    satellites_visible: Optional[int] = None


@dataclass
class OdomGpsSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    frame_id: Optional[str] = None
    child_frame_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    yaw_rad: Optional[float] = None


@dataclass
class LocalizationSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    frame_id: Optional[str] = None
    child_frame_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    yaw_rad: Optional[float] = None
    cov_xx: Optional[float] = None
    cov_yy: Optional[float] = None


@dataclass
class NavSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    active_goals: int = 0
    status_summary: str = "unknown"


@dataclass
class TFHealth:
    ok: bool = False
    checked_unix: float = 0.0
    map_to_odom: bool = False
    odom_to_base: bool = False
    map_to_base: bool = False
    error_map_odom: str = ""
    error_odom_base: str = ""
    error_map_base: str = ""


@dataclass
class GPSValidity:
    cls: str = "unknown"
    reason: str = "unknown"
    age_sec: Optional[float] = None
    sats: Optional[int] = None
    rms_cov_m: Optional[float] = None


@dataclass
class CostmapSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    frame_id: Optional[str] = None
    resolution: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    origin_x: Optional[float] = None
    origin_y: Optional[float] = None
    ds: int = 1
    render_w: int = 0
    render_h: int = 0
    gray: Optional[List[int]] = None


@dataclass
class HealthSummary:
    ok: bool = False
    reasons: list[str] = None


@dataclass
class MissionWaypoint:
    lat: float = 0.0
    lon: float = 0.0
    name: str = ''


@dataclass
class MissionSnapshot:
    present: bool = False
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
    nav_enabled: bool = False
    waypoints: Optional[List[MissionWaypoint]] = None
    pose_x: Optional[float] = None
    pose_y: Optional[float] = None
    pose_yaw_rad: Optional[float] = None
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    carrot_x: Optional[float] = None
    carrot_y: Optional[float] = None
    waypoint_index: Optional[int] = None
    mission_complete: bool = False
    acceptance_radius_m: float = 2.5


# ── NEW: BT Snapshot ──────────────────────────────────────────────────────────
@dataclass
class BTNodeEvent:
    node_name: str = ""
    previous_status: str = ""
    current_status: str = ""
    stamp_unix: float = 0.0


@dataclass
class BTSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    last_events: List[BTNodeEvent] = field(default_factory=list)
    recovery_active: bool = False
    follow_path_status: str = "unknown"
    compute_path_status: str = "unknown"
    recovery_count: int = 0


# ── NEW: cmd_vel Snapshot ─────────────────────────────────────────────────────
@dataclass
class CmdVelSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    vx: Optional[float] = None
    vy: Optional[float] = None
    wz: Optional[float] = None


# ── NEW: MAVROS / ArduPilot Snapshot ─────────────────────────────────────────
@dataclass
class MavrosSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    connected: bool = False
    armed: bool = False
    mode: str = "unknown"
    system_status: str = "unknown"
    battery_voltage: Optional[float] = None
    battery_current: Optional[float] = None
    battery_remaining: Optional[float] = None


# ── NEW: Path Snapshot ────────────────────────────────────────────────────────
@dataclass
class PathSnapshot:
    present: bool = False
    stamp_unix: float = 0.0
    frame_id: str = ""
    # Downsampled path points as flat [x0,y0, x1,y1, ...] for JSON efficiency
    points_xy: Optional[List[float]] = None
    point_count: int = 0