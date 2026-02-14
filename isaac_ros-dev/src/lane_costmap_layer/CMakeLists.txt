cmake_minimum_required(VERSION 3.8)
project(lane_costmap_layer)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(nav2_util REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(pluginlib REQUIRED)

include_directories(include)

add_library(lane_costmap_layer SHARED
  src/lane_costmap_layer.cpp
)

ament_target_dependencies(lane_costmap_layer
  rclcpp
  nav2_costmap_2d
  nav2_util
  nav_msgs
  pluginlib
)

pluginlib_export_plugin_description_file(nav2_costmap_2d plugin.xml)

install(TARGETS lane_costmap_layer
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include/
)

install(FILES plugin.xml
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
