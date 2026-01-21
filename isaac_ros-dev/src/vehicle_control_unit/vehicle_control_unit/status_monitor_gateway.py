#!/usr/bin/env python3
"""
Status-only monitoring gateway for IGVC operations.
FastAPI serves a low-bandwidth JSON snapshot while rclpy collects telemetry.

Endpoints:
  GET /status
  GET /healthz
  GET /       (minimal HTML, auto-refresh at 1 Hz)

Optional security:
  Set env var DS_API_KEY and pass header X-API-Key: <key>

ROS params:
  frame_map: "map"
  frame_base: "base_link"

  # VESC left state topics (primitive numeric topics)
  vesc_left_prefix: "/left_vesc"
    expects:
      /left_vesc/state/input_voltage_v      (std_msgs/Float32)
      /left_vesc/state/input_current_a      (std_msgs/Float32)
      /left_vesc/state/motor_current_a      (std_msgs/Float32)
      /left_vesc/state/erpm                 (std_msgs/Float32)
      /left_vesc/state/duty                 (std_msgs/Float32)
      /left_vesc/state/fault_code           (std_msgs/Int32)  # adjust if different
      /left_vesc/state/temp_fet_c           (std_msgs/Float32)
      /left_vesc/state/temp_motor_c         (std_msgs/Float32)

  # MAVROS GPS (BEST_EFFORT QoS)
  gps_topic:     "/mavros/mavros/global_position/global"        (sensor_msgs/NavSatFix)
  gps_sat_topic: "/mavros/mavros/global_position/raw/satellites" (std_msgs/UInt32)

  localization_topic: "/odometry/filtered"             (nav_msgs/Odometry)
  nav_status_topic: "/navigate_to_pose/_action/status" (action_msgs/GoalStatusArray) (optional)
"""

from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry
from action_msgs.msg import GoalStatusArray
from tf2_ros import Buffer, TransformListener

# Primitive topics
from std_msgs.msg import Float32, Int32, UInt32  # If fault_code is not Int32, change here.

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse

# ------------------------------------------------------------------------------
# QoS presets
# ------------------------------------------------------------------------------
qos_reliable = QoSProfile(depth=10)
qos_reliable.reliability = ReliabilityPolicy.RELIABLE
qos_reliable.durability = DurabilityPolicy.VOLATILE

# MAVROS sensors commonly publish BEST_EFFORT
qos_sensor = QoSProfile(depth=10)
qos_sensor.reliability = ReliabilityPolicy.BEST_EFFORT
qos_sensor.durability = DurabilityPolicy.VOLATILE

API_KEY = os.environ.get("DS_API_KEY", "").strip()


def require_key(x_api_key: Optional[str]):
    if not API_KEY:
        return
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    status_summary: str = "unknown"  # idle | active | unknown


@dataclass
class TFHealth:
    ok: bool = False
    checked_unix: float = 0.0
    map_to_base: bool = False
    error: str = ""


@dataclass
class HealthSummary:
    ok: bool = False
    reasons: list[str] = None


