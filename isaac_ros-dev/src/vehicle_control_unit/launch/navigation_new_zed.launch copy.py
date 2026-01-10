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
    # Robot Localization EKF (pose-only ZED VO)
    # ------------------------------------------------
    ekf_params_path = os.path.join(
        get_package_share_directory('vehicle_control_unit'),
        'config',
        'ekf_odom_zed.yaml'
    )

    actions.append(
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_odom',
            output='screen',
            parameters=[
                ekf_params_path,
                {'use_sim_time': False}
            ],
            remappings=[
                # ZED publishes odom pose here (verify exact topic)
                ('/odometry/filtered', '/odometry/filtered')
            ]
        )
    )

    actions.append(
    lu.include(
        'vehicle_control_unit',
        'launch/visualization/rviz_odom.launch.py',
        launch_arguments={
            'fixed_frame': 'odom'
            }
        )
    )




    # # Nvblox
    # actions.append(
    #     lu.include(
    #         'nvblox_examples_bringup',
    #         'launch/perception/nvblox.launch.py',
    #         launch_arguments={
    #             'container_name': NVBLOX_CONTAINER_NAME,
    #             'mode': NvbloxMode.static,
    #             'camera': args.camera,
    #         },
    #     )
    # )


    
    
    # # NAV2 bringup
    # nav2_params_path = os.path.join(
    #     get_package_share_directory('vehicle_control_unit'),
    #     'config',
    #     'nav2_params.yaml'
    # )
    # actions.append(
    #     lu.include(
    #         'nav2_bringup',
    #         'launch/navigation_launch.py',
    #         {
    #             'use_sim_time': 'false',
    #             'params_file': nav2_params_path,
    #             'log_level': 'error'
    #         }
    #     )
    # )

    # # Visualization
    # actions.append(
    #     lu.include(
    #         'vehicle_control_unit',
    #         'launch/visualization/visualization.launch.py',
    #         launch_arguments={
    #             'mode': NvbloxMode.static,
    #             'camera': args.camera,
    #             'use_foxglove_whitelist': args.use_foxglove_whitelist,
    #         }        
    #     )
    # )

    return LaunchDescription(actions)
