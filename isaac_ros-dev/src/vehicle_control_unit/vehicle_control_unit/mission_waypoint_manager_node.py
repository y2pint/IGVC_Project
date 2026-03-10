#!/usr/bin/env python3

import math
import os
import yaml
from typing import List, Dict, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Bool
from std_srvs.srv import Trigger
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import PoseStamped, PointStamped
from visualization_msgs.msg import Marker, MarkerArray


class MissionWaypointManagerNode(Node):
    def __init__(self):
        super().__init__('mission_waypoint_manager_node')

        # ----------------------------
        # Parameters
        # ----------------------------
        self.declare_parameter('waypoints_file', '')
        self.declare_parameter('acceptance_radius_m', 2.5)
        self.declare_parameter('auto_advance', True)
        self.declare_parameter('loop_waypoints', False)
        self.declare_parameter('publish_markers', True)

        # Fallback origin (your current origin)
        self.declare_parameter('origin_latitude', 36.1756259)
        self.declare_parameter('origin_longitude', -85.5085356)
        self.declare_parameter('origin_altitude', 327.41380321122205)

        # Optional topic names
        self.declare_parameter('pose_topic', '/mission/global_pose_xy')
        self.declare_parameter('origin_topic', '/mission/origin_fix')
        self.declare_parameter('target_topic', '/mission/current_waypoint_xy')

        self.waypoints_file = self.get_parameter('waypoints_file').get_parameter_value().string_value
        self.acceptance_radius_m = self.get_parameter('acceptance_radius_m').value
        self.auto_advance = self.get_parameter('auto_advance').value
        self.loop_waypoints = self.get_parameter('loop_waypoints').value
        self.publish_markers = self.get_parameter('publish_markers').value

        self.pose_topic = self.get_parameter('pose_topic').value
        self.origin_topic = self.get_parameter('origin_topic').value
        self.target_topic = self.get_parameter('target_topic').value

        self.origin_lat = self.get_parameter('origin_latitude').value
        self.origin_lon = self.get_parameter('origin_longitude').value
        self.origin_alt = self.get_parameter('origin_altitude').value

        self.origin_received = False
        self.current_pose_xy: Optional[PoseStamped] = None
        self.current_index = 0
        self.mission_complete = False

        # Raw GPS waypoint list:
        # each item: {'name': ..., 'latitude': ..., 'longitude': ..., 'altitude': ...}
        self.raw_waypoints: List[Dict] = []

        # Local XY waypoint list:
        # each item: {'name': ..., 'x': ..., 'y': ..., 'z': ..., 'lat': ..., 'lon': ...}
        self.local_waypoints: List[Dict] = []

        # ----------------------------
        # Subscribers
        # ----------------------------
        self.pose_sub = self.create_subscription(
            PoseStamped,
            self.pose_topic,
            self.pose_callback,
            10
        )

        self.origin_sub = self.create_subscription(
            NavSatFix,
            self.origin_topic,
            self.origin_callback,
            10
        )

        # ----------------------------
        # Publishers
        # ----------------------------
        self.target_pub = self.create_publisher(PoseStamped, self.target_topic, 10)
        self.index_pub = self.create_publisher(Int32, '/mission/waypoint_index', 10)
        self.done_pub = self.create_publisher(Bool, '/mission/mission_complete', 10)

        self.active_wp_point_pub = self.create_publisher(PointStamped, '/mission/current_waypoint_point', 10)

        if self.publish_markers:
            self.marker_pub = self.create_publisher(MarkerArray, '/mission/waypoint_markers', 10)
        else:
            self.marker_pub = None

        # ----------------------------
        # Services
        # ----------------------------
        self.next_srv = self.create_service(Trigger, '/mission/next_waypoint', self.next_waypoint_srv)
        self.reset_srv = self.create_service(Trigger, '/mission/reset_waypoints', self.reset_waypoints_srv)

        # ----------------------------
        # Timer
        # ----------------------------
        self.timer = self.create_timer(0.2, self.timer_callback)

        # ----------------------------
        # Load waypoints
        # ----------------------------
        self.load_waypoints()

        if self.raw_waypoints:
            self.recompute_local_waypoints()
        else:
            self.get_logger().warn('No waypoints loaded yet.')

        self.get_logger().info('mission_waypoint_manager_node started.')

    # ==========================================================
    # Callbacks
    # ==========================================================
    def origin_callback(self, msg: NavSatFix):
        self.origin_lat = msg.latitude
        self.origin_lon = msg.longitude
        self.origin_alt = msg.altitude
        first_time = not self.origin_received
        self.origin_received = True

        if first_time:
            self.get_logger().info(
                f'Received mission origin from topic: '
                f'lat={self.origin_lat:.8f}, lon={self.origin_lon:.8f}, alt={self.origin_alt:.3f}'
            )
            if self.raw_waypoints:
                self.recompute_local_waypoints()

    def pose_callback(self, msg: PoseStamped):
        self.current_pose_xy = msg

    def timer_callback(self):
        self.publish_status()

        if not self.local_waypoints:
            return

        if self.mission_complete:
            self.publish_active_waypoint()
            self.publish_markers_if_needed()
            return

        self.check_waypoint_reached()
        self.publish_active_waypoint()
        self.publish_markers_if_needed()

    # ==========================================================
    # Services
    # ==========================================================
    def next_waypoint_srv(self, request, response):
        del request
        if not self.local_waypoints:
            response.success = False
            response.message = 'No waypoints loaded.'
            return response

        self.advance_waypoint(force=True)
        response.success = True
        response.message = f'Advanced to waypoint index {self.current_index}.'
        return response

    def reset_waypoints_srv(self, request, response):
        del request
        self.current_index = 0
        self.mission_complete = False
        response.success = True
        response.message = 'Waypoint sequence reset to index 0.'
        self.get_logger().info(response.message)
        return response

    # ==========================================================
    # Waypoint loading / conversion
    # ==========================================================
    def load_waypoints(self):
        if not self.waypoints_file:
            self.get_logger().warn('Parameter waypoints_file is empty.')
            return

        if not os.path.isfile(self.waypoints_file):
            self.get_logger().error(f'Waypoints file does not exist: {self.waypoints_file}')
            return

        try:
            with open(self.waypoints_file, 'r') as f:
                data = yaml.safe_load(f)

            if not data or 'waypoints' not in data:
                self.get_logger().error('YAML must contain a top-level "waypoints" list.')
                return

            self.raw_waypoints.clear()

            for i, wp in enumerate(data['waypoints']):
                if 'latitude' not in wp or 'longitude' not in wp:
                    self.get_logger().warn(f'Waypoint {i} missing latitude/longitude. Skipping.')
                    continue

                name = wp.get('name', f'wp_{i}')
                altitude = float(wp.get('altitude', 0.0))

                self.raw_waypoints.append({
                    'name': name,
                    'latitude': float(wp['latitude']),
                    'longitude': float(wp['longitude']),
                    'altitude': altitude,
                })

            self.get_logger().info(f'Loaded {len(self.raw_waypoints)} GPS waypoints from {self.waypoints_file}')

        except Exception as e:
            self.get_logger().error(f'Failed to load waypoints file: {e}')

    def recompute_local_waypoints(self):
        self.local_waypoints.clear()

        for wp in self.raw_waypoints:
            x, y = self.latlon_to_local_xy(
                wp['latitude'],
                wp['longitude'],
                self.origin_lat,
                self.origin_lon
            )

            self.local_waypoints.append({
                'name': wp['name'],
                'x': x,
                'y': y,
                'z': wp['altitude'],
                'lat': wp['latitude'],
                'lon': wp['longitude'],
            })

        self.get_logger().info(
            f'Computed {len(self.local_waypoints)} local XY waypoints using origin '
            f'({self.origin_lat:.8f}, {self.origin_lon:.8f})'
        )

        for i, wp in enumerate(self.local_waypoints):
            self.get_logger().info(
                f'  [{i}] {wp["name"]}: x={wp["x"]:.2f}, y={wp["y"]:.2f}, '
                f'lat={wp["lat"]:.8f}, lon={wp["lon"]:.8f}'
            )

    # ==========================================================
    # Core logic
    # ==========================================================
    def check_waypoint_reached(self):
        if self.current_pose_xy is None:
            return

        if not self.local_waypoints:
            return

        if self.current_index >= len(self.local_waypoints):
            return

        wp = self.local_waypoints[self.current_index]

        rx = self.current_pose_xy.pose.position.x
        ry = self.current_pose_xy.pose.position.y

        dx = wp['x'] - rx
        dy = wp['y'] - ry
        dist = math.hypot(dx, dy)

        if dist <= self.acceptance_radius_m:
            self.get_logger().info(
                f'Waypoint reached: idx={self.current_index}, name={wp["name"]}, dist={dist:.2f} m'
            )
            if self.auto_advance:
                self.advance_waypoint(force=False)

    def advance_waypoint(self, force: bool = False):
        if not self.local_waypoints:
            return

        if self.current_index < len(self.local_waypoints) - 1:
            self.current_index += 1
            self.get_logger().info(f'Advanced to waypoint index {self.current_index}')
            return

        # At final waypoint
        if self.loop_waypoints:
            self.current_index = 0
            self.mission_complete = False
            self.get_logger().info('Looping waypoints: returning to waypoint index 0')
        else:
            self.mission_complete = True
            if force:
                self.get_logger().info('Already at final waypoint; mission marked complete.')
            else:
                self.get_logger().info('Final waypoint reached; mission complete.')

    # ==========================================================
    # Publish helpers
    # ==========================================================
    def publish_status(self):
        idx_msg = Int32()
        idx_msg.data = self.current_index
        self.index_pub.publish(idx_msg)

        done_msg = Bool()
        done_msg.data = self.mission_complete
        self.done_pub.publish(done_msg)

    def publish_active_waypoint(self):
        if not self.local_waypoints:
            return

        if self.current_index >= len(self.local_waypoints):
            return

        wp = self.local_waypoints[self.current_index]

        pose_msg = PoseStamped()
        pose_msg.header.stamp = self.get_clock().now().to_msg()
        pose_msg.header.frame_id = 'mission'
        pose_msg.pose.position.x = wp['x']
        pose_msg.pose.position.y = wp['y']
        pose_msg.pose.position.z = wp['z']
        pose_msg.pose.orientation.w = 1.0
        self.target_pub.publish(pose_msg)

        point_msg = PointStamped()
        point_msg.header = pose_msg.header
        point_msg.point.x = wp['x']
        point_msg.point.y = wp['y']
        point_msg.point.z = wp['z']
        self.active_wp_point_pub.publish(point_msg)

    def publish_markers_if_needed(self):
        if self.marker_pub is None:
            return

        if not self.local_waypoints:
            return

        marker_array = MarkerArray()

        # Sphere markers for each waypoint
        for i, wp in enumerate(self.local_waypoints):
            m = Marker()
            m.header.frame_id = 'mission'
            m.header.stamp = self.get_clock().now().to_msg()
            m.ns = 'mission_waypoints'
            m.id = i
            m.type = Marker.SPHERE
            m.action = Marker.ADD
            m.pose.position.x = wp['x']
            m.pose.position.y = wp['y']
            m.pose.position.z = 0.2
            m.pose.orientation.w = 1.0
            m.scale.x = 0.8
            m.scale.y = 0.8
            m.scale.z = 0.8

            if i < self.current_index:
                m.color.r = 0.2
                m.color.g = 0.2
                m.color.b = 0.2
                m.color.a = 0.8
            elif i == self.current_index and not self.mission_complete:
                m.color.r = 0.0
                m.color.g = 1.0
                m.color.b = 0.0
                m.color.a = 1.0
            else:
                m.color.r = 0.0
                m.color.g = 0.3
                m.color.b = 1.0
                m.color.a = 0.9

            marker_array.markers.append(m)

            txt = Marker()
            txt.header.frame_id = 'mission'
            txt.header.stamp = m.header.stamp
            txt.ns = 'mission_waypoint_labels'
            txt.id = 1000 + i
            txt.type = Marker.TEXT_VIEW_FACING
            txt.action = Marker.ADD
            txt.pose.position.x = wp['x']
            txt.pose.position.y = wp['y']
            txt.pose.position.z = 1.2
            txt.pose.orientation.w = 1.0
            txt.scale.z = 0.6
            txt.color.r = 1.0
            txt.color.g = 1.0
            txt.color.b = 1.0
            txt.color.a = 1.0
            txt.text = f'{i}: {wp["name"]}'
            marker_array.markers.append(txt)

        # Line strip through all waypoints
        line = Marker()
        line.header.frame_id = 'mission'
        line.header.stamp = self.get_clock().now().to_msg()
        line.ns = 'mission_waypoint_path'
        line.id = 2000
        line.type = Marker.LINE_STRIP
        line.action = Marker.ADD
        line.pose.orientation.w = 1.0
        line.scale.x = 0.2
        line.color.r = 1.0
        line.color.g = 1.0
        line.color.b = 0.0
        line.color.a = 0.8

        for wp in self.local_waypoints:
            p = self.make_point(wp['x'], wp['y'], 0.1)
            line.points.append(p)

        marker_array.markers.append(line)
        self.marker_pub.publish(marker_array)

    # ==========================================================
    # Geodesy helpers
    # ==========================================================
    @staticmethod
    def latlon_to_local_xy(lat_deg: float, lon_deg: float, lat0_deg: float, lon0_deg: float):
        """
        Local tangent-plane approximation:
          x = East [m]
          y = North [m]
        Good for small mission areas like IGVC fields/courses.
        """
        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)
        lat0 = math.radians(lat0_deg)
        lon0 = math.radians(lon0_deg)

        dlat = lat - lat0
        dlon = lon - lon0

        earth_radius = 6378137.0  # WGS84 approx

        x = earth_radius * dlon * math.cos(lat0)
        y = earth_radius * dlat
        return x, y

    @staticmethod
    def make_point(x: float, y: float, z: float):
        from geometry_msgs.msg import Point
        p = Point()
        p.x = x
        p.y = y
        p.z = z
        return p


def main(args=None):
    rclpy.init(args=args)
    node = MissionWaypointManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()