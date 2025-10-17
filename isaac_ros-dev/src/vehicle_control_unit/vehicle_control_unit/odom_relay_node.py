#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

class OdomRelayNode(Node):
    def __init__(self):
        super().__init__('odom_relay_node')
        self.sub = self.create_subscription(Odometry, '/visual_slam/tracking/odometry', self.relay_callback, 10)
        self.pub = self.create_publisher(Odometry, '/odom', 10)

    def relay_callback(self, msg):
        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = OdomRelayNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()
