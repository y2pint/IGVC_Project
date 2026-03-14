from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Optional, Dict, Any, List, Tuple

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from rclpy.qos import QoSProfile

from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry, OccupancyGrid
from action_msgs.msg import GoalStatusArray
from tf2_ros import Buffer, TransformListener
from std_msgs.msg import Float32, Float64, Int32, UInt32, Bool, String
from geometry_msgs.msg import PoseStamped

from .qos import qos_reliable, qos_sensor
from .utils import now_unix, clamp, yaw_from_quat
from .models import (
    TopicFreshness, VescSnapshot, GPSSnapshot, SatSnapshot,
    OdomGpsSnapshot, LocalizationSnapshot, NavSnapshot,
    TFHealth, GPSValidity, CostmapSnapshot, HealthSummary, MissionSnapshot, MissionWaypoint,
)


class StatusBridge(Node):
    def __init__(self):
        super().__init__("status_monitor_gateway")

        # Frames
        self.declare_parameter("frame_map", "map")
        self.declare_parameter("frame_odom", "odom")
        self.declare_parameter("frame_base", "base_link")

        # Topics
        self.declare_parameter("vesc_left_prefix", "/left_vesc")
        self.declare_parameter("vesc_right_prefix", "/right_vesc")
        self.declare_parameter("gps_topic", "/mavros/mavros/global_position/global")
        self.declare_parameter("gps_sat_topic", "/mavros/mavros/global_position/raw/satellites")
        self.declare_parameter("gps_compass_topic", "/mavros/mavros/global_position/compass_hdg")
        self.declare_parameter("odom_gps_topic", "/odometry/gps")
        self.declare_parameter("localization_topic", "/odometry/local")
        self.declare_parameter("nav_status_topic", "/navigate_to_pose/_action/status")
        self.declare_parameter("local_costmap_topic", "/local_costmap/costmap")
        self.declare_parameter("global_costmap_topic", "/global_costmap/costmap")

        # Mission planner topics
        self.declare_parameter("mission_pose_topic",              "/mission/global_pose_xy")
        self.declare_parameter("mission_target_topic",            "/mission/current_waypoint_xy")
        self.declare_parameter("mission_carrot_topic",            "/mission/carrot_target")
        self.declare_parameter("mission_index_topic",             "/mission/waypoint_index")
        self.declare_parameter("mission_complete_topic",          "/mission/mission_complete")
        self.declare_parameter("mission_waypoints_latlon_topic",  "/mission/waypoints_latlon")
        self.declare_parameter("mission_origin_topic",            "/mission/origin_fix")
        self.declare_parameter("mission_nav_enabled_topic",       "/mission/navigation_enabled")
        self.declare_parameter("mission_cancel_topic",            "/mission/cancel_nav_goal")
        self.declare_parameter("mission_acceptance_radius_m", 2.5)
        self.declare_parameter("mission_waypoints_file", "")

        self.frame_map = self.get_parameter("frame_map").value
        self.frame_odom = self.get_parameter("frame_odom").value
        self.frame_base = self.get_parameter("frame_base").value

        vesc_left_prefix = self.get_parameter("vesc_left_prefix").value.rstrip("/")
        vesc_right_prefix = self.get_parameter("vesc_right_prefix").value.rstrip("/")
        gps_topic = self.get_parameter("gps_topic").value
        gps_sat_topic = self.get_parameter("gps_sat_topic").value
        gps_compass_topic = self.get_parameter("gps_compass_topic").value
        odom_gps_topic = self.get_parameter("odom_gps_topic").value
        localization_topic = self.get_parameter("localization_topic").value
        nav_status_topic = self.get_parameter("nav_status_topic").value
        local_costmap_topic = self.get_parameter("local_costmap_topic").value
        global_costmap_topic = self.get_parameter("global_costmap_topic").value

        mission_pose_topic    = self.get_parameter("mission_pose_topic").value
        mission_target_topic  = self.get_parameter("mission_target_topic").value
        mission_carrot_topic  = self.get_parameter("mission_carrot_topic").value
        mission_index_topic   = self.get_parameter("mission_index_topic").value
        mission_complete_topic = self.get_parameter("mission_complete_topic").value
        mission_waypoints_latlon_topic = self.get_parameter("mission_waypoints_latlon_topic").value
        mission_origin_topic  = self.get_parameter("mission_origin_topic").value
        mission_nav_enabled_topic = self.get_parameter("mission_nav_enabled_topic").value
        mission_cancel_topic  = self.get_parameter("mission_cancel_topic").value
        self._mission_acceptance_radius_m = float(
            self.get_parameter("mission_acceptance_radius_m").value)

        # Shared state
        self._lock = threading.Lock()
        self.vesc_left = VescSnapshot()
        self.vesc_right = VescSnapshot()
        self.gps = GPSSnapshot()
        self.gps_sats = SatSnapshot()
        self.odom_gps = OdomGpsSnapshot()
        self.loc = LocalizationSnapshot()
        self.nav = NavSnapshot()
        self.tf = TFHealth()
        self.gps_validity = GPSValidity()

        self.costmap_local = CostmapSnapshot()
        self.costmap_global = CostmapSnapshot()

        self.mission = MissionSnapshot()

        # Publishers for mission control
        self._nav_enabled_pub = self.create_publisher(Bool, mission_nav_enabled_topic, qos_reliable)
        self._cancel_pub      = self.create_publisher(Bool, mission_cancel_topic,      qos_reliable)
        self._waypoints_latlon_pub = self.create_publisher(String, mission_waypoints_latlon_topic, qos_reliable)

        # Subscribe back to navigation_enabled so dashboard reflects actual state
        self.create_subscription(Bool, mission_nav_enabled_topic, self._on_nav_enabled_echo, qos_reliable)

        # Topic freshness
        self.topic_fresh: Dict[str, TopicFreshness] = {
            "gps_fix": TopicFreshness(),
            "gps_sats": TopicFreshness(),
            "odom_gps": TopicFreshness(),
            "localization": TopicFreshness(),
            "nav_status": TopicFreshness(),
            "vesc_left": TopicFreshness(),
            "vesc_right": TopicFreshness(),
            "costmap_local": TopicFreshness(),
            "costmap_global": TopicFreshness(),
        }

        # -------------------------
        # VESC Left subscriptions (RELIABLE)
        # -------------------------
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/input_voltage_v",
                                 self._on_left_input_voltage, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/input_current_a",
                                 self._on_left_input_current, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/motor_current_a",
                                 self._on_left_motor_current, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/erpm",
                                 self._on_left_erpm, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/duty",
                                 self._on_left_duty, qos_reliable)
        self.create_subscription(Int32, f"{vesc_left_prefix}/state/fault_code",
                                 self._on_left_fault, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/temp_fet_c",
                                 self._on_left_temp_fet, qos_reliable)
        self.create_subscription(Float32, f"{vesc_left_prefix}/state/temp_motor_c",
                                 self._on_left_temp_motor, qos_reliable)

        # -------------------------
        # VESC Right subscriptions (RELIABLE)
        # -------------------------
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/input_voltage_v",
                                 self._on_right_input_voltage, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/input_current_a",
                                 self._on_right_input_current, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/motor_current_a",
                                 self._on_right_motor_current, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/erpm",
                                 self._on_right_erpm, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/duty",
                                 self._on_right_duty, qos_reliable)
        self.create_subscription(Int32, f"{vesc_right_prefix}/state/fault_code",
                                 self._on_right_fault, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/temp_fet_c",
                                 self._on_right_temp_fet, qos_reliable)
        self.create_subscription(Float32, f"{vesc_right_prefix}/state/temp_motor_c",
                                 self._on_right_temp_motor, qos_reliable)

        # -------------------------
        # GPS (BEST_EFFORT)
        # -------------------------
        self.create_subscription(NavSatFix, gps_topic, self._on_gps, qos_sensor)
        self.create_subscription(UInt32, gps_sat_topic, self._on_gps_sats, qos_sensor)
        self.create_subscription(Float64, gps_compass_topic, self._on_gps_compass, qos_sensor)

        # -------------------------
        # /odometry/gps (BEST_EFFORT is fine)
        # -------------------------
        self.create_subscription(Odometry, odom_gps_topic, self._on_odom_gps, qos_sensor)

        # -------------------------
        # Other telemetry
        # -------------------------
        self.create_subscription(Odometry, localization_topic, self._on_loc, qos_reliable)
        self.create_subscription(GoalStatusArray, nav_status_topic, self._on_nav_status, qos_reliable)

        # -------------------------
        # Costmaps
        # -------------------------
        self.create_subscription(OccupancyGrid, local_costmap_topic, self._on_costmap_local, qos_sensor)
        self.create_subscription(OccupancyGrid, global_costmap_topic, self._on_costmap_global, qos_sensor)

        # -------------------------
        # Mission planner topics
        # -------------------------
        self.create_subscription(NavSatFix,   mission_origin_topic,  self._on_mission_origin,  qos_reliable)
        self.create_subscription(PoseStamped, mission_pose_topic,    self._on_mission_pose,    qos_sensor)
        self.create_subscription(PoseStamped, mission_target_topic,  self._on_mission_target,  qos_sensor)
        self.create_subscription(PoseStamped, mission_carrot_topic,  self._on_mission_carrot,  qos_sensor)
        self.create_subscription(Int32,       mission_index_topic,   self._on_mission_index,   qos_reliable)
        self.create_subscription(Bool,        mission_complete_topic, self._on_mission_complete, qos_reliable)
        self.create_subscription(String,      mission_waypoints_latlon_topic, self._on_mission_waypoints_latlon, qos_reliable)

        # TF
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_timer(0.5, self._check_tf)
        self.create_timer(0.5, self._compute_gps_validity)

        self.get_logger().info("Status monitor gateway started (VESC + GPS + TF + costmaps).")
        self.get_logger().info(f"TF check: {self.frame_map}->{self.frame_odom}, {self.frame_odom}->{self.frame_base}")
        self.get_logger().info(f"Local costmap:  {local_costmap_topic}")
        self.get_logger().info(f"Global costmap: {global_costmap_topic}")

    # ---- VESC ----
    def _touch_vesc_left(self):
        t = now_unix()
        self.vesc_left.present = True
        self.vesc_left.stamp_unix = t
        self.topic_fresh["vesc_left"].touch(t)

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

    # ---- VESC Right ----
    def _touch_vesc_right(self):
        t = now_unix()
        self.vesc_right.present = True
        self.vesc_right.stamp_unix = t
        self.topic_fresh["vesc_right"].touch(t)

    def _on_right_input_voltage(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.input_voltage_v = float(msg.data)

    def _on_right_input_current(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.input_current_a = float(msg.data)

    def _on_right_motor_current(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.motor_current_a = float(msg.data)

    def _on_right_erpm(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.erpm = float(msg.data)

    def _on_right_duty(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.duty = float(msg.data)

    def _on_right_fault(self, msg: Int32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.fault_code = int(msg.data)

    def _on_right_temp_fet(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.temp_fet_c = float(msg.data)

    def _on_right_temp_motor(self, msg: Float32):
        with self._lock:
            self._touch_vesc_right()
            self.vesc_right.temp_motor_c = float(msg.data)

    # ---- GPS ----
    def _on_gps(self, msg: NavSatFix):
        t = now_unix()
        with self._lock:
            self.topic_fresh["gps_fix"].touch(t)

            self.gps.present = True
            self.gps.stamp_unix = t
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
        t = now_unix()
        with self._lock:
            self.topic_fresh["gps_sats"].touch(t)
            self.gps_sats.present = True
            self.gps_sats.stamp_unix = t
            self.gps_sats.satellites_visible = int(msg.data)

    def _on_gps_compass(self, msg: Float64):
        with self._lock:
            self.gps.compass_hdg_deg = float(msg.data)

    # ---- /odometry/gps ----
    def _on_odom_gps(self, msg: Odometry):
        yaw = yaw_from_quat(msg.pose.pose.orientation)
        t = now_unix()
        with self._lock:
            self.topic_fresh["odom_gps"].touch(t)

            self.odom_gps.present = True
            self.odom_gps.stamp_unix = t
            self.odom_gps.frame_id = msg.header.frame_id
            self.odom_gps.child_frame_id = msg.child_frame_id
            self.odom_gps.x = float(msg.pose.pose.position.x)
            self.odom_gps.y = float(msg.pose.pose.position.y)
            self.odom_gps.yaw_rad = float(yaw)

    # ---- Localization ----
    def _on_loc(self, msg: Odometry):
        yaw = yaw_from_quat(msg.pose.pose.orientation)
        t = now_unix()
        with self._lock:
            self.topic_fresh["localization"].touch(t)

            self.loc.present = True
            self.loc.stamp_unix = t
            self.loc.frame_id = msg.header.frame_id
            self.loc.child_frame_id = msg.child_frame_id
            self.loc.x = float(msg.pose.pose.position.x)
            self.loc.y = float(msg.pose.pose.position.y)
            self.loc.yaw_rad = float(yaw)
            cov = msg.pose.covariance
            if len(cov) == 36:
                self.loc.cov_xx = float(cov[0])
                self.loc.cov_yy = float(cov[7])

    # ---- Nav status ----
    def _on_nav_status(self, msg: GoalStatusArray):
        active = 0
        for st in msg.status_list:
            if st.status in (1, 2):  # ACCEPTED=1, EXECUTING=2
                active += 1
        t = now_unix()
        with self._lock:
            self.topic_fresh["nav_status"].touch(t)

            self.nav.present = True
            self.nav.stamp_unix = t
            self.nav.active_goals = int(active)
            self.nav.status_summary = "active" if active > 0 else "idle"

    # ---- Costmap handling ----
    @staticmethod
    def render_costmap_downsample(msg: OccupancyGrid, max_dim: int = 240) -> CostmapSnapshot:
        """
        Convert OccupancyGrid into a downsampled grayscale array for browser canvas.
        Output gray is row-major with TOP row first (canvas-friendly).
        Mapping:
          unknown (-1) -> 127
          free (0)     -> 255
          occupied(100)-> 0
          intermediate -> linear
        """
        snap = CostmapSnapshot()
        snap.present = True
        snap.stamp_unix = now_unix()
        snap.frame_id = msg.header.frame_id

        info = msg.info
        W = int(info.width)
        H = int(info.height)
        r = float(info.resolution)
        ox = float(info.origin.position.x)
        oy = float(info.origin.position.y)

        snap.resolution = r
        snap.width = W
        snap.height = H
        snap.origin_x = ox
        snap.origin_y = oy

        if W <= 0 or H <= 0:
            snap.gray = None
            return snap

        ds = max(1, int((max(W, H) + max_dim - 1) // max_dim))
        render_w = max(1, W // ds)
        render_h = max(1, H // ds)

        snap.ds = ds
        snap.render_w = render_w
        snap.render_h = render_h

        data = msg.data
        gray: List[int] = []
        for ry in range(render_h):
            y0 = ry * ds
            orig_y = (H - 1) - y0
            base = orig_y * W
            for rx in range(render_w):
                x0 = rx * ds
                idx = base + x0
                v = int(data[idx]) if 0 <= idx < len(data) else -1
                if v < 0:
                    g = 127
                else:
                    g = int(clamp(255 - (v * 255 / 100.0), 0, 255))
                gray.append(g)

        snap.gray = gray
        return snap

    def _on_costmap_local(self, msg: OccupancyGrid):
        t = now_unix()
        with self._lock:
            self.topic_fresh["costmap_local"].touch(t)
            self.costmap_local = self.render_costmap_downsample(msg, max_dim=240)

    def _on_costmap_global(self, msg: OccupancyGrid):
        t = now_unix()
        with self._lock:
            self.topic_fresh["costmap_global"].touch(t)
            self.costmap_global = self.render_costmap_downsample(msg, max_dim=240)

    # ---- TF ----
    def _check_tf_one(self, parent: str, child: str) -> Tuple[bool, str]:
        try:
            _ = self.tf_buffer.lookup_transform(
                parent, child, rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05)
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def _check_tf(self):
        ok_mo, err_mo = self._check_tf_one(self.frame_map, self.frame_odom)
        ok_ob, err_ob = self._check_tf_one(self.frame_odom, self.frame_base)
        ok_mb, err_mb = self._check_tf_one(self.frame_map, self.frame_base)

        with self._lock:
            self.tf.checked_unix = now_unix()
            self.tf.map_to_odom = ok_mo
            self.tf.odom_to_base = ok_ob
            self.tf.map_to_base = ok_mb
            self.tf.error_map_odom = "" if ok_mo else err_mo
            self.tf.error_odom_base = "" if ok_ob else err_ob
            self.tf.error_map_base = "" if ok_mb else err_mb
            self.tf.ok = bool(ok_mo and ok_ob)

    # ---- GPS validity ----
    def _compute_gps_validity(self):
        with self._lock:
            now = now_unix()
            gps_age = (now - self.gps.stamp_unix) if self.gps.present else None
            sats = self.gps_sats.satellites_visible if self.gps_sats.present else None

            rms = None
            if self.gps.cov_xx is not None and self.gps.cov_yy is not None:
                if self.gps.cov_xx >= 0.0 and self.gps.cov_yy >= 0.0:
                    rms = (self.gps.cov_xx + self.gps.cov_yy) ** 0.5

            cls = "unknown"
            reason = "unknown"

            if gps_age is None or gps_age > 2.0:
                cls = "no_fix"
                reason = "gps_stale_or_absent"
            else:
                if self.gps.status is not None and self.gps.status < 0:
                    cls = "no_fix"
                    reason = f"navsat_status={self.gps.status}"
                else:
                    if sats is not None and sats < 6:
                        cls = "poor"
                        reason = f"low_sats={sats}"
                    else:
                        if rms is None:
                            cls = "degraded"
                            reason = "no_covariance"
                        else:
                            if rms <= 2.0:
                                cls = "good"
                                reason = "rms_cov<=2m"
                            elif rms <= 10.0:
                                cls = "degraded"
                                reason = "2m<rms_cov<=10m"
                            else:
                                cls = "poor"
                                reason = "rms_cov>10m"

            self.gps_validity = GPSValidity(
                cls=cls,
                reason=reason,
                age_sec=gps_age,
                sats=sats,
                rms_cov_m=rms,
            )

    # ---- Health + snapshots ----
    def compute_health_locked(self) -> HealthSummary:
        reasons: list[str] = []

        if not self.tf.map_to_odom:
            reasons.append(f"TF missing: {self.frame_map}->{self.frame_odom}")
        if not self.tf.odom_to_base:
            reasons.append(f"TF missing: {self.frame_odom}->{self.frame_base}")

        if self.vesc_left.present and (self.vesc_left.fault_code is not None):
            if self.vesc_left.fault_code != 0:
                reasons.append(f"Left VESC fault_code={self.vesc_left.fault_code}")

        if self.vesc_right.present and (self.vesc_right.fault_code is not None):
            if self.vesc_right.fault_code != 0:
                reasons.append(f"Right VESC fault_code={self.vesc_right.fault_code}")

        if self.vesc_left.present and (self.vesc_left.input_voltage_v is not None):
            if self.vesc_left.input_voltage_v < 20.0:
                reasons.append(f"Low pack voltage (L): {self.vesc_left.input_voltage_v:.2f} V")

        if self.vesc_right.present and (self.vesc_right.input_voltage_v is not None):
            if self.vesc_right.input_voltage_v < 20.0:
                reasons.append(f"Low pack voltage (R): {self.vesc_right.input_voltage_v:.2f} V")

        if self.gps_validity.cls in ("poor", "no_fix"):
            reasons.append(f"GPS validity: {self.gps_validity.cls} ({self.gps_validity.reason})")

        ok = (len(reasons) == 0)
        return HealthSummary(ok=ok, reasons=reasons)

    def _freshness_snapshot_locked(self) -> Dict[str, Any]:
        now = now_unix()
        out = {}
        for k, v in self.topic_fresh.items():
            v.update_age(now)
            out[k] = {
                "present": v.present,
                "age_sec": v.age_sec,
                "ema_hz": v.ema_hz,
                "msg_count": v.msg_count,
            }
        return out

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "node": self.get_name(),
                "time_unix": now_unix(),
                "vesc_left": asdict(self.vesc_left),
                "vesc_right": asdict(self.vesc_right),
                "gps": asdict(self.gps),
                "gps_sats": asdict(self.gps_sats),
                "odometry_gps": asdict(self.odom_gps),
                "localization": asdict(self.loc),
                "nav": asdict(self.nav),
                "tf": asdict(self.tf),
                "gps_validity": asdict(self.gps_validity),
                "topic_freshness": self._freshness_snapshot_locked(),
                "health": asdict(self.compute_health_locked()),
                "mission": self._mission_snapshot_locked(),
            }

    def _mission_snapshot_locked(self) -> Dict[str, Any]:
        m = self.mission
        return {
            "present":            m.present,
            "origin_lat":         m.origin_lat,
            "origin_lon":         m.origin_lon,
            "nav_enabled":        m.nav_enabled,
            "waypoints":          [{"lat": w.lat, "lon": w.lon, "name": w.name} for w in m.waypoints] if m.waypoints else [],
            "pose_x":             m.pose_x,
            "pose_y":             m.pose_y,
            "pose_yaw_rad":       m.pose_yaw_rad,
            "target_x":           m.target_x,
            "target_y":           m.target_y,
            "carrot_x":           m.carrot_x,
            "carrot_y":           m.carrot_y,
            "waypoint_index":     m.waypoint_index,
            "mission_complete":   m.mission_complete,
            "acceptance_radius_m": m.acceptance_radius_m,
        }

    def costmap_snapshot(self, which: str) -> Dict[str, Any]:
        with self._lock:
            cm = self.costmap_local if which == "local" else self.costmap_global
            return asdict(cm)


    # ---- Mission planner callbacks ----
    def _on_nav_enabled_echo(self, msg: Bool) -> None:
        with self._lock:
            self.mission.nav_enabled = bool(msg.data)

    def publish_nav_enabled(self, enabled: bool) -> None:
        msg = Bool()
        msg.data = enabled
        self._nav_enabled_pub.publish(msg)
        with self._lock:
            self.mission.nav_enabled = enabled

    def publish_cancel(self) -> None:
        msg = Bool()
        msg.data = True
        self._cancel_pub.publish(msg)

    def _on_mission_origin(self, msg: NavSatFix) -> None:
        """Store the fixed mission origin from mission_global_frame_node."""
        with self._lock:
            self.mission.origin_lat = float(msg.latitude)
            self.mission.origin_lon = float(msg.longitude)
            self.mission.present = True

    def _on_mission_waypoints_latlon(self, msg: String) -> None:
        """Receive waypoints as JSON [{lat, lon, name}, ...] from the mission manager."""
        import json
        try:
            data = json.loads(msg.data)
            with self._lock:
                self.mission.waypoints = [
                    MissionWaypoint(
                        lat=float(w['lat']),
                        lon=float(w['lon']),
                        name=str(w.get('name', f'wp_{i}'))
                    )
                    for i, w in enumerate(data)
                ]
                self.mission.present = True
        except Exception as e:
            self.get_logger().warn(f'Failed to parse waypoints_latlon: {e}')

    def _on_mission_pose(self, msg: PoseStamped) -> None:
        with self._lock:
            self.mission.present = True
            self.mission.pose_x = float(msg.pose.position.x)
            self.mission.pose_y = float(msg.pose.position.y)
            self.mission.pose_yaw_rad = yaw_from_quat(msg.pose.orientation)

    def _on_mission_target(self, msg: PoseStamped) -> None:
        with self._lock:
            self.mission.present = True
            self.mission.target_x = float(msg.pose.position.x)
            self.mission.target_y = float(msg.pose.position.y)

    def _on_mission_carrot(self, msg: PoseStamped) -> None:
        with self._lock:
            self.mission.present = True
            self.mission.carrot_x = float(msg.pose.position.x)
            self.mission.carrot_y = float(msg.pose.position.y)

    def _on_mission_index(self, msg: Int32) -> None:
        with self._lock:
            self.mission.waypoint_index = int(msg.data)

    def _on_mission_complete(self, msg: Bool) -> None:
        with self._lock:
            self.mission.mission_complete = bool(msg.data)

    def publish_waypoints_latlon(self, waypoints_json: str) -> None:
        """
        Push a new waypoint list onto /mission/waypoints_latlon.
        waypoints_json: JSON string — [{"lat": ..., "lon": ..., "name": ...}, ...]
        """
        msg = String()
        msg.data = waypoints_json
        self._waypoints_latlon_pub.publish(msg)

    def get_waypoints_as_yaml(self) -> str:
        """Return the current in-memory waypoints serialised as YAML (for download)."""
        import yaml
        with self._lock:
            wps = self.mission.waypoints or []
            data = {
                'waypoints': [
                    {'name': w.name, 'latitude': w.lat, 'longitude': w.lon, 'altitude': 0.0}
                    for w in wps
                ]
            }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def set_mission_waypoints(self, waypoints: list) -> None:
        """
        waypoints: list of (lat, lon) or (lat, lon, name) tuples.
        Called from main.py after loading the YAML file.
        """
        with self._lock:
            self.mission.waypoints = [
                MissionWaypoint(
                    lat=float(w[0]),
                    lon=float(w[1]),
                    name=str(w[2]) if len(w) > 2 else f'wp_{i}'
                )
                for i, w in enumerate(waypoints)
            ]
            self.mission.acceptance_radius_m = self._mission_acceptance_radius_m


    def call_trigger_service(self, service_name: str, timeout_sec: float = 3.0) -> Dict[str, Any]:
        """
        Synchronously call a std_srvs/Trigger service from the bridge node.
        Returns {success: bool, message: str}.
        """
        from std_srvs.srv import Trigger
        client = self.create_client(Trigger, service_name)
        try:
            if not client.wait_for_service(timeout_sec=timeout_sec):
                return {"success": False, "message": f"Service {service_name} not available"}
            future = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
            if future.done():
                result = future.result()
                return {"success": bool(result.success), "message": str(result.message)}
            else:
                return {"success": False, "message": f"Service {service_name} timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}
        finally:
            self.destroy_client(client)


def spin_ros(node: StatusBridge, num_threads: int = 2) -> None:
    executor = MultiThreadedExecutor(num_threads=num_threads)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()