# 🏎️ IGVC Project

Autonomous ground vehicle platform for the **Intelligent Ground Vehicle Competition (IGVC)**.  
This project integrates NVIDIA’s **Isaac ROS** packages for perception and mapping with **Nav2** for motion planning and control.  
It is designed for **real-time navigation and obstacle avoidance** using stereo vision and GPU-accelerated mapping on **Jetson AGX Orin**.

---

## 📦 Repository Structure

This repository includes two **Isaac ROS forked repositories** as submodules to enable customization and reproducibility:

```
igvc_project/
│
├── isaac_ros_common/        # (Submodule) Forked from NVIDIA Isaac ROS Common
├── isaac_ros_nvblox/        # (Submodule) Forked from NVIDIA Isaac ROS NVBlox
├── src/                     # Custom packages (e.g., navigation, sensors, interfaces)
├── launch/                  # Launch files integrating mapping, perception, and Nav2
└── README.md
```

### Submodules
- **[isaac_ros_common](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common)**  
  Forked for environment setup, container build support, and integration with additional sensor drivers.

- **[isaac_ros_nvblox](https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nvblox)**  
  Forked for GPU-based 3D reconstruction and costmap generation for Nav2.

To clone with submodules:
```bash
git clone --recurse-submodules https://github.com/<your-org>/igvc_project.git
```

If already cloned without submodules:
```bash
git submodule update --init --recursive
```

---

## 🧠 System Overview

This system combines **perception**, **mapping**, and **navigation** components for real-time operation.

| Component | Description |
|------------|--------------|
| **Perception** | Stereo vision from **Intel RealSense D435** and **ZED 2i** cameras. |
| **Mapping** | **isaac_ros_nvblox** for voxel and costmap generation. |
| **Planning** | **Nav2 with MPPI (Model Predictive Path Integral)** controller for smooth and reactive motion. |
| **Localization** | Visual SLAM (Isaac ROS Visual SLAM or Realsense pose topic). |
| **Platform** | Jetson AGX Orin running Ubuntu 22.04 + ROS 2 Humble. |

---

## 🧰 Dependencies

| Category | Package / Hardware |
|-----------|--------------------|
| **Base OS** | Ubuntu 22.04 |
| **ROS 2** | Humble Hawksbill |
| **GPU Acceleration** | CUDA 12.6, TensorRT |
| **Isaac ROS Packages** | `isaac_ros_common`, `isaac_ros_nvblox`, `isaac_ros_visual_slam`, `isaac_ros_image_pipeline` |
| **Navigation** | Nav2 + MPPI plugin |
| **Sensors** | Intel RealSense (D435) and ZED 2i |
| **Optional** | NVBlox costmap plugin for Nav2 |

---

## ⚙️ Build Instructions

1. **Clone and setup submodules**
   ```bash
   git clone --recurse-submodules https://github.com/<your-org>/igvc_project.git
   cd igvc_project
   ```

2. **Install dependencies**
   ```bash
   sudo apt update
   rosdep update
   rosdep install --from-paths src --ignore-src -y
   ```

3. **Build workspace**
   ```bash
   source /opt/ros/humble/setup.bash
   colcon build --symlink-install
   ```

4. **Run in Docker (Recommended)**
   The project supports **Isaac ROS Docker** environment:
   ```bash
   ./scripts/run_dev.sh
   ```

---

## 🚀 Launch Examples

### Run Full Stack (Perception + Mapping + Nav2)
```bash
ros2 launch igvc_project igvc_full_stack.launch.py
```

### Run NVBlox Mapping Only
```bash
ros2 launch isaac_ros_nvblox nvblox_realsense.launch.py
```

### Run Navigation (MPPI)
```bash
ros2 launch nav2_bringup navigation_launch.py params_file:=config/nav2_mppi.yaml
```

---

## 🧭 Sensors

| Sensor | Topic | Usage |
|---------|--------|-------|
| **Intel RealSense D435** | `/camera/color/image_raw`, `/camera/depth/image_raw` | RGB-D mapping and SLAM |
| **ZED 2i** | `/zed/zed_node/stereo/image_left`, `/zed/zed_node/depth/depth_registered` | Depth perception and obstacle avoidance |

---

## 📚 Notes

- The repository assumes both **zed-ros2-wrapper** and **realsense2_camera** drivers are installed.  
- `nvblox::nav2::NvbloxCostmapLayer` is used in both local and global costmaps (replaces `obstacle_layer`).  
- MPPI parameters can be tuned for responsiveness and smoothness.

---

## 🧩 Future Work

- Integrate **lidar fusion** with NVBlox.
- Implement **visual-inertial odometry** for improved localization.
- Add **Braille display interface** for accessibility research (TAP-IN project).

---

## 🧑‍💻 Maintainers

- **Dr. Hyungjin Yoon**  
  Assistant Professor, Mechanical Engineering, Tennessee Technological University  
- IGVC Research Team, TTU Robotics Lab
