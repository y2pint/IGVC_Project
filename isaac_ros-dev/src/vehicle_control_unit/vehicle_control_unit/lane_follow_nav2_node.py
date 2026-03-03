#!/usr/bin/env python3
import math
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_srvs.srv import Trigger
from nav_msgs.msg import Path
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose

import tf2_ros
from tf2_ros import TransformException


def quat_from_yaw(yaw: float):
    half = 0.5 * yaw
    return (0.0, 0.0, math.sin(half), math.cos(half))


def yaw_from_segment(p0, p1) -> float:
    return math.atan2(p1.y - p0.y, p1.x - p0.x)


def dist2_xy(p) -> float:
    return p.x * p.x + p.y * p.y


class LaneFollowNav2Node(Node):
    """
    Lane-following "carrot goal" node with:
      - Start/Stop services
      - Nav2 NavigateToPose action client
      - Auto-cancel if lane path becomes stale / empty
      - Debug publishers for RViz (lookahead pose, goal pose, 2-point goal path)

    Assumption:
      - /lane/centerline_path frame_id: base_link (or other frame connected by TF)
      - We express Nav2 goals in goal_frame (default: odom)
    """

    def __init__(self):
        super().__init__('lane_follow_nav2_node')

        # -------------------------
        # Parameters
        # -------------------------
        self.declare_parameter('path_topic', '/lane/centerline_path')
        self.declare_parameter('lookahead_m', 1.2)
        self.declare_parameter('publish_rate_hz', 8.0)
        self.declare_parameter('min_forward_x', 0.2)
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('goal_frame', 'odom')
        self.declare_parameter('action_name', 'navigate_to_pose')
        self.declare_parameter('lane_timeout_s', 0.4)
        self.declare_parameter('min_poses', 5)
        self.declare_parameter('send_goal_dist_m', 0.25)
        self.declare_parameter('send_goal_yaw_rad', 0.35)
        self.declare_parameter('publish_zero_cmd_vel_on_loss', True)
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')

        # Debug params (publish even when disabled)
        self.declare_parameter('debug_publish', True)
        self.declare_parameter('debug_republish_input_path', False)
        self.declare_parameter('debug_input_path_topic', '/lane_follow/debug/input_path')
        self.declare_parameter('debug_lookahead_topic', '/lane_follow/debug/lookahead')
        self.declare_parameter('debug_goal_topic', '/lane_follow/debug/goal')
        self.declare_parameter('debug_goal_path_topic', '/lane_follow/debug/goal_path')

        self.path_topic = self.get_parameter('path_topic').value
        self.lookahead_m = float(self.get_parameter('lookahead_m').value)
        self.publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self.min_forward_x = float(self.get_parameter('min_forward_x').value)
        self.base_frame = self.get_parameter('base_frame').value
        self.goal_frame = self.get_parameter('goal_frame').value
        self.action_name = self.get_parameter('action_name').value
        self.lane_timeout_s = float(self.get_parameter('lane_timeout_s').value)
        self.min_poses = int(self.get_parameter('min_poses').value)
        self.send_goal_dist_m = float(self.get_parameter('send_goal_dist_m').value)
        self.send_goal_yaw_rad = float(self.get_parameter('send_goal_yaw_rad').value)
        self.publish_zero_on_loss = bool(self.get_parameter('publish_zero_cmd_vel_on_loss').value)
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').value

        self.debug_publish = bool(self.get_parameter('debug_publish').value)
        self.debug_republish_input_path = bool(self.get_parameter('debug_republish_input_path').value)
        self.debug_input_path_topic = self.get_parameter('debug_input_path_topic').value
        self.debug_lookahead_topic = self.get_parameter('debug_lookahead_topic').value
        self.debug_goal_topic = self.get_parameter('debug_goal_topic').value
        self.debug_goal_path_topic = self.get_parameter('debug_goal_path_topic').value

        # -------------------------
        # TF
        # -------------------------
        self.tf_buffer = tf2_ros.Buffer(cache_time=Duration(seconds=2.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # -------------------------
        # QoS
        # -------------------------
        # For Path coming from perception, BEST_EFFORT is often used.
        # Keep it simple; RViz also commonly subscribes with BEST_EFFORT.
        debug_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE
        )

        # -------------------------
        # ROS I/O
        # -------------------------
        self.path_sub = self.create_subscription(Path, self.path_topic, self._on_path, 10)

        self.start_srv = self.create_service(Trigger, '/lane_follow/start', self._on_start)
        self.stop_srv = self.create_service(Trigger, '/lane_follow/stop', self._on_stop)

        self.nav_client = ActionClient(self, NavigateToPose, self.action_name)

        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10) if self.publish_zero_on_loss else None

        # Debug publishers
        self.debug_input_path_pub = None
        self.debug_lookahead_pub = None
        self.debug_goal_pub = None
        self.debug_goal_path_pub = None
        if self.debug_publish:
            if self.debug_republish_input_path:
                self.debug_input_path_pub = self.create_publisher(Path, self.debug_input_path_topic, debug_qos)
            self.debug_lookahead_pub = self.create_publisher(PoseStamped, self.debug_lookahead_topic, debug_qos)
            self.debug_goal_pub = self.create_publisher(PoseStamped, self.debug_goal_topic, debug_qos)
            self.debug_goal_path_pub = self.create_publisher(Path, self.debug_goal_path_topic, debug_qos)

        # State
        self.enabled = False
        self.latest_path: Optional[Path] = None
        self.last_path_time = None  # rclpy.time.Time
        self.goal_handle = None     # active NavigateToPose goal handle (if any)
        self.last_sent_goal: Optional[Tuple[float, float, float]] = None  # (x,y,yaw) in goal_frame

        # Timer
        period = 1.0 / max(1e-3, self.publish_rate_hz)
        self.timer = self.create_timer(period, self._on_timer)

        self.get_logger().info(
            "LaneFollowNav2Node ready.\n"
            f"  path_topic: {self.path_topic}\n"
            f"  action: {self.action_name}\n"
            f"  goal_frame: {self.goal_frame}\n"
            f"  lookahead_m: {self.lookahead_m}\n"
            f"  lane_timeout_s: {self.lane_timeout_s}\n"
            f"  debug_publish: {self.debug_publish}\n"
            f"  debug_republish_input_path: {self.debug_republish_input_path}\n"
            "Services:\n"
            "  /lane_follow/start (Trigger)\n"
            "  /lane_follow/stop  (Trigger)"
        )

    # -------------------------
    # Services
    # -------------------------
    def _on_start(self, req, resp):
        self.enabled = True
        resp.success = True
        resp.message = "Lane following enabled."
        self.get_logger().info(resp.message)
        return resp

    def _on_stop(self, req, resp):
        self.enabled = False
        self._cancel_nav2("Stopped by service.")
        resp.success = True
        resp.message = "Lane following disabled; navigation canceled."
        self.get_logger().info(resp.message)
        return resp

    # -------------------------
    # Subscriptions
    # -------------------------
    def _on_path(self, msg: Path):
        self.latest_path = msg
        self.last_path_time = self.get_clock().now()

        if self.debug_input_path_pub is not None:
            self.debug_input_path_pub.publish(msg)

    # -------------------------
    # Core logic
    # -------------------------
    def _lane_ok(self) -> bool:
        if self.latest_path is None or self.last_path_time is None:
            return False
        if len(self.latest_path.poses) < self.min_poses:
            return False
        age = (self.get_clock().now() - self.last_path_time).nanoseconds * 1e-9
        return age <= self.lane_timeout_s

    def _pick_lookahead(self, path: Path) -> Optional[Tuple[float, float, float]]:
        """Returns (x,y,yaw) in path frame (expected base_link)."""
        poses = path.poses
        if not poses:
            return None

        # Prefer forward points
        best_i = None
        best_d2 = float('inf')
        for i, ps in enumerate(poses):
            p = ps.pose.position
            if p.x < self.min_forward_x:
                continue
            d2 = dist2_xy(p)
            if d2 < best_d2:
                best_d2 = d2
                best_i = i

        if best_i is None:
            # fallback: closest overall
            for i, ps in enumerate(poses):
                d2 = dist2_xy(ps.pose.position)
                if d2 < best_d2:
                    best_d2 = d2
                    best_i = i

        if best_i is None:
            return None

        # March along arc-length
        target_s = self.lookahead_m
        s = 0.0
        i = best_i
        while i + 1 < len(poses) and s < target_s:
            p0 = poses[i].pose.position
            p1 = poses[i + 1].pose.position
            s += math.hypot(p1.x - p0.x, p1.y - p0.y)
            i += 1

        # Tangent yaw
        if i >= 1:
            yaw = yaw_from_segment(poses[i - 1].pose.position, poses[i].pose.position)
        elif len(poses) >= 2:
            yaw = yaw_from_segment(poses[0].pose.position, poses[1].pose.position)
        else:
            yaw = 0.0

        p = poses[i].pose.position
        return float(p.x), float(p.y), float(yaw)

    def _make_goal_pose(self, x: float, y: float, yaw: float, frame_id: str) -> PoseStamped:
        ps = PoseStamped()
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.header.frame_id = frame_id
        ps.pose.position.x = x
        ps.pose.position.y = y
        ps.pose.position.z = 0.0

        qx, qy, qz, qw = quat_from_yaw(yaw)
        ps.pose.orientation.x = qx
        ps.pose.orientation.y = qy
        ps.pose.orientation.z = qz
        ps.pose.orientation.w = qw
        return ps

    def _transform_pose(self, pose_in: PoseStamped, target_frame: str) -> Optional[PoseStamped]:
        try:
            tf = self.tf_buffer.lookup_transform(
                target_frame,
                pose_in.header.frame_id,
                rclpy.time.Time()
            )
        except TransformException as ex:
            self.get_logger().warn_throttle(2000, f"TF lookup failed {pose_in.header.frame_id}->{target_frame}: {ex}")
            return None

        # Apply transform (position + quaternion multiply)
        tx = tf.transform.translation.x
        ty = tf.transform.translation.y
        tz = tf.transform.translation.z
        qx = tf.transform.rotation.x
        qy = tf.transform.rotation.y
        qz = tf.transform.rotation.z
        qw = tf.transform.rotation.w

        # rotation matrix from tf quaternion
        r00 = 1 - 2 * (qy*qy + qz*qz)
        r01 = 2 * (qx*qy - qz*qw)
        r02 = 2 * (qx*qz + qy*qw)
        r10 = 2 * (qx*qy + qz*qw)
        r11 = 1 - 2 * (qx*qx + qz*qz)
        r12 = 2 * (qy*qz - qx*qw)
        r20 = 2 * (qx*qz - qy*qw)
        r21 = 2 * (qy*qz + qx*qw)
        r22 = 1 - 2 * (qx*qx + qy*qy)

        px = pose_in.pose.position.x
        py = pose_in.pose.position.y
        pz = pose_in.pose.position.z

        out = PoseStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = target_frame
        out.pose.position.x = r00*px + r01*py + r02*pz + tx
        out.pose.position.y = r10*px + r11*py + r12*pz + ty
        out.pose.position.z = r20*px + r21*py + r22*pz + tz

        # q_out = q_tf * q_in
        ax, ay, az, aw = (qx, qy, qz, qw)
        bx, by, bz, bw = (
            pose_in.pose.orientation.x,
            pose_in.pose.orientation.y,
            pose_in.pose.orientation.z,
            pose_in.pose.orientation.w
        )
        out.pose.orientation.x = aw*bx + ax*bw + ay*bz - az*by
        out.pose.orientation.y = aw*by - ax*bz + ay*bw + az*bx
        out.pose.orientation.z = aw*bz + ax*by - ay*bx + az*bw
        out.pose.orientation.w = aw*bw - ax*bx - ay*by - az*bz
        return out

    def _goal_changed_enough(self, x: float, y: float, yaw: float) -> bool:
        if self.last_sent_goal is None:
            return True
        lx, ly, lyaw = self.last_sent_goal
        d = math.hypot(x - lx, y - ly)
        dyaw = abs((yaw - lyaw + math.pi) % (2*math.pi) - math.pi)
        return (d >= self.send_goal_dist_m) or (dyaw >= self.send_goal_yaw_rad)

    def _send_nav2_goal(self, goal_pose: PoseStamped):
        if not self.nav_client.wait_for_server(timeout_sec=0.2):
            self.get_logger().warn_throttle(2000, f"Nav2 action server '{self.action_name}' not available.")
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = goal_pose

        # If a goal is active, cancel it first (keeps Nav2 from stacking behaviors)
        if self.goal_handle is not None:
            self._cancel_nav2("Updating moving goal.")

        self.get_logger().debug("Sending Nav2 goal.")
        send_future = self.nav_client.send_goal_async(goal_msg)
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        gh = future.result()
        if not gh.accepted:
            self.get_logger().warn("Nav2 rejected goal.")
            self.goal_handle = None
            return
        self.goal_handle = gh
        self.get_logger().info_throttle(2000, "Nav2 goal accepted (lane follow).")

    def _cancel_nav2(self, reason: str):
        if self.goal_handle is None:
            if self.publish_zero_on_loss:
                self._publish_zero_cmd_vel()
            return
        self.get_logger().warn(f"Cancelling Nav2 goal: {reason}")
        cancel_future = self.goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(lambda f: None)
        self.goal_handle = None
        self.last_sent_goal = None

        if self.publish_zero_on_loss:
            self._publish_zero_cmd_vel()

    def _publish_zero_cmd_vel(self):
        if self.cmd_vel_pub is None:
            return
        t = Twist()
        t.linear.x = 0.0
        t.angular.z = 0.0
        self.cmd_vel_pub.publish(t)

    def _publish_goal_path(self, goal: PoseStamped):
        """Publish a 2-point Path in goal.header.frame_id: origin -> goal."""
        if self.debug_goal_path_pub is None:
            return
        p = Path()
        p.header.stamp = self.get_clock().now().to_msg()
        p.header.frame_id = goal.header.frame_id

        origin = PoseStamped()
        origin.header = p.header
        origin.pose.orientation.w = 1.0

        p.poses = [origin, goal]
        self.debug_goal_path_pub.publish(p)

    def _on_timer(self):
        # Need a path before doing anything
        if self.latest_path is None or self.last_path_time is None:
            return

        path = self.latest_path

        # Compute lookahead once
        pick = self._pick_lookahead(path)
        if pick is None:
            if self.enabled:
                self._cancel_nav2("Lane path empty.")
            return

        x_bl, y_bl, yaw_bl = pick
        lookahead_bl = self._make_goal_pose(x_bl, y_bl, yaw_bl, frame_id=path.header.frame_id)

        # Debug publish lookahead in path frame (often base_link)
        if self.debug_lookahead_pub is not None:
            self.debug_lookahead_pub.publish(lookahead_bl)

        # Transform lookahead to goal_frame (odom) for debug + nav
        goal_out = lookahead_bl
        if lookahead_bl.header.frame_id != self.goal_frame:
            goal_out = self._transform_pose(lookahead_bl, self.goal_frame)
            if goal_out is None:
                # TF missing; can’t visualize goal_out nor command Nav2
                return

        # Debug publish transformed goal + a line path
        if self.debug_goal_pub is not None:
            self.debug_goal_pub.publish(goal_out)
        self._publish_goal_path(goal_out)

        # Navigation is gated by start/stop
        if not self.enabled:
            return

        # Lane health check (stale/short) is only enforced for nav
        if not self._lane_ok():
            self._cancel_nav2("Lane path missing/stale.")
            return

        gx = goal_out.pose.position.x
        gy = goal_out.pose.position.y

        # NOTE: yaw thresholding uses base_link-frame yaw; good enough for lane-following
        yaw = yaw_bl

        if self._goal_changed_enough(gx, gy, yaw):
            self.last_sent_goal = (gx, gy, yaw)
            self._send_nav2_goal(goal_out)


def main():
    rclpy.init()
    node = LaneFollowNav2Node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
