#!/usr/bin/env python3
"""
odom_relay_node.py
------------------
Relays odometry from /zed/zed_node/odom to /odom,
ensuring frame IDs match the TF tree expected by Nav2:

    header.frame_id  = "odom"
    child_frame_id   = "base_link"

This prevents TF and Nav2 costmap frame mismatches.
"""

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

class OdomRelayNode(Node):
    def __init__(self):
        super().__init__('odom_relay_node')

        # Declare parameters for input/output topics (optional override in launch)
        self.declare_parameter('input_topic', '/zed/zed_node/odom')
        self.declare_parameter('output_topic', '/odom')

        input_topic = self.get_parameter('input_topic').value
        output_topic = self.get_parameter('output_topic').value

        # Subscribers and publishers
        self.sub = self.create_subscription(Odometry, input_topic, self.relay_callback, 10)
        self.pub = self.create_publisher(Odometry, output_topic, 10)

        self.get_logger().info(f"Relaying odometry: {input_topic} → {output_topic}")
        self.get_logger().info("Fixing frame_id='odom', child_frame_id='base_link'")

        # For periodic debug print
        self.msg_count = 0

    def relay_callback(self, msg: Odometry):
        # Rewrite frame IDs to match Nav2 expectations
        # msg.header.frame_id = 'odom'
        # msg.child_frame_id = 'base_link'

        # Publish modified odometry
        self.pub.publish(msg)

        # Optional debug logging every 100 messages
        # self.msg_count += 1
        # if self.msg_count % 100 == 0:
        #     self.get_logger().debug(
        #         f"Published {self.msg_count} odom msgs with frame_id={msg.header.frame_id}, child_frame_id={msg.child_frame_id}"
        #     )

def main(args=None):
    rclpy.init(args=args)
    node = OdomRelayNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()



# #!/usr/bin/env python3

# import rclpy
# from rclpy.node import Node
# from nav_msgs.msg import Odometry

# class OdomRelayNode(Node):
#     def __init__(self):
#         super().__init__('odom_relay_node')
#         # self.sub = self.create_subscription(Odometry, '/visual_slam/tracking/odometry', self.relay_callback, 10)  # TODO: make it as ros argument later.
#         self.sub = self.create_subscription(Odometry, '/zed/zed_node/odom', self.relay_callback, 10)
#         self.pub = self.create_publisher(Odometry, '/odom', 10)

#     def relay_callback(self, msg):
#         self.pub.publish(msg)

# def main(args=None):
#     rclpy.init(args=args)
#     node = OdomRelayNode()
#     rclpy.spin(node)
#     rclpy.shutdown()

# if __name__ == '__main__':
#     main()
