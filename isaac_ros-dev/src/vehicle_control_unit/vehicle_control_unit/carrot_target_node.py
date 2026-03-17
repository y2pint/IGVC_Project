#!/usr/bin/env python3
import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from collections import deque
import numpy as np

class CarrotTargetNode(Node):
    def __init__(self):
        super().__init__('carrot_target_node')
        # Parameters
        self.declare_parameter('lookahead_distance', 10.0)
        self.declare_parameter('taper_distance', 2.0)
        self.declare_parameter('min_lookahead', 0.5)
        self.declare_parameter('max_heading_change_deg', 10.0)
        self.declare_parameter('history_length_m', 3.0)

        self.lookahead = self.get_parameter(
            'lookahead_distance').get_parameter_value().double_value
        self.taper_distance = self.get_parameter(
            'taper_distance').get_parameter_value().double_value
        self.min_lookahead = self.get_parameter(
            'min_lookahead').get_parameter_value().double_value
        self.max_heading_change_deg = self.get_parameter(
            'max_heading_change_deg').get_parameter_value().double_value
        self.history_length_m = self.get_parameter(
            'history_length_m').get_parameter_value().double_value

        # Position history
        self.position_history = deque()
        self.history_total_dist = 0.0
        self.last_robot_pos = None

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

        # Timer (10 Hz)
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.get_logger().info('Carrot target node started')
        self.get_logger().info(f'lookahead_distance    : {self.lookahead}')
        self.get_logger().info(f'taper_distance        : {self.taper_distance}')
        self.get_logger().info(f'min_lookahead         : {self.min_lookahead}')
        self.get_logger().info(f'max_heading_change_deg: {self.max_heading_change_deg}')
        self.get_logger().info(f'history_length_m      : {self.history_length_m}')

    def robot_callback(self, msg):
        self.robot_pose = msg

        # Update position history
        x = msg.pose.position.x
        y = msg.pose.position.y

        if self.last_robot_pos is not None:
            dx = x - self.last_robot_pos[0]
            dy = y - self.last_robot_pos[1]
            dist = math.sqrt(dx*dx + dy*dy)

            # Only add if robot moved at least 0.05m to avoid GPS noise
            if dist >= 0.05:
                self.position_history.append((x, y))
                self.history_total_dist += dist

                # Trim history to history_length_m
                while self.history_total_dist > self.history_length_m and len(self.position_history) > 2:
                    oldest = self.position_history.popleft()
                    second = self.position_history[0]
                    removed_dist = math.sqrt(
                        (second[0] - oldest[0])**2 +
                        (second[1] - oldest[1])**2
                    )
                    self.history_total_dist -= removed_dist

                self.last_robot_pos = (x, y)
        else:
            self.last_robot_pos = (x, y)
            self.position_history.append((x, y))

    def goal_callback(self, msg):
        self.goal_pose = msg

    def compute_lane_heading(self) -> float:
        """
        Compute average heading from position history.
        Uses direction from oldest to newest point in history.
        Falls back to robot orientation if not enough history.
        """
        if len(self.position_history) < 2:
            if self.robot_pose is not None:
                return self.quaternion_to_yaw(self.robot_pose.pose.orientation)
            return 0.0

        pts = list(self.position_history)
        xs = np.array([p[0] for p in pts])
        ys = np.array([p[1] for p in pts])

        dx = xs[-1] - xs[0]
        dy = ys[-1] - ys[0]

        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            if self.robot_pose is not None:
                return self.quaternion_to_yaw(self.robot_pose.pose.orientation)
            return 0.0

        return math.atan2(dy, dx)

    def quaternion_to_yaw(self, q) -> float:
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        return math.atan2(siny_cosp, cosy_cosp)

    def wrap_to_pi(self, angle: float) -> float:
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def constrain_heading(self, desired_yaw: float, base_yaw: float) -> float:
        """
        Constrain desired_yaw to within max_heading_change_deg of base_yaw.
        """
        max_rad = math.radians(self.max_heading_change_deg)
        diff = self.wrap_to_pi(desired_yaw - base_yaw)
        clamped = max(-max_rad, min(max_rad, diff))
        return self.wrap_to_pi(base_yaw + clamped)

    def timer_callback(self):
        if self.robot_pose is None or self.goal_pose is None:
            return

        # Allow runtime parameter updates
        self.lookahead = self.get_parameter(
            'lookahead_distance').get_parameter_value().double_value
        self.taper_distance = self.get_parameter(
            'taper_distance').get_parameter_value().double_value
        self.min_lookahead = self.get_parameter(
            'min_lookahead').get_parameter_value().double_value
        self.max_heading_change_deg = self.get_parameter(
            'max_heading_change_deg').get_parameter_value().double_value
        self.history_length_m = self.get_parameter(
            'history_length_m').get_parameter_value().double_value

        xr = self.robot_pose.pose.position.x
        yr = self.robot_pose.pose.position.y
        xg = self.goal_pose.pose.position.x
        yg = self.goal_pose.pose.position.y
        dx = xg - xr
        dy = yg - yr
        dist = math.sqrt(dx*dx + dy*dy)

        if dist < 0.01:
            return

        # Taper lookahead smoothly only near goal
        if dist < self.taper_distance:
            lookahead = self.lookahead * (dist / self.taper_distance)
            lookahead = max(lookahead, self.min_lookahead)
        else:
            lookahead = self.lookahead

        # Desired heading toward waypoint
        desired_yaw = math.atan2(dy, dx)

        # Compute lane heading from position history
        lane_heading = self.compute_lane_heading()

        # Constrain carrot heading to max_heading_change_deg from lane heading
        constrained_yaw = self.constrain_heading(desired_yaw, lane_heading)

        # Recompute carrot position using constrained heading
        xc = xr + lookahead * math.cos(constrained_yaw)
        yc = yr + lookahead * math.sin(constrained_yaw)

        carrot = PoseStamped()
        carrot.header.stamp = self.get_clock().now().to_msg()
        carrot.header.frame_id = self.robot_pose.header.frame_id
        carrot.pose.position.x = xc
        carrot.pose.position.y = yc
        carrot.pose.position.z = 0.0
        carrot.pose.orientation.x = 0.0
        carrot.pose.orientation.y = 0.0
        carrot.pose.orientation.z = math.sin(constrained_yaw * 0.5)
        carrot.pose.orientation.w = math.cos(constrained_yaw * 0.5)

        self.carrot_pub.publish(carrot)

def main(args=None):
    rclpy.init(args=args)
    node = CarrotTargetNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()