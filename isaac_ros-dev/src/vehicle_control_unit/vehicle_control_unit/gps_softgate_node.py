#!/usr/bin/env python3
"""
gps_softgate_node.py

Soft-gated GPS fusion helper for robot_localization pipelines.
Subscribes to:
  - NavSatFix      (BEST_EFFORT): /mavros/mavros/global_position/raw/fix
  - UInt32 sats    (BEST_EFFORT): /mavros/mavros/global_position/raw/satellites

Publishes:
  - NavSatFix with inflated covariance: /gps/fix_softgated

Design:
  - Never disables GPS
  - Always publishes a fix message
  - Scales position_covariance based on satellite count, sigma, fix validity, and message age
  - Optional smoothing of the scale factor (recommended)

Notes:
  - Does NOT change latitude/longitude/altitude
  - Does NOT change frame_id or timestamp
"""

from __future__ import annotations

import math
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import UInt32


def _now_unix() -> float:
    return time.time()


class GPSSoftgateNode(Node):
    def __init__(self):
        super().__init__("gps_softgate_node")

        # -------------------------
        # Parameters
        # -------------------------
        self.declare_parameter("fix_in", "/mavros/mavros/global_position/raw/fix")
        self.declare_parameter("sats_in", "/mavros/mavros/global_position/raw/satellites")
        self.declare_parameter("fix_out", "/gps/fix_softgated")

        # gating thresholds
        self.declare_parameter("min_sats_good", 10)
        self.declare_parameter("min_sats_ok", 8)
        self.declare_parameter("min_sats_poor", 6)

        self.declare_parameter("sigma_good_m", 3.0)
        self.declare_parameter("sigma_ok_m", 5.0)
        self.declare_parameter("sigma_poor_m", 8.0)

        # covariance scale values
        self.declare_parameter("scale_good", 1.0)
        self.declare_parameter("scale_ok", 5.0)
        self.declare_parameter("scale_poor", 20.0)
        self.declare_parameter("scale_bad", 100.0)

        # message age handling (stale sats or stale fix)
        self.declare_parameter("max_sats_age_s", 1.0)
        self.declare_parameter("max_fix_age_s", 1.0)

        # smoothing (time constant in seconds). 0 disables smoothing.
        self.declare_parameter("scale_smoothing_tau_s", 1.5)

        # diagnostics
        self.declare_parameter("log_throttle_s", 2.0)

        self.fix_in = str(self.get_parameter("fix_in").value)
        self.sats_in = str(self.get_parameter("sats_in").value)
        self.fix_out = str(self.get_parameter("fix_out").value)

        self.min_sats_good = int(self.get_parameter("min_sats_good").value)
        self.min_sats_ok = int(self.get_parameter("min_sats_ok").value)
        self.min_sats_poor = int(self.get_parameter("min_sats_poor").value)

        self.sigma_good = float(self.get_parameter("sigma_good_m").value)
        self.sigma_ok = float(self.get_parameter("sigma_ok_m").value)
        self.sigma_poor = float(self.get_parameter("sigma_poor_m").value)

        self.scale_good = float(self.get_parameter("scale_good").value)
        self.scale_ok = float(self.get_parameter("scale_ok").value)
        self.scale_poor = float(self.get_parameter("scale_poor").value)
        self.scale_bad = float(self.get_parameter("scale_bad").value)

        self.max_sats_age_s = float(self.get_parameter("max_sats_age_s").value)
        self.max_fix_age_s = float(self.get_parameter("max_fix_age_s").value)

        self.tau = float(self.get_parameter("scale_smoothing_tau_s").value)
        self.log_throttle_s = float(self.get_parameter("log_throttle_s").value)

        # -------------------------
        # QoS: match MAVROS publishers (BEST_EFFORT, VOLATILE)
        # -------------------------
        qos_sensor = QoSProfile(depth=10)
        qos_sensor.reliability = ReliabilityPolicy.BEST_EFFORT
        qos_sensor.durability = DurabilityPolicy.VOLATILE

        self.sub_fix = self.create_subscription(NavSatFix, self.fix_in, self._on_fix, qos_sensor)
        self.sub_sats = self.create_subscription(UInt32, self.sats_in, self._on_sats, qos_sensor)
        self.pub_fix = self.create_publisher(NavSatFix, self.fix_out, qos_sensor)

        # -------------------------
        # State
        # -------------------------
        self._last_sats: Optional[int] = None
        self._last_sats_rx_unix: float = 0.0

        self._last_fix_rx_unix: float = 0.0

        self._scale_filt: float = 1.0
        self._last_scale_update_unix: float = 0.0

        self._last_log_unix: float = 0.0

        self.get_logger().info("gps_softgate_node started.")
        self.get_logger().info(f"  fix_in:  {self.fix_in}")
        self.get_logger().info(f"  sats_in: {self.sats_in}")
        self.get_logger().info(f"  fix_out: {self.fix_out}")

    def _on_sats(self, msg: UInt32) -> None:
        self._last_sats = int(msg.data)
        self._last_sats_rx_unix = _now_unix()

    @staticmethod
    def _sigma_from_cov(msg: NavSatFix) -> Optional[float]:
        # position_covariance is row-major 3x3
        if len(msg.position_covariance) < 9:
            return None
        cov_xx = msg.position_covariance[0]
        cov_yy = msg.position_covariance[4]
        if not (math.isfinite(cov_xx) and math.isfinite(cov_yy)):
            return None
        if cov_xx <= 0.0 and cov_yy <= 0.0:
            return None
        return math.sqrt(max(cov_xx, cov_yy))

    def _compute_scale(self, fix: NavSatFix) -> tuple[float, str]:
        now = _now_unix()

        # 1) Fix validity
        if fix.status.status < 0:  # NavSatStatus.STATUS_NO_FIX is -1
            return self.scale_bad, "no_fix"

        # 2) Fix age (optional safety net)
        fix_age = max(0.0, now - self._last_fix_rx_unix)
        if fix_age > self.max_fix_age_s:
            return self.scale_bad, f"stale_fix({fix_age:.2f}s)"

        # 3) Satellite age and value
        sats_age = max(0.0, now - self._last_sats_rx_unix)
        if self._last_sats is None or sats_age > self.max_sats_age_s:
            return self.scale_bad, f"stale_sats({sats_age:.2f}s)"

        sats = int(self._last_sats)

        # 4) Sigma from covariance (horizontal)
        sigma = self._sigma_from_cov(fix)
        # If covariance is missing/invalid, be conservative
        if sigma is None:
            # Use satellites only, but still conservative
            if sats >= self.min_sats_good:
                return self.scale_ok, "no_cov_sats_good"
            if sats >= self.min_sats_ok:
                return self.scale_poor, "no_cov_sats_ok"
            return self.scale_bad, "no_cov_sats_poor"

        # 5) Apply your table logic
        # Good
        if (sats >= self.min_sats_good) and (sigma <= self.sigma_good):
            return self.scale_good, f"good(sats={sats},sigma={sigma:.2f})"
        # OK
        if (sats >= self.min_sats_ok) or (sigma <= self.sigma_ok):
            return self.scale_ok, f"ok(sats={sats},sigma={sigma:.2f})"
        # Poor
        if (sats >= self.min_sats_poor) or (sigma <= self.sigma_poor):
            return self.scale_poor, f"poor(sats={sats},sigma={sigma:.2f})"
        # Bad
        return self.scale_bad, f"bad(sats={sats},sigma={sigma:.2f})"

    def _update_filtered_scale(self, scale_raw: float) -> float:
        now = _now_unix()

        # Initialize
        if self._last_scale_update_unix <= 0.0:
            self._scale_filt = float(scale_raw)
            self._last_scale_update_unix = now
            return self._scale_filt

        dt = max(1e-3, now - self._last_scale_update_unix)
        self._last_scale_update_unix = now

        # No smoothing if tau <= 0
        if self.tau <= 0.0:
            self._scale_filt = float(scale_raw)
            return self._scale_filt

        # First-order low-pass: y += alpha*(u - y)
        alpha = 1.0 - math.exp(-dt / self.tau)
        self._scale_filt = self._scale_filt + alpha * (float(scale_raw) - self._scale_filt)
        return self._scale_filt

    @staticmethod
    def _scale_covariance(msg: NavSatFix, scale: float) -> None:
        # Scale full 3x3 covariance to preserve structure.
        # If covariance is zero/unknown, we still inflate if any entries exist.
        if len(msg.position_covariance) >= 9:
            for i in range(9):
                v = msg.position_covariance[i]
                if math.isfinite(v):
                    msg.position_covariance[i] = v * scale
                else:
                    # If NaN/inf appears, replace with large value
                    msg.position_covariance[i] = (100.0 * 100.0)  # 1e4 m^2
        else:
            # If not populated, fill a diagonal covariance (conservative) then scale
            base = 25.0  # (5m)^2 baseline
            msg.position_covariance = [0.0] * 9
            msg.position_covariance[0] = base * scale
            msg.position_covariance[4] = base * scale
            msg.position_covariance[8] = base * scale

        # Ensure covariance type is set
        if msg.position_covariance_type == NavSatFix.COVARIANCE_TYPE_UNKNOWN:
            msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_KNOWN

    def _on_fix(self, msg: NavSatFix) -> None:
        self._last_fix_rx_unix = _now_unix()

        scale_raw, reason = self._compute_scale(msg)
        scale_filt = self._update_filtered_scale(scale_raw)

        out = NavSatFix()
        out.header = msg.header
        out.status = msg.status
        out.latitude = msg.latitude
        out.longitude = msg.longitude
        out.altitude = msg.altitude

        out.position_covariance = list(msg.position_covariance)  # copy
        out.position_covariance_type = msg.position_covariance_type

        # Apply filtered scale
        self._scale_covariance(out, scale_filt)

        self.pub_fix.publish(out)

        # Throttled logging
        now = _now_unix()
        if (now - self._last_log_unix) >= self.log_throttle_s:
            self._last_log_unix = now
            sats = self._last_sats if self._last_sats is not None else -1
            sigma = self._sigma_from_cov(msg)
            sigma_s = f"{sigma:.2f}" if sigma is not None else "None"
            self.get_logger().info(
                f"softgate: sats={sats} sigma={sigma_s} scale_raw={scale_raw:.2f} scale={scale_filt:.2f} reason={reason}"
            )


def main():
    rclpy.init()
    node = GPSSoftgateNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
