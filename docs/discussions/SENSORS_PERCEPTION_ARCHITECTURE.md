# Sensor & Perception Architecture for IGVC

**ZED2i + RealSense + NVBlox + Nav2**

This document summarizes the design decisions, rationale, and implementation strategy for using **ZED2i** and **Intel RealSense (D435/D435i)** together in an IGVC ground robot stack.

The goal is to achieve:

* **Robust outdoor localization**
* **Reliable lane detection**
* **Low-latency near-field obstacle avoidance**
* **Efficient computation on Jetson Orin**

---

## 1. High-Level Sensor Roles (Final Decision)

| Function                       | Sensor                         | Rationale                                              |
| ------------------------------ | ------------------------------ | ------------------------------------------------------ |
| Visual localization / odometry | **ZED2i**                      | Stereo + tightly coupled IMU (VI-SLAM), outdoor-robust |
| 3D mapping (TSDF/ESDF)         | **ZED2i → NVBlox**             | Consistent depth + pose, avoids noisy fusion           |
| Lane detection (RGB)           | **ZED2i RGB**                  | Better dynamic range, outdoor image quality            |
| Near-field obstacle avoidance  | **RealSense D435 / D435i**     | Clean short-range depth                                |
| Nav2 local obstacles           | **RealSense → LaserScan (2D)** | Fast, stable, LiDAR-like behavior                      |

This division avoids overlapping responsibilities and minimizes failure modes.

---

## 2. Why ZED2i Is the Localization Backbone

### 2.1 Visual–Inertial SLAM (VI-SLAM)

* ZED2i tightly fuses:

  * Stereo RGB cameras
  * Onboard IMU (gyro + accelerometer)
* IMU provides:

  * High-rate orientation prediction
  * Stability during fast turns and brief visual degradation

Result: **more stable odometry than visual-only pipelines**, especially outdoors.

### 2.2 Stereo Scale Observability

* Fixed stereo baseline gives **metric scale directly**
* No dependence on wheel odometry for scale
* Robust under wheel slip (common in IGVC terrain)

### 2.3 Outdoor-Optimized Imaging

* Better handling of:

  * Sun/shadow transitions
  * Grass, asphalt, concrete
  * Long-range visual features

**Conclusion:** ZED2i localization is superior and should own `odom → base_link`.

---

## 3. Why RealSense Is *Not* Used for Localization

Even though the D435i includes an IMU:

* There is no mature, tightly integrated VI-SLAM stack comparable to ZED’s
* Using it would require additional EKF/VIO tuning with limited benefit

Given that ZED2i already provides strong VI-SLAM:

* **RealSense IMU is unused**
* RealSense is treated as a **pure depth sensor**

---

## 4. NVBlox: Use ZED Only

### 4.1 Why NVBlox Favors ZED Depth

* NVBlox integrates depth over time (TSDF/ESDF)
* It assumes:

  * Low-variance depth
  * Consistent noise statistics

ZED depth:

* Passive stereo
* Consistent noise structure
* Aligned with ZED odometry

RealSense depth:

* Active IR stereo
* Can degrade in sunlight
* Produces artifacts that “fatten” obstacles in voxel maps

**Decision:**
➡ **Feed NVBlox with ZED depth only**

---

## 5. RealSense as a “2D LiDAR” (Option 1)

### 5.1 Why Depth → LaserScan Is Ideal

* Nav2 local planners only need **where obstacles are**, not full 3D geometry
* A LaserScan is:

  * Cheap to compute
  * Easy to fuse
  * Extremely stable for MPPI/DWB

### 5.2 Depth Image vs Point Cloud (Cost Comparison)

| Approach              | Data Processed     | Relative Cost    |
| --------------------- | ------------------ | ---------------- |
| Full point cloud      | ~300k points/frame | High             |
| Depth image (10 rows) | ~6k pixels/frame   | **~50× cheaper** |

Filtering in depth space first is **mathematically equivalent** and vastly cheaper.

---

## 6. Interpreting `image_rect_raw` with `camera_info`

The RealSense depth image is **rectified**, meaning a simple pinhole model applies.

From `camera_info`:

[
K =
\begin{bmatrix}
f_x & 0 & c_x \
0 & f_y & c_y \
0 & 0 & 1
\end{bmatrix}
]

Pixel → 3D (camera frame):

[
X = (u - c_x)\frac{Z}{f_x}, \quad
Y = (v - c_y)\frac{Z}{f_y}, \quad
Z = Z
]

This is exactly what `depthimage_to_laserscan` uses internally.

---

## 7. Why Using Depth Directly Is the Correct Optimization

If your logic ultimately filters by XYZ:

* **Filter first in depth space**
* Only project the small subset you care about

Row selection in the depth image is equivalent to:

* Height filtering in 3D
* A horizontal LiDAR scan plane

This is not a hack—it is **proper computational ordering**.

---

## 8. RealSense D435 vs D435i

| Feature           | D435     | D435i    |
| ----------------- | -------- | -------- |
| Depth quality     | Same     | Same     |
| RGB               | Same     | Same     |
| IMU               | No       | Yes      |
| Depth → LaserScan | **Same** | **Same** |

For obstacle detection:

* **D435 = D435i**
* IMU on D435i is unused in this architecture

---

## 9. NVBlox RealSense Bringup (`rs_splitter`)

* The NVBlox RealSense example bringup and `rs_splitter`:

  * Subscribe only to depth + camera_info
  * Do **not** depend on IMU
* Therefore:

  * **Works identically for D435 and D435i**

You may keep the splitter if you want multiple consumers of the depth stream, even if RealSense is not used by NVBlox.

---

## 10. Camera Mounting Recommendations

### ZED2i

* Height: **~1.2–1.4 m (4.0–4.6 ft)**
* Pitch: **10–20° downward**
* Purpose:

  * Lane detection
  * VIO stability
  * Long look-ahead

### RealSense

* Height: **0.3–0.6 m (1–2 ft)**
* Pitch: **5–15° downward**
* Purpose:

  * Near-field obstacles
  * Pseudo-LiDAR scan

---

## 11. Final Architecture Summary

```
ZED2i (RGB + IMU)
 ├─ Visual–Inertial SLAM → odom
 ├─ RGB → lane detection
 └─ Depth → NVBlox → global/local costmaps

RealSense D435 / D435i
 └─ Depth image
     → narrow row band
     → LaserScan
     → Nav2 local obstacle layer
```

This architecture:

* Minimizes compute
* Maximizes robustness
* Matches how high-performing IGVC teams converge in practice

---

## 12. Key Takeaway

> **ZED2i owns localization and mapping.
> RealSense provides fast, cheap, near-field obstacles.
> Depth-first filtering is the right computational strategy.**

This design is technically sound, efficient, and competition-ready.

---

If you want next:

* A **launch file template** for RealSense → LaserScan
* A **diagram figure** for the README
* Or a **minimal custom depth-to-scan node** instead of a generic package

just tell me.
