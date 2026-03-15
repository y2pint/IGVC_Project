from setuptools import setup, find_packages
from glob import glob
import os

package_name = "vehicle_control_unit"


def _collect_share_files(root_dir: str, patterns: list[str]):
    """
    Collect files matching patterns under root_dir and install them under:
      share/<package_name>/<relative_dir>
    """
    out = []
    for pat in patterns:
        for f in glob(os.path.join(root_dir, "**", pat), recursive=True):
            if os.path.isfile(f):
                out.append((os.path.join("share", package_name, os.path.dirname(f)), [f]))
    return out


# Collect launch/config/rviz/urdf files recursively
launch_files = _collect_share_files("launch", ["*.py"])
config_files = _collect_share_files("config", ["*.yaml", "*.yml"])
rviz_files = _collect_share_files("config", ["*.rviz"])
urdf_files = _collect_share_files("urdf", ["*"])  # includes xacro/urdf/meshes/etc.

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(where=".", include=[package_name, f"{package_name}.*"], exclude=["test"]),
    package_dir={"": "."},
    data_files=[
        # Required for ROS 2 package indexing
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        # Include the package.xml
        (f"share/{package_name}", ["package.xml"]),
    ]
    + launch_files
    + config_files
    + rviz_files
    + urdf_files,
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="Your Name",
    maintainer_email="your@email.com",
    description="Python-based ROS 2 nodes for vehicle control and monitoring",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "rc_bridge_node = vehicle_control_unit.rc_bridge_node:main",
            "vesc_bridge_node = vehicle_control_unit.vesc_bridge_node:main",
            "odom_relay_node = vehicle_control_unit.odom_relay_node:main",
            "manual_control_node = vehicle_control_unit.manual_control_node:main",
            "cmd_vel_node = vehicle_control_unit.cmd_vel_node:main",

            # RC (/mavros/rc/in) → /cmd_vel
            "rc_to_cmd_vel = vehicle_control_unit.rc_to_cmd_vel:main",

            # VESC Can
            "vesc_can_node = vehicle_control_unit.vesc_can_node:main",

            # Wheel Odom
            "wheel_odom_node = vehicle_control_unit.vesc_erpm_wheel_odom:main",

            # Status monitor gateway (ROS2 + FastAPI)
            # Requires: vehicle_control_unit/status_monitor_gateway/main.py with def main()
            "status_monitor_gateway = vehicle_control_unit.status_monitor_gateway.main:main",

            # Goal Reach Checker
            "goal_reach_checker_node = vehicle_control_unit.goal_reach_checker_node:main",

            # NAV2 GOAL CANCEL
            "nav2_goal_cancel_node = vehicle_control_unit.nav2_goal_cancel_node:main",

            # GPS Soft Gate
            "gps_softgate_node = vehicle_control_unit.gps_softgate_node:main",

            # GPS Hard Gate
            "gps_hardgate_node = vehicle_control_unit.gps_hardgate_node:main",

            # NAV2 LED INDICATOR
            'nav2_led_indicator = vehicle_control_unit.nav2_led_indicator_node:main',

            # LANE DETECTOR
            'lane_detector_node = vehicle_control_unit.lane_detector_node:main',

            # LANE PROJECTION
            'lane_projection_node = vehicle_control_unit.lane_projection_node:main',

            # LANE FOLLOW
            'lane_follow_nav2_node = vehicle_control_unit.lane_follow_nav2_node:main',

            # GPS PROJECTION
            'gps_projection_node = vehicle_control_unit.gps_projection_node:main',

            # GLOBAL EKF
            'global_ekf_node = vehicle_control_unit.global_ekf_node:main',

            # MISSION GLOBAL FRAME NODE
            'mission_global_frame_node = vehicle_control_unit.mission_global_frame_node:main',

            # MISSION WAYPOINT MANAGER NODE
            'mission_waypoint_manager_node = vehicle_control_unit.mission_waypoint_manager_node:main',

            # MISSION PLOTTER NODE
            'mission_plotter_node = vehicle_control_unit.mission_plotter_node:main',

            # CARROT TARGET NODE
            'carrot_target_node = vehicle_control_unit.carrot_target_node:main',

            # carrot_to_nav2_action_node
            'carrot_to_nav2_action_node = vehicle_control_unit.carrot_to_nav2_action_node:main',

            # map_odom_broadcaster_node
            'map_odom_broadcaster = vehicle_control_unit.map_odom_broadcaster:main',

            #compass_heading_publisher
            'compass_heading_publisher = vehicle_control_unit.compass_heading_publisher:main',
            
        ],
    },
)
