#!/usr/bin/env python3
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    QoSHistoryPolicy,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
)

from sensor_msgs.msg import NavSatFix, NavSatStatus
from nav_msgs.msg import Odometry


class GpsHardGateNode(Node):
    def __init__(self):
        super().__init__('gps_hardgate_node')

        # --------------------------
        # Parameters
        # --------------------------
        self.declare_parameter('mode', 'INDOOR')  # INDOOR / OUTDOOR
        self.declare_parameter('fix_in', '/mavros/mavros/global_position/raw/fix')
        self.declare_parameter('fix_out', '/gps/fix_hardgated')

        self.declare_parameter('odom_in', '/odometry/local')
        self.declare_parameter('use_odom_speed_gate', True)

        # Hard gate thresholds
        self.declare_parameter('hard_var_thresh', 25.0)   # m^2 (xy variance)
        self.declare_parameter('max_speed_mps', 5.0)      # m/s
        self.declare_parameter('max_fix_age_s', 1.0)      # sec; <=0 disables

        # Behavior on fail: 'drop' or 'publish_no_fix'
        self.declare_parameter('fail_behavior', 'drop')

        # Additional strictness
        self.declare_parameter('reject_unknown_cov', True)

        # --------------------------
        # Read params
        # --------------------------
        self.mode = str(self.get_parameter('mode').value).upper()
        self.fix_in = str(self.get_parameter('fix_in').value)
        self.fix_out = str(self.get_parameter('fix_out').value)

        self.odom_in = str(self.get_parameter('odom_in').value)
        self.use_odom_speed_gate = bool(self.get_parameter('use_odom_speed_gate').value)

        self.hard_var_thresh = float(self.get_parameter('hard_var_thresh').value)
        self.max_speed_mps = float(self.get_parameter('max_speed_mps').value)
        self.max_fix_age_s = float(self.get_parameter('max_fix_age_s').value)

        self.fail_behavior = str(self.get_parameter('fail_behavior').value).lower()
        self.reject_unknown_cov = bool(self.get_parameter('reject_unknown_cov').value)

        # --------------------------
        # QoS profiles
        # --------------------------
        # MAVROS GPS publishers are typically BEST_EFFORT / VOLATILE
        self.qos_sensor = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        # Odometry is typically RELIABLE; keep it that way to avoid drops
        self.qos_odom = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        # --------------------------
        # State
        # --------------------------
        self.last_speed_mps = 0.0
        self.have_speed = False

        # --------------------------
        # Pub/Sub
        # --------------------------
        self.pub_fix = self.create_publisher(NavSatFix, self.fix_out, self.qos_sensor)

        self.sub_fix = self.create_subscription(
            NavSatFix,
            self.fix_in,
            self._on_fix,
            self.qos_sensor,   # <-- critical fix for MAVROS QoS
        )

        if self.use_odom_speed_gate:
            self.sub_odom = self.create_subscription(
                Odometry,
                self.odom_in,
                self._on_odom,
                self.qos_odom,
            )

        self.get_logger().info(
            f"[gps_hardgate] mode={self.mode} in={self.fix_in} out={self.fix_out} "
            f"var_thresh={self.hard_var_thresh} max_speed={self.max_speed_mps} "
            f"max_age={self.max_fix_age_s}s fail={self.fail_behavior} "
            f"reject_unknown_cov={self.reject_unknown_cov} "
            f"use_odom_speed_gate={self.use_odom_speed_gate} odom_in={self.odom_in}"
        )

    # --------------------------
    # Callbacks
    # --------------------------
    def _on_odom(self, msg: Odometry):
        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        self.last_speed_mps = math.hypot(vx, vy)
        self.have_speed = True

    def _on_fix(self, msg: NavSatFix):
        status_ok = self._status_ok(msg)
        cov_ok, var_xy, cov_reason = self._cov_ok(msg)
        age_ok, age_s = self._age_ok(msg)
        speed_ok = self._speed_ok()

        if self.mode == 'INDOOR':
            pass_fix = status_ok and cov_ok and age_ok and speed_ok
        else:
            pass_fix = status_ok and cov_ok and age_ok

        if pass_fix:
            self.pub_fix.publish(msg)
            return

        reason = (
            f"status_ok={status_ok} "
            f"cov_ok={cov_ok}(var_xy={var_xy:.3g}<= {self.hard_var_thresh}, {cov_reason}) "
            f"age_ok={age_ok}(age={age_s:.3f}s<= {self.max_fix_age_s}) "
            f"speed_ok={speed_ok}(v={self.last_speed_mps:.2f}<= {self.max_speed_mps})"
        )

        if self.fail_behavior == 'publish_no_fix':
            self._publish_no_fix(msg, reason)
        else:
            self.get_logger().warn(f"[DROP] {reason}")

    # --------------------------
    # Gate helpers
    # --------------------------
    def _status_ok(self, msg: NavSatFix) -> bool:
        return msg.status.status != NavSatStatus.STATUS_NO_FIX

    def _cov_ok(self, msg: NavSatFix) -> tuple[bool, float, str]:
        # Optionally reject unknown covariance
        if self.reject_unknown_cov and msg.position_covariance_type == NavSatFix.COVARIANCE_TYPE_UNKNOWN:
            return False, float('inf'), "cov_type=UNKNOWN"

        cov = msg.position_covariance
        if len(cov) != 9:
            return False, float('inf'), "cov_len!=9"

        var_xy = max(cov[0], cov[4])
        ok = (var_xy <= self.hard_var_thresh)
        return ok, var_xy, f"cov_type={msg.position_covariance_type}"

    def _age_ok(self, msg: NavSatFix) -> tuple[bool, float]:
        if self.max_fix_age_s <= 0.0:
            return True, 0.0

        if msg.header.stamp.sec == 0 and msg.header.stamp.nanosec == 0:
            # No timestamp => be conservative indoors
            return (self.mode != 'INDOOR'), float('inf')

        now = self.get_clock().now()
        t = rclpy.time.Time.from_msg(msg.header.stamp)
        age_s = (now - t).nanoseconds * 1e-9
        return (age_s <= self.max_fix_age_s), age_s

    def _speed_ok(self) -> bool:
        if not self.use_odom_speed_gate:
            return True
        if not self.have_speed:
            # Be conservative indoors until we have odom
            return self.mode != 'INDOOR'
        return self.last_speed_mps <= self.max_speed_mps

    def _publish_no_fix(self, msg: NavSatFix, reason: str):
        out = NavSatFix()
        out.header = msg.header
        out.latitude = msg.latitude
        out.longitude = msg.longitude
        out.altitude = msg.altitude
        out.status.status = NavSatStatus.STATUS_NO_FIX
        out.status.service = msg.status.service
        out.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        out.position_covariance = [
            1e9, 0.0, 0.0,
            0.0, 1e9, 0.0,
            0.0, 0.0, 1e9,
        ]
        self.pub_fix.publish(out)
        self.get_logger().warn(f"[DROP->NO_FIX] {reason}")


def main(args=None):
    rclpy.init(args=args)
    node = GpsHardGateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
