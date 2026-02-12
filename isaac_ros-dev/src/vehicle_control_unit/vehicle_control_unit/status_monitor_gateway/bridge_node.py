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
from std_msgs.msg import Float32, Int32, UInt32

from .qos import qos_reliable, qos_sensor
from .utils import now_unix, clamp, yaw_from_quat
from .models import (
    TopicFreshness, VescSnapshot, GPSSnapshot, SatSnapshot,
    OdomGpsSnapshot, LocalizationSnapshot, NavSnapshot,
    TFHealth, GPSValidity, CostmapSnapshot, HealthSummary,
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
        self.declare_parameter("gps_topic", "/mavros/mavros/global_position/global")
        self.declare_parameter("gps_sat_topic", "/mavros/mavros/global_position/raw/satellites")
        self.declare_parameter("odom_gps_topic", "/odometry/gps")
        self.declare_parameter("localization_topic", "/odometry/local")
        self.declare_parameter("nav_status_topic", "/navigate_to_pose/_action/status")
        self.declare_parameter("local_costmap_topic", "/local_costmap/costmap")
        self.declare_parameter("global_costmap_topic", "/global_costmap/costmap")

        self.frame_map = self.get_parameter("frame_map").value
        self.frame_odom = self.get_parameter("frame_odom").value
        self.frame_base = self.get_parameter("frame_base").value

        vesc_left_prefix = self.get_parameter("vesc_left_prefix").value.rstrip("/")
        gps_topic = self.get_parameter("gps_topic").value
        gps_sat_topic = self.get_parameter("gps_sat_topic").value
        odom_gps_topic = self.get_parameter("odom_gps_topic").value
        localization_topic = self.get_parameter("localization_topic").value
        nav_status_topic = self.get_parameter("nav_status_topic").value
        local_costmap_topic = self.get_parameter("local_costmap_topic").value
        global_costmap_topic = self.get_parameter("global_costmap_topic").value

        # Shared state
        self._lock = threading.Lock()
        self.vesc_left = VescSnapshot()
        self.gps = GPSSnapshot()
        self.gps_sats = SatSnapshot()
        self.odom_gps = OdomGpsSnapshot()
        self.loc = LocalizationSnapshot()
        self.nav = NavSnapshot()
        self.tf = TFHealth()
        self.gps_validity = GPSValidity()

        self.costmap_local = CostmapSnapshot()
        self.costmap_global = CostmapSnapshot()

        # Topic freshness
        self.topic_fresh: Dict[str, TopicFreshness] = {
            "gps_fix": TopicFreshness(),
            "gps_sats": TopicFreshness(),
            "odom_gps": TopicFreshness(),
            "localization": TopicFreshness(),
            "nav_status": TopicFreshness(),
            "vesc_left": TopicFreshness(),
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
        # GPS (BEST_EFFORT)
        # -------------------------
        self.create_subscription(NavSatFix, gps_topic, self._on_gps, qos_sensor)
        self.create_subscription(UInt32, gps_sat_topic, self._on_gps_sats, qos_sensor)

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

        if self.vesc_left.present and (self.vesc_left.input_voltage_v is not None):
            if self.vesc_left.input_voltage_v < 20.0:
                reasons.append(f"Low pack voltage: {self.vesc_left.input_voltage_v:.2f} V")

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
                "gps": asdict(self.gps),
                "gps_sats": asdict(self.gps_sats),
                "odometry_gps": asdict(self.odom_gps),
                "localization": asdict(self.loc),
                "nav": asdict(self.nav),
                "tf": asdict(self.tf),
                "gps_validity": asdict(self.gps_validity),
                "topic_freshness": self._freshness_snapshot_locked(),
                "health": asdict(self.compute_health_locked()),
            }

    def costmap_snapshot(self, which: str) -> Dict[str, Any]:
        with self._lock:
            cm = self.costmap_local if which == "local" else self.costmap_global
            return asdict(cm)


def spin_ros(node: StatusBridge, num_threads: int = 2) -> None:
    executor = MultiThreadedExecutor(num_threads=num_threads)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()