class StatusBridge(Node):
    def __init__(self):
        super().__init__("status_monitor_gateway")

        # Parameters
        self.declare_parameter("frame_map", "map")
        self.declare_parameter("frame_base", "base_link")

        self.declare_parameter("vesc_left_prefix", "/left_vesc")

        # MAVROS topics
        self.declare_parameter("gps_topic", "/mavros/mavros/global_position/global")
        self.declare_parameter("gps_sat_topic", "/mavros/mavros/global_position/raw/satellites")

        self.declare_parameter("localization_topic", "/odometry/filtered")
        self.declare_parameter("nav_status_topic", "/navigate_to_pose/_action/status")

        self.frame_map = self.get_parameter("frame_map").value
        self.frame_base = self.get_parameter("frame_base").value

        vesc_left_prefix = self.get_parameter("vesc_left_prefix").value.rstrip("/")

        gps_topic = self.get_parameter("gps_topic").value
        gps_sat_topic = self.get_parameter("gps_sat_topic").value

        localization_topic = self.get_parameter("localization_topic").value
        nav_status_topic = self.get_parameter("nav_status_topic").value

        # Shared state
        self._lock = threading.Lock()
        self.vesc_left = VescSnapshot()
        self.gps = GPSSnapshot()
        self.gps_sats = SatSnapshot()
        self.loc = LocalizationSnapshot()
        self.nav = NavSnapshot()
        self.tf = TFHealth()

        # -------------------------
        # VESC Left subscriptions (RELIABLE)
        # -------------------------
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/input_voltage_v",
            self._on_left_input_voltage, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/input_current_a",
            self._on_left_input_current, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/motor_current_a",
            self._on_left_motor_current, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/erpm",
            self._on_left_erpm, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/duty",
            self._on_left_duty, qos_reliable
        )
        self.create_subscription(
            Int32, f"{vesc_left_prefix}/state/fault_code",
            self._on_left_fault, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/temp_fet_c",
            self._on_left_temp_fet, qos_reliable
        )
        self.create_subscription(
            Float32, f"{vesc_left_prefix}/state/temp_motor_c",
            self._on_left_temp_motor, qos_reliable
        )

        # -------------------------
        # MAVROS GPS subscriptions (BEST_EFFORT)
        # -------------------------
        self.create_subscription(NavSatFix, gps_topic, self._on_gps, qos_sensor)
        self.create_subscription(UInt32, gps_sat_topic, self._on_gps_sats, qos_sensor)

        # -------------------------
        # Other telemetry
        # -------------------------
        self.create_subscription(Odometry, localization_topic, self._on_loc, qos_reliable)
        self.create_subscription(GoalStatusArray, nav_status_topic, self._on_nav_status, qos_reliable)

        # TF buffer/listener
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_timer(0.5, self._check_tf)

        self.get_logger().info("Status monitor gateway started (VESC + MAVROS satellites).")
        self.get_logger().info(f"VESC left prefix: {vesc_left_prefix}")
        self.get_logger().info(f"GPS fix topic:     {gps_topic}")
        self.get_logger().info(f"GPS sats topic:    {gps_sat_topic}")
        self.get_logger().info(f"TF check: {self.frame_map} -> {self.frame_base}")

    # ---- VESC Left callbacks ----
    def _touch_vesc_left(self):
        self.vesc_left.present = True
        self.vesc_left.stamp_unix = time.time()

    def _on_left_input_voltage(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.input_voltage_v = float(msg.data)

    def _on_left_input_current(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.input_current_a = float(msg.data)

    def _on_left_motor_current(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.motor_current_a = float(msg.data)

    def _on_left_erpm(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.erpm = float(msg.data)

    def _on_left_duty(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.duty = float(msg.data)

    def _on_left_fault(self, msg: Int32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.fault_code = int(msg.data)

    def _on_left_temp_fet(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.temp_fet_c = float(msg.data)

    def _on_left_temp_motor(self, msg: Float32):
        with self._lock:
            self._touch_vesc_left()
            self.vesc_left.temp_motor_c = float(msg.data)

    # ---- GPS / satellites ----
    def _on_gps(self, msg: NavSatFix):
        with self._lock:
            self.gps.present = True
            self.gps.stamp_unix = time.time()
            self.gps.lat = float(msg.latitude)
            self.gps.lon = float(msg.longitude)
            self.gps.alt_m = float(msg.altitude) if msg.altitude == msg.altitude else None
            self.gps.status = int(msg.status.status)
            self.gps.service = int(msg.status.service)
            if len(msg.position_covariance) >= 9:
                self.gps.cov_xx = float(msg.position_covariance[0])
                self.gps.cov_yy = float(msg.position_covariance[4])
                self.gps.cov_zz = float(msg.position_covariance[8])

    def _on_gps_sats(self, msg: UInt32):
        with self._lock:
            self.gps_sats.present = True
            self.gps_sats.stamp_unix = time.time()
            self.gps_sats.satellites_visible = int(msg.data)

    # ---- Localization / Nav ----
    def _on_loc(self, msg: Odometry):
        import math
        q = msg.pose.pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        with self._lock:
            self.loc.present = True
            self.loc.stamp_unix = time.time()
            self.loc.frame_id = msg.header.frame_id
            self.loc.child_frame_id = msg.child_frame_id
            self.loc.x = float(msg.pose.pose.position.x)
            self.loc.y = float(msg.pose.pose.position.y)
            self.loc.yaw_rad = float(yaw)
            cov = msg.pose.covariance
            if len(cov) == 36:
                self.loc.cov_xx = float(cov[0])
                self.loc.cov_yy = float(cov[7])

    def _on_nav_status(self, msg: GoalStatusArray):
        active = 0
        for st in msg.status_list:
            if st.status in (1, 2):  # ACCEPTED=1, EXECUTING=2
                active += 1
        with self._lock:
            self.nav.present = True
            self.nav.stamp_unix = time.time()
            self.nav.active_goals = int(active)
            self.nav.status_summary = "active" if active > 0 else "idle"

    def _check_tf(self):
        ok = False
        err = ""
        try:
            _ = self.tf_buffer.lookup_transform(
                self.frame_map, self.frame_base, rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05)
            )
            ok = True
        except Exception as e:
            ok = False
            err = str(e)

        with self._lock:
            self.tf.checked_unix = time.time()
            self.tf.map_to_base = ok
            self.tf.ok = ok
            self.tf.error = "" if ok else err

    def compute_health_locked(self) -> HealthSummary:
        reasons: list[str] = []

        if not self.tf.map_to_base:
            reasons.append(f"TF missing: {self.frame_map}->{self.frame_base}")

        # VESC fault is a hard red flag (if present and non-zero)
        if self.vesc_left.present and (self.vesc_left.fault_code is not None):
            if self.vesc_left.fault_code != 0:
                reasons.append(f"Left VESC fault_code={self.vesc_left.fault_code}")

        # Low voltage heuristic (tune to your battery pack; example thresholds)
        if self.vesc_left.present and (self.vesc_left.input_voltage_v is not None):
            if self.vesc_left.input_voltage_v < 20.0:
                reasons.append(f"Low pack voltage: {self.vesc_left.input_voltage_v:.2f} V")

        # Satellites (tune threshold; 10 is a reasonable operator alert)
        if self.gps_sats.present and (self.gps_sats.satellites_visible is not None):
            if self.gps_sats.satellites_visible < 10:
                reasons.append(f"GPS weak: sats={self.gps_sats.satellites_visible}")

        ok = (len(reasons) == 0)
        return HealthSummary(ok=ok, reasons=reasons)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "node": self.get_name(),
                "time_unix": time.time(),
                "vesc_left": asdict(self.vesc_left),
                "gps": asdict(self.gps),
                "gps_sats": asdict(self.gps_sats),
                "localization": asdict(self.loc),
                "nav": asdict(self.nav),
                "tf": asdict(self.tf),
                "health": asdict(self.compute_health_locked()),
            }


# ---------------- FastAPI ----------------

app = FastAPI(title="IGVC Status Monitor", version="0.3.0")
_bridge: Optional[StatusBridge] = None


@app.get("/", response_class=HTMLResponse)
def root(x_api_key: Optional[str] = Header(default=None)):
    require_key(x_api_key)

    # If DS_API_KEY is enabled, reuse the validated header value for subsequent AJAX calls.
    # If DS_API_KEY is not enabled, leave it empty.
    key_for_browser = x_api_key if API_KEY else ""

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>IGVC Status Monitor</title>

  <!-- Leaflet (map) -->
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>

  <style>
    body {{ font-family: system-ui, sans-serif; margin: 16px; max-width: 1400px; }}
    .grid {{ display: grid; grid-template-columns: 420px 1fr; gap: 12px; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; }}
    button {{ padding: 10px 12px; }}
    pre {{ background: #f7f7f7; padding: 10px; border-radius: 10px; overflow:auto; max-height: 360px; }}
    #map {{ height: 680px; border-radius: 10px; border: 1px solid #ddd; }}
    .kv {{ display: grid; grid-template-columns: 140px 1fr; gap: 6px 10px; font-size: 14px; }}
    .muted {{ color: #666; font-size: 12px; }}
    .ok {{ color: #136f2d; font-weight: 600; }}
    .bad {{ color: #a11; font-weight: 600; }}
  </style>
</head>

<body>
  <h2>IGVC Status Monitor (VESC + GPS)</h2>
  <div class="grid">
    <div class="card">
      <div class="row" style="align-items:center; justify-content: space-between;">
        <div>
          <div><span id="healthBadge" class="muted">Health: unknown</span></div>
          <div class="muted">Refresh: 1 Hz</div>
        </div>
        <div class="row">
          <button onclick="centerOnRobot()">Center</button>
          <button onclick="clearTrail()">Clear trail</button>
          <button onclick="refresh()">Refresh</button>
        </div>
      </div>

      <hr/>

      <div class="kv">
        <div>GPS</div><div id="gpsLine" class="muted">—</div>
        <div>Satellites</div><div id="satLine" class="muted">—</div>
        <div>Cov (m)</div><div id="covLine" class="muted">—</div>
        <div>Age (s)</div><div id="ageLine" class="muted">—</div>
      </div>

      <hr/>

      <h3 style="margin: 8px 0;">Health</h3>
      <pre id="health"></pre>

      <h3 style="margin: 8px 0;">Full Status</h3>
      <pre id="status"></pre>
    </div>

    <div class="card">
      <h3 style="margin-top: 0;">GPS Map (live)</h3>
      <div class="muted" style="margin-bottom: 8px;">
        Trail shows the last 300 points. Accuracy circle approximates 1σ from NavSatFix covariance.
        (Requires internet for map tiles.)
      </div>
      <div id="map"></div>
    </div>
  </div>

<script>
const DS_API_KEY = {repr(key_for_browser)};
const MAX_TRAIL = 300;

function fetchHeaders() {{
  if (DS_API_KEY && DS_API_KEY.length > 0) {{
    return {{ 'X-API-Key': DS_API_KEY }};
  }}
  return {{}};
}}

let timer = null;

// Map state
let map = null;
let robotMarker = null;
let trailLine = null;
let accuracyCircle = null;
let trail = [];
let lastLatLon = null;

function initMap() {{
  // Default: Cookeville-ish; will recenter on first valid GPS.
  map = L.map('map').setView([36.162, -85.501], 17);

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 20,
    attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);

  robotMarker = L.circleMarker([36.162, -85.501], {{
    radius: 7,
    weight: 2,
    fillOpacity: 0.8
  }}).addTo(map);

  trailLine = L.polyline([], {{ weight: 3 }}).addTo(map);

  accuracyCircle = L.circle([36.162, -85.501], {{
    radius: 3,
    weight: 1,
    fillOpacity: 0.08
  }}).addTo(map);
}}

function clearTrail() {{
  trail = [];
  if (trailLine) trailLine.setLatLngs(trail);
}}

function centerOnRobot() {{
  if (!map) return;
  if (lastLatLon) map.setView(lastLatLon, Math.max(map.getZoom(), 18));
}}

function safeNum(x) {{
  return (typeof x === 'number' && isFinite(x)) ? x : null;
}}

function updateMapFromStatus(j) {{
  const gps = j.gps || {{}};
  const sats = j.gps_sats || {{}};

  const lat = safeNum(gps.lat);
  const lon = safeNum(gps.lon);

  if (lat === null || lon === null) {{
    return;
  }}

  lastLatLon = [lat, lon];

  // Add to trail (avoid duplicates by tiny threshold)
  const last = trail.length ? trail[trail.length - 1] : null;
  const eps = 1e-7;
  if (!last || (Math.abs(last[0]-lat) > eps || Math.abs(last[1]-lon) > eps)) {{
    trail.push([lat, lon]);
    if (trail.length > MAX_TRAIL) trail.shift();
  }}

  robotMarker.setLatLng([lat, lon]);
  trailLine.setLatLngs(trail);

  // Approximate 1σ accuracy radius from covariance (meters)
  // Use sqrt(mean(cov_xx, cov_yy)) when available; fallback to 3 m.
  const cov_xx = safeNum(gps.cov_xx);
  const cov_yy = safeNum(gps.cov_yy);
  let sigma_m = 3.0;
  if (cov_xx !== null && cov_yy !== null && cov_xx > 0 && cov_yy > 0) {{
    sigma_m = Math.sqrt(0.5 * (cov_xx + cov_yy));
    // Clamp to avoid ridiculous circles if covariance is corrupted
    sigma_m = Math.min(Math.max(sigma_m, 0.5), 50.0);
  }}
  accuracyCircle.setLatLng([lat, lon]);
  accuracyCircle.setRadius(sigma_m);

  // Auto-center first time we get GPS
  if (trail.length === 1) {{
    map.setView([lat, lon], 18);
  }}
}}

function updateLeftPanel(j) {{
  const gps = j.gps || {{}};
  const sats = j.gps_sats || {{}};

  const lat = safeNum(gps.lat);
  const lon = safeNum(gps.lon);

  document.getElementById('gpsLine').textContent =
    (lat !== null && lon !== null) ? `${{lat.toFixed(7)}}, ${{lon.toFixed(7)}}` : '—';

  const sv = (sats && sats.satellites_visible !== null && sats.satellites_visible !== undefined)
    ? sats.satellites_visible : null;
  document.getElementById('satLine').textContent = (sv !== null) ? String(sv) : '—';

  const cov_xx = safeNum(gps.cov_xx);
  const cov_yy = safeNum(gps.cov_yy);
  if (cov_xx !== null && cov_yy !== null && cov_xx > 0 && cov_yy > 0) {{
    const sx = Math.sqrt(cov_xx);
    const sy = Math.sqrt(cov_yy);
    document.getElementById('covLine').textContent = `σx=${{sx.toFixed(2)}} m, σy=${{sy.toFixed(2)}} m`;
  }} else {{
    document.getElementById('covLine').textContent = '—';
  }}

  const now = (typeof j.time_unix === 'number') ? j.time_unix : (Date.now()/1000.0);
  const age = (typeof gps.stamp_unix === 'number') ? (now - gps.stamp_unix) : null;
  document.getElementById('ageLine').textContent = (age !== null) ? age.toFixed(2) : '—';

  const healthOk = j.health && j.health.ok === true;
  const badge = document.getElementById('healthBadge');
  badge.textContent = `Health: ${{healthOk ? 'OK' : 'CHECK'}}`;
  badge.className = healthOk ? 'ok' : 'bad';
}}

async function refresh() {{
  try {{
    const r = await fetch('/status', {{ cache: 'no-store', headers: fetchHeaders() }});
    if (!r.ok) throw new Error(`HTTP ${{r.status}}`);
    const j = await r.json();

    document.getElementById('health').textContent =
      JSON.stringify(j.health, null, 2);

    document.getElementById('status').textContent =
      JSON.stringify(j, null, 2);

    updateLeftPanel(j);
    updateMapFromStatus(j);

  }} catch (e) {{
    document.getElementById('health').textContent =
      JSON.stringify({{ ok: false, error: String(e) }}, null, 2);
  }}
}}

initMap();
refresh();
timer = setInterval(refresh, 1000);
</script>

</body>
</html>
"""



@app.get("/status")
def status(x_api_key: Optional[str] = Header(default=None)):
    require_key(x_api_key)
    if _bridge is None:
        raise HTTPException(status_code=503, detail="ROS bridge not ready")
    return _bridge.snapshot()


@app.get("/healthz")
def healthz(x_api_key: Optional[str] = Header(default=None)):
    require_key(x_api_key)
    if _bridge is None:
        raise HTTPException(status_code=503, detail="ROS bridge not ready")
    s = _bridge.snapshot()
    return {"ok": bool(s["health"]["ok"]), "reasons": s["health"]["reasons"]}


def _spin_ros(node: StatusBridge):
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()


def main():
    global _bridge

    rclpy.init()
    _bridge = StatusBridge()

    t = threading.Thread(target=_spin_ros, args=(_bridge,), daemon=True)
    t.start()

    import uvicorn
    host = os.environ.get("DS_HOST", "0.0.0.0")
    port = int(os.environ.get("DS_PORT", "8081"))
    uvicorn.run(app, host=host, port=port, log_level="info")

    rclpy.shutdown()


if __name__ == "__main__":
    main()
