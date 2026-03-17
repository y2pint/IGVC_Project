#!/usr/bin/env python3

import math
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped, Quaternion
from std_msgs.msg import Bool
from nav2_msgs.action import NavigateToPose
from action_msgs.msg import GoalStatus

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

        self.declare_parameter('timer_rate_hz', 2.0)              # was 0.5
        self.declare_parameter('min_goal_shift_m', 0.5)           # was 1.5
        self.declare_parameter('min_goal_yaw_shift_rad', 0.2)     # was 0.4
        self.declare_parameter('use_pointing_yaw', True)
        self.declare_parameter('allow_preemption', True)

        self.declare_parameter('max_goal_distance_m', 20.0)
        self.declare_parameter('log_debug_info', True)
        self.declare_parameter('goal_stale_timeout_sec', 2.0)

        carrot_topic = str(self.get_parameter('carrot_topic').value)
        global_pose_topic = str(self.get_parameter('global_pose_topic').value)
        enable_topic = str(self.get_parameter('enable_topic').value)
        cancel_topic = str(self.get_parameter('cancel_topic').value)

        self.goal_frame_id = str(self.get_parameter('goal_frame_id').value)
        self.robot_base_frame = str(self.get_parameter('robot_base_frame').value)

        timer_rate_hz = float(self.get_parameter('timer_rate_hz').value)
        self.min_goal_shift_m = float(self.get_parameter('min_goal_shift_m').value)
        self.min_goal_yaw_shift_rad = float(self.get_parameter('min_goal_yaw_shift_rad').value)
        self.use_pointing_yaw = bool(self.get_parameter('use_pointing_yaw').value)
        self.allow_preemption = bool(self.get_parameter('allow_preemption').value)

        self.max_goal_distance_m = float(self.get_parameter('max_goal_distance_m').value)
        self.log_debug_info = bool(self.get_parameter('log_debug_info').value)
        self.goal_stale_timeout_sec = float(self.get_parameter('goal_stale_timeout_sec').value)

        # ------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------
        self.carrot_pose: Optional[PoseStamped] = None
        self.global_pose: Optional[PoseStamped] = None
        self.navigation_enabled = False

        self.last_sent_goal_x: Optional[float] = None
        self.last_sent_goal_y: Optional[float] = None
        self.last_sent_goal_yaw: Optional[float] = None

        # Clean action state machine
        self.send_in_progress = False
        self.goal_active = False
        self.cancel_in_progress = False
        self.current_goal_handle = None
        self.pending_goal: Optional[Tuple[float, float, float]] = None

        self.goal_seq = 0
        self.active_goal_seq: Optional[int] = None
        self.pending_goal_seq: Optional[int] = None

        self.last_carrot_time = None
        self.last_global_pose_time = None

        self.last_server_not_ready_log_ns = 0
        self.server_not_ready_log_period_ns = int(2.0 * 1e9)

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
        self.get_logger().info(f'carrot_topic           : {carrot_topic}')
        self.get_logger().info(f'global_pose_topic      : {global_pose_topic}')
        self.get_logger().info(f'goal_frame_id          : {self.goal_frame_id}')
        self.get_logger().info(f'robot_base_frame       : {self.robot_base_frame}')
        self.get_logger().info(f'enable_topic           : {enable_topic}')
        self.get_logger().info(f'cancel_topic           : {cancel_topic}')
        self.get_logger().info(f'timer_rate_hz          : {timer_rate_hz}')
        self.get_logger().info(f'min_goal_shift_m       : {self.min_goal_shift_m}')
        self.get_logger().info(f'min_goal_yaw_shift_rad : {self.min_goal_yaw_shift_rad}')
        self.get_logger().info(f'use_pointing_yaw       : {self.use_pointing_yaw}')
        self.get_logger().info(f'allow_preemption       : {self.allow_preemption}')

    # ------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------
    def carrot_cb(self, msg: PoseStamped) -> None:
        self.carrot_pose = msg
        self.last_carrot_time = self.get_clock().now()

    def global_pose_cb(self, msg: PoseStamped) -> None:
        self.global_pose = msg
        self.last_global_pose_time = self.get_clock().now()

    def enable_cb(self, msg: Bool) -> None:
        prev = self.navigation_enabled
        self.navigation_enabled = msg.data

        if self.navigation_enabled and not prev:
            self.get_logger().info('Navigation enabled')
        elif (not self.navigation_enabled) and prev:
            self.get_logger().warn('Navigation disabled, cancelling active goal if needed')
            self.pending_goal = None
            self.pending_goal_seq = None
            self.request_cancel_current_goal()

    def cancel_cb(self, msg: Bool) -> None:
        if not msg.data:
            return
        self.get_logger().warn('External cancel requested')
        self.pending_goal = None
        self.pending_goal_seq = None
        self.request_cancel_current_goal()

    # ------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------
    def log_info_throttled(self, msg: str, period_sec: float = 2.0) -> None:
        now_ns = self.get_clock().now().nanoseconds
        period_ns = int(period_sec * 1e9)
        if now_ns - self.last_server_not_ready_log_ns >= period_ns:
            self.last_server_not_ready_log_ns = now_ns
            self.get_logger().info(msg)

    # ------------------------------------------------------------
    # Status helper
    # ------------------------------------------------------------
    def status_to_string(self, status: int) -> str:
        mapping = {
            GoalStatus.STATUS_UNKNOWN: 'UNKNOWN',
            GoalStatus.STATUS_ACCEPTED: 'ACCEPTED',
            GoalStatus.STATUS_EXECUTING: 'EXECUTING',
            GoalStatus.STATUS_CANCELING: 'CANCELING',
            GoalStatus.STATUS_SUCCEEDED: 'SUCCEEDED',
            GoalStatus.STATUS_CANCELED: 'CANCELED',
            GoalStatus.STATUS_ABORTED: 'ABORTED',
        }
        return mapping.get(status, f'UNRECOGNIZED({status})')

    # ------------------------------------------------------------
    # Action state helpers
    # ------------------------------------------------------------
    def reset_action_state(self) -> None:
        self.send_in_progress = False
        self.goal_active = False
        self.cancel_in_progress = False
        self.current_goal_handle = None
        self.active_goal_seq = None

    def request_cancel_current_goal(self) -> None:
        if self.cancel_in_progress:
            self.get_logger().info('Cancel already in progress')
            return

        if self.send_in_progress:
            self.get_logger().warn('Cancel requested while goal send is in progress; waiting for acceptance/result')
            return

        if not self.goal_active or self.current_goal_handle is None:
            self.get_logger().info('Cancel requested, but no active Nav2 goal exists')
            self.reset_action_state()
            return

        self.cancel_in_progress = True
        seq = self.active_goal_seq
        self.get_logger().warn(f'Requesting cancel for active Nav2 goal seq={seq}')
        cancel_future = self.current_goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(self.cancel_response_callback)

    def cancel_response_callback(self, future) -> None:
        try:
            cancel_response = future.result()
            num = len(cancel_response.goals_canceling)
            self.get_logger().info(f'Nav2 cancel response received, goals_canceling={num}')
        except Exception as e:
            self.get_logger().error(f'Failed to send cancel request to Nav2: {e}')
            self.cancel_in_progress = False

    # ------------------------------------------------------------
    # Nav2 goal management
    # ------------------------------------------------------------
    def send_goal(self, goal_x: float, goal_y: float, goal_yaw: float) -> None:
        if self.send_in_progress:
            self.get_logger().warn('send_goal() called while send_in_progress=True; ignoring')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.header.frame_id = self.goal_frame_id
        goal_msg.pose.pose.position.x = goal_x
        goal_msg.pose.pose.position.y = goal_y
        goal_msg.pose.pose.position.z = 0.0
        goal_msg.pose.pose.orientation = yaw_to_quaternion(goal_yaw)

        self.goal_seq += 1
        seq = self.goal_seq

        self.send_in_progress = True
        self.pending_goal = None
        self.pending_goal_seq = None

        self.get_logger().info(
            f'Sending Nav2 goal seq={seq}: x={goal_x:.2f}, y={goal_y:.2f}, yaw={goal_yaw:.2f}'
        )

        send_future = self.nav_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )
        send_future.add_done_callback(
            lambda future: self.goal_response_callback(future, goal_x, goal_y, goal_yaw, seq)
        )

    def goal_response_callback(
        self,
        future,
        goal_x: float,
        goal_y: float,
        goal_yaw: float,
        seq: int
    ) -> None:
        self.send_in_progress = False

        try:
            goal_handle = future.result()
        except Exception as e:
            self.get_logger().error(f'Failed to send Nav2 goal seq={seq}: {e}')
            return

        if not goal_handle.accepted:
            self.get_logger().warn(f'Nav2 goal seq={seq} rejected')
            return

        self.current_goal_handle = goal_handle
        self.goal_active = True
        self.cancel_in_progress = False
        self.active_goal_seq = seq

        self.last_sent_goal_x = goal_x
        self.last_sent_goal_y = goal_y
        self.last_sent_goal_yaw = goal_yaw

        self.get_logger().info(f'Nav2 goal seq={seq} accepted')

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def feedback_callback(self, feedback_msg) -> None:
        _ = feedback_msg

    def result_callback(self, future) -> None:
        prev_seq = self.active_goal_seq

        try:
            result = future.result()
        except Exception as e:
            self.get_logger().error(f'Failed to get Nav2 result for seq={prev_seq}: {e}')
            self.reset_action_state()
            return

        if result is None:
            self.get_logger().warn(f'Nav2 result callback returned None for seq={prev_seq}')
            self.reset_action_state()
            return

        status = result.status
        status_str = self.status_to_string(status)

        self.get_logger().info(f'Nav2 goal seq={prev_seq} finished with status {status_str} ({status})')

        self.reset_action_state()

        # If a newer goal was queued during preemption, send it now
        if self.navigation_enabled and self.pending_goal is not None:
            pending = self.pending_goal
            pending_seq = self.pending_goal_seq

            self.pending_goal = None
            self.pending_goal_seq = None

            self.get_logger().info(
                f'Sending deferred goal after result of seq={prev_seq}. '
                f'Deferred marker={pending_seq}'
            )
            self.send_goal(*pending)

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

    def is_input_fresh(self) -> bool:
        now = self.get_clock().now()

        if self.last_carrot_time is None or self.last_global_pose_time is None:
            return False

        carrot_age = (now - self.last_carrot_time).nanoseconds / 1e9
        global_age = (now - self.last_global_pose_time).nanoseconds / 1e9

        if carrot_age > self.goal_stale_timeout_sec:
            self.log_info_throttled(
                f'Carrot target stale: age={carrot_age:.2f}s > {self.goal_stale_timeout_sec:.2f}s',
                period_sec=2.0
            )
            return False

        if global_age > self.goal_stale_timeout_sec:
            self.log_info_throttled(
                f'Global pose stale: age={global_age:.2f}s > {self.goal_stale_timeout_sec:.2f}s',
                period_sec=2.0
            )
            return False

        return True

    def lookup_robot_pose_in_map(self) -> Optional[Tuple[float, float, float]]:
        try:
            tf_msg = self.tf_buffer.lookup_transform(
                self.goal_frame_id,
                self.robot_base_frame,
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

        if not self.is_input_fresh():
            return None

        robot_pose_map = self.lookup_robot_pose_in_map()
        if robot_pose_map is None:
            return None

        robot_map_x, robot_map_y, robot_map_yaw = robot_pose_map

        robot_global_x = self.global_pose.pose.position.x
        robot_global_y = self.global_pose.pose.position.y
        robot_global_yaw = quaternion_to_yaw(self.global_pose.pose.orientation)

        carrot_global_x = self.carrot_pose.pose.position.x
        carrot_global_y = self.carrot_pose.pose.position.y

        dx_global = carrot_global_x - robot_global_x
        dy_global = carrot_global_y - robot_global_y

        theta = wrap_to_pi(robot_map_yaw - robot_global_yaw)

        c = math.cos(theta)
        s = math.sin(theta)

        dx_map = c * dx_global - s * dy_global
        dy_map = s * dx_global + c * dy_global

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
                f'd_map=({dx_map:.2f},{dy_map:.2f}), '
                f'goal=({goal_x:.2f},{goal_y:.2f},{goal_yaw:.2f})'
            )

        return goal_x, goal_y, goal_yaw

    # ------------------------------------------------------------
    # Main timer
    # ------------------------------------------------------------
    def timer_cb(self) -> None:
        if not self.navigation_enabled:
            return

        if not self.nav_client.server_is_ready():
            self.nav_client.wait_for_server(timeout_sec=0.05)
            self.log_info_throttled('Nav2 action server not ready yet', period_sec=2.0)
            return

        goal = self.compute_goal_in_map()
        if goal is None:
            return

        goal_x, goal_y, goal_yaw = goal

        if not self.should_send_goal(goal_x, goal_y, goal_yaw):
            return

        # If no action activity exists, send immediately
        if (not self.goal_active) and (not self.send_in_progress) and (not self.cancel_in_progress):
            self.send_goal(goal_x, goal_y, goal_yaw)
            return

        # If preemption is disabled, do nothing until current goal finishes
        if not self.allow_preemption:
            return

        # If a send is still in progress, just remember the latest target
        if self.send_in_progress:
            self.pending_goal = (goal_x, goal_y, goal_yaw)
            self.pending_goal_seq = self.goal_seq + 1
            self.get_logger().info(
                f'Deferred new goal while send_in_progress=True; '
                f'pending marker={self.pending_goal_seq}'
            )
            return

        # If cancel is already in progress, only update the pending goal
        if self.cancel_in_progress:
            self.pending_goal = (goal_x, goal_y, goal_yaw)
            self.pending_goal_seq = self.goal_seq + 1
            self.get_logger().info(
                f'Updated pending goal while cancel_in_progress=True; '
                f'pending marker={self.pending_goal_seq}'
            )
            return

        # Active goal exists: queue the new goal and cancel the old one once
        if self.goal_active:
            self.pending_goal = (goal_x, goal_y, goal_yaw)
            self.pending_goal_seq = self.goal_seq + 1
            self.get_logger().info(
                f'Queued preempting goal; active seq={self.active_goal_seq}, '
                f'pending marker={self.pending_goal_seq}'
            )
            self.request_cancel_current_goal()
            return


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