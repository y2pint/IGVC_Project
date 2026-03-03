# Standard library
import os

# ROS 2 launch
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition, UnlessCondition
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
    # ------------------------------------------------
    # Launch Arguments
    # ------------------------------------------------
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

        # NEW: indoor/outdoor mode
        dict(
            name='indoor',
            default='true',
            choices=['true', 'false'],
            description='If true: publish static map->odom identity and do NOT run global EKF/navsat/GPS gates.',
        ),

        # NEW: lane detection / projection pipeline
        dict(
            name='enable_lane_detection',
            default='false',
            choices=['true', 'false'],
            description='If true: run lane detection + projection nodes to publish /lane_mask.',
        ),

        # RealSense Control
        dict(
            name='enable_realsense',
            default='false',
            choices=['true', 'false'],
        ),
        dict(
            name='realsense_fps',
            default='6',
            choices=['6', '15', '30'],
            description='Lowering FPS reduces USB 3.0 EMI noise for GPS.'
        ),
        dict(
            name='realsense_usb_port_type',
            default='2',
            choices=['2', '3'],
            description='Force USB 2.0 mode (2) to reduce high-frequency RFI, or use 3.0 (3).'
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

    # ------------------------------------------------
    # Common constants
    # ------------------------------------------------
    pkg = 'vehicle_control_unit'

    wheel_radius = 0.0891
    track_width = 0.305
    gear_ratio = 4.5

    ekf_local_params = _cfg(pkg, 'config', 'ekf_local.yaml')
    ekf_global_params = _cfg(pkg, 'config', 'ekf_global.yaml')
    navsat_params = _cfg(pkg, 'config', 'navsat_transform.yaml')
    nav2_params = _cfg(pkg, 'config', 'nav2_params.yaml')

    # Check for RealSense package installation
    rs_pkg_found = True
    try:
        rs_share = get_package_share_directory('realsense2_camera')
    except PackageNotFoundError:
        rs_pkg_found = False

    # Resolution string construction (using launch substitutions)
    rs_res_fps = PythonExpression(["'640x480x' + str(", args.realsense_fps, ")"])

    # =============================================================================
    # NVBlox, MAVROS, RC Bridge, VESC CAN, Differential Drive, ZED, Wheel Odom
    # =============================================================================
    actions += [
        # NVBlox container
        lu.component_container(NVBLOX_CONTAINER_NAME, log_level='warn'),

        # MAVROS (isolated launch context)
        GroupAction(
            [
                PushRosNamespace('mavros'),
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        os.path.join(_pkg_share(pkg), 'launch', 'mavros_apm.launch.py')
                    )
                ),
            ]
        ),

        # RC → /cmd_vel Bridge
        _node(
            package=pkg,
            executable='rc_to_cmd_vel',
            name='rc_to_cmd_vel',
            remaps=[
                ('/mavros/rc/in', '/mavros/mavros/rc/in'),
                ('/cmd_vel', '/cmd_vel'),
            ],
        ),

        # VESC CAN nodes
        _node(
            package=pkg,
            executable='vesc_can_node',
            name='left_vesc',
            params=[{'vesc_id': 117, 'vesc_name': 'left_vesc'}],
        ),
        _node(
            package=pkg,
            executable='vesc_can_node',
            name='right_vesc',
            params=[{'vesc_id': 39, 'vesc_name': 'right_vesc'}],
        ),

        # /cmd_vel → wheel RPM
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

        # ZED driver
        lu.include(
            pkg,
            'launch/sensors/zed_new.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'zed_camera_model': args.camera,
            },
        ),

        # RealSense Driver with EMI mitigation parameters
        GroupAction(
            condition=IfCondition(args.enable_realsense),
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource([os.path.join(rs_share, 'launch', 'rs_launch.py')]),
                    launch_arguments={
                        'pointcloud.enable': 'true',
                        'enable_depth': 'true',
                        'enable_color': 'true',
                        'depth_module.profile': rs_res_fps,
                        'rgb_camera.profile': rs_res_fps,
                        'align_depth.enable': 'true',
                        # Reduce infrared stream rate specifically
                        'depth_module.infra_fps': args.realsense_fps,
                        # Set USB mode (2 = USB 2.0, 3 = USB 3.0)
                        'usb_port_type': args.realsense_usb_port_type,
                    }.items(),
                ) if rs_pkg_found else LogInfo(msg="RealSense package not found.")
            ]
        ),

        # ---------------------------------------------------------------------
        # Lane Detection + Projection (optional)
        # ---------------------------------------------------------------------
        GroupAction(
            condition=IfCondition(args.enable_lane_detection),
            actions=[
                # (Optional) slight delay to let camera topics start publishing
                TimerAction(
                    period=2.0,
                    actions=[
                        _node(
                            package=pkg,
                            executable='lane_detector_node',
                            name='lane_detection',
                            params=[{
                                # if your node uses parameters to pick topics
                                'image_topic': '/zed/zed_node/rgb/image_rect_color',
                                # add detection params here (HSV, morphology, etc.)
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
                                'global_frame': 'odom',     # IMPORTANT: matches local_costmap global_frame
                                'resolution': 0.05,
                                'width_m': 6.0,
                                'height_m': 6.0,
                            }],
                        ),
                    ],
                ),
            ],
        ),

        # Wheel odom (publishes /wheel/odom; publish_tf=False)
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

        # NVBlox
        lu.include(
            'nvblox_examples_bringup',
            'launch/perception/nvblox.launch.py',
            launch_arguments={
                'container_name': NVBLOX_CONTAINER_NAME,
                'mode': NvbloxMode.static,
                'camera': args.camera,
            },
        ),

        # Nav2 LED indicator (blinks during NavigateToPose)
        _node(
            package=pkg,  # change if your node is in a different package
            executable='nav2_led_indicator',  # entry point name (console_scripts)
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

    # =============================================================================
    # LOCAL EKF always on: odom -> base_link
    # =============================================================================
    actions += [
        _node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_local',
            params=[ekf_local_params, {'use_sim_time': False}],
            remaps=[('/odometry/filtered', '/odometry/local')],
        ),
    ]

    # =============================================================================
    # INDOOR MODE: force map == odom via static TF (map->odom identity)
    # =============================================================================
    actions += [
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='map_to_odom_identity',
            output='screen',
            # x y z yaw pitch roll frame_id child_frame_id
            arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom'],
            condition=IfCondition(args.indoor),
        ),
    ]

    # =============================================================================
    # OUTDOOR MODE ONLY: GPS Gates + navsat_transform + GLOBAL EKF (map -> odom)
    # =============================================================================
    actions += [
        # GPS Hard-Gater (outdoor only)
        _node(
            package=pkg,
            executable='gps_hardgate_node',
            name='gps_gate',
            params=[{
                'mode': 'OUTDOOR',
                'fix_in': '/mavros/mavros/global_position/raw/fix',
                'fix_out': '/gps/fix_hardgated',
                'hard_var_thresh': 25.0,
                'max_speed_mps': 5.0,
                'odom_in': '/wheel/odom',
                'use_odom_speed_gate': True,
                'max_fix_age_s': 1.0,
                'fail_behavior': 'drop',
            }],
            condition=UnlessCondition(args.indoor),
        ),

        # GPS Soft-Gater (outdoor only)
        _node(
            package=pkg,
            executable='gps_softgate_node',
            name='gps_softgate',
            params=[{
                'fix_in': '/gps/fix_hardgated',
                'sats_in': '/mavros/mavros/global_position/raw/satellites',
                'fix_out': '/gps/fix_gated',
                'max_sats_age_s': 1.0,
                'max_fix_age_s': 1.0,
                'scale_smoothing_tau_s': 1.5,
            }],
            condition=UnlessCondition(args.indoor),
        ),

        # navsat_transform (outdoor only)
        _node(
            package='robot_localization',
            executable='navsat_transform_node',
            name='navsat_transform',
            params=[
                navsat_params,
                {'use_sim_time': False},
                {'gps_topic': '/gps/fix_gated'},
            ],
            remaps=[
                ('gps/fix', '/gps/fix_gated'),
                ('odometry/filtered', '/odometry/local'),
                ('odometry/gps', '/odometry/gps'),
                # ('imu/data', '/zed/zed_node/imu/data'),  # if needed
            ],
            condition=UnlessCondition(args.indoor),
        ),

        # EKF (GLOBAL): map -> odom (outdoor only)
        _node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_global',
            params=[ekf_global_params, {'use_sim_time': False}],
            remaps=[('/odometry/filtered', '/odometry/global')],
            condition=UnlessCondition(args.indoor),
        ),
    ]

    # =============================================================================
    # Nav2 (Delayed) + Goal Reach Checker + Auto Cancel + Visualization
    # =============================================================================
    goal_pose_topic_expr = PythonExpression([
        "'/odometry/local' if '", args.indoor, "' == 'true' else '/odometry/global'"
    ])

    actions += [
        TimerAction(
            period=10.0,
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
                        'pose_topic': goal_pose_topic_expr,
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

    # Status monitor (always-on)
    actions += [
        _node(
            package='vehicle_control_unit',
            executable='status_monitor_gateway',
            name='status_monitor_gateway',
        ),
    ]

    return LaunchDescription(actions)
