from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():

    mavros_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('vehicle_control_unit'),
                'launch',
                'mavros_apm.launch.py'
            )
        )
    )

    return LaunchDescription([

        # ------------------------------------------------------------
        # MAVROS (APM)
        # ------------------------------------------------------------
        mavros_launch,

        # ------------------------------------------------------------
        # RC → /cmd_vel bridge
        # ------------------------------------------------------------
        Node(
            package='vehicle_control_unit',
            executable='rc_to_cmd_vel',
            name='rc_to_cmd_vel',
            output='screen'
        ),

        # ------------------------------------------------------------
        # Left VESC
        # ------------------------------------------------------------
        Node(
            package='vehicle_control_unit',
            executable='vesc_bridge_node',
            name='vesc_left',
            parameters=[{
                'vesc_port': '/host_dev/vesc_left',
                'reverse': False,
                'cmd_timeout': 0.2,
                'use_kickstart': False
            }],
            remappings=[
                ('vesc_rpm_cmd', 'vesc_left/rpm_cmd'),
                ('vesc_battery', 'vesc_left/vesc_battery'),
            ],
            output='screen'
        ),

        # ------------------------------------------------------------
        # Right VESC
        # ------------------------------------------------------------
        Node(
            package='vehicle_control_unit',
            executable='vesc_bridge_node',
            name='vesc_right',
            parameters=[{
                'vesc_port': '/host_dev/vesc_right',
                'reverse': False,
                'cmd_timeout': 0.2,
                'use_kickstart': False
            }],
            remappings=[
                ('vesc_rpm_cmd', 'vesc_right/rpm_cmd'),
                ('vesc_battery', 'vesc_right/vesc_battery'),
            ],
            output='screen'
        ),

        # ------------------------------------------------------------
        # /cmd_vel → wheel RPM (diff drive)
        # ------------------------------------------------------------
        Node(
            package='vehicle_control_unit',
            executable='cmd_vel_node',
            name='cmd_vel_to_wheel_rpm',
            parameters=[{
                'wheel_radius': 0.095,   # meters
                'track_width': 0.38,     # meters
                'gear_ratio': 4.0
            }],
            output='screen'
        )

    ])
