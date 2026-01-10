import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # -------------------------------
    # Launch arguments
    # -------------------------------
    fixed_frame_arg = DeclareLaunchArgument(
        'fixed_frame',
        default_value='odom',
        description='Fixed frame for RViz'
    )

    rviz_config_arg = DeclareLaunchArgument(
        'rviz_config',
        default_value=os.path.join(
            os.getenv('HOME'),
            'rviz',
            'odom_debug.rviz'
        ),
        description='RViz config file (source/user space)'
    )

    fixed_frame = LaunchConfiguration('fixed_frame')
    rviz_config = LaunchConfiguration('rviz_config')

    # -------------------------------
    # RViz Node
    # -------------------------------
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz_odom',
        output='screen',
        arguments=[
            '-d', rviz_config
        ],
        parameters=[
            {
                'use_sim_time': False
            }
        ]
    )

    # -------------------------------
    # Launch Description
    # -------------------------------
    return LaunchDescription([
        fixed_frame_arg,
        rviz_config_arg,
        rviz_node,
    ])
