#!/usr/bin/env python3
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, String
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry


def yaw_from_quat(x: float, y: float, z: float, w: float) -> float:
    # yaw (Z axis rotation) from quaternion
    # Reference: standard yaw extraction for ROS ENU frames
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def wrap_to_pi(a: float) -> float:
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


@dataclass
class GoalState:
    goal: PoseStamped
    set_time: float
    last_hit_time: Optional[float] = None
    consecutive_hits: int = 0
    reached_latched: bool = False


class GoalReachChecker(Node):
    """
    Independent goal reach checker (position + yaw) with stability gating.
    """

    def __init__(self):
        super().__init__("goal_reach_checker")

        # --- Params ---
        self.declare_parameter("pose_topic", "/odometry/global")
        self.declare_parameter("goal_topic", "/goal_pose")
        self.declare_parameter("xy_tolerance_m", 0.40)
        self.declare_parameter("yaw_tolerance_rad", 0.45)  # ~20 deg
        self.declare_parameter("require_yaw", False)

        # Stability gating: you can use either/both.
        self.declare_parameter("hold_time_sec", 0.50)       # must stay in tol for this long
        self.declare_parameter("consecutive_hits", 5)       # or this many consecutive pose updates in tol

        # Safety/behavior
        self.declare_parameter("goal_timeout_sec", 0.0)     # 0 disables timeout
        self.declare_parameter("min_pose_rate_hz", 5.0)     # used only for warnings
        self.declare_parameter("latch_on_reach", True)      # once reached, stays true until new goal

        # Publishers
        self.pub_reached = self.create_publisher(Bool, "goal_reached", 10)
        self.pub_status = self.create_publisher(String, "goal_reach_status", 10)

        # Subscribers
        pose_topic = self.get_parameter("pose_topic").get_parameter_value().string_value
        goal_topic = self.get_parameter("goal_topic").get_parameter_value().string_value

        self.sub_pose = self.create_subscription(Odometry, pose_topic, self.on_pose, 20)
        self.sub_goal = self.create_subscription(PoseStamped, goal_topic, self.on_goal, 10)

        # Timer for periodic publish + timeout checks
        self.timer = self.create_timer(0.10, self.on_timer)

        self.goal_state: Optional[GoalState] = None

        self.last_pose_time: Optional[float] = None
        self.latest_pose_xy_yaw: Optional[Tuple[float, float, float]] = None

        self.get_logger().info(
            f"GoalReachChecker started. pose_topic={pose_topic}, goal_topic={goal_topic}"
        )

    def on_goal(self, msg: PoseStamped):
        now = self.get_clock().now().nanoseconds / 1e9
        self.goal_state = GoalState(goal=msg, set_time=now)
        self.get_logger().info(
            f"New goal received: frame={msg.header.frame_id} "
            f"pos=({msg.pose.position.x:.2f},{msg.pose.position.y:.2f})"
        )

    def on_pose(self, msg: Odometry):
        now = self.get_clock().now().nanoseconds / 1e9
        self.last_pose_time = now

        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = yaw_from_quat(q.x, q.y, q.z, q.w)
        self.latest_pose_xy_yaw = (p.x, p.y, yaw)

        # If no goal, nothing to evaluate
        if self.goal_state is None:
            return

        # If latched and configured to latch, keep it
        latch = self.get_parameter("latch_on_reach").get_parameter_value().bool_value
        if latch and self.goal_state.reached_latched:
            return

        ok, dist_xy, dyaw = self.check_goal(p.x, p.y, yaw, self.goal_state.goal)

        if ok:
            self.goal_state.consecutive_hits += 1
            if self.goal_state.last_hit_time is None:
                self.goal_state.last_hit_time = now
        else:
            self.goal_state.consecutive_hits = 0
            self.goal_state.last_hit_time = None

        # Determine reach condition
        hold_time = self.get_parameter("hold_time_sec").get_parameter_value().double_value
        needed_hits = self.get_parameter("consecutive_hits").get_parameter_value().integer_value

        reached_by_hold = (
            hold_time > 0.0 and
            self.goal_state.last_hit_time is not None and
            (now - self.goal_state.last_hit_time) >= hold_time
        )
        reached_by_hits = (needed_hits > 0 and self.goal_state.consecutive_hits >= needed_hits)

        if reached_by_hold or reached_by_hits:
            self.goal_state.reached_latched = True
            self.get_logger().info(
                f"GOAL REACHED (xy={dist_xy:.3f} m, yaw={dyaw:.3f} rad, "
                f"hits={self.goal_state.consecutive_hits})"
            )

    def check_goal(self, x: float, y: float, yaw: float, goal: PoseStamped) -> Tuple[bool, float, float]:
        xy_tol = self.get_parameter("xy_tolerance_m").get_parameter_value().double_value
        yaw_tol = self.get_parameter("yaw_tolerance_rad").get_parameter_value().double_value
        require_yaw = self.get_parameter("require_yaw").get_parameter_value().bool_value

        gx = goal.pose.position.x
        gy = goal.pose.position.y
        gq = goal.pose.orientation
        gyaw = yaw_from_quat(gq.x, gq.y, gq.z, gq.w)

        dx = gx - x
        dy = gy - y
        dist_xy = math.hypot(dx, dy)

        dyaw = abs(wrap_to_pi(gyaw - yaw))

        ok_xy = dist_xy <= xy_tol
        ok_yaw = (dyaw <= yaw_tol) if require_yaw else True

        return (ok_xy and ok_yaw), dist_xy, dyaw

    def on_timer(self):
        now = self.get_clock().now().nanoseconds / 1e9

        reached = False
        status = "no_goal"

        if self.goal_state is not None:
            reached = self.goal_state.reached_latched
            status = "reached" if reached else "tracking"

            # Optional timeout
            timeout = self.get_parameter("goal_timeout_sec").get_parameter_value().double_value
            if timeout > 0.0 and not reached:
                if (now - self.goal_state.set_time) > timeout:
                    status = "timeout_not_reached"

        # Pose rate warning (soft)
        if self.last_pose_time is None:
            status = status + "|no_pose"
        else:
            dt = now - self.last_pose_time
            if dt > 0.5:
                status = status + f"|pose_stale_dt={dt:.2f}s"

        self.pub_reached.publish(Bool(data=reached))
        self.pub_status.publish(String(data=status))


def main():
    rclpy.init()
    node = GoalReachChecker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
