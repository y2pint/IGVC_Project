from __future__ import annotations

import os
import threading
from typing import Optional

import rclpy
import uvicorn

from .bridge_node import StatusBridge, spin_ros
from .webapp import create_app


_bridge: Optional[StatusBridge] = None


def _get_bridge() -> Optional[StatusBridge]:
    return _bridge


def main() -> None:
    global _bridge

    rclpy.init()
    _bridge = StatusBridge()

    t = threading.Thread(target=spin_ros, args=(_bridge, 4), daemon=True)
    t.start()

    app = create_app(_get_bridge)

    host = os.environ.get("DS_HOST", "0.0.0.0")
    port = int(os.environ.get("DS_PORT", "8081"))
    uvicorn.run(app, host=host, port=port, log_level="info")

    rclpy.shutdown()


if __name__ == "__main__":
    main()