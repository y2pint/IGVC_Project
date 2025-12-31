from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([

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
            ]
        ),

        Node(
            package='vehicle_control_unit',
            executable='vesc_bridge_node',
            name='vesc_right',
            parameters=[{
                'vesc_port': '/host_dev/vesc_right',
                'reverse': True,
                'cmd_timeout': 0.2,
                'use_kickstart': False
            }],
            remappings=[
                ('vesc_rpm_cmd', 'vesc_right/rpm_cmd'),
                ('vesc_battery', 'vesc_right/vesc_battery'),
            ]
        )
    ])
