#!/usr/bin/env python3
import math

import rclpy
from rclpy.node import Node

from std_msgs.msg import Int32
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


def yaw_to_quat(yaw: float):
    """Return (x,y,z,w) quaternion for yaw about +Z."""
    half = 0.5 * yaw
    return (0.0, 0.0, math.sin(half), math.cos(half))


class VescErpmWheelOdom(Node):
    def __init__(self):
        super().__init__('vesc_erpm_wheel_odom')

        self.declare_parameter('publish_tf', True)

        # ----------------------------
        # Parameters (match your cmd_vel node)
        # ----------------------------
        self.declare_parameter('wheel_radius', 0.075)     # meters
        self.declare_parameter('track_width', 0.38)      # meters
        self.declare_parameter('gear_ratio', 4.0)        # motor_rpm / wheel_rpm
        self.declare_parameter('pole_pairs', 7)          # motor pole pairs

        # Frames / topics
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('odom_topic', '/wheel/odom')

        # Input topics
        self.declare_parameter('left_erpm_topic',  '/left_vesc/state/erpm')
        self.declare_parameter('right_erpm_topic', '/right_vesc/state/erpm')

        # Sign and deadband
        self.declare_parameter('left_sign',  1.0)         # set -1.0 if left wheel is reversed
        self.declare_parameter('right_sign', 1.0)         # set -1.0 if right wheel is reversed
        self.declare_parameter('erpm_deadband', 50)       # below this, treat as 0 to prevent creep

        # Publish rate for odom/TF (use your ERPM rate ~50Hz)
        self.declare_parameter('publish_rate_hz', 50.0)

        # Load params

        self.publish_tf = bool(self.get_parameter('publish_tf').value)
        self.r = float(self.get_parameter('wheel_radius').value)
        self.L = float(self.get_parameter('track_width').value)
        self.G = float(self.get_parameter('gear_ratio').value)
        self.pole_pairs = int(self.get_parameter('pole_pairs').value)

        self.odom_frame = str(self.get_parameter('odom_frame').value)
        self.base_frame = str(self.get_parameter('base_frame').value)
        self.odom_topic = str(self.get_parameter('odom_topic').value)

        self.left_topic  = str(self.get_parameter('left_erpm_topic').value)
        self.right_topic = str(self.get_parameter('right_erpm_topic').value)

        self.left_sign  = float(self.get_parameter('left_sign').value)
        self.right_sign = float(self.get_parameter('right_sign').value)
        self.erpm_deadband = int(self.get_parameter('erpm_deadband').value)

        publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self.dt = 1.0 / max(publish_rate_hz, 1.0)

        # ----------------------------
        # State
        # ----------------------------
        self.left_erpm = 0
        self.right_erpm = 0
        self.have_left = False
        self.have_right = False

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0

        self.last_time = self.get_clock().now()

        # ----------------------------
        # ROS interfaces
        # ----------------------------
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        self.create_subscription(Int32, self.left_topic, self.left_cb, 10)
        self.create_subscription(Int32, self.right_topic, self.right_cb, 10)

        self.create_timer(self.dt, self.update)

        self.get_logger().info(
            f"Wheel odom node started.\n"
            f"  left_erpm:  {self.left_topic}\n"
            f"  right_erpm: {self.right_topic}\n"
            f"  publish:    {self.odom_topic} and TF {self.odom_frame}->{self.base_frame}\n"
            f"  r={self.r:.4f} m, L={self.L:.4f} m, G={self.G:.3f}, pole_pairs={self.pole_pairs}\n"
            f"  signs: left={self.left_sign:+.1f}, right={self.right_sign:+.1f}, deadband={self.erpm_deadband}"
        )

    # ----------------------------
    # Callbacks
    # ----------------------------
    def left_cb(self, msg: Int32):
        self.left_erpm = int(msg.data)
        self.have_left = True

    def right_cb(self, msg: Int32):
        self.right_erpm = int(msg.data)
        self.have_right = True

    # ----------------------------
    # Math helpers
    # ----------------------------
    def erpm_to_linear(self, erpm: int) -> float:
        """Convert ERPM -> wheel linear velocity (m/s), using pole_pairs and gear_ratio."""
        # deadband to avoid creep at stop
        if abs(erpm) < self.erpm_deadband:
            return 0.0

        # ERPM -> motor mechanical RPM
        motor_rpm = float(erpm) / float(self.pole_pairs)

        # motor RPM -> wheel RPM
        wheel_rpm = motor_rpm / float(self.G)

        # wheel RPM -> wheel RPS
        wheel_rps = wheel_rpm / 60.0

        # linear velocity
        return wheel_rps * (2.0 * math.pi * self.r)

    # ----------------------------
    # Main update loop
    # ----------------------------
    def update(self):
        # Only start integrating once both wheels have been seen
        if not (self.have_left and self.have_right):
            return

        now = self.get_clock().now()
        dt = (now - self.last_time).nanoseconds * 1e-9
        if dt <= 0.0:
            dt = self.dt
        self.last_time = now

        # Apply sign convention
        le = int(self.left_sign * self.left_erpm)
        re = int(self.right_sign * self.right_erpm)

        # ERPM -> wheel linear velocities
        v_l = self.erpm_to_linear(le)
        v_r = self.erpm_to_linear(re)

        # Differential drive body velocities
        v = 0.5 * (v_r + v_l)
        wz = (v_r - v_l) / self.L

        # Integrate pose
        self.x += v * math.cos(self.yaw) * dt
        self.y += v * math.sin(self.yaw) * dt
        self.yaw += wz * dt

        # Normalize yaw to [-pi, pi] (optional but nice)
        self.yaw = (self.yaw + math.pi) % (2.0 * math.pi) - math.pi

        # Publish Odometry and TF with consistent timestamp
        stamp = now.to_msg()

        qx, qy, qz, qw = yaw_to_quat(self.yaw)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw

        odom.twist.twist.linear.x = v
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = wz

        self.odom_pub.publish(odom)

        t = TransformStamped()
        t.header.stamp = stamp
        t.header.frame_id = self.odom_frame
        t.child_frame_id = self.base_frame
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw

        if self.publish_tf:
            self.tf_broadcaster.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = VescErpmWheelOdom()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
