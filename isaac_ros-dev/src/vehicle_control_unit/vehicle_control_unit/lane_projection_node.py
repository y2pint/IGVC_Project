#!/usr/bin/env python3
import numpy as np

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PolygonStamped, PoseStamped
from nav_msgs.msg import Path
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import Float32

import tf2_ros


def quat_to_rot(qx, qy, qz, qw) -> np.ndarray:
    """Quaternion (x,y,z,w) -> 3x3 rotation matrix."""
    # Normalize
    n = np.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
    if n < 1e-12:
        return np.eye(3)
    qx, qy, qz, qw = qx/n, qy/n, qz/n, qw/n

    xx, yy, zz = qx*qx, qy*qy, qz*qz
    xy, xz, yz = qx*qy, qx*qz, qy*qz
    wx, wy, wz = qw*qx, qw*qy, qw*qz

    R = np.array([
        [1.0 - 2.0*(yy + zz), 2.0*(xy - wz),       2.0*(xz + wy)],
        [2.0*(xy + wz),       1.0 - 2.0*(xx + zz), 2.0*(yz - wx)],
        [2.0*(xz - wy),       2.0*(yz + wx),       1.0 - 2.0*(xx + yy)],
    ], dtype=float)
    return R


def rot_x(a: float) -> np.ndarray:
    ca, sa = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0],
                     [0, ca, -sa],
                     [0, sa, ca]], dtype=float)


