#include "lane_costmap_layer/lane_costmap_layer.hpp"

#include <algorithm>
#include <cmath>

#include "pluginlib/class_list_macros.hpp"
#include "nav2_costmap_2d/costmap_math.hpp"

namespace lane_costmap_layer
{

void LaneCostmapLayer::onInitialize()
{
  auto node = node_.lock();
  if (!node) {
    throw std::runtime_error("LaneCostmapLayer: node expired");
  }

  // Declare + get params
  declareParameter("enabled", rclcpp::ParameterValue(true));
  declareParameter("lane_topic", rclcpp::ParameterValue(std::string("/lane/occupancy_grid")));
  declareParameter("lane_threshold", rclcpp::ParameterValue(50));
  declareParameter("lane_cost", rclcpp::ParameterValue(int(nav2_costmap_2d::LETHAL_OBSTACLE)));
  declareParameter("use_maximum", rclcpp::ParameterValue(true));

  node->get_parameter(name_ + ".enabled", enabled_);
  node->get_parameter(name_ + ".lane_topic", lane_topic_);
  node->get_parameter(name_ + ".lane_threshold", lane_threshold_);
  node->get_parameter(name_ + ".lane_cost", lane_cost_);
  node->get_parameter(name_ + ".use_maximum", use_maximum_);

  enabled_ = std::clamp(enabled_, false, true);
  lane_threshold_ = std::clamp(lane_threshold_, 0, 100);
  lane_cost_ = std::clamp(lane_cost_, 0, 255);

  RCLCPP_INFO(
    node->get_logger(),
    "[%s] enabled=%s lane_topic=%s threshold=%d lane_cost=%d use_maximum=%s",
    name_.c_str(),
    enabled_ ? "true" : "false",
    lane_topic_.c_str(),
    lane_threshold_,
    lane_cost_,
    use_maximum_ ? "true" : "false");

  // Subscribe
  sub_ = node->create_subscription<nav_msgs::msg::OccupancyGrid>(
    lane_topic_, rclcpp::QoS(1).best_effort(),
    std::bind(&LaneCostmapLayer::laneMaskCallback, this, std::placeholders::_1));

  current_ = true;
}

void LaneCostmapLayer::laneMaskCallback(const nav_msgs::msg::OccupancyGrid::SharedPtr msg)
{
  std::lock_guard<std::mutex> lock(mutex_);
  lane_mask_ = msg;
  has_mask_ = true;

  // Cache world bounds of the mask
  const auto & info = msg->info;
  const double res = info.resolution;
  mask_min_x_ = info.origin.position.x;
  mask_min_y_ = info.origin.position.y;
  mask_max_x_ = mask_min_x_ + res * static_cast<double>(info.width);
  mask_max_y_ = mask_min_y_ + res * static_cast<double>(info.height);
}

void LaneCostmapLayer::updateBounds(
  double /*robot_x*/, double /*robot_y*/, double /*robot_yaw*/,
  double * min_x, double * min_y, double * max_x, double * max_y)
{
  if (!enabled_) {
    return;
  }

  std::lock_guard<std::mutex> lock(mutex_);
  if (!has_mask_ || !lane_mask_) {
    return;
  }

  // Expand bounds to include the lane mask bounds (simple + safe)
  *min_x = std::min(*min_x, mask_min_x_);
  *min_y = std::min(*min_y, mask_min_y_);
  *max_x = std::max(*max_x, mask_max_x_);
  *max_y = std::max(*max_y, mask_max_y_);
}

void LaneCostmapLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i, int min_j, int max_i, int max_j)
{
  if (!enabled_) {
    return;
  }

  nav_msgs::msg::OccupancyGrid::SharedPtr mask;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!has_mask_ || !lane_mask_) {
      return;
    }
    mask = lane_mask_;
  }

  const auto & info = mask->info;
  const double mask_res = info.resolution;
  const double mask_origin_x = info.origin.position.x;
  const double mask_origin_y = info.origin.position.y;

  // For each cell in the update window, map it into lane mask indices
  for (int j = min_j; j < max_j; ++j) {
    for (int i = min_i; i < max_i; ++i) {

      double wx, wy;
      master_grid.mapToWorld(i, j, wx, wy);

      // Convert world -> mask cell
      const int mx = static_cast<int>(std::floor((wx - mask_origin_x) / mask_res));
      const int my = static_cast<int>(std::floor((wy - mask_origin_y) / mask_res));

      if (mx < 0 || my < 0 || mx >= static_cast<int>(info.width) || my >= static_cast<int>(info.height)) {
        continue;
      }

      const int idx = my * static_cast<int>(info.width) + mx;
      const int8_t occ = mask->data[idx];

      if (occ < 0) {
        continue;  // unknown -> ignore
      }

      if (occ >= lane_threshold_) {
        const unsigned char old_cost = master_grid.getCost(i, j);
        const unsigned char new_cost = static_cast<unsigned char>(lane_cost_);

        if (use_maximum_) {
          master_grid.setCost(i, j, std::max(old_cost, new_cost));
        } else {
          master_grid.setCost(i, j, new_cost);
        }
      }
    }
  }
}

void LaneCostmapLayer::reset()
{
  // Nothing to clear: costs are re-applied every cycle based on mask
  current_ = true;
}

}  // namespace lane_costmap_layer

PLUGINLIB_EXPORT_CLASS(lane_costmap_layer::LaneCostmapLayer, nav2_costmap_2d::Layer)
