from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PyxleTelemetryMiddleware(BaseHTTPMiddleware):
    """Annotates requests with timing + metadata for the starter template."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = uuid.uuid4().hex[:8]
        started_at = datetime.now(tz=timezone.utc)

        request.state.pyxle_demo = {
            "requestId": request_id,
            "issuedAt": started_at.isoformat(),
            "path": request.url.path,
        }

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers.setdefault("x-pyxle-demo", f"{elapsed_ms:.1f}ms")
        response.headers.setdefault("x-pyxle-request", request_id)
        return response
