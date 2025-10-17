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

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        # Required for ROS 2 package indexing
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        # Include the package.xml
        ('share/' + package_name, ['package.xml']),
    ] + launch_files + config_files + rviz_files,
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
            

        ],
    },
)