#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from mavros_msgs.msg import RCIn


class RCToCmdVel(Node):
    def __init__(self):
        super().__init__('rc_to_cmd_vel')

        # ------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------
        self.declare_parameter('ch_linear', 1)   # ch1
        self.declare_parameter('ch_angular', 0)  # ch2
        self.declare_parameter('ch_enable', 2)   # ch3

        self.declare_parameter('pwm_center', 1500)
        self.declare_parameter('pwm_range', 500)
        self.declare_parameter('deadzone', 50)

        self.declare_parameter('max_linear_vel', 1.5)   # m/s
        self.declare_parameter('max_angular_vel', 1.0)  # rad/s

        self.ch_linear = self.get_parameter('ch_linear').value
        self.ch_angular = self.get_parameter('ch_angular').value
        self.ch_enable = self.get_parameter('ch_enable').value

        self.pwm_center = self.get_parameter('pwm_center').value
        self.pwm_range = self.get_parameter('pwm_range').value
        self.deadzone = self.get_parameter('deadzone').value

        self.max_v = self.get_parameter('max_linear_vel').value
        self.max_omega = self.get_parameter('max_angular_vel').value

        # ------------------------------------------------------------
        # ROS interfaces
        # ------------------------------------------------------------
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.create_subscription(
            RCIn,
            '/mavros/rc/in',
            self.rc_callback,
            10
        )

        self.enabled = False

        self.get_logger().info("✅ RC → cmd_vel node initialized")

    # ------------------------------------------------------------
    # RC callback
    # ------------------------------------------------------------
    def rc_callback(self, msg: RCIn):
        # Safety check
        if len(msg.channels) <= max(self.ch_linear, self.ch_angular, self.ch_enable):
            self.get_logger().warn("RC channel index out of range")
            return

        pwm_linear = msg.channels[self.ch_linear]
        pwm_angular = msg.channels[self.ch_angular]
        pwm_enable = msg.channels[self.ch_enable]

        # Enable logic (dead-man switch)
        self.enabled = pwm_enable > self.pwm_center

        cmd = Twist()

        if not self.enabled:
            # Disabled → publish zero velocity
            self.cmd_vel_pub.publish(cmd)
            return

        # Map PWM → normalized [-1, 1]
        lin_norm = self.pwm_to_norm(pwm_linear)
        ang_norm = self.pwm_to_norm(pwm_angular)

        # Scale to physical units
        cmd.linear.x = lin_norm * self.max_v
        cmd.angular.z = -ang_norm * self.max_omega

        self.cmd_vel_pub.publish(cmd)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def pwm_to_norm(self, pwm):
        delta = pwm - self.pwm_center

        # Deadzone
        if abs(delta) < self.deadzone:
            return 0.0

        # Normalize
        return max(min(delta / self.pwm_range, 1.0), -1.0)


def main(args=None):
    rclpy.init(args=args)
    node = RCToCmdVel()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
