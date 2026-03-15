#!/usr/bin/env python3
"""
compass_heading_publisher.py

Computes yaw from ZED2 magnetometer with tilt compensation using ZED IMU.
Publishes PoseWithCovarianceStamped with only yaw populated,
relative to robot startup heading.

Features:
- Tilt compensation using ZED IMU roll/pitch
- Low-pass filter in sin/cos space (handles wraparound correctly)
- Deadband gate — only publishes when heading change exceeds threshold
  This prevents stationary magnetometer noise from jerking the EKF
"""
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy


class CompassHeadingPublisher(Node):
    def __init__(self):
        super().__init__('compass_heading_publisher')

        self.declare_parameter('mag_topic',      '/zed/zed_node/imu/mag')
        self.declare_parameter('imu_topic',      '/zed/zed_node/imu/data')
        self.declare_parameter('output_topic',   '/compass/pose')
        self.declare_parameter('frame_id',       'odom')
        self.declare_parameter('yaw_stdev_deg',  10.0)  # soft correction weight
        self.declare_parameter('alpha',          0.05)  # heavy smoothing
        self.declare_parameter('deadband_deg',   2.0)   # min change to publish

        mag_topic    = self.get_parameter('mag_topic').get_parameter_value().string_value
        imu_topic    = self.get_parameter('imu_topic').get_parameter_value().string_value
        output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.frame_id     = self.get_parameter('frame_id').get_parameter_value().string_value
        yaw_stdev_deg     = self.get_parameter('yaw_stdev_deg').get_parameter_value().double_value
        self.alpha        = self.get_parameter('alpha').get_parameter_value().double_value
        deadband_deg      = self.get_parameter('deadband_deg').get_parameter_value().double_value

        self.yaw_variance       = math.radians(yaw_stdev_deg) ** 2
        self.deadband           = math.radians(deadband_deg)
        self.heading_offset     = None
        self.smoothed_yaw       = None
        self.last_published_yaw = None

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.latest_imu: Imu = None
        self.sub_imu = self.create_subscription(
            Imu, imu_topic, self.imu_callback, sensor_qos
        )
        self.sub_mag = self.create_subscription(
            MagneticField, mag_topic, self.mag_callback, sensor_qos
        )
        self.pub = self.create_publisher(
            PoseWithCovarianceStamped, output_topic, 10
        )

        self.get_logger().info(f'Mag topic:      {mag_topic}')
        self.get_logger().info(f'IMU topic:      {imu_topic}')
        self.get_logger().info(f'Output topic:   {output_topic}')
        self.get_logger().info(f'Yaw stdev:      {yaw_stdev_deg:.2f} deg')
        self.get_logger().info(f'Yaw variance:   {self.yaw_variance:.6f} rad²')
        self.get_logger().info(f'Alpha:          {self.alpha}')
        self.get_logger().info(f'Deadband:       {deadband_deg:.2f} deg')

    # ------------------------------------------------------------------

    def imu_callback(self, msg: Imu):
        self.latest_imu = msg

    def quaternion_to_roll_pitch(self, q) -> tuple:
        """Extract roll and pitch from quaternion."""
        x, y, z, w = q.x, q.y, q.z, q.w
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(sinp)
        return roll, pitch

    def tilt_compensate(self, mx: float, my: float, mz: float,
                        roll: float, pitch: float) -> tuple:
        """Tilt-compensate magnetometer readings using roll and pitch."""
        cos_roll  = math.cos(roll)
        sin_roll  = math.sin(roll)
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        mx2 = mx * cos_pitch + mz * sin_pitch
        my2 = mx * sin_roll * sin_pitch + my * cos_roll - mz * sin_roll * cos_pitch
        return mx2, my2

    def normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-pi, pi]."""
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def low_pass(self, new_yaw: float) -> float:
        """Low-pass filter in sin/cos space to handle wraparound."""
        if self.smoothed_yaw is None:
            self.smoothed_yaw = new_yaw
            return self.smoothed_yaw
        sin_f = (1.0 - self.alpha) * math.sin(self.smoothed_yaw) + self.alpha * math.sin(new_yaw)
        cos_f = (1.0 - self.alpha) * math.cos(self.smoothed_yaw) + self.alpha * math.cos(new_yaw)
        self.smoothed_yaw = math.atan2(sin_f, cos_f)
        return self.smoothed_yaw

    def yaw_to_quaternion(self, yaw: float) -> tuple:
        return (0.0, 0.0, math.sin(yaw * 0.5), math.cos(yaw * 0.5))

    def mag_callback(self, msg: MagneticField):
        mx = msg.magnetic_field.x
        my = msg.magnetic_field.y
        mz = msg.magnetic_field.z

        # Tilt compensate if IMU is available
        if self.latest_imu is not None:
            roll, pitch = self.quaternion_to_roll_pitch(self.latest_imu.orientation)
            mx, my = self.tilt_compensate(mx, my, mz, roll, pitch)

        # Compute yaw — ROS convention: counter-clockwise from East
        raw_yaw = math.atan2(-my, mx)

        # Initialize offset on first message
        if self.heading_offset is None:
            self.heading_offset = raw_yaw
            self.get_logger().info(
                f'Heading offset initialized: {math.degrees(self.heading_offset):.2f} deg'
            )

        relative_yaw = self.normalize_angle(raw_yaw - self.heading_offset)
        filtered_yaw = self.low_pass(relative_yaw)

        # ------------------------------------------------------------------
        # Deadband gate — skip publish if change is below threshold
        # Prevents stationary magnetometer noise from jerking the EKF
        # ------------------------------------------------------------------
        if self.last_published_yaw is not None:
            delta = abs(self.normalize_angle(filtered_yaw - self.last_published_yaw))
            if delta < self.deadband:
                self.get_logger().debug(
                    f'Skipped — delta {math.degrees(delta):.2f}° < deadband '
                    f'{math.degrees(self.deadband):.2f}°'
                )
                return

        # Publish correction
        self.last_published_yaw = filtered_yaw

        qx, qy, qz, qw = self.yaw_to_quaternion(filtered_yaw)

        out = PoseWithCovarianceStamped()
        out.header.stamp    = self.get_clock().now().to_msg()
        out.header.frame_id = self.frame_id

        out.pose.pose.orientation.x = qx
        out.pose.pose.orientation.y = qy
        out.pose.pose.orientation.z = qz
        out.pose.pose.orientation.w = qw

        out.pose.covariance       = [0.0] * 36
        out.pose.covariance[0]    = 1e6   # x
        out.pose.covariance[7]    = 1e6   # y
        out.pose.covariance[14]   = 1e6   # z
        out.pose.covariance[21]   = 1e6   # roll
        out.pose.covariance[28]   = 1e6   # pitch
        out.pose.covariance[35]   = self.yaw_variance  # yaw

        self.pub.publish(out)

        self.get_logger().debug(
            f'Published — '
            f'raw: {math.degrees(raw_yaw):.2f}°  '
            f'relative: {math.degrees(relative_yaw):.2f}°  '
            f'filtered: {math.degrees(filtered_yaw):.2f}°'
        )


def main(args=None):
    rclpy.init(args=args)
    node = CompassHeadingPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()