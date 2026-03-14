from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, FileResponse, Response, PlainTextResponse
from pydantic import BaseModel

from .auth import require_key
from .dashboard_html import dashboard_html
from .bridge_node import StatusBridge

# Directory that holds pre-downloaded tiles
_DEFAULT_TILES_DIR = Path(__file__).parent.parent / "tiles"
TILES_DIR = Path(os.environ.get("DS_TILES_DIR", str(_DEFAULT_TILES_DIR)))


class WaypointItem(BaseModel):
    lat: float
    lon: float
    name: str = ''


def create_app(get_bridge) -> FastAPI:
    """
    get_bridge: callable returning current StatusBridge | None
    """
    app = FastAPI(title="IGVC Status Monitor", version="0.5.0")

    @app.get("/", response_class=HTMLResponse)
    def root(x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        return dashboard_html(x_api_key)

    @app.get("/status")
    def status(x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        try:
            return bridge.snapshot()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ROS bridge unavailable: {e}")

    @app.get("/healthz")
    def healthz(x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        try:
            s = bridge.snapshot()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ROS bridge unavailable: {e}")
        return {"ok": bool(s["health"]["ok"]), "reasons": s["health"]["reasons"]}

    @app.get("/costmap/{which}")
    def costmap(which: str, x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        if which not in ("local", "global"):
            raise HTTPException(status_code=400, detail="which must be 'local' or 'global'")
        try:
            return bridge.costmap_snapshot(which)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ROS bridge unavailable: {e}")

    @app.post("/mission/command/{cmd}")
    def mission_command(cmd: str, x_api_key: Optional[str] = Header(default=None)):
        """
        Mission control commands:
          start  → reset_waypoints (index→0) + publish nav_enabled=True
          stop   → publish nav_enabled=False (carrot_to_nav2 cancels active Nav2 goal)
          cancel → publish cancel_nav_goal=True (one-shot cancel without disabling)
          next   → /mission/next_waypoint service call
          reset  → /mission/reset_origin_here service call
        """
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")

        try:
            if cmd == "start":
                # 1. Reset waypoint index to 0
                svc_result = bridge.call_trigger_service("/mission/reset_waypoints")
                if not svc_result["success"]:
                    return svc_result
                # 2. Enable navigation (carrot_to_nav2 will start forwarding goals)
                bridge.publish_nav_enabled(True)
                return {"success": True, "message": "Mission started: waypoints reset, navigation enabled"}

            elif cmd == "stop":
                bridge.publish_nav_enabled(False)
                return {"success": True, "message": "Navigation disabled — robot will stop after current goal cancels"}

            elif cmd == "cancel":
                bridge.publish_cancel()
                return {"success": True, "message": "Cancel signal sent to Nav2"}

            elif cmd == "next":
                return bridge.call_trigger_service("/mission/next_waypoint")

            elif cmd == "reset":
                return bridge.call_trigger_service("/mission/reset_origin_here")

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown command '{cmd}'. Use: start, stop, cancel, next, reset"
                )
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.post("/mission/waypoints")
    def set_waypoints(
        waypoints: List[WaypointItem],
        x_api_key: Optional[str] = Header(default=None)
    ):
        """
        Push a new waypoint list to the waypoint manager via the ROS2 topic.
        The manager will recompute XY and reset the mission index to 0.
        """
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        try:
            payload = json.dumps([
                {"lat": w.lat, "lon": w.lon, "name": w.name or f"wp_{i}"}
                for i, w in enumerate(waypoints)
            ])
            bridge.publish_waypoints_latlon(payload)
            return {"success": True, "message": f"Published {len(waypoints)} waypoints"}
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.post("/mission/save_waypoints")
    def save_waypoints_to_file(x_api_key: Optional[str] = Header(default=None)):
        """
        Tell the waypoint manager to save the current in-memory list back to its YAML file.
        Calls the /mission/save_waypoints ROS2 Trigger service.
        """
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        try:
            return bridge.call_trigger_service("/mission/save_waypoints")
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.get("/mission/export_waypoints")
    def export_waypoints(x_api_key: Optional[str] = Header(default=None)):
        """
        Download the current in-memory waypoint list as a YAML file.
        """
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        try:
            yaml_str = bridge.get_waypoints_as_yaml()
            return PlainTextResponse(
                content=yaml_str,
                media_type="application/x-yaml",
                headers={"Content-Disposition": "attachment; filename=waypoints.yaml"}
            )
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.get("/tiles/{z}/{x}/{y}.png")
    def tile(z: int, x: int, y: int):
        """Serve a pre-downloaded OSM tile from the local tiles directory.

        Download tiles first with:
            python -m status_monitor_gateway.download_tiles \\
                --lat <lat> --lon <lon> --radius-m 800 --min-zoom 14 --max-zoom 19
        """
        tile_path = TILES_DIR / str(z) / str(x) / f"{y}.png"
        if not tile_path.exists():
            # Return a 1x1 transparent PNG so Leaflet doesn't show broken images
            _transparent = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            return Response(content=_transparent, media_type="image/png", status_code=200)
        return FileResponse(str(tile_path), media_type="image/png")

    return app