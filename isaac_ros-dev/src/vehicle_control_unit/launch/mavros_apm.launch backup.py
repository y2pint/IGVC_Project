from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction, ExecuteProcess
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution

def generate_launch_description():

    mavros_launch = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('mavros'),
                'launch',
                'apm.launch'
            ])
        ),
        launch_arguments={
            'fcu_url': 'serial:///dev/ttyTHS1:57600',
            'time_sync': 'false',
        }.items()
    )

    # IMPORTANT: use the fully-qualified service that exists in your graph
    service_name = '/mavros/mavros/set_message_interval'

    # GPS_RAW_INT (ID 24) -> /mavros/global_position/raw/*
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

    # GLOBAL_POSITION_INT (ID 33) -> /mavros/global_position/global
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

    # RC_CHANNELS (ID 65) -> /mavros/rc/in
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
