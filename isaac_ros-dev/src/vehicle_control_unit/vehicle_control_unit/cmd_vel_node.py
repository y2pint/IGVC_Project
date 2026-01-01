#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32, Bool
import math


class CmdVelToWheelRPM(Node):
    def __init__(self):
        super().__init__('cmd_vel_to_wheel_rpm')

        # ------------------------------------------------------------
        # Robot parameters (EDIT THESE ONCE)
        # ------------------------------------------------------------
        self.declare_parameter('wheel_radius', 0.075)   # meters
        self.declare_parameter('track_width', 0.38)    # meters
        self.declare_parameter('gear_ratio', 4.0)      # motor_rpm / wheel_rpm
        self.declare_parameter('pole_pairs', 7)
        self.declare_parameter('min_linear_velocity', 0.2)   # m/s
        self.declare_parameter('min_angular_velocity', 0.05) # rad/s
        
        self.pole_pairs = self.get_parameter('pole_pairs').value
        self.wheel_radius = self.get_parameter('wheel_radius').value
        self.track_width = self.get_parameter('track_width').value
        self.gear_ratio = self.get_parameter('gear_ratio').value
        self.min_v = self.get_parameter('min_linear_velocity').value
        self.min_omega = self.get_parameter('min_angular_velocity').value

        # ------------------------------------------------------------
        # Limits
        # ------------------------------------------------------------
        self.max_linear_accel =  2.0      # m/s^2
        self.max_angular_accel = 2.0     # rad/s^2
        self.dt = 0.02                   # 20 Hz control loop
        self.min_erpm = 300              # deadzone clamp
        self.max_erpm = 4000

        # ------------------------------------------------------------
        # Publishers
        # ------------------------------------------------------------
        self.left_rpm_pub = self.create_publisher(
            Int32, '/left_vesc/cmd_rpm', 10
        )
        self.right_rpm_pub = self.create_publisher(
            Int32, '/right_vesc/cmd_rpm', 10
        )

        # ------------------------------------------------------------
        # Subscribers
        # ------------------------------------------------------------
        self.create_subscription(Twist, '/cmd_vel', self.cmd_vel_cb, 10)
        self.create_subscription(Bool, '/stop_flag', self.stop_flag_cb, 10)

        # ------------------------------------------------------------
        # State
        # ------------------------------------------------------------
        self.latest_cmd_vel = Twist()
        self.stop_flag = False

        self.prev_v = 0.0
        self.prev_omega = 0.0

        # ------------------------------------------------------------
        # Timer
        # ------------------------------------------------------------
        self.create_timer(self.dt, self.control_loop)

        self.get_logger().info("✅ CmdVelToWheelRPM (diff drive) initialized")

    # ------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------
    def cmd_vel_cb(self, msg: Twist):
        self.latest_cmd_vel = msg

    def stop_flag_cb(self, msg: Bool):
        self.stop_flag = msg.data
        if self.stop_flag:
            self.get_logger().warn("🛑 stop_flag asserted")

    # ------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------
    def control_loop(self):
        if self.stop_flag:
            self.publish_rpm(0, 0)
            return

        # Desired velocities
        target_v = self.latest_cmd_vel.linear.x
        target_omega = self.latest_cmd_vel.angular.z

        # ---- Linear accel limiting ----
        dv = target_v - self.prev_v
        max_dv = self.max_linear_accel * self.dt
        dv = max(min(dv, max_dv), -max_dv)
        v = self.prev_v + dv
        self.prev_v = v

        # ---- Angular accel limiting ----
        domega = target_omega - self.prev_omega
        max_domega = self.max_angular_accel * self.dt
        domega = max(min(domega, max_domega), -max_domega)
        omega = self.prev_omega + domega
        self.prev_omega = omega

        # ------------------------------------------------------------
        # Enforce minimum controllable velocities (EXPLICIT)
        # ------------------------------------------------------------
        if 0.0 < abs(v) < self.min_v:
            v = math.copysign(self.min_v, v)

        if 0.0 < abs(omega) < self.min_omega:
            omega = math.copysign(self.min_omega, omega)

        # ------------------------------------------------------------
        # Differential drive kinematics
        # ------------------------------------------------------------
        v_left = v - omega * (self.track_width / 2.0)
        v_right = v + omega * (self.track_width / 2.0)

        left_erpm = self.linear_to_erpm(v_left)
        right_erpm = self.linear_to_erpm(v_right)

        self.publish_rpm(left_erpm, right_erpm)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def linear_to_erpm(self, v):
        if abs(v) < 1e-3:
            return 0

        wheel_rps = v / (2.0 * math.pi * self.wheel_radius)
        wheel_rpm = wheel_rps * 60.0

        motor_rpm = wheel_rpm * self.gear_ratio
        erpm = motor_rpm * self.pole_pairs

        erpm = int(erpm)

        # Deadzone clamp
        if 0 < abs(erpm) < self.min_erpm:
            erpm = int(math.copysign(self.min_erpm, erpm))

        return max(min(erpm, self.max_erpm), -self.max_erpm)

    def publish_rpm(self, left, right):
        self.left_rpm_pub.publish(Int32(data=left))
        self.right_rpm_pub.publish(Int32(data=right))


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelToWheelRPM()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
