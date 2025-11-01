# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# Licensed under the Apache License, Version 2.0

from isaac_ros_launch_utils.all_types import *
import isaac_ros_launch_utils as lu

from nvblox_ros_python_utils.nvblox_launch_utils import NvbloxMode, NvbloxCamera, NvbloxPeopleSegmentation
from nvblox_ros_python_utils.nvblox_constants import NVBLOX_CONTAINER_NAME

from launch_ros.actions import Node
from launch.actions import ExecuteProcess
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    args = lu.ArgumentContainer()

    # Argument Definitions
    args.add_arg('rosbag', 'None', description='Path to rosbag.', cli=True)
    args.add_arg('rosbag_args', '', description='Additional ros2 bag play args.', cli=True)
    args.add_arg('log_level', 'info', choices=['debug', 'info', 'warn'], cli=True)
    args.add_arg('num_cameras', 1, description='Number of cameras.', cli=True)
    args.add_arg('camera_serial_numbers', '', description='Comma-separated list of serial numbers.', cli=True)
    args.add_arg(
        'multicam_urdf_path',
        lu.get_path('vehicle_control_unit', 'config/urdf/4_realsense_carter_example_calibration.urdf.xacro'),
        description='URDF file path for camera rig extrinsics.',
        cli=True)
    args.add_arg('mode', default=NvbloxMode.static, choices=NvbloxMode.names(), description='nvblox mode.', cli=True)
    args.add_arg(
        'people_segmentation',
        default=NvbloxPeopleSegmentation.peoplesemsegnet_vanilla,
        choices=[
            str(NvbloxPeopleSegmentation.peoplesemsegnet_vanilla),
            str(NvbloxPeopleSegmentation.peoplesemsegnet_shuffleseg)
        ],
        description='PeopleSegNet model type.',
        cli=True)
    args.add_arg('attach_to_container', 'False', description='Use existing component container.', cli=True)
    args.add_arg('container_name', NVBLOX_CONTAINER_NAME, description='Component container name.')
    args.add_arg('run_realsense', 'True', description='Launch Realsense drivers')
    args.add_arg('use_foxglove_whitelist', True, description='Disable bandwidth-heavy topics in Foxglove.', cli=True)

    actions = args.get_launch_actions()

    # Reset RealSense hardware
    actions.append(
        ExecuteProcess(
            cmd=['/workspaces/isaac_ros-dev/scripts/reset_realsense.sh'],
            shell=True,
            output='screen'
        )
    )

    # Set use_sim_time if rosbag is provided
    actions.append(SetParameter('use_sim_time', True, condition=IfCondition(lu.is_valid(args.rosbag))))

    # Validate camera count
    actions.append(
        lu.assert_condition(
            'Up to 4 cameras have been tested! num_cameras must be less than 5.',
            IfCondition(PythonExpression(['int("', args.num_cameras, '") > 4']))
        )
    )

    # Determine camera mode
    camera_mode = lu.if_else_substitution(
        lu.is_equal(args.num_cameras, '1'),
        str(NvbloxCamera.realsense),
        str(NvbloxCamera.multi_realsense)
    )
    is_multi_cam = UnlessCondition(lu.is_equal(args.num_cameras, '1'))

    # Launch Realsense if enabled and not using rosbag
    run_rs_driver = UnlessCondition(
        OrSubstitution(lu.is_valid(args.rosbag), lu.is_false(args.run_realsense))
    )
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/sensors/realsense.launch.py',
            {
                'container_name': args.container_name,
                'camera_serial_numbers': args.camera_serial_numbers,
                'num_cameras': args.num_cameras,
            },
            condition=run_rs_driver
        )
    )

    # # Launch SLLIDAR C1
    # actions.append(
    #     lu.include(
    #         'sllidar_ros2',
    #         'launch/sllidar_c1_launch.py',
    #         {},
    #     )
    # )

    # Visual SLAM
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/perception/vslam.launch.py',
            {
                'container_name': args.container_name,
                'camera': camera_mode,
            },
            delay=1.0
        )
    )


    # Odometry relay
    actions.append(
        Node(
            package='vehicle_control_unit',
            executable='odom_relay_node',
            name='odom_relay_node',
            output='screen',
            parameters=[{
                'input_topic': '/visual_slam/tracking/odometry'  # or '/zed/zed_node/odom'
            }]
        )
    )


    # Static TF base_link ↔ camera0_link
    actions.append(
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0.2', '0', '0', '0', '0', '0', 'base_link', 'camera0_link']
        )
    )

    # Static TF base_link ↔ laser
    actions.append(
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0.0', '0.0', '0.1', '0', '0', '0', 'base_link', 'laser'],
            output='screen'
        )
    )
    

    # People segmentation setup
    camera_namespaces = ['camera0', 'camera1', 'camera2', 'camera3']
    camera_input_topics = [f'/{ns}/color/image_raw' for ns in camera_namespaces]
    input_camera_info_topics = [f'/{ns}/color/camera_info' for ns in camera_namespaces]
    output_resized_image_topics = [f'/{ns}/segmentation/image_resized' for ns in camera_namespaces]
    output_resized_camera_info_topics = [f'/{ns}/segmentation/camera_info_resized' for ns in camera_namespaces]

    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/perception/segmentation.launch.py',
            {
                'container_name': args.container_name,
                'people_segmentation': args.people_segmentation,
                'namespace_list': camera_namespaces,
                'input_topic_list': camera_input_topics,
                'input_camera_info_topic_list': input_camera_info_topics,
                'output_resized_image_topic_list': output_resized_image_topics,
                'output_resized_camera_info_topic_list': output_resized_camera_info_topics,
                'num_cameras': args.num_cameras,
                'one_container_per_camera': True,
            },
            condition=IfCondition(lu.has_substring(args.mode, NvbloxMode.people_segmentation))
        )
    )

    # People detection
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/perception/detection.launch.py',
            {
                'namespace_list': camera_namespaces,
                'input_topic_list': camera_input_topics,
                'num_cameras': args.num_cameras,
                'container_name': args.container_name,
                'one_container_per_camera': True
            },
            condition=IfCondition(lu.has_substring(args.mode, NvbloxMode.people_detection))
        )
    )

    # Nvblox mapping
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/perception/nvblox.launch.py',
            {
                'container_name': args.container_name,
                'mode': args.mode,
                'camera': camera_mode,
                'num_cameras': args.num_cameras,
                'lidar': 'True',   # ← ✅ 0711 Add

            }
        )
    )

    # Load robot description for multi-cam
    actions.append(
        lu.add_robot_description(robot_calibration_path=args.multicam_urdf_path, condition=is_multi_cam)
    )

    # Play rosbag
    actions.append(
        lu.play_rosbag(
            bag_path=args.rosbag,
            additional_bag_play_args=args.rosbag_args,
            condition=IfCondition(lu.is_valid(args.rosbag))
        )
    )

    # Visualization
    actions.append(
        lu.include(
            'vehicle_control_unit',
            'launch/visualization/visualization.launch.py',
            {
                'mode': args.mode,
                'camera': camera_mode,
                'use_foxglove_whitelist': args.use_foxglove_whitelist,
            }
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
            }
        )
    )

    # # rc_bridge_node
    # actions.append(
    #     Node(
    #         package='vehicle_control_unit',
    #         executable='rc_bridge_node',
    #         name='rc_bridge_node',
    #         output='screen'
    #     )
    # )

    # # vesc_bridge_node
    # actions.append(
    #     Node(
    #         package='vehicle_control_unit',
    #         executable='vesc_bridge_node',
    #         name='vesc_bridge_node',
    #         output='screen'
    #     )
    # )

    # # manual_control_node
    # actions.append(
    #     Node(
    #         package='vehicle_control_unit',
    #         executable='manual_control_node',
    #         name='manual_control_node',
    #         output='screen'
    #     )
    # )

    # # cmd_vel_node
    # actions.append(
    #     Node(
    #         package='vehicle_control_unit',
    #         executable='cmd_vel_node',
    #         name='cmd_vel_node',
    #         output='screen'
    #     )
    # )                  
                      
    
            
    # ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: { x: 0.4}, angular: { z: 0.3}}"


    # Optional controller development (uncomment as needed)
    # actions.append(Node(...))

    # Component container
    actions.append(
        lu.component_container(
            NVBLOX_CONTAINER_NAME,
            condition=UnlessCondition(args.attach_to_container),
            log_level=args.log_level
        )
    )

    return LaunchDescription(actions)
