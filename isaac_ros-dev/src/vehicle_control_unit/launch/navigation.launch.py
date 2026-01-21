from isaac_ros_launch_utils.all_types import *
import isaac_ros_launch_utils as lu

from nvblox_ros_python_utils.nvblox_launch_utils import (
    NvbloxMode,
    NvbloxCamera,
)
from nvblox_ros_python_utils.nvblox_constants import NVBLOX_CONTAINER_NAME

from launch.actions import (
    SetEnvironmentVariable,
    TimerAction,
    GroupAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition
from launch_ros.actions import (
    Node,
    PushRosNamespace,
)

import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    # ------------------------------------------------
    # Launch Arguments
    # ------------------------------------------------
    args = lu.ArgumentContainer()

    args.add_arg(
        'camera',
        NvbloxCamera.zed2,
        choices=[str(NvbloxCamera.zed2), str(NvbloxCamera.zedx)],
        description='The ZED camera type.',
        cli=True,
    )

    args.add_arg(
        'rosbag',
        'None',
        description='Path to rosbag (running on sensor if not set).',
        cli=True,
    )

    args.add_arg(
        'rosbag_args',
        '',
        description='Additional args for ros2 bag play.',
        cli=True,
    )

    args.add_arg(
        'log_level',
        'info',
        choices=['debug', 'info', 'warn'],
        cli=True,
    )

    args.add_arg(
        'use_foxglove_whitelist',
        True,
        description='Disable bandwidth-heavy topics in Foxglove.',
        cli=True,
    )

    # NEW: independent goal reach checker enable switch
    args.add_arg(
        'enable_goal_reach_checker',
        True,
        description='Run independent goal reach checker node.',
        cli=True,
    )

    args.add_arg(
        'enable_nav2_auto_cancel',
        True,
        cli=True,
    )

    actions = args.get_launch_actions()

    # ------------------------------------------------
    # NVBlox Component Container
    # ------------------------------------------------
    actions.append(
        lu.component_container(
            NVBLOX_CONTAINER_NAME,
            log_level='warn',  # intentionally restricted
        )
    )

    # ------------------------------------------------
    # MAVROS (isolated launch context)
    # ------------------------------------------------
    actions.append(
        GroupAction(
            [
                PushRosNamespace('mavros'),
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        os.path.join(
                            get_package_share_directory('vehicle_control_unit'),
                            'launch',
                            'mavros_apm.launch.py',
                        )
                    )
                ),
            ]
        )
    )

    # ------------------------------------------------
    # RC → /cmd_vel Bridge
    # ------------------------------------------------
    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='rc_to_cmd_vel',
            name='rc_to_cmd_vel',
            output='screen',
            remappings=[
                ('/mavros/rc/in', '/mavros/mavros/rc/in'),
                ('/cmd_vel', '/cmd_vel'),
            ]
        )
    )

    # ------------------------------------------------
    # VESC CAN Nodes
    # ------------------------------------------------
    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='vesc_can_node',
            name='left_vesc',
            output='screen',
            parameters=[
                {'vesc_id': 70},
                {'vesc_name': 'left_vesc'},
            ],
        )
    )

    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='vesc_can_node',
            name='right_vesc',
            output='screen',
            parameters=[
                {'vesc_id': 8},
                {'vesc_name': 'right_vesc'},
            ],
        )
    )

    # ------------------------------------------------
    # /cmd_vel → Wheel RPM (Differential Drive)
    # ------------------------------------------------
    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='cmd_vel_node',
            name='cmd_vel_to_wheel_rpm',
            output='screen',
            parameters=[
                {
                    'wheel_radius': 0.095,  # meters
                    'track_width': 0.38,    # meters
                    'gear_ratio': 4.0,
                }
            ],
        )
    )

    # ------------------------------------------------
    # ZED Driver
    # ------------------------------------------------
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/sensors/zed_new.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'zed_camera_model': args.camera,
            },
        )
    )

    # ------------------------------------------------
    # Wheel Odometry (ERPM-based)
    # Owns odom → base_link
    # ------------------------------------------------
    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='wheel_odom_node',
            name='wheel_odom',
            output='screen',
            parameters=[
                {
                    'wheel_radius': 0.075,
                    'track_width': 0.38,
                    'gear_ratio': 4.0,
                    'pole_pairs': 7,

                    # Frames
                    'odom_frame': 'odom',
                    'base_frame': 'base_link',

                    # Topics
                    'left_erpm_topic': '/left_vesc/state/erpm',
                    'right_erpm_topic': '/right_vesc/state/erpm',
                    'odom_topic': '/wheel/odom',

                    # Safety / noise
                    'erpm_deadband': 50,

                    # Signs (change ONLY if needed)
                    'left_sign': 1.0,
                    'right_sign': 1.0,

                    'publish_tf': False,
                }
            ],
        )
    )

    # ------------------------------------------------
    # Robot Localization EKF (LOCAL)
    # Publishes: odom → base_link
    # ------------------------------------------------
    ekf_local_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'ekf_local.yaml',
    )

    actions.append(
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_local',
            output='screen',
            parameters=[
                ekf_local_params_path,
                {'use_sim_time': False},
            ],
            remappings=[
                ('/odometry/filtered', '/odometry/local'),
            ],
        )
    )

    # ------------------------------------------------
    # TF Bootstrap (map → odom → base_link)
    # ------------------------------------------------
    actions.append(
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom'],
        )
    )

    actions.append(
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0', '0', '0', '0', '0', '0', 'odom', 'base_link'],
        )
    )

    # ------------------------------------------------
    # Robot Localization EKF (GLOBAL)
    # Publishes: map → odom
    # ------------------------------------------------
    ekf_global_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'ekf_global.yaml',
    )

    actions.append(
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_global',
            output='screen',
            parameters=[
                ekf_global_params_path,
                {'use_sim_time': False},
            ],
            remappings=[
                ('/odometry/filtered', '/odometry/global'),
            ],
        )
    )

    # ------------------------------------------------
    # NVBlox
    # ------------------------------------------------
    actions.append(
        lu.include(
            'nvblox_examples_bringup',
            'launch/perception/nvblox.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'mode': NvbloxMode.static,
                'camera': args.camera,
            },
        )
    )

    # ------------------------------------------------
    # Nav2 Bringup (Delayed) + Independent Goal Reach Checker (Option A)
    # ------------------------------------------------
    nav2_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'nav2_params.yaml',
    )

    actions.append(
        TimerAction(
            period=10.0,
            actions=[
                lu.include(
                    'nav2_bringup',
                    'launch/navigation_launch.py',
                    {
                        'use_sim_time': 'false',
                        'params_file': nav2_params_path,
                        'log_level': 'error',
                    },
                ),

                # NEW: independent goal reach checker node
                Node(
                    package='vehicle_control_unit',           # change if your node lives elsewhere
                    executable='goal_reach_checker_node',     # must match your installed executable/entrypoint
                    name='goal_reach_checker',
                    output='screen',
                    parameters=[
                        {
                            # Pose source: use the EKF output you want to evaluate against.
                            # Recommend LOCAL for arrival detection stability:
                            'pose_topic': '/odometry/global',
                            # Alternative:
                            # 'pose_topic': '/odometry/local',

                            # Goal source:
                            'goal_topic': '/goal_pose',

                            # Tolerances (tune for IGVC)
                            'xy_tolerance_m': 0.40,
                            'yaw_tolerance_rad': 0.35,
                            'require_yaw': True,

                            # Stability gating (tune)
                            'hold_time_sec': 0.50,
                            'consecutive_hits': 5,

                            # Behavior
                            'goal_timeout_sec': 0.0,
                            'latch_on_reach': True,
                        }
                    ],
                    condition=IfCondition(args.enable_goal_reach_checker),
                ),

                Node(
                    package='vehicle_control_unit',
                    executable='nav2_goal_cancel_node',
                    name='nav2_goal_cancel',
                    condition=IfCondition(args.enable_nav2_auto_cancel),
                    output='screen',
                ),
            ],
        )
    )

    # ------------------------------------------------
    # Visualization
    # ------------------------------------------------
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/visualization/visualization.launch.py',
            launch_arguments={
                'mode': NvbloxMode.static,
                'camera': args.camera,
                'use_foxglove_whitelist': args.use_foxglove_whitelist,
            },
        )
    )

    return LaunchDescription(actions)
