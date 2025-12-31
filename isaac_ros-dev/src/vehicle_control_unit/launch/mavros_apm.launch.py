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
            'fcu_url': 'serial:///host_dev/pixhawk:57600',
            'time_sync': 'false'
        }.items()
    )

    # Set MAVLink message intervals for critical data (higher rate) and non-critical data (lower rate)
    set_rc_rate = ExecuteProcess(
        cmd=[
            'ros2', 'service', 'call',
            '/mavros/set_message_interval',
            'mavros_msgs/srv/MessageInterval',
            '{message_id: 65, message_rate: 10.0}'  # RC_CHANNELS to 10 Hz (reduce)
        ],
        output='screen'
    )

    # Reduce frequency for non-critical topics (e.g., GPS, raw data)
    set_gps_rate = ExecuteProcess(
        cmd=[
            'ros2', 'service', 'call',
            '/mavros/set_message_interval',
            'mavros_msgs/srv/MessageInterval',
            '{message_id: 26, message_rate: 1.0}'  # Global position data (e.g., GPS) to 1 Hz (reduce)
        ],
        output='screen'
    )

    set_imu_rate = ExecuteProcess(
        cmd=[
            'ros2', 'service', 'call',
            '/mavros/set_message_interval',
            'mavros_msgs/srv/MessageInterval',
            '{message_id: 132, message_rate: 5.0}'  # IMU data (lower frequency for less critical)
        ],
        output='screen'
    )

    return LaunchDescription([
        mavros_launch,

        # Wait 5 seconds to ensure MAVROS is connected
        TimerAction(
            period=5.0,
            actions=[set_rc_rate]
        ),
        
        # Wait 5 seconds to set GPS message interval
        TimerAction(
            period=5.0,
            actions=[set_gps_rate]
        ),
        
        # Set IMU message interval
        TimerAction(
            period=5.0,
            actions=[set_imu_rate]
        ),
    ])