class LaneProjectionNode(Node):
    """
    Subscribes:
      - /lane/centerline_pixels (PolygonStamped): Point32(x=u, y=v) in pixel coordinates
      - camera_info_topic (CameraInfo): for K intrinsics

    Publishes:
      - /lane/centerline_path (nav_msgs/Path) in base_link
      - /lane/confidence (Float32)
      - /lane/width (Float32)
    """

    def __init__(self):
        super().__init__('lane_projection_node')

        # -------------------------
        # Parameters
        # -------------------------
        self.declare_parameter('pixels_topic', '/lane/centerline_pixels')
        self.declare_parameter('camera_info_topic', '/zed/zed_node/rgb/camera_info')

        # Output
        self.declare_parameter('output_frame', 'base_link')
        self.declare_parameter('path_topic', '/lane/centerline_path')

        # Camera mount (fallback if TF not available)
        self.declare_parameter('camera_frame', 'camera_link')   # non-optical frame name
        self.declare_parameter('cam_x_m', 0.0)
        self.declare_parameter('cam_y_m', 0.0)
        self.declare_parameter('cam_z_m', 1.5)

        # Pitch (about camera_link Y axis *in base_link convention* is messy),
        # so we apply a simple pitch in camera_link frame around its Y axis if desired.
        # Start with 0.0.
        self.declare_parameter('camera_pitch_rad', 0.0)

        # Guard: ignore points above this normalized image row
        # (e.g., 0.5 means only use lower half). Keeps away from horizon.
        self.declare_parameter('min_v_frac', 0.45)

        # Lane width published (meters) (fixed for now; update later if you estimate it)
        self.declare_parameter('lane_width_m', 0.8)

        # TF lookup timeout
        self.declare_parameter('tf_timeout_sec', 0.05)

        # -------------------------
        # State
        # -------------------------
        self.K = None
        self.fx = self.fy = self.cx = self.cy = None
        self.img_w = None
        self.img_h = None

        # TF
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # Pub/Sub
        pixels_topic = self.get_parameter('pixels_topic').value
        caminfo_topic = self.get_parameter('camera_info_topic').value

        self.sub_px = self.create_subscription(PolygonStamped, pixels_topic, self.on_pixels, 10)
        self.sub_ci = self.create_subscription(CameraInfo, caminfo_topic, self.on_camera_info, 10)

        self.pub_path = self.create_publisher(Path, self.get_parameter('path_topic').value, 10)
        self.pub_conf = self.create_publisher(Float32, '/lane/confidence', 10)
        self.pub_width = self.create_publisher(Float32, '/lane/width', 10)

        self.get_logger().info(f'LaneProjectionNode subscribed to {pixels_topic} + {caminfo_topic}')
        self.get_logger().info(f'Publishing {self.get_parameter("path_topic").value}, /lane/confidence, /lane/width')

    def on_camera_info(self, msg: CameraInfo):
        # K is row-major 3x3 in msg.k
        K = np.array(msg.k, dtype=float).reshape(3, 3)
        self.K = K
        self.fx = K[0, 0]
        self.fy = K[1, 1]
        self.cx = K[0, 2]
        self.cy = K[1, 2]
        self.img_w = msg.width
        self.img_h = msg.height

    def on_pixels(self, msg: PolygonStamped):
        if self.K is None or self.img_w is None or self.img_h is None:
            return  # wait for CameraInfo

        output_frame = self.get_parameter('output_frame').value
        camera_frame = self.get_parameter('camera_frame').value
        pitch = float(self.get_parameter('camera_pitch_rad').value)
        min_v_frac = float(self.get_parameter('min_v_frac').value)

        # Prepare TF from camera_link -> base_link (or chosen output frame)
        R_bc = None
        t_bc = None

        tf_timeout = float(self.get_parameter('tf_timeout_sec').value)
        try:
            # transform from output_frame <- camera_frame
            tf = self.tf_buffer.lookup_transform(
                output_frame,
                camera_frame,
                rclpy.time.Time(),
                rclpy.duration.Duration(seconds=tf_timeout),
            )
            q = tf.transform.rotation
            R_bc = quat_to_rot(q.x, q.y, q.z, q.w)
            t_bc = np.array([
                tf.transform.translation.x,
                tf.transform.translation.y,
                tf.transform.translation.z
            ], dtype=float)
        except Exception:
            # Fallback to parameters (assume camera_frame axes aligned with output_frame)
            R_bc = np.eye(3)
            t_bc = np.array([
                float(self.get_parameter('cam_x_m').value),
                float(self.get_parameter('cam_y_m').value),
                float(self.get_parameter('cam_z_m').value),
            ], dtype=float)

        # Optical frame ray -> camera_link ray conversion (REP-103)
        # optical: x right, y down, z forward
        # camera_link: x forward, y left, z up
        # v_link = [ z_opt, -x_opt, -y_opt ]
        def opt_to_link(v_opt: np.ndarray) -> np.ndarray:
            return np.array([v_opt[2], -v_opt[0], -v_opt[1]], dtype=float)

        # Apply optional pitch in camera_link frame around its X-axis? or Y-axis?
        # For a typical forward-facing camera, "pitch down" corresponds to rotation about camera_link Y (left) axis.
        # But depending on your camera_link definition, this might vary.
        # We apply pitch about camera_link Y (left) axis:
        cp, sp = np.cos(pitch), np.sin(pitch)
        R_pitch = np.array([[cp, 0, sp],
                            [0,  1, 0 ],
                            [-sp,0, cp]], dtype=float)

        pts_out = []
        total = len(msg.polygon.points)
        valid = 0

        v_min = int(min_v_frac * self.img_h)

        for p in msg.polygon.points:
            u = float(p.x)
            v = float(p.y)

            # Ignore pixels near/above horizon (keep only lower image region)
            if v < v_min:
                continue

            # Ray direction in *optical frame* (x right, y down, z forward)
            x = (u - self.cx) / self.fx
            y = (v - self.cy) / self.fy
            ray_cam = np.array([x, y, 1.0], dtype=float)
            ray_cam /= (np.linalg.norm(ray_cam) + 1e-12)

            # Transform ray into output frame using TF rotation (output <- camera)
            ray_out = R_bc @ ray_cam
            ray_out /= (np.linalg.norm(ray_out) + 1e-12)

            # Ray origin in output frame (camera origin expressed in output frame)
            o = t_bc

            # Intersect ray with ground plane z=0 in output frame
            dz = ray_out[2]
            if dz >= -1e-6:
                # Ray not pointing downward enough to hit ground
                continue

            t = -o[2] / dz
            if t <= 0.0:
                continue

            X = o + t * ray_out
            X[2] = 0.0  # enforce ground plane

            pts_out.append(X)
            valid += 1

        # Publish confidence + width regardless
        conf_msg = Float32()
        conf_msg.data = float(valid) / float(max(1, total))
        self.pub_conf.publish(conf_msg)

        width_msg = Float32()
        width_msg.data = float(self.get_parameter('lane_width_m').value)
        self.pub_width.publish(width_msg)

        # Publish path
        path = Path()
        path.header = msg.header
        path.header.frame_id = output_frame

        if valid < 3:
            # publish empty path
            self.pub_path.publish(path)
            return

        # Simple downsample/smoothing: keep order as received (already monotonic v)
        for i, X in enumerate(pts_out):
            ps = PoseStamped()
            ps.header = path.header
            ps.pose.position.x = float(X[0])
            ps.pose.position.y = float(X[1])
            ps.pose.position.z = 0.0
            ps.pose.orientation.w = 1.0  # no orientation for path points
            path.poses.append(ps)

        self.pub_path.publish(path)


def main():
    rclpy.init()
    node = LaneProjectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
