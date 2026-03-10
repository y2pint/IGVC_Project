#!/usr/bin/env python3

import math
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped, Quaternion
from std_msgs.msg import Bool
from nav2_msgs.action import NavigateToPose

import tf2_ros


def yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.x = 0.0
    q.y = 0.0
    q.z = math.sin(yaw * 0.5)
    q.w = math.cos(yaw * 0.5)
    return q


def quaternion_to_yaw(q: Quaternion) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def wrap_to_pi(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


class CarrotToNav2ActionNode(Node):
    def __init__(self) -> None:
        super().__init__('carrot_to_nav2_action_node')

        # ------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------
        self.declare_parameter('carrot_topic', '/mission/carrot_target')
        self.declare_parameter('global_pose_topic', '/mission/global_pose_xy')
        self.declare_parameter('goal_frame_id', 'map')
        self.declare_parameter('robot_base_frame', 'base_link')
        self.declare_parameter('enable_topic', '/mission/navigation_enabled')
        self.declare_parameter('cancel_topic', '/mission/cancel_nav_goal')

        self.declare_parameter('timer_rate_hz', 0.5)
        self.declare_parameter('min_goal_shift_m', 0.75)
        self.declare_parameter('min_goal_yaw_shift_rad', 0.4)
        self.declare_parameter('use_pointing_yaw', True)
        self.declare_parameter('allow_preemption', True)

        # Optional safety/debug parameters
        self.declare_parameter('max_goal_distance_m', 20.0)
        self.declare_parameter('log_debug_info', True)

        carrot_topic = self.get_parameter('carrot_topic').value
        global_pose_topic = self.get_parameter('global_pose_topic').value
        enable_topic = self.get_parameter('enable_topic').value
        cancel_topic = self.get_parameter('cancel_topic').value

        self.goal_frame_id = self.get_parameter('goal_frame_id').value
        self.robot_base_frame = self.get_parameter('robot_base_frame').value

        timer_rate_hz = float(self.get_parameter('timer_rate_hz').value)
        self.min_goal_shift_m = float(self.get_parameter('min_goal_shift_m').value)
        self.min_goal_yaw_shift_rad = float(self.get_parameter('min_goal_yaw_shift_rad').value)
        self.use_pointing_yaw = bool(self.get_parameter('use_pointing_yaw').value)
        self.allow_preemption = bool(self.get_parameter('allow_preemption').value)

        self.max_goal_distance_m = float(self.get_parameter('max_goal_distance_m').value)
        self.log_debug_info = bool(self.get_parameter('log_debug_info').value)

        # ------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------
        self.carrot_pose: Optional[PoseStamped] = None
        self.global_pose: Optional[PoseStamped] = None
        self.navigation_enabled = True

        self.last_sent_goal_x: Optional[float] = None
        self.last_sent_goal_y: Optional[float] = None
        self.last_sent_goal_yaw: Optional[float] = None

        self.goal_in_progress = False
        self.current_goal_handle = None
        self.cancel_requested = False

        # ------------------------------------------------------------
        # ROS interfaces
        # ------------------------------------------------------------
        self.create_subscription(PoseStamped, carrot_topic, self.carrot_cb, 10)
        self.create_subscription(PoseStamped, global_pose_topic, self.global_pose_cb, 10)
        self.create_subscription(Bool, enable_topic, self.enable_cb, 10)
        self.create_subscription(Bool, cancel_topic, self.cancel_cb, 10)

        self.nav_client = ActionClient(self, NavigateToPose, '/navigate_to_pose')

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        self.timer = self.create_timer(1.0 / max(timer_rate_hz, 1e-3), self.timer_cb)

        self.get_logger().info('carrot_to_nav2_action_node started')
        self.get_logger().info(f'carrot_topic         : {carrot_topic}')
        self.get_logger().info(f'global_pose_topic    : {global_pose_topic}')
        self.get_logger().info(f'goal_frame_id        : {self.goal_frame_id}')
        self.get_logger().info(f'robot_base_frame     : {self.robot_base_frame}')
        self.get_logger().info(f'enable_topic         : {enable_topic}')
        self.get_logger().info(f'cancel_topic         : {cancel_topic}')

    # ------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------
    def carrot_cb(self, msg: PoseStamped) -> None:
        self.carrot_pose = msg

    def global_pose_cb(self, msg: PoseStamped) -> None:
        self.global_pose = msg

    def enable_cb(self, msg: Bool) -> None:
        self.navigation_enabled = msg.data
        if not self.navigation_enabled:
            self.get_logger().info('Navigation disabled')
        else:
            self.get_logger().info('Navigation enabled')

    def cancel_cb(self, msg: Bool) -> None:
        if msg.data:
            self.cancel_requested = True
            self.cancel_current_goal()

    # ------------------------------------------------------------
    # Nav2 goal management
    # ------------------------------------------------------------
    def cancel_current_goal(self) -> None:
        if self.current_goal_handle is None:
            self.get_logger().info('Cancel requested, but no active Nav2 goal exists')
            self.goal_in_progress = False
            self.cancel_requested = False
            return

        self.get_logger().warn('Cancelling current Nav2 goal...')
        cancel_future = self.current_goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(self.cancel_done_callback)

    def cancel_done_callback(self, future) -> None:
        try:
            _ = future.result()
            self.get_logger().info('Nav2 cancel request sent')
        except Exception as e:
            self.get_logger().error(f'Failed to cancel Nav2 goal: {e}')

        self.goal_in_progress = False
        self.current_goal_handle = None
        self.cancel_requested = False

    def goal_response_callback(self, future, goal_x: float, goal_y: float, goal_yaw: float) -> None:
        try:
            goal_handle = future.result()
        except Exception as e:
            self.goal_in_progress = False
            self.get_logger().error(f'Failed to send Nav2 goal: {e}')
            return

        if not goal_handle.accepted:
            self.goal_in_progress = False
            self.get_logger().warn('Nav2 goal rejected')
            return

        self.current_goal_handle = goal_handle
        self.last_sent_goal_x = goal_x
        self.last_sent_goal_y = goal_y
        self.last_sent_goal_yaw = goal_yaw

        self.get_logger().info('Nav2 goal accepted')

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def feedback_callback(self, feedback_msg) -> None:
        # Keep as placeholder for future use
        _ = feedback_msg

    def result_callback(self, future) -> None:
        self.goal_in_progress = False
        self.current_goal_handle = None

        try:
            result = future.result()
        except Exception as e:
            self.get_logger().error(f'Failed to get Nav2 result: {e}')
            return

        if result is None:
            self.get_logger().warn('Nav2 result callback returned None')
            return

        status = result.status
        self.get_logger().info(f'Nav2 goal finished with status {status}')

    def send_goal(self, goal_x: float, goal_y: float, goal_yaw: float) -> None:
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.header.frame_id = self.goal_frame_id
        goal_msg.pose.pose.position.x = goal_x
        goal_msg.pose.pose.position.y = goal_y
        goal_msg.pose.pose.position.z = 0.0
        goal_msg.pose.pose.orientation = yaw_to_quaternion(goal_yaw)

        self.get_logger().info(
            f'Sending Nav2 goal: x={goal_x:.2f}, y={goal_y:.2f}, yaw={goal_yaw:.2f}'
        )

        self.goal_in_progress = True
        send_future = self.nav_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )
        send_future.add_done_callback(
            lambda future: self.goal_response_callback(future, goal_x, goal_y, goal_yaw)
        )

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def angle_diff(self, a: float, b: float) -> float:
        return wrap_to_pi(a - b)

    def should_send_goal(self, goal_x: float, goal_y: float, goal_yaw: float) -> bool:
        if self.last_sent_goal_x is None or self.last_sent_goal_y is None or self.last_sent_goal_yaw is None:
            return True

        pos_shift = math.hypot(goal_x - self.last_sent_goal_x, goal_y - self.last_sent_goal_y)
        yaw_shift = abs(self.angle_diff(goal_yaw, self.last_sent_goal_yaw))

        return (pos_shift >= self.min_goal_shift_m) or (yaw_shift >= self.min_goal_yaw_shift_rad)

    def lookup_robot_pose_in_map(self) -> Optional[Tuple[float, float, float]]:
        try:
            tf_msg = self.tf_buffer.lookup_transform(
                self.goal_frame_id,     # target frame
                self.robot_base_frame,  # source frame
                rclpy.time.Time()
            )
        except Exception as e:
            self.get_logger().debug(
                f'Failed TF lookup {self.goal_frame_id} <- {self.robot_base_frame}: {e}'
            )
            return None

        x = tf_msg.transform.translation.x
        y = tf_msg.transform.translation.y
        yaw = quaternion_to_yaw(tf_msg.transform.rotation)
        return (x, y, yaw)

    def compute_goal_in_map(self) -> Optional[Tuple[float, float, float]]:
        if self.carrot_pose is None or self.global_pose is None:
            return None

        robot_pose_map = self.lookup_robot_pose_in_map()
        if robot_pose_map is None:
            return None

        robot_map_x, robot_map_y, robot_map_yaw = robot_pose_map

        # Robot position in global mission frame
        robot_global_x = self.global_pose.pose.position.x
        robot_global_y = self.global_pose.pose.position.y
        robot_global_yaw = quaternion_to_yaw(self.global_pose.pose.orientation)

        # Carrot position in global mission frame
        carrot_global_x = self.carrot_pose.pose.position.x
        carrot_global_y = self.carrot_pose.pose.position.y

        # Global displacement from robot to carrot
        dx_global = carrot_global_x - robot_global_x
        dy_global = carrot_global_y - robot_global_y

        # Current rotation between global mission frame and Nav2 map frame
        # map_yaw = global_yaw + theta   =>   theta = map_yaw - global_yaw
        theta = wrap_to_pi(robot_map_yaw - robot_global_yaw)

        # Rotate global displacement into map frame
        c = math.cos(theta)
        s = math.sin(theta)

        dx_map = c * dx_global - s * dy_global
        dy_map = s * dx_global + c * dy_global

        # Optional safety clamp
        goal_dist = math.hypot(dx_map, dy_map)
        if goal_dist > self.max_goal_distance_m and goal_dist > 1e-6:
            scale = self.max_goal_distance_m / goal_dist
            dx_map *= scale
            dy_map *= scale
            self.get_logger().warn(
                f'Clamped goal distance from {goal_dist:.2f} m '
                f'to {self.max_goal_distance_m:.2f} m'
            )

        goal_x = robot_map_x + dx_map
        goal_y = robot_map_y + dy_map

        if self.use_pointing_yaw:
            if abs(dx_map) > 1e-6 or abs(dy_map) > 1e-6:
                goal_yaw = math.atan2(dy_map, dx_map)
            else:
                goal_yaw = robot_map_yaw
        else:
            goal_yaw = robot_map_yaw

        if self.log_debug_info:
            self.get_logger().info(
                f'global_yaw={robot_global_yaw:.3f}, map_yaw={robot_map_yaw:.3f}, '
                f'theta(map-global)={theta:.3f}, '
                f'd_global=({dx_global:.2f},{dy_global:.2f}), '
                f'd_map=({dx_map:.2f},{dy_map:.2f})'
            )

        return goal_x, goal_y, goal_yaw

    # ------------------------------------------------------------
    # Main timer
    # ------------------------------------------------------------
    def timer_cb(self) -> None:
        if not self.navigation_enabled:
            return

        if self.cancel_requested:
            return

        if not self.nav_client.server_is_ready():
            self.nav_client.wait_for_server(timeout_sec=0.1)
            return

        goal = self.compute_goal_in_map()
        if goal is None:
            return

        goal_x, goal_y, goal_yaw = goal

        if not self.should_send_goal(goal_x, goal_y, goal_yaw):
            return

        if self.goal_in_progress and not self.allow_preemption:
            return

        if self.goal_in_progress and self.allow_preemption and self.current_goal_handle is not None:
            cancel_future = self.current_goal_handle.cancel_goal_async()
            cancel_future.add_done_callback(
                lambda _: self.send_goal(goal_x, goal_y, goal_yaw)
            )
            return

        self.send_goal(goal_x, goal_y, goal_yaw)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CarrotToNav2ActionNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()