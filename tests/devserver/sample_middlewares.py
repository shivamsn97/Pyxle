from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class HeaderCaptureMiddleware(BaseHTTPMiddleware):
    """Test middleware that echoes a header back to the client."""

    async def dispatch(self, request: Request, call_next):
        value = request.headers.get("x-auth-token", "")
        response = await call_next(request)
        if value:
            response.headers["x-auth-token"] = value
        return response


def create_rate_limit_middleware() -> Middleware:
    class _RateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request.state.rate_limit_checked = True
            response = await call_next(request)
            response.headers["x-rate-limit"] = "ok"
            return response

    return Middleware(_RateLimitMiddleware)


def invalid_factory():
    return "not-a-middleware"


class ConfigurableSuffixMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, suffix: str = ""):
        super().__init__(app)
        self._suffix = suffix

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if self._suffix:
            response.headers["x-config-suffix"] = self._suffix
        return response


def tuple_middleware_factory():
    return (ConfigurableSuffixMiddleware, {"suffix": "beta"})


async def record_route_hook(context, request, call_next):
    request.state.recorded_route = context.path
    return await call_next(request)


def build_target_hook():
    async def _hook(context, request, call_next):
        markers = getattr(request.state, "route_targets", [])
        markers = list(markers)
        markers.append(context.target)
        request.state.route_targets = markers
        return await call_next(request)

    return _hook


def invalid_route_hook_factory():
    return "not-an-async-hook"
