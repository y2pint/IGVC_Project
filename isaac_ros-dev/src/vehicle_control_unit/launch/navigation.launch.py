# Standard library
import os

# ROS 2 launch
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch.actions import GroupAction, IncludeLaunchDescription, TimerAction, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PythonExpression
from launch_ros.actions import Node, PushRosNamespace

# Isaac ROS / NVBlox
import isaac_ros_launch_utils as lu
from nvblox_ros_python_utils.nvblox_launch_utils import NvbloxCamera, NvbloxMode
from nvblox_ros_python_utils.nvblox_constants import NVBLOX_CONTAINER_NAME


def _pkg_share(pkg: str) -> str:
    return get_package_share_directory(pkg)


def _cfg(pkg: str, *relpath: str) -> str:
    return os.path.join(_pkg_share(pkg), *relpath)


def _node(*, package: str, executable: str, name: str, params=None, remaps=None, condition=None):
    kwargs = dict(
        package=package,
        executable=executable,
        name=name,
        output='screen',
    )
    if params:
        kwargs['parameters'] = params
    if remaps:
        kwargs['remappings'] = remaps
    if condition is not None:
        kwargs['condition'] = condition
    return Node(**kwargs)


def generate_launch_description() -> LaunchDescription:
    # ----------------------------------------------------------------
    # Launch Arguments
    # ----------------------------------------------------------------
    args = lu.ArgumentContainer()

    for a in [
        dict(
            name='camera',
            default=NvbloxCamera.zed2,
            choices=[str(NvbloxCamera.zed2), str(NvbloxCamera.zedx)],
            description='The ZED camera type.',
        ),
        dict(name='rosbag', default='None', description='Path to rosbag (running on sensor if not set).'),
        dict(name='rosbag_args', default='', description='Additional args for ros2 bag play.'),
        dict(name='log_level', default='info', choices=['debug', 'info', 'warn']),
        dict(name='use_foxglove_whitelist', default=True, description='Disable bandwidth-heavy topics in Foxglove.'),
        dict(name='enable_goal_reach_checker', default=True, description='Run independent goal reach checker node.'),
        dict(name='enable_nav2_auto_cancel', default=True),
        dict(
            name='enable_lane_detection',
            default='false',
            choices=['true', 'false'],
            description='Run lane detection + projection nodes to publish /lane_mask.',
        ),
        dict(
            name='enable_realsense',
            default='false',
            choices=['true', 'false'],
        ),
        dict(
            name='realsense_fps',
            default='10',
            choices=['6', '10', '20'],
            description='Lowering FPS reduces USB 3.0 EMI noise for GPS.',
        ),
        dict(
            name='realsense_usb_port_type',
            default='2',
            choices=['2', '3'],
            description='Force USB 2.0 mode (2) to reduce high-frequency RFI, or use 3.0 (3).',
        ),
    ]:
        args.add_arg(
            a['name'],
            a['default'],
            choices=a.get('choices'),
            description=a.get('description'),
            cli=True,
        )

    actions = args.get_launch_actions()

    # ----------------------------------------------------------------
    # Common constants
    # ----------------------------------------------------------------
    pkg = 'vehicle_control_unit'

    wheel_radius  = 0.0891
    track_width   = 0.305
    gear_ratio    = 4.5

    ekf_local_params  = _cfg(pkg, 'config', 'ekf_local.yaml')
    nav2_params       = _cfg(pkg, 'config', 'nav2_params.yaml')
    waypoint_params   = _cfg(pkg, 'config', 'mission_waypoint_params.yaml')

    # Check for optional RealSense package
    rs_pkg_found = True
    try:
        rs_share = get_package_share_directory('realsense2_camera')
    except PackageNotFoundError:
        rs_pkg_found = False

    rs_res_fps = PythonExpression(["'640x480x' + str(", args.realsense_fps, ")"])

    # ================================================================
    # HARDWARE + SENSORS
    # NVBlox container, MAVROS, RC bridge, VESCs, drive, ZED,
    # RealSense (optional), wheel odometry, NVBlox perception
    # ================================================================
    actions += [
        # NVBlox container
        lu.component_container(NVBLOX_CONTAINER_NAME, log_level='warn'),

        # MAVROS
        GroupAction([
            PushRosNamespace('mavros'),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(_pkg_share(pkg), 'launch', 'mavros_apm.launch.py')
                )
            ),
        ]),

        # RC → /cmd_vel bridge
        _node(
            package=pkg,
            executable='rc_to_cmd_vel',
            name='rc_to_cmd_vel',
            remaps=[
                ('/mavros/rc/in', '/mavros/mavros/rc/in'),
                ('/cmd_vel', '/cmd_vel'),
            ],
        ),

        # VESC CAN drivers
        _node(
            package=pkg, executable='vesc_can_node', name='left_vesc',
            params=[{'vesc_id': 117, 'vesc_name': 'left_vesc'}],
        ),
        _node(
            package=pkg, executable='vesc_can_node', name='right_vesc',
            params=[{'vesc_id': 39, 'vesc_name': 'right_vesc'}],
        ),

        # cmd_vel → wheel RPM
        _node(
            package=pkg,
            executable='cmd_vel_node',
            name='cmd_vel_to_wheel_rpm',
            params=[{
                'wheel_radius': wheel_radius,
                'track_width': track_width,
                'gear_ratio': gear_ratio,
            }],
        ),

        # ZED camera driver
        lu.include(
            pkg,
            'launch/sensors/zed_new.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'zed_camera_model': args.camera,
            },
        ),

        # RealSense driver (optional)
        GroupAction(
            condition=IfCondition(args.enable_realsense),
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        [os.path.join(rs_share, 'launch', 'rs_launch.py')]
                    ),
                    launch_arguments={
                        'pointcloud.enable': 'true',
                        'enable_depth': 'true',
                        'enable_color': 'true',
                        'depth_module.profile': rs_res_fps,
                        'rgb_camera.profile': rs_res_fps,
                        'align_depth.enable': 'true',
                        'depth_module.infra_fps': args.realsense_fps,
                        'usb_port_type': args.realsense_usb_port_type,
                    }.items(),
                ) if rs_pkg_found else LogInfo(msg='RealSense package not found, skipping.')
            ],
        ),

        # Lane detection + projection (optional)
        GroupAction(
            condition=IfCondition(args.enable_lane_detection),
            actions=[
                TimerAction(
                    period=2.0,
                    actions=[
                        _node(
                            package=pkg,
                            executable='lane_detector_node',
                            name='lane_detection',
                            params=[{
                                'image_topic': '/zed/zed_node/rgb/image_rect_color',
                            }],
                        ),
                        _node(
                            package=pkg,
                            executable='lane_projection_node',
                            name='lane_projection',
                            params=[{
                                'camera_frame': 'zed_left_camera_optical_frame',
                                'output_frame': 'base_link',
                                'camera_info_topic': '/zed/zed_node/rgb/camera_info',
                                'pixels_topic': '/lane/centerline_pixels',
                                'path_topic': '/lane/centerline_path',
                                'lane_mask_topic': '/lane/mask_projected',
                                'global_frame': 'odom',
                                'resolution': 0.05,
                                'width_m': 6.0,
                                'height_m': 6.0,
                            }],
                        ),
                    ],
                ),
            ],
        ),

        # Wheel odometry (publish_tf=False — EKF owns odom→base_link)
        _node(
            package=pkg,
            executable='wheel_odom_node',
            name='wheel_odom',
            params=[{
                'wheel_radius': wheel_radius,
                'track_width': track_width,
                'gear_ratio': gear_ratio,
                'pole_pairs': 7,
                'odom_frame': 'odom',
                'base_frame': 'base_link',
                'left_erpm_topic': '/left_vesc/state/erpm',
                'right_erpm_topic': '/right_vesc/state/erpm',
                'odom_topic': '/wheel/odom',
                'erpm_deadband': 50,
                'left_sign': 1.0,
                'right_sign': 1.0,
                'publish_tf': False,
            }],
        ),

        # NVBlox perception
        lu.include(
            'vehicle_control_unit',
            'launch/perception/nvblox.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'mode': NvbloxMode.static,
                'camera': args.camera,
                'lidar': 'False',
            },
        ),

        # Nav2 LED indicator
        _node(
            package=pkg,
            executable='nav2_led_indicator',
            name='nav2_led_indicator',
            params=[{
                'port': '/dev/arduino_led',
                'baud': 115200,
                'startup_delay_sec': 2.0,
                'cmd_auto': 'MODE AUTO\n',
                'cmd_manual': 'MODE MANUAL\n',
                'resend_period_sec': 2.0,
                'status_topic': '/navigate_to_pose/_action/status',
            }],
        ),
    ]

    actions += [
        
        _node(
            package=pkg,
            executable='compass_heading_publisher',
            name='compass_heading_publisher',
            params=[{
                'mag_topic':      '/zed/zed_node/imu/mag',
                'imu_topic':      '/zed/zed_node/imu/data',
                'output_topic':   '/compass/pose',
                'frame_id':       'odom',
                'yaw_stdev_deg':  10.0,
                'alpha':          0.05,
                'deadband_deg':   10.0,
            }],
        ),
    ]

    # ================================================================
    # LOCAL EKF  (always on)
    # fuses wheel odometry → publishes odom → base_link TF
    # ================================================================
    actions += [
        _node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_local',
            params=[ekf_local_params, {'use_sim_time': False}],
            remaps=[('/odometry/filtered', '/odometry/local')],
        ),
    ]

    # ================================================================
    # OUTDOOR MODE  (no global EKF — GPS is used by mission pipeline
    # only, not for Nav2 localization)
    # map→odom is still identity; carrot_to_nav2 handles the
    # mission→map frame conversion using live TF + compass heading.
    # ================================================================
    actions += [
        _node(
            package=pkg,
            executable='map_odom_broadcaster',
            name='map_odom_broadcaster',
            params=[{
                'map_frame': 'map',
                'odom_frame': 'odom',
                'publish_rate_hz': 10.0, # was 50 hz
            }],
        ),
    ]

    # ================================================================
    # MISSION NAVIGATION PIPELINE  (outdoor only)
    # GPS → mission XY → waypoints → carrot → Nav2 action goal
    # ================================================================
    actions += [
        _node(
            package=pkg,
            executable='mission_global_frame_node',
            name='mission_global_frame_node',
        ),
        _node(
            package=pkg,
            executable='mission_waypoint_manager_node',
            name='mission_waypoint_manager_node',
            params=[waypoint_params],
        ),
        _node(
            package=pkg,
            executable='carrot_target_node',
            name='carrot_target_node',
        ),
        _node(
            package=pkg,
            executable='carrot_to_nav2_action_node',
            name='carrot_to_nav2_action_node',
        ),
    ]

    # ================================================================
    # NAV2  (delayed 5 s to let sensors and TF settle)
    # + goal reach checker + auto cancel + visualization
    # ================================================================
    # Always use local odometry — no global EKF
    goal_pose_topic = '/odometry/local'

    actions += [
        TimerAction(
            period=5.0,
            actions=[
                lu.include(
                    'nav2_bringup',
                    'launch/navigation_launch.py',
                    launch_arguments={
                        'use_sim_time': 'false',
                        'params_file': nav2_params,
                        'log_level': 'error',
                    },
                ),
                _node(
                    package=pkg,
                    executable='goal_reach_checker_node',
                    name='goal_reach_checker',
                    params=[{
                        'pose_topic': goal_pose_topic,
                        'goal_topic': '/goal_pose',
                        'xy_tolerance_m': 0.40,
                        'yaw_tolerance_rad': 0.35,
                        'require_yaw': True,
                        'hold_time_sec': 0.50,
                        'consecutive_hits': 5,
                        'goal_timeout_sec': 0.0,
                        'latch_on_reach': True,
                    }],
                    condition=IfCondition(args.enable_goal_reach_checker),
                ),
                _node(
                    package=pkg,
                    executable='nav2_goal_cancel_node',
                    name='nav2_goal_cancel',
                    condition=IfCondition(args.enable_nav2_auto_cancel),
                ),
            ],
        ),

        lu.include(
            pkg,
            'launch/visualization/visualization.launch.py',
            launch_arguments={
                'mode': NvbloxMode.static,
                'camera': args.camera,
                'use_foxglove_whitelist': args.use_foxglove_whitelist,
            },
        ),
    ]

    # ================================================================
    # STATUS MONITOR  (always on)
    # ================================================================
    actions += [
        _node(
            package=pkg,
            executable='status_monitor_gateway',
            name='status_monitor_gateway',
        ),
    ]

    return LaunchDescription(actions)