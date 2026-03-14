from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction, ExecuteProcess
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():

    pluginlists_yaml = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'mavros_plugins_rover.yaml'
    )

    config_yaml = os.path.join(
        get_package_share_directory('mavros'),
        'launch',
        'apm_config.yaml'    # keep using the default config
    )

    mavros_launch = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('mavros'),
                'launch',
                'node.launch'       # call node.launch directly, not apm.launch
            ])
        ),
        launch_arguments={
            'fcu_url': 'serial:///dev/ttyTHS1:57600',
            'gcs_url': '',
            'tgt_system': '1',
            'tgt_component': '1',
            'fcu_protocol': 'v2.0',
            'respawn_mavros': 'false',
            'pluginlists_yaml': pluginlists_yaml,  # now actually passed
            'config_yaml': config_yaml,
        }.items()
    )
    
    service_name = '/mavros/mavros/set_message_interval'

    set_gps_raw_int = TimerAction(
        period=3.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'ros2', 'service', 'call',
                    service_name,
                    'mavros_msgs/srv/MessageInterval',
                    '{message_id: 24, message_rate: 2.0}'
                ],
                output='screen'
            )
        ]
    )

    set_global_position_int = TimerAction(
        period=3.5,
        actions=[
            ExecuteProcess(
                cmd=[
                    'ros2', 'service', 'call',
                    service_name,
                    'mavros_msgs/srv/MessageInterval',
                    '{message_id: 33, message_rate: 2.0}'
                ],
                output='screen'
            )
        ]
    )

    set_rc_channels = TimerAction(
        period=4.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'ros2', 'service', 'call',
                    service_name,
                    'mavros_msgs/srv/MessageInterval',
                    '{message_id: 65, message_rate: 10.0}'
                ],
                output='screen'
            )
        ]
    )

    return LaunchDescription([
        mavros_launch,
        set_gps_raw_int,
        set_global_position_int,
        set_rc_channels,
    ])