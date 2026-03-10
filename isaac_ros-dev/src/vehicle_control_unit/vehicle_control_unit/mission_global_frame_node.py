#!/usr/bin/env python3

import math
from typing import Optional

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Float64
from geometry_msgs.msg import PoseStamped
from std_srvs.srv import Trigger

from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

gps_qos = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
)



def yaw_to_quaternion(yaw: float):
    """Convert planar yaw [rad] to quaternion (x, y, z, w)."""
    half = 0.5 * yaw
    return 0.0, 0.0, math.sin(half), math.cos(half)


class MissionGlobalFrameNode(Node):
    """
    Owns the shared mission origin and publishes:
      1) /mission/global_pose_xy   : robot pose in local mission XY
      2) /mission/origin_fix       : shared mission origin as NavSatFix

    Input topics:
      - /mavros/mavros/global_position/global
      - /mavros/mavros/global_position/compass_hdg

    Service:
      - /mission/reset_origin_here  (std_srvs/Trigger)
    """

    def __init__(self):
        super().__init__('mission_global_frame_node')

        # ------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------
        self.declare_parameter(
            'gps_topic',
            '/mavros/mavros/global_position/global'
        )
        self.declare_parameter(
            'heading_topic',
            '/mavros/mavros/global_position/compass_hdg'
        )
        self.declare_parameter(
            'output_pose_topic',
            '/mission/global_pose_xy'
        )
        self.declare_parameter(
            'origin_topic',
            '/mission/origin_fix'
        )
        self.declare_parameter(
            'output_frame',
            'mission'
        )
        self.declare_parameter(
            'use_first_fix_as_origin',
            True
        )
        self.declare_parameter(
            'origin_lat_deg',
            0.0
        )
        self.declare_parameter(
            'origin_lon_deg',
            0.0
        )
        self.declare_parameter(
            'origin_alt_m',
            0.0
        )
        self.declare_parameter(
            'heading_offset_deg',
            0.0
        )
        self.declare_parameter(
            'publish_origin_period_sec',
            1.0
        )

        self.gps_topic = self.get_parameter('gps_topic').value
        self.heading_topic = self.get_parameter('heading_topic').value
        self.output_pose_topic = self.get_parameter('output_pose_topic').value
        self.origin_topic = self.get_parameter('origin_topic').value
        self.output_frame = self.get_parameter('output_frame').value
        self.use_first_fix_as_origin = bool(
            self.get_parameter('use_first_fix_as_origin').value
        )
        self.origin_lat_deg = float(
            self.get_parameter('origin_lat_deg').value
        )
        self.origin_lon_deg = float(
            self.get_parameter('origin_lon_deg').value
        )
        self.origin_alt_m = float(
            self.get_parameter('origin_alt_m').value
        )
        self.heading_offset_deg = float(
            self.get_parameter('heading_offset_deg').value
        )
        self.publish_origin_period_sec = float(
            self.get_parameter('publish_origin_period_sec').value
        )

        # ------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------
        self.latest_fix: Optional[NavSatFix] = None
        self.latest_heading_deg: Optional[float] = None

        self.origin_set = False
        if not self.use_first_fix_as_origin:
            self.origin_set = True

        # ------------------------------------------------------------
        # Publishers
        # ------------------------------------------------------------
        self.pose_pub = self.create_publisher(
            PoseStamped,
            self.output_pose_topic,
            10
        )

        self.origin_pub = self.create_publisher(
            NavSatFix,
            self.origin_topic,
            10
        )

        # ------------------------------------------------------------
        # Subscribers
        # ------------------------------------------------------------
        self.create_subscription(
            NavSatFix,
            self.gps_topic,
            self.fix_callback,
            gps_qos
        )

        self.create_subscription(
            Float64,
            self.heading_topic,
            self.heading_callback,
            gps_qos
        )

        # ------------------------------------------------------------
        # Service
        # ------------------------------------------------------------
        self.reset_origin_srv = self.create_service(
            Trigger,
            '/mission/reset_origin_here',
            self.handle_reset_origin_here
        )

        # ------------------------------------------------------------
        # Timer for periodic origin publication
        # ------------------------------------------------------------
        self.origin_timer = self.create_timer(
            self.publish_origin_period_sec,
            self.publish_origin_if_available
        )

        # ------------------------------------------------------------
        # Startup logs
        # ------------------------------------------------------------
        self.get_logger().info('mission_global_frame_node started')
        self.get_logger().info(f'GPS topic: {self.gps_topic}')
        self.get_logger().info(f'Heading topic: {self.heading_topic}')
        self.get_logger().info(f'Output pose topic: {self.output_pose_topic}')
        self.get_logger().info(f'Origin topic: {self.origin_topic}')

        if self.origin_set:
            self.get_logger().info(
                f'Using fixed origin: '
                f'lat={self.origin_lat_deg:.8f}, '
                f'lon={self.origin_lon_deg:.8f}, '
                f'alt={self.origin_alt_m:.3f}'
            )
        else:
            self.get_logger().info(
                'Origin will be initialized from the first valid GPS fix.'
            )

    # ============================================================
    # ROS callbacks
    # ============================================================
    def heading_callback(self, msg: Float64) -> None:
        self.latest_heading_deg = msg.data

    def fix_callback(self, msg: NavSatFix) -> None:
        self.latest_fix = msg

        if not self.is_valid_fix(msg):
            self.get_logger().warn('Invalid GPS fix received, skipping.')
            return

        if not self.origin_set:
            self.set_origin_from_fix(msg)
            self.publish_origin_if_available()

        if self.latest_heading_deg is None:
            return

        x_m, y_m = self.latlon_to_local_xy(
            lat_deg=msg.latitude,
            lon_deg=msg.longitude,
            lat0_deg=self.origin_lat_deg,
            lon0_deg=self.origin_lon_deg
        )

        # MAVROS compass_hdg is typically degrees clockwise from North.
        # ROS yaw is radians counterclockwise from +X (East).
        heading_deg = self.latest_heading_deg + self.heading_offset_deg
        yaw_rad = math.radians(90.0 - heading_deg)
        yaw_rad = self.wrap_to_pi(yaw_rad)

        qx, qy, qz, qw = yaw_to_quaternion(yaw_rad)

        pose_msg = PoseStamped()
        pose_msg.header.stamp = msg.header.stamp
        pose_msg.header.frame_id = self.output_frame

        pose_msg.pose.position.x = x_m
        pose_msg.pose.position.y = y_m
        pose_msg.pose.position.z = msg.altitude - self.origin_alt_m

        pose_msg.pose.orientation.x = qx
        pose_msg.pose.orientation.y = qy
        pose_msg.pose.orientation.z = qz
        pose_msg.pose.orientation.w = qw

        self.pose_pub.publish(pose_msg)

    # ============================================================
    # Service callback
    # ============================================================
    def handle_reset_origin_here(self, request, response):
        del request

        if self.latest_fix is None:
            response.success = False
            response.message = 'No GPS fix available yet; cannot reset origin.'
            return response

        if not self.is_valid_fix(self.latest_fix):
            response.success = False
            response.message = 'Latest GPS fix is invalid; cannot reset origin.'
            return response

        self.set_origin_from_fix(self.latest_fix)
        self.publish_origin_if_available()

        response.success = True
        response.message = (
            f'Origin reset to current fix: '
            f'lat={self.origin_lat_deg:.8f}, '
            f'lon={self.origin_lon_deg:.8f}, '
            f'alt={self.origin_alt_m:.3f}'
        )
        self.get_logger().info(response.message)
        return response

    # ============================================================
    # Helpers
    # ============================================================
    def set_origin_from_fix(self, fix: NavSatFix) -> None:
        self.origin_lat_deg = fix.latitude
        self.origin_lon_deg = fix.longitude
        self.origin_alt_m = fix.altitude
        self.origin_set = True

        self.get_logger().info(
            f'Origin set: '
            f'lat={self.origin_lat_deg:.8f}, '
            f'lon={self.origin_lon_deg:.8f}, '
            f'alt={self.origin_alt_m:.3f}'
        )

    def publish_origin_if_available(self) -> None:
        if not self.origin_set:
            return

        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.output_frame

        # For an origin point, status/service are not critical, but we can
        # set reasonable defaults.
        msg.status.status = 0
        msg.status.service = 1

        msg.latitude = self.origin_lat_deg
        msg.longitude = self.origin_lon_deg
        msg.altitude = self.origin_alt_m

        # Covariance is not meaningful here unless you want to preserve it
        # from the original fix; we publish zeros for a shared reference point.
        msg.position_covariance = [
            0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, 0.0, 0.0
        ]
        msg.position_covariance_type = 0

        self.origin_pub.publish(msg)

    @staticmethod
    def is_valid_fix(msg: NavSatFix) -> bool:
        if math.isnan(msg.latitude) or math.isnan(msg.longitude):
            return False
        if abs(msg.latitude) < 1e-12 and abs(msg.longitude) < 1e-12:
            return False
        return True

    @staticmethod
    def latlon_to_local_xy(
        lat_deg: float,
        lon_deg: float,
        lat0_deg: float,
        lon0_deg: float
    ):
        """
        Small-area tangent-plane approximation.
        x = East [m]
        y = North [m]
        Suitable for a site like 50 m x 50 m.
        """
        earth_radius_m = 6378137.0

        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)
        lat0 = math.radians(lat0_deg)
        lon0 = math.radians(lon0_deg)

        dlat = lat - lat0
        dlon = lon - lon0

        x_m = earth_radius_m * dlon * math.cos(lat0)
        y_m = earth_radius_m * dlat
        return x_m, y_m

    @staticmethod
    def wrap_to_pi(angle: float) -> float:
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle


def main(args=None):
    rclpy.init(args=args)
    node = MissionGlobalFrameNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()