# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pathlib

from launch import Action, LaunchDescription
from launch_ros.actions import Node
import isaac_ros_launch_utils as lu

from nvblox_ros_python_utils.nvblox_launch_utils import NvbloxMode, NvbloxCamera


def add_rviz(args: lu.ArgumentContainer) -> list[Action]:
    if lu.is_valid(args.rviz_config):
        rviz_config_path = pathlib.Path(args.rviz_config)
    else:
        mode = NvbloxMode[args.mode]
        camera = NvbloxCamera[args.camera]

        if camera in [NvbloxCamera.zed2, NvbloxCamera.zedx]:
            camera_str = 'zed'
        else:
            camera_str = str(camera)

        # Multi-RS static: same as single RS; others display overlays
        if camera is NvbloxCamera.multi_realsense and mode is NvbloxMode.static:
            camera_str = 'realsense'

        if mode is NvbloxMode.people_detection:
            rviz_config_name = f'{camera_str}_people_detection_example.rviz'
        elif mode is NvbloxMode.people_segmentation:
            rviz_config_name = f'{camera_str}_people_segmentation_example.rviz'
        elif mode is NvbloxMode.dynamic:
            rviz_config_name = f'{camera_str}_dynamics_example.rviz'
        else:
            rviz_config_name = f'{camera_str}_example.rviz'

        # Now use your package, not nvblox_examples_bringup
        rviz_config_path = lu.get_path(
            'vehicle_control_unit',
            f'config/visualization/{rviz_config_name}'
        )

    actions = []
    assert rviz_config_path.exists(), f'RViz config {rviz_config_path} does not exist.'
    actions.append(
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', str(rviz_config_path)],
            output='screen'
        )
    )
    return actions


def generate_launch_description() -> LaunchDescription:
    args = lu.ArgumentContainer()
    args.add_arg(
        'rviz_config',
        'None',
        description='Path to RViz config (uses default if not set).',
        cli=True)
    args.add_arg('mode', NvbloxMode.static)
    args.add_arg('camera', NvbloxCamera.realsense)

    args.add_opaque_function(add_rviz)
    return LaunchDescription(args.get_launch_actions())
