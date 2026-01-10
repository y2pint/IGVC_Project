from isaac_ros_launch_utils.all_types import *
import isaac_ros_launch_utils as lu

from nvblox_ros_python_utils.nvblox_launch_utils import NvbloxMode, NvbloxCamera
from nvblox_ros_python_utils.nvblox_constants import NVBLOX_CONTAINER_NAME

import os
from ament_index_python.packages import get_package_share_directory

def generate_launch_description() -> LaunchDescription:
    args = lu.ArgumentContainer()
    args.add_arg(
        'camera',
        NvbloxCamera.zed2,
        choices=[str(NvbloxCamera.zed2), str(NvbloxCamera.zedx)],
        description='The ZED camera type.',
        cli=True)
    args.add_arg(
        'rosbag', 'None', description='Path to rosbag (running on sensor if not set).', cli=True)
    args.add_arg('rosbag_args', '', description='Additional args for ros2 bag play.', cli=True)
    args.add_arg('log_level', 'info', choices=['debug', 'info', 'warn'], cli=True)
    args.add_arg('use_foxglove_whitelist', True, description='Disable bandwidth-heavy topics in Foxglove.', cli=True)
    actions = args.get_launch_actions()

    # Container
    actions.append(lu.component_container(NVBLOX_CONTAINER_NAME, log_level=args.log_level))

    # ZED driver
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
    # Wheel Odometry (ERPM-based, owns odom->base_link)
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

    # # ------------------------------------------------
    # # Robot Localization EKF (wheel odom + ZED IMU)
    # # ------------------------------------------------
    # ekf_params_path = os.path.join(
    #     get_package_share_directory('vehicle_control_unit'),
    #     'config',
    #     'ekf_odom_zed.yaml'
    # )

    # actions.append(
    #     Node(
    #         package='robot_localization',
    #         executable='ekf_node',
    #         name='ekf_odom',
    #         output='screen',
    #         parameters=[
    #             ekf_params_path,
    #             {'use_sim_time': False}
    #         ],
    #     )
    # )

    # # ------------------------------------------------
    # # Robot Localization EKF (wheel odom + ZED IMU)
    # # ------------------------------------------------
    # ekf_params_path = os.path.join(
    #     get_package_share_directory('vehicle_control_unit'),
    #     'config',
    #     'ekf_odom_zed.yaml'
    # )

    # actions.append(
    #     Node(
    #         package='robot_localization',
    #         executable='ekf_node',
    #         name='ekf_odom',
    #         output='screen',
    #         parameters=[
    #             ekf_params_path,
    #             {'use_sim_time': False}
    #         ],
    #     )
    # )

    # ------------------------------------------------
    # Robot Localization EKF (LOCAL)
    # Publishes: odom -> base_link
    # ------------------------------------------------
    ekf_local_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'ekf_local.yaml'
    )

    actions.append(
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_local',
            output='screen',
            parameters=[
                ekf_local_params_path,
                {'use_sim_time': False}
            ],
            remappings=[
                ('/odometry/filtered', '/odometry/local')
            ]
        )
    )

    # ------------------------------------------------
    # Robot Localization EKF (GLOBAL)
    # Publishes: map -> odom
    # ------------------------------------------------
    static_map_to_odom = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='map_to_odom_bootstrap',
        arguments=[
            '0', '0', '0',   # x y z
            '0', '0', '0',   # roll pitch yaw
            'map',
            'odom'
        ]
    )
    actions.append(static_map_to_odom)


    ekf_global_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'ekf_global.yaml'
    )

    actions.append(
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_global',
            output='screen',
            parameters=[
                ekf_global_params_path,
                {'use_sim_time': False}
            ],
            remappings=[
                ('/odometry/filtered', '/odometry/global')
            ]
        )
    )

    # Nvblox
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
    
    
    # NAV2 bringup
    nav2_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'nav2_params.yaml'
    )
    actions.append(
        lu.include(
            'nav2_bringup',
            'launch/navigation_launch.py',
            {
                'use_sim_time': 'false',
                'params_file': nav2_params_path,
                'log_level': 'error'
            }
        )
    )

    # Visualization
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/visualization/visualization.launch.py',
            launch_arguments={
                'mode': NvbloxMode.static,
                'camera': args.camera,
                'use_foxglove_whitelist': args.use_foxglove_whitelist,
            }        
        )
    )

    return LaunchDescription(actions)
