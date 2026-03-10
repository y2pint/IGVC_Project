#!/usr/bin/env python3

import math
from typing import Optional, Tuple

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

def yaw_from_quaternion_msg(q):
    """
    Extract yaw from geometry_msgs/Quaternion
    """
    x = q.x
    y = q.y
    z = q.z
    w = q.w

    siny_cosp = 2.0 * (w*z + x*y)
    cosy_cosp = 1.0 - 2.0 * (y*y + z*z)

    return math.atan2(siny_cosp, cosy_cosp)


def quaternion_msg_from_yaw(yaw):
    """
    Convert yaw -> quaternion (x,y,z,w)
    """
    half = yaw * 0.5
    qz = math.sin(half)
    qw = math.cos(half)

    return 0.0, 0.0, qz, qw


def wrap_angle(angle: float) -> float:
    """Wrap angle to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def pose_to_T2(x: float, y: float, yaw: float) -> np.ndarray:
    """Build 2D homogeneous transform."""
    c = math.cos(yaw)
    s = math.sin(yaw)
    return np.array([
        [c, -s, x],
        [s,  c, y],
        [0.0, 0.0, 1.0]
    ], dtype=float)


def T2_to_pose(T: np.ndarray) -> Tuple[float, float, float]:
    """Extract x, y, yaw from 2D homogeneous transform."""
    x = T[0, 2]
    y = T[1, 2]
    yaw = math.atan2(T[1, 0], T[0, 0])
    return x, y, yaw


class GlobalEkfNode(Node):
    def __init__(self):
        super().__init__('global_ekf_node')

        # ---------------- Parameters ----------------
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')

        self.declare_parameter('local_odom_topic', '/odometry/local')
        self.declare_parameter('gps_odom_topic', '/gps/odom_projected')
        self.declare_parameter('global_odom_topic', '/odometry/global')

        # Process noise added at every prediction
        self.declare_parameter('q_x', 0.02)
        self.declare_parameter('q_y', 0.02)
        self.declare_parameter('q_yaw', 0.01)

        # GPS measurement noise
        self.declare_parameter('r_gps_x', 1024.0)
        self.declare_parameter('r_gps_y', 1024.0)

        # Mahalanobis gating
        self.declare_parameter('gps_gate_threshold', 9.21)  # ~chi2 2 dof at 99%
        self.declare_parameter('use_gps_gate', True)

        # Diagnostics throttling
        self.declare_parameter('diag_period_sec', 1.0)

        self.map_frame = self.get_parameter('map_frame').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value

        self.local_odom_topic = self.get_parameter('local_odom_topic').value
        self.gps_odom_topic = self.get_parameter('gps_odom_topic').value
        self.global_odom_topic = self.get_parameter('global_odom_topic').value

        qx = float(self.get_parameter('q_x').value)
        qy = float(self.get_parameter('q_y').value)
        qyaw = float(self.get_parameter('q_yaw').value)

        rx = float(self.get_parameter('r_gps_x').value)
        ry = float(self.get_parameter('r_gps_y').value)

        self.gps_gate_threshold = float(self.get_parameter('gps_gate_threshold').value)
        self.use_gps_gate = bool(self.get_parameter('use_gps_gate').value)
        self.diag_period_sec = float(self.get_parameter('diag_period_sec').value)

        self.Q = np.diag([qx, qy, qyaw])
        self.R = np.diag([rx, ry])

        self.H = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        ], dtype=float)

        # ---------------- EKF state ----------------
        # x = [x, y, yaw] in map frame
        self.x = np.zeros((3, 1), dtype=float)
        self.P = np.diag([10.0, 10.0, 1.0])  # large initial uncertainty
        self.initialized = False

        # Store latest local odom pose
        self.prev_local_odom_pose: Optional[Tuple[float, float, float]] = None
        self.latest_local_odom_pose: Optional[Tuple[float, float, float]] = None
        self.latest_local_odom_msg: Optional[Odometry] = None

        # Diagnostics bookkeeping
        self.last_diag_time = self.get_clock().now()
        self.last_gps_accept = None
        self.last_innovation = np.zeros((2, 1), dtype=float)
        self.last_mahalanobis = float('nan')

        # ---------------- ROS interfaces ----------------
        # Best-effort is often appropriate for sensor-style odometry/GPS streams
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        self.sub_local = self.create_subscription(
            Odometry,
            self.local_odom_topic,
            self.local_odom_callback,
            qos
        )

        self.sub_gps = self.create_subscription(
            Odometry,
            self.gps_odom_topic,
            self.gps_odom_callback,
            qos
        )

        self.pub_global = self.create_publisher(
            Odometry,
            self.global_odom_topic,
            10
        )

        self.tf_broadcaster = TransformBroadcaster(self)

        self.get_logger().info('global_ekf_node started')
        self.get_logger().info(f'  local odom topic : {self.local_odom_topic}')
        self.get_logger().info(f'  gps topic        : {self.gps_odom_topic}')
        self.get_logger().info(f'  global odom topic: {self.global_odom_topic}')

    # ------------------------------------------------------------------
    # Local odometry callback: prediction from relative odom increment
    # ------------------------------------------------------------------
    def local_odom_callback(self, msg: Odometry):
        x_o = msg.pose.pose.position.x
        y_o = msg.pose.pose.position.y
        yaw_o = yaw_from_quaternion_msg(msg.pose.pose.orientation)

        current_pose = (x_o, y_o, yaw_o)
        self.latest_local_odom_pose = current_pose
        self.latest_local_odom_msg = msg

        if self.prev_local_odom_pose is None:
            self.prev_local_odom_pose = current_pose
            return

        # If not initialized yet, just keep tracking local odom history
        if not self.initialized:
            self.prev_local_odom_pose = current_pose
            return

        self.predict_from_local_odom(self.prev_local_odom_pose, current_pose)
        self.prev_local_odom_pose = current_pose

        self.publish_global_odom(msg.header.stamp)
        self.publish_map_to_odom_tf(msg.header.stamp)
        self.maybe_print_diagnostics()

    def predict_from_local_odom(
        self,
        prev_pose: Tuple[float, float, float],
        curr_pose: Tuple[float, float, float]
    ):
        x0, y0, yaw0 = prev_pose
        x1, y1, yaw1 = curr_pose

        # Relative motion between local odom poses:
        # T_prev_curr = inv(T_odom_base_prev) * T_odom_base_curr
        T0 = pose_to_T2(x0, y0, yaw0)
        T1 = pose_to_T2(x1, y1, yaw1)
        T_rel = np.linalg.inv(T0) @ T1

        dx_body, dy_body, dyaw = T2_to_pose(T_rel)
        dyaw = wrap_angle(dyaw)

        # Predict in map frame using current EKF yaw
        yaw = float(self.x[2, 0])
        c = math.cos(yaw)
        s = math.sin(yaw)

        dx_map = c * dx_body - s * dy_body
        dy_map = s * dx_body + c * dy_body

        self.x[0, 0] += dx_map
        self.x[1, 0] += dy_map
        self.x[2, 0] = wrap_angle(self.x[2, 0] + dyaw)

        self.P = self.P + self.Q

    # ------------------------------------------------------------------
    # GPS callback: initialization or EKF measurement update
    # ------------------------------------------------------------------
    def gps_odom_callback(self, msg: Odometry):
        gps_x = msg.pose.pose.position.x
        gps_y = msg.pose.pose.position.y

        # Need local odom pose to define map->odom after initialization
        if self.latest_local_odom_pose is None:
            return

        if not self.initialized:
            _, _, yaw_local = self.latest_local_odom_pose
            self.x[0, 0] = gps_x
            self.x[1, 0] = gps_y
            self.x[2, 0] = yaw_local  # initialize heading from local odom
            self.P = np.diag([2.0, 2.0, 0.5])
            self.initialized = True

            self.get_logger().info(
                f'Initialized global EKF at x={gps_x:.3f}, y={gps_y:.3f}, yaw={yaw_local:.3f}'
            )

            self.publish_global_odom(msg.header.stamp)
            self.publish_map_to_odom_tf(msg.header.stamp)
            return

        z = np.array([[gps_x], [gps_y]], dtype=float)
        z_hat = self.H @ self.x
        innovation = z - z_hat

        S = self.H @ self.P @ self.H.T + self.R
        S_inv = np.linalg.inv(S)
        maha = float((innovation.T @ S_inv @ innovation)[0, 0])

        gps_accepted = True
        if self.use_gps_gate and maha > self.gps_gate_threshold:
            gps_accepted = False

        self.last_innovation = innovation
        self.last_mahalanobis = maha
        self.last_gps_accept = gps_accepted

        if gps_accepted:
            K = self.P @ self.H.T @ S_inv
            self.x = self.x + K @ innovation
            self.x[2, 0] = wrap_angle(self.x[2, 0])

            I = np.eye(3)
            self.P = (I - K @ self.H) @ self.P
        else:
            self.get_logger().warn(
                f'GPS rejected: maha={maha:.3f} > gate={self.gps_gate_threshold:.3f}'
            )

        self.publish_global_odom(msg.header.stamp)
        self.publish_map_to_odom_tf(msg.header.stamp)
        self.maybe_print_diagnostics()

    # ------------------------------------------------------------------
    # Publish /odometry/global as map -> base_link pose
    # ------------------------------------------------------------------
    def publish_global_odom(self, stamp):
        if not self.initialized:
            return

        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = self.map_frame
        msg.child_frame_id = self.base_frame

        msg.pose.pose.position.x = float(self.x[0, 0])
        msg.pose.pose.position.y = float(self.x[1, 0])
        msg.pose.pose.position.z = 0.0

        qx, qy, qz, qw = quaternion_msg_from_yaw(float(self.x[2, 0]))
        msg.pose.pose.orientation.x = qx
        msg.pose.pose.orientation.y = qy
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw

        # Fill 6x6 pose covariance
        pose_cov = [0.0] * 36
        pose_cov[0] = float(self.P[0, 0])      # x
        pose_cov[1] = float(self.P[0, 1])
        pose_cov[5] = float(self.P[0, 2])

        pose_cov[6] = float(self.P[1, 0])
        pose_cov[7] = float(self.P[1, 1])      # y
        pose_cov[11] = float(self.P[1, 2])

        pose_cov[30] = float(self.P[2, 0])
        pose_cov[31] = float(self.P[2, 1])
        pose_cov[35] = float(self.P[2, 2])     # yaw

        msg.pose.covariance = pose_cov

        # Optional: pass through local twist if available
        if self.latest_local_odom_msg is not None:
            msg.twist = self.latest_local_odom_msg.twist

        self.pub_global.publish(msg)

    # ------------------------------------------------------------------
    # Broadcast map -> odom TF
    # map->odom = map->base * inv(odom->base)
    # ------------------------------------------------------------------
    def publish_map_to_odom_tf(self, stamp):
        if not self.initialized or self.latest_local_odom_pose is None:
            return

        x_map, y_map, yaw_map = float(self.x[0, 0]), float(self.x[1, 0]), float(self.x[2, 0])
        x_odom, y_odom, yaw_odom = self.latest_local_odom_pose

        T_map_base = pose_to_T2(x_map, y_map, yaw_map)
        T_odom_base = pose_to_T2(x_odom, y_odom, yaw_odom)
        T_map_odom = T_map_base @ np.linalg.inv(T_odom_base)

        tx, ty, tyaw = T2_to_pose(T_map_odom)
        qx, qy, qz, qw = quaternion_msg_from_yaw(tyaw)

        tf_msg = TransformStamped()
        tf_msg.header.stamp = stamp
        tf_msg.header.frame_id = self.map_frame
        tf_msg.child_frame_id = self.odom_frame

        tf_msg.transform.translation.x = float(tx)
        tf_msg.transform.translation.y = float(ty)
        tf_msg.transform.translation.z = 0.0

        tf_msg.transform.rotation.x = qx
        tf_msg.transform.rotation.y = qy
        tf_msg.transform.rotation.z = qz
        tf_msg.transform.rotation.w = qw

        self.tf_broadcaster.sendTransform(tf_msg)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def maybe_print_diagnostics(self):
        now = self.get_clock().now()
        dt = (now - self.last_diag_time).nanoseconds * 1e-9
        if dt < self.diag_period_sec:
            return

        cov_trace = float(np.trace(self.P))
        innov_x = float(self.last_innovation[0, 0])
        innov_y = float(self.last_innovation[1, 0])

        gps_status = 'N/A'
        if self.last_gps_accept is True:
            gps_status = 'accepted'
        elif self.last_gps_accept is False:
            gps_status = 'rejected'

        self.get_logger().info(
            f'EKF diag | innov=({innov_x:.3f}, {innov_y:.3f}) '
            f'| maha={self.last_mahalanobis:.3f} '
            f'| gps={gps_status} '
            f'| trace(P)={cov_trace:.3f}'
        )

        self.last_diag_time = now


def main(args=None):
    rclpy.init(args=args)
    node = GlobalEkfNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()