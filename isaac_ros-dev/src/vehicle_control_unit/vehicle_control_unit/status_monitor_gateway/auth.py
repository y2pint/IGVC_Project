import os
from typing import Optional

from fastapi import HTTPException

API_KEY = os.environ.get("DS_API_KEY", "").strip()


def require_key(x_api_key: Optional[str]) -> None:
    """
    Optional API key enforcement. If DS_API_KEY is unset/empty, auth is disabled.
    If set, callers must pass header X-API-Key with exact match.
    """
    if not API_KEY:
        return
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
