#pragma once

#include <mutex>
#include <string>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "nav2_costmap_2d/layer.hpp"
#include "nav2_costmap_2d/layered_costmap.hpp"
#include "nav2_costmap_2d/costmap_layer.hpp"
#include "nav2_costmap_2d/cost_values.hpp"

#include "nav_msgs/msg/occupancy_grid.hpp"

namespace lane_costmap_layer
{

class LaneCostmapLayer : public nav2_costmap_2d::Layer
{
public:
  LaneCostmapLayer() = default;
  ~LaneCostmapLayer() override = default;

  void onInitialize() override;

  void updateBounds(
    double robot_x, double robot_y, double robot_yaw,
    double * min_x, double * min_y, double * max_x, double * max_y) override;

  void updateCosts(
    nav2_costmap_2d::Costmap2D & master_grid,
    int min_i, int min_j, int max_i, int max_j) override;

  void reset() override;

  bool isClearable() override { return false; }

private:
  void laneMaskCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg);

  // Parameters
  std::string lane_topic_ = "/lane/occupancy_grid";
  int lane_threshold_ = 50;                  // occupancy >= threshold => lane
  int lane_cost_ = nav2_costmap_2d::LETHAL_OBSTACLE;   // cost to paint for lane
  bool use_maximum_ = true;                  // max(master, lane_cost) vs overwrite
  bool enabled_ = true;

  // Lane mask storage (latest)
  std::mutex mutex_;
  nav_msgs::msg::OccupancyGrid::SharedPtr lane_mask_;
  rclcpp::Subscription<nav_msgs::msg::OccupancyGrid>::SharedPtr sub_;
  bool has_mask_ = false;

  // Cached bounds from last mask (world coords)
  double mask_min_x_{0.0}, mask_min_y_{0.0}, mask_max_x_{0.0}, mask_max_y_{0.0};
};

}  // namespace lane_costmap_layer
