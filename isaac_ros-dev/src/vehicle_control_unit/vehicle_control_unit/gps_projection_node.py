#!/usr/bin/env python3

import math
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import NavSatFix, NavSatStatus
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Quaternion
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

gps_qos = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
)



# =========================
# WGS84 constants
# =========================
WGS84_A = 6378137.0                  # semi-major axis [m]
WGS84_F = 1.0 / 298.257223563        # flattening
WGS84_E2 = WGS84_F * (2.0 - WGS84_F) # eccentricity squared


def geodetic_to_ecef(lat_rad: float, lon_rad: float, h: float) -> Tuple[float, float, float]:
    """
    Convert geodetic coordinates (rad, rad, m) to ECEF (m).
    """
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    sin_lon = math.sin(lon_rad)
    cos_lon = math.cos(lon_rad)

    N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)

    x = (N + h) * cos_lat * cos_lon
    y = (N + h) * cos_lat * sin_lon
    z = (N * (1.0 - WGS84_E2) + h) * sin_lat
    return x, y, z


def ecef_to_enu(
    x: float, y: float, z: float,
    x0: float, y0: float, z0: float,
    lat0_rad: float, lon0_rad: float
) -> Tuple[float, float, float]:
    """
    Convert ECEF coordinates to local ENU coordinates relative to reference origin.
    """
    dx = x - x0
    dy = y - y0
    dz = z - z0

    sin_lat0 = math.sin(lat0_rad)
    cos_lat0 = math.cos(lat0_rad)
    sin_lon0 = math.sin(lon0_rad)
    cos_lon0 = math.cos(lon0_rad)

    east = -sin_lon0 * dx + cos_lon0 * dy
    north = -sin_lat0 * cos_lon0 * dx - sin_lat0 * sin_lon0 * dy + cos_lat0 * dz
    up = cos_lat0 * cos_lon0 * dx + cos_lat0 * sin_lon0 * dy + sin_lat0 * dz

    return east, north, up


def geodetic_to_enu(
    lat_deg: float, lon_deg: float, h: float,
    lat0_deg: float, lon0_deg: float, h0: float
) -> Tuple[float, float, float]:
    """
    Convert geodetic coordinates (deg, deg, m) to local ENU (m)
    using a geodetic reference origin.
    """
    lat_rad = math.radians(lat_deg)
    lon_rad = math.radians(lon_deg)
    lat0_rad = math.radians(lat0_deg)
    lon0_rad = math.radians(lon0_deg)

    x, y, z = geodetic_to_ecef(lat_rad, lon_rad, h)
    x0, y0, z0 = geodetic_to_ecef(lat0_rad, lon0_rad, h0)

    return ecef_to_enu(x, y, z, x0, y0, z0, lat0_rad, lon0_rad)


def yaw_to_quaternion(yaw: float) -> Quaternion:
    """
    Create a quaternion from yaw only.
    For GPS projected odometry, yaw is unknown, so usually 0.
    """
    q = Quaternion()
    q.x = 0.0
    q.y = 0.0
    q.z = math.sin(yaw * 0.5)
    q.w = math.cos(yaw * 0.5)
    return q


