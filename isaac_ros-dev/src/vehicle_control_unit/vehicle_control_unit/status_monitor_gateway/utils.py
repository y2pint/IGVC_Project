from __future__ import annotations

import time
from typing import Tuple


def now_unix() -> float:
    return time.time()


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def yaw_from_quat(q) -> float:
    """
    q has fields x,y,z,w (geometry_msgs/Quaternion)
    """
    import math
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def quat_from_yaw(yaw: float) -> Tuple[float, float, float, float]:
    import math
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (0.0, 0.0, sy, cy)
