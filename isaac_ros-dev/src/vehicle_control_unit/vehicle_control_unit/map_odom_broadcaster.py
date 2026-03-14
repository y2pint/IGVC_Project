#!/usr/bin/env python3
"""
Publishes a continuous map → odom identity transform.

Nav2 requires map → odom to be published at a steady rate (default timeout
is 0.1–0.3 s depending on the costmap config). A static_transform_publisher
only publishes once on /tf_static which Nav2 may not honour for the costmap
transform lookup — this node publishes at a configurable rate on /tf instead.

Use when:
  - map ≡ odom (no SLAM, no AMCL, no GPS-fused localization)
  - You want Nav2 to do local obstacle avoidance only
  - Your global mission planning is handled separately (e.g. mission frame)
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


class MapOdomIdentityPublisher(Node):
    def __init__(self):
        super().__init__('map_odom_identity_publisher')

        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('publish_rate_hz', 50.0)

        self.map_frame = self.get_parameter('map_frame').value
        self.odom_frame = self.get_parameter('odom_frame').value
        rate = float(self.get_parameter('publish_rate_hz').value)

        self.broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(1.0 / rate, self.publish_transform)

        self.get_logger().info(
            f'Publishing identity transform {self.map_frame} → {self.odom_frame} '
            f'at {rate:.0f} Hz'
        )

    def publish_transform(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.map_frame
        t.child_frame_id = self.odom_frame

        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = 1.0

        self.broadcaster.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = MapOdomIdentityPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()