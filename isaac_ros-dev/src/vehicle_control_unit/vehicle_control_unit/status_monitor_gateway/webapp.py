from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse

from .auth import require_key
from .dashboard_html import dashboard_html
from .bridge_node import StatusBridge


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
        return bridge.snapshot()

    @app.get("/healthz")
    def healthz(x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        s = bridge.snapshot()
        return {"ok": bool(s["health"]["ok"]), "reasons": s["health"]["reasons"]}

    @app.get("/costmap/{which}")
    def costmap(which: str, x_api_key: Optional[str] = Header(default=None)):
        require_key(x_api_key)
        bridge: StatusBridge | None = get_bridge()
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge not ready")
        if which not in ("local", "global"):
            raise HTTPException(status_code=400, detail="which must be 'local' or 'global'")
        return bridge.costmap_snapshot(which)

    return app
