#!/usr/bin/env python3
"""
lane_projection_node.py

Lane projection node that:
  - Subscribes to /lane/centerline_pixels (PolygonStamped; Point32(x=u,y=v) pixels)
  - Subscribes to camera_info_topic (CameraInfo) for intrinsics
  - Projects pixel centerline points to ground (z=0) in output_frame (default: base_link)
  - Publishes:
      * /lane/centerline_path   (nav_msgs/Path) in output_frame
      * /lane/confidence       (std_msgs/Float32)
      * /lane/width            (std_msgs/Float32)
      * /lane/mask_projected   (sensor_msgs/Image mono8) polyline mask in image coords
      * /lane/occupancy_grid   (nav_msgs/OccupancyGrid) rolling grid in lane_grid_frame (default: odom)

Key design choices for robustness / Nav2 compatibility:
  - OccupancyGrid is built in lane_grid_frame with a rolling origin tied to robot pose
  - Uses Time(0) TF lookups to avoid stamp synchronization issues during bringup
  - Always anchors the corridor at the robot (base_link origin) by prepending (0,0,0)
    and optionally bridging to the first visible lane point; this fixes "robot not in corridor"
    when the camera can't see close range.
  - Corridor rasterization is segment-based (dense sampling) for continuity, not sparse point stamping.

Semantics:
  - lane_grid_mode == 'corridor': outside lane corridor = 100 (occupied), inside = 0 (free)
  - lane_grid_mode == 'centerline_only': unknown (-1) everywhere, and 0 along the centerline
"""

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration

from geometry_msgs.msg import PolygonStamped, PoseStamped
from nav_msgs.msg import Path, OccupancyGrid
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Float32

import tf2_ros
from builtin_interfaces.msg import Time as TimeMsg


# -------------------------
# Math utilities
# -------------------------
def quat_to_rot(qx, qy, qz, qw) -> np.ndarray:
    """Quaternion (x,y,z,w) -> 3x3 rotation matrix."""
    n = np.sqrt(qx*qx + qy*qy + qz*qz + qw*qw)
    if n < 1e-12:
        return np.eye(3)
    qx, qy, qz, qw = qx/n, qy/n, qz/n, qw/n

    xx, yy, zz = qx*qx, qy*qy, qz*qz
    xy, xz, yz = qx*qy, qx*qz, qy*qz
    wx, wy, wz = qw*qx, qw*qy, qw*qz

    return np.array([
        [1.0 - 2.0*(yy + zz), 2.0*(xy - wz),       2.0*(xz + wy)],
        [2.0*(xy + wz),       1.0 - 2.0*(xx + zz), 2.0*(yz - wx)],
        [2.0*(xz - wy),       2.0*(yz + wx),       1.0 - 2.0*(xx + yy)],
    ], dtype=float)


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else (hi if v > hi else v)