class GpsProjectionNode(Node):
    def __init__(self) -> None:
        super().__init__('gps_projection_node')

        # Parameters
        self.declare_parameter('gps_topic', '/mavros/mavros/global_position/raw/fix')
        self.declare_parameter('odom_topic', '/gps/odom_projected')
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('child_frame_id', 'gps')
        self.declare_parameter('use_first_fix_as_origin', True)
        self.declare_parameter('origin_lat', 0.0)
        self.declare_parameter('origin_lon', 0.0)
        self.declare_parameter('origin_alt', 0.0)
        self.declare_parameter('publish_altitude', False)

        gps_topic = self.get_parameter('gps_topic').get_parameter_value().string_value
        odom_topic = self.get_parameter('odom_topic').get_parameter_value().string_value
        self.frame_id = self.get_parameter('frame_id').get_parameter_value().string_value
        self.child_frame_id = self.get_parameter('child_frame_id').get_parameter_value().string_value
        self.use_first_fix_as_origin = self.get_parameter('use_first_fix_as_origin').get_parameter_value().bool_value
        self.publish_altitude = self.get_parameter('publish_altitude').get_parameter_value().bool_value

        self.origin_lat = self.get_parameter('origin_lat').get_parameter_value().double_value
        self.origin_lon = self.get_parameter('origin_lon').get_parameter_value().double_value
        self.origin_alt = self.get_parameter('origin_alt').get_parameter_value().double_value

        self.origin_initialized = False

        if not self.use_first_fix_as_origin:
            self.origin_initialized = True
            self.get_logger().info(
                f'Using fixed origin: lat={self.origin_lat:.8f}, '
                f'lon={self.origin_lon:.8f}, alt={self.origin_alt:.3f}'
            )

        self.sub_fix = self.create_subscription(
            NavSatFix,
            gps_topic,
            self.fix_callback,
            gps_qos
        )

        self.pub_odom = self.create_publisher(Odometry, odom_topic, 10)

        self.get_logger().info(f'Subscribed to GPS topic: {gps_topic}')
        self.get_logger().info(f'Publishing projected odometry: {odom_topic}')

    def gps_fix_valid(self, msg: NavSatFix) -> bool:
        """
        Basic validity check for GPS fix.
        """
        if msg.status.status == NavSatStatus.STATUS_NO_FIX:
            return False

        if math.isnan(msg.latitude) or math.isnan(msg.longitude):
            return False

        return True

    def initialize_origin_from_fix(self, msg: NavSatFix) -> None:
        self.origin_lat = msg.latitude
        self.origin_lon = msg.longitude
        self.origin_alt = 0.0 if math.isnan(msg.altitude) else msg.altitude
        self.origin_initialized = True

        self.get_logger().info(
            f'GPS origin initialized at lat={self.origin_lat:.8f}, '
            f'lon={self.origin_lon:.8f}, alt={self.origin_alt:.3f}'
        )

    def build_pose_covariance(self, msg: NavSatFix) -> list:
        """
        Convert NavSatFix 3x3 position covariance into Odometry 6x6 pose covariance.
        Layout for Odometry pose covariance:
        [x y z roll pitch yaw] row-major
        """
        pose_cov = [0.0] * 36

        # Default large uncertainties if covariance is unknown
        large_var = 1e6

        if msg.position_covariance_type == NavSatFix.COVARIANCE_TYPE_UNKNOWN:
            pose_cov[0] = large_var
            pose_cov[7] = large_var
            pose_cov[14] = large_var
        else:
            # NavSatFix covariance is row-major 3x3 for ENU position
            # [xx xy xz
            #  yx yy yz
            #  zx zy zz]
            gps_cov = msg.position_covariance

            pose_cov[0] = gps_cov[0]   # x-x
            pose_cov[1] = gps_cov[1]   # x-y
            pose_cov[2] = gps_cov[2]   # x-z

            pose_cov[6] = gps_cov[3]   # y-x
            pose_cov[7] = gps_cov[4]   # y-y
            pose_cov[8] = gps_cov[5]   # y-z

            pose_cov[12] = gps_cov[6]  # z-x
            pose_cov[13] = gps_cov[7]  # z-y
            pose_cov[14] = gps_cov[8]  # z-z

        # Orientation is unknown
        pose_cov[21] = large_var  # roll
        pose_cov[28] = large_var  # pitch
        pose_cov[35] = large_var  # yaw

        return pose_cov

    def fix_callback(self, msg: NavSatFix) -> None:
        if not self.gps_fix_valid(msg):
            self.get_logger().warn_throttle(5000, 'Received invalid GPS fix.')
            return

        if not self.origin_initialized:
            self.initialize_origin_from_fix(msg)

        alt = 0.0 if math.isnan(msg.altitude) else msg.altitude

        east, north, up = geodetic_to_enu(
            msg.latitude,
            msg.longitude,
            alt,
            self.origin_lat,
            self.origin_lon,
            self.origin_alt
        )

        odom = Odometry()
        odom.header = msg.header
        odom.header.frame_id = self.frame_id
        odom.child_frame_id = self.child_frame_id

        odom.pose.pose.position.x = east
        odom.pose.pose.position.y = north
        odom.pose.pose.position.z = up if self.publish_altitude else 0.0
        odom.pose.pose.orientation = yaw_to_quaternion(0.0)

        odom.pose.covariance = self.build_pose_covariance(msg)

        # Velocity unknown from plain NavSatFix
        odom.twist.covariance[0] = 1e6
        odom.twist.covariance[7] = 1e6
        odom.twist.covariance[14] = 1e6
        odom.twist.covariance[21] = 1e6
        odom.twist.covariance[28] = 1e6
        odom.twist.covariance[35] = 1e6

        self.pub_odom.publish(odom)

        self.get_logger().debug(
            f'Projected GPS ENU: x={east:.3f}, y={north:.3f}, z={up:.3f}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GpsProjectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()