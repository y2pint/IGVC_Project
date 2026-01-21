from setuptools import setup
from glob import glob
import os

package_name = 'vehicle_control_unit'

# Collect launch files recursively
launch_files = [
    (os.path.join('share', package_name, os.path.dirname(f)), [f])
    for f in glob(os.path.join('launch', '**', '*.py'), recursive=True)
]

# Collect YAML config files recursively
config_files = [
    (os.path.join('share', package_name, os.path.dirname(f)), [f])
    for f in glob(os.path.join('config', '**', '*.yaml'), recursive=True)
]

# Collect RViz config files recursively
rviz_files = [
    (os.path.join('share', package_name, os.path.dirname(f)), [f])
    for f in glob(os.path.join('config', '**', '*.rviz'), recursive=True)
]

# Collect URDF / Xacro files recursively
urdf_files = [
    (os.path.join('share', package_name, os.path.dirname(f)), [f])
    for f in glob(os.path.join('urdf', '**', '*'), recursive=True)
    if os.path.isfile(f)
]

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        # Required for ROS 2 package indexing
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        # Include the package.xml
        ('share/' + package_name, ['package.xml']),
    ] + launch_files + config_files + rviz_files + urdf_files,
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='Your Name',
    maintainer_email='your@email.com',
    description='Python-based ROS 2 node example with launch file and visualization support',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'rc_bridge_node = vehicle_control_unit.rc_bridge_node:main',
            'vesc_bridge_node = vehicle_control_unit.vesc_bridge_node:main',
            'odom_relay_node = vehicle_control_unit.odom_relay_node:main',
            'manual_control_node = vehicle_control_unit.manual_control_node:main',
            'cmd_vel_node = vehicle_control_unit.cmd_vel_node:main',

            # NEW: RC (/mavros/rc/in) → /cmd_vel
            'rc_to_cmd_vel = vehicle_control_unit.rc_to_cmd_vel:main',

            # NEW: VESC Can
            'vesc_can_node = vehicle_control_unit.vesc_can_node:main',

            # NEW: Wheel Odom
            'wheel_odom_node = vehicle_control_unit.vesc_erpm_wheel_odom:main',

            # NEW: Wheel Odom
            'status_monitor_gateway = vehicle_control_unit.status_monitor_gateway:main',

            # NEW: Goal Reach Checker
            'goal_reach_checker_node = vehicle_control_unit.goal_reach_checker_node:main',

            # NEW: NAV2 GOAL CANCEL
            'nav2_goal_cancel_node = vehicle_control_unit.nav2_goal_cancel_node:main',

        ],
    },
)