def bresenham_line(x0: int, y0: int, x1: int, y1: int):
    """Yield integer pixels along a line (inclusive)."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


# -------------------------
# Node
# -------------------------
class LaneProjectionNode(Node):
    def __init__(self):
        super().__init__('lane_projection_node')

        # -------------------------
        # Parameters
        # -------------------------
        self.declare_parameter('pixels_topic', '/lane/centerline_pixels')
        self.declare_parameter('camera_info_topic', '/zed/zed_node/rgb/camera_info')

        # Frames
        self.declare_parameter('output_frame', 'base_link')                  # where projected ground points are expressed
        self.declare_parameter('camera_frame', 'zed_left_camera_optical_frame')

        # Output topics
        self.declare_parameter('path_topic', '/lane/centerline_path')
        self.declare_parameter('lane_mask_topic', '/lane/mask_projected')
        self.declare_parameter('lane_grid_topic', '/lane/occupancy_grid')

        # Projection / filtering
        self.declare_parameter('min_v_frac', 0.45)                           # ignore pixels above this image row fraction
        self.declare_parameter('lane_width_m', 1.2)

        # Fallback camera translation if TF missing (camera frame assumed aligned)
        self.declare_parameter('cam_x_m', 0.0)
        self.declare_parameter('cam_y_m', 0.0)
        self.declare_parameter('cam_z_m', 1.5)

        # TF lookup
        self.declare_parameter('tf_timeout_sec', 0.20)                       # 0.05 is tight during bringup

        # Lane mask (image)
        self.declare_parameter('lane_mask_thickness_px', 6)

        # Occupancy grid (rolling window)
        self.declare_parameter('publish_lane_grid', True)
        self.declare_parameter('lane_grid_frame', 'odom')                    # should match local_costmap.global_frame
        self.declare_parameter('lane_grid_resolution', 0.05)
        self.declare_parameter('lane_grid_width_m', 20.0)
        self.declare_parameter('lane_grid_height_m', 20.0)
        self.declare_parameter('lane_grid_origin_x_m', -10.0)                # robot-relative offset inside the grid
        self.declare_parameter('lane_grid_origin_y_m', -10.0)
        self.declare_parameter('lane_grid_mode', 'corridor')                 # 'corridor' or 'centerline_only'

        # Corridor anchoring / bridging (fixes "robot not in corridor")
        self.declare_parameter('anchor_robot_in_corridor', True)
        self.declare_parameter('bridge_to_first_point', True)
        self.declare_parameter('bridge_step_m', 0.25)                        # sample spacing along robot->first lane point
        self.declare_parameter('robot_free_radius_m', 0.6)                   # always carve free bubble around robot

        # Rasterization density
        self.declare_parameter('segment_sample_step_m', 0.10)                # sampling along lane segments in meters

        # -------------------------
        # State (intrinsics)
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

        self.pub_mask = self.create_publisher(Image, self.get_parameter('lane_mask_topic').value, 10)
        self.pub_grid = self.create_publisher(OccupancyGrid, self.get_parameter('lane_grid_topic').value, 10)

        self.get_logger().info(f'LaneProjectionNode subscribed to {pixels_topic} + {caminfo_topic}')
        self.get_logger().info(
            f'Publishing {self.get_parameter("path_topic").value}, /lane/confidence, /lane/width, '
            f'{self.get_parameter("lane_mask_topic").value}, {self.get_parameter("lane_grid_topic").value}'
        )

    # -------------------------
    # CameraInfo
    # -------------------------
    def on_camera_info(self, msg: CameraInfo):
        K = np.array(msg.k, dtype=float).reshape(3, 3)
        self.K = K
        self.fx = K[0, 0]
        self.fy = K[1, 1]
        self.cx = K[0, 2]
        self.cy = K[1, 2]
        self.img_w = int(msg.width)
        self.img_h = int(msg.height)

    # -------------------------
    # Lane mask (image space)
    # -------------------------
    def publish_lane_mask(self, header, points_uv):
        if self.img_w is None or self.img_h is None:
            return

        mask = np.zeros((self.img_h, self.img_w), dtype=np.uint8)

        if len(points_uv) >= 2:
            thick = max(1, int(self.get_parameter('lane_mask_thickness_px').value))
            r = thick // 2

            for (u0, v0), (u1, v1) in zip(points_uv[:-1], points_uv[1:]):
                x0 = int(round(u0)); y0 = int(round(v0))
                x1 = int(round(u1)); y1 = int(round(v1))
                for x, y in bresenham_line(x0, y0, x1, y1):
                    if x < 0 or x >= self.img_w or y < 0 or y >= self.img_h:
                        continue
                    x_lo = clamp(x - r, 0, self.img_w - 1)
                    x_hi = clamp(x + r, 0, self.img_w - 1)
                    y_lo = clamp(y - r, 0, self.img_h - 1)
                    y_hi = clamp(y + r, 0, self.img_h - 1)
                    mask[y_lo:y_hi+1, x_lo:x_hi+1] = 255

        imsg = Image()
        imsg.header = header
        imsg.height = int(self.img_h)
        imsg.width = int(self.img_w)
        imsg.encoding = 'mono8'
        imsg.is_bigendian = False
        imsg.step = int(self.img_w)
        imsg.data = mask.tobytes()
        self.pub_mask.publish(imsg)

    # -------------------------
    # Rolling OccupancyGrid
    # -------------------------
    def publish_lane_grid(self, stamp: TimeMsg, lane_pts_out: np.ndarray, output_frame: str):
        """
        lane_pts_out: Nx3 in output_frame (typically base_link), z=0
        """
        if not bool(self.get_parameter('publish_lane_grid').value):
            return
        if lane_pts_out is None or len(lane_pts_out) < 2:
            return

        grid_frame = str(self.get_parameter('lane_grid_frame').value)
        res = float(self.get_parameter('lane_grid_resolution').value)
        Wm = float(self.get_parameter('lane_grid_width_m').value)
        Hm = float(self.get_parameter('lane_grid_height_m').value)
        ox_rel = float(self.get_parameter('lane_grid_origin_x_m').value)
        oy_rel = float(self.get_parameter('lane_grid_origin_y_m').value)
        mode = str(self.get_parameter('lane_grid_mode').value)
        lane_w = float(self.get_parameter('lane_width_m').value)

        if res <= 0.0 or Wm <= 0.0 or Hm <= 0.0:
            return

        width = max(1, int(round(Wm / res)))
        height = max(1, int(round(Hm / res)))

        tf_timeout = float(self.get_parameter('tf_timeout_sec').value)
        timeout = Duration(seconds=tf_timeout)

        # For rolling local grids: use latest TF
        t_tf = rclpy.time.Time()

        # -------- robot pose in grid_frame (for rolling origin + robot bubble)
        bx = by = 0.0
        have_robot_tf = False
        if grid_frame == output_frame:
            have_robot_tf = True
            bx, by = 0.0, 0.0
        else:
            try:
                tf_rb = self.tf_buffer.lookup_transform(grid_frame, output_frame, t_tf, timeout)
                bx = float(tf_rb.transform.translation.x)
                by = float(tf_rb.transform.translation.y)
                have_robot_tf = True
            except Exception as e:
                self.get_logger().warn(
                    f"[lane_grid] TF missing ({grid_frame} <- {output_frame}); using fallback origin/bubble. err={e}",
                    throttle_duration_sec=2.0,
                )

        origin_x = bx + ox_rel
        origin_y = by + oy_rel

        # -------- transform lane points into grid_frame
        pts = lane_pts_out.astype(float)

        if output_frame == grid_frame:
            pts_grid = pts
        else:
            try:
                tf_go = self.tf_buffer.lookup_transform(grid_frame, output_frame, t_tf, timeout)
                q = tf_go.transform.rotation
                R = quat_to_rot(q.x, q.y, q.z, q.w)
                t = np.array([tf_go.transform.translation.x,
                              tf_go.transform.translation.y,
                              tf_go.transform.translation.z], dtype=float)
                pts_grid = (R @ pts.T).T + t[None, :]
            except Exception as e:
                self.get_logger().warn(
                    f"[lane_grid] TF missing for lane points ({grid_frame} <- {output_frame}); skipping. err={e}",
                    throttle_duration_sec=2.0,
                )
                return

        # -------- grid init (semantics)
        if mode == "centerline_only":
            grid = np.full((height, width), -1, dtype=np.int8)
        else:
            grid = np.full((height, width), 100, dtype=np.int8)

        def world_to_cell(x: float, y: float):
            cx = int(np.floor((x - origin_x) / res))
            cy = int(np.floor((y - origin_y) / res))
            return cx, cy

        # Always carve a free bubble around the robot (prevents "robot starts in obstacle")
        robot_r = float(self.get_parameter('robot_free_radius_m').value)
        rr = max(1, int(np.ceil(max(0.0, robot_r) / res)))
        # robot position in grid_frame is (bx, by); if TF missing, bubble may be at fallback (0,0)
        rcx, rcy = world_to_cell(bx, by)
        x0 = clamp(rcx - rr, 0, width - 1); x1 = clamp(rcx + rr, 0, width - 1)
        y0 = clamp(rcy - rr, 0, height - 1); y1 = clamp(rcy + rr, 0, height - 1)
        if mode == "centerline_only":
            grid[y0:y1+1, x0:x1+1] = 0
        else:
            grid[y0:y1+1, x0:x1+1] = 0

        # Corridor radius (half width)
        rad_m = 0.5 * max(0.05, lane_w)
        rad_cells = max(1, int(np.ceil(rad_m / res)))

        # Dense rasterization along segments for continuity
        step = float(self.get_parameter('segment_sample_step_m').value)
        step = max(0.05, step)

        def carve_at_xy(x: float, y: float):
            cx, cy = world_to_cell(x, y)
            if cx < -rad_cells or cx >= width + rad_cells or cy < -rad_cells or cy >= height + rad_cells:
                return
            if mode == "centerline_only":
                if 0 <= cx < width and 0 <= cy < height:
                    grid[cy, cx] = 0
            else:
                x0_ = clamp(cx - rad_cells, 0, width - 1)
                x1_ = clamp(cx + rad_cells, 0, width - 1)
                y0_ = clamp(cy - rad_cells, 0, height - 1)
                y1_ = clamp(cy + rad_cells, 0, height - 1)
                grid[y0_:y1_+1, x0_:x1_+1] = 0

        for A, B in zip(pts_grid[:-1], pts_grid[1:]):
            ax, ay = float(A[0]), float(A[1])
            bx2, by2 = float(B[0]), float(B[1])
            dist = float(np.hypot(bx2 - ax, by2 - ay))
            n = max(2, int(np.ceil(dist / step)))
            for s in np.linspace(0.0, 1.0, n):
                x = ax + s * (bx2 - ax)
                y = ay + s * (by2 - ay)
                carve_at_xy(x, y)

        og = OccupancyGrid()
        og.header.stamp = stamp
        og.header.frame_id = grid_frame

        og.info.resolution = float(res)
        og.info.width = int(width)
        og.info.height = int(height)
        og.info.origin.position.x = float(origin_x)
        og.info.origin.position.y = float(origin_y)
        og.info.origin.position.z = 0.0
        og.info.origin.orientation.w = 1.0

        og.data = grid.reshape(-1).tolist()
        self.pub_grid.publish(og)

    # -------------------------
    # Main callback
    # -------------------------
    def on_pixels(self, msg: PolygonStamped):
        if self.K is None or self.img_w is None or self.img_h is None:
            return  # wait for CameraInfo

        output_frame = str(self.get_parameter('output_frame').value)
        camera_frame = str(self.get_parameter('camera_frame').value)
        min_v_frac = float(self.get_parameter('min_v_frac').value)
        tf_timeout = float(self.get_parameter('tf_timeout_sec').value)

        # TF: output_frame <- camera_frame
        try:
            tf = self.tf_buffer.lookup_transform(
                output_frame,
                camera_frame,
                rclpy.time.Time(),  # latest
                Duration(seconds=tf_timeout),
            )
            q = tf.transform.rotation
            R_oc = quat_to_rot(q.x, q.y, q.z, q.w)
            t_oc = np.array([tf.transform.translation.x,
                             tf.transform.translation.y,
                             tf.transform.translation.z], dtype=float)
        except Exception:
            # Fallback: camera axes assumed aligned with output_frame
            R_oc = np.eye(3)
            t_oc = np.array([
                float(self.get_parameter('cam_x_m').value),
                float(self.get_parameter('cam_y_m').value),
                float(self.get_parameter('cam_z_m').value),
            ], dtype=float)

        pts_out = []
        pts_uv = []

        total = len(msg.polygon.points)
        valid = 0
        v_min = int(min_v_frac * self.img_h)

        for p in msg.polygon.points:
            u = float(p.x)
            v = float(p.y)
            if v < v_min:
                continue

            # Ray in optical frame: x right, y down, z forward
            x = (u - self.cx) / self.fx
            y = (v - self.cy) / self.fy
            ray_cam = np.array([x, y, 1.0], dtype=float)
            ray_cam /= (np.linalg.norm(ray_cam) + 1e-12)

            # Transform ray into output_frame
            ray_out = R_oc @ ray_cam
            ray_out /= (np.linalg.norm(ray_out) + 1e-12)

            # Ray origin in output_frame
            o = t_oc

            # Intersect with ground plane z=0 in output_frame
            dz = float(ray_out[2])
            if dz >= -1e-6:
                continue
            t = -float(o[2]) / dz
            if t <= 0.0:
                continue

            X = o + t * ray_out
            X[2] = 0.0
            pts_out.append(X)
            pts_uv.append((u, v))
            valid += 1

        # Publish confidence + width
        conf_msg = Float32()
        conf_msg.data = float(valid) / float(max(1, total))
        self.pub_conf.publish(conf_msg)

        width_msg = Float32()
        width_msg.data = float(self.get_parameter('lane_width_m').value)
        self.pub_width.publish(width_msg)

        # Publish pixel-space lane mask
        self.publish_lane_mask(msg.header, pts_uv)

        # Publish path
        path = Path()
        path.header = msg.header
        path.header.frame_id = output_frame

        if valid < 3:
            self.pub_path.publish(path)
            return

        for X in pts_out:
            ps = PoseStamped()
            ps.header = path.header
            ps.pose.position.x = float(X[0])
            ps.pose.position.y = float(X[1])
            ps.pose.position.z = 0.0
            ps.pose.orientation.w = 1.0
            path.poses.append(ps)

        self.pub_path.publish(path)

        # Build lane points array (output_frame)
        pts_np = np.array(pts_out, dtype=float)

        # ---- Anchor corridor at robot + bridge to first visible lane point
        if bool(self.get_parameter('anchor_robot_in_corridor').value):
            robot_pt = np.array([[0.0, 0.0, 0.0]], dtype=float)

            if bool(self.get_parameter('bridge_to_first_point').value) and len(pts_np) > 0:
                bridge_step = float(self.get_parameter('bridge_step_m').value)
                bridge_step = max(0.05, bridge_step)

                p0 = pts_np[0].copy()
                dist = float(np.linalg.norm(p0[:2]))
                if dist > 1e-6:
                    n = max(2, int(np.ceil(dist / bridge_step)))
                    bridge = []
                    for s in np.linspace(0.0, 1.0, n):
                        xy = s * p0[:2]
                        bridge.append([xy[0], xy[1], 0.0])
                    pts_np = np.vstack([robot_pt, np.array(bridge, dtype=float), pts_np])
                else:
                    pts_np = np.vstack([robot_pt, pts_np])
            else:
                pts_np = np.vstack([robot_pt, pts_np])

        # Publish rolling OccupancyGrid
        self.publish_lane_grid(msg.header.stamp, pts_np, output_frame)


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
