from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import Any, Dict

from starlette.requests import Request
from starlette.responses import JSONResponse

from pyxle import __version__

_START_TIME = datetime.now(tz=timezone.utc)


def _format_uptime(delta_seconds: float) -> str:
    total_seconds = int(delta_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_pulse_payload() -> Dict[str, Any]:
    """Return diagnostic data shared by the initial template and API."""

    now = datetime.now(tz=timezone.utc)
    uptime = (now - _START_TIME).total_seconds()

    return {
        "timestamp": now.isoformat(),
        "uptime": _format_uptime(uptime),
        "pyxleVersion": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
        "pid": os.getpid(),
        "features": [
            "Single-file loader + component authoring",
            "Starlette-compatible API routes",
            "Project-scoped middleware via pyxle.config.json",
            "Vite-powered client bundling",
        ],
    }


def _request_details(request: Request) -> Dict[str, Any]:
    client = request.client[0] if request.client else "unknown"
    return {
        "path": request.url.path,
        "client": client,
        "userAgent": request.headers.get("user-agent", "unknown"),
        "method": request.method,
    }


async def endpoint(request: Request) -> JSONResponse:
    payload = build_pulse_payload()
    payload["request"] = _request_details(request)
    return JSONResponse(payload)
