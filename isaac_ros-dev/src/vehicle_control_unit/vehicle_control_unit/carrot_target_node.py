#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped


class CarrotTargetNode(Node):

    def __init__(self):
        super().__init__('carrot_target_node')

        # Parameters
        self.declare_parameter('lookahead_distance', 2.5)
        self.lookahead = self.get_parameter(
            'lookahead_distance').get_parameter_value().double_value

        # State
        self.robot_pose = None
        self.goal_pose = None

        # Subscribers
        self.create_subscription(
            PoseStamped,
            '/mission/global_pose_xy',
            self.robot_callback,
            10)

        self.create_subscription(
            PoseStamped,
            '/mission/current_waypoint_xy',
            self.goal_callback,
            10)

        # Publisher
        self.carrot_pub = self.create_publisher(
            PoseStamped,
            '/mission/carrot_target',
            10)

        # Timer (2 Hz)
        self.timer = self.create_timer(0.5, self.timer_callback)

        self.get_logger().info('Carrot target node started')

    def robot_callback(self, msg):
        self.robot_pose = msg

    def goal_callback(self, msg):
        self.goal_pose = msg

    def timer_callback(self):

        if self.robot_pose is None or self.goal_pose is None:
            return

        xr = self.robot_pose.pose.position.x
        yr = self.robot_pose.pose.position.y

        xg = self.goal_pose.pose.position.x
        yg = self.goal_pose.pose.position.y

        dx = xg - xr
        dy = yg - yr

        dist = math.sqrt(dx*dx + dy*dy)

        if dist < 0.01:
            return

        lookahead = min(self.lookahead, dist)

        ux = dx / dist
        uy = dy / dist

        xc = xr + lookahead * ux
        yc = yr + lookahead * uy

        carrot = PoseStamped()

        carrot.header.stamp = self.get_clock().now().to_msg()
        carrot.header.frame_id = self.robot_pose.header.frame_id

        carrot.pose.position.x = xc
        carrot.pose.position.y = yc
        carrot.pose.position.z = 0.0

        carrot.pose.orientation = self.robot_pose.pose.orientation

        self.carrot_pub.publish(carrot)


def main(args=None):

    rclpy.init(args=args)

    node = CarrotTargetNode()

    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()