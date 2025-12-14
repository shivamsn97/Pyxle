"""Helpers assembling the Starlette application for `pyxle dev`."""

from __future__ import annotations

import importlib.util
import inspect
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Iterable, Sequence

from starlette.applications import Starlette
from starlette.endpoints import HTTPEndpoint
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Router, WebSocketRoute
from starlette.staticfiles import StaticFiles

from pyxle.cli.logger import ConsoleLogger
from pyxle.ssr import (
    ComponentRenderer,
    build_page_navigation_response,
    build_page_response,
)

from .middleware import MiddlewareHookError, load_custom_middlewares
from .overlay import OverlayManager
from .proxy import ViteProxy
from .route_hooks import (
    DEFAULT_API_POLICIES,
    DEFAULT_PAGE_POLICIES,
    RouteContext,
    RouteHook,
    RouteHookError,
    load_route_hooks,
    wrap_with_route_hooks,
)
from .routes import ApiRoute, PageRoute, RouteTable
from .settings import DevServerSettings

_API_HTTP_METHODS: Sequence[str] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
_NAVIGATION_HEADER = "x-pyxle-navigation"


def _ensure_project_root_on_sys_path(project_root: Path) -> None:
    """Guarantee the project root is importable for custom middleware hooks."""

    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)


class ApiRouteError(RuntimeError):
    """Raised when an API module cannot be resolved to a valid handler."""


def build_api_router(
    routes: Iterable[ApiRoute],
    *,
    route_hooks: Sequence[RouteHook] | None = None,
) -> Router:
    """Create a Starlette ``Router`` populated from compiled API artifacts."""

    router = Router()
    hooks = list(route_hooks or [])

    for route in routes:
        module = _import_module(route.module_key, route.server_module_path)
        handler = _resolve_api_handler(module)
        context = RouteContext(
            target="api",
            path=route.path,
            source_relative_path=route.source_relative_path,
            source_absolute_path=route.source_absolute_path,
            module_key=route.module_key,
            content_hash=route.content_hash,
            allowed_methods=tuple(_API_HTTP_METHODS),
        )
        handler = wrap_with_route_hooks(handler, hooks=hooks, context=context)

        if inspect.isclass(handler) and issubclass(handler, HTTPEndpoint):
            router.add_route(route.path, handler)  # type: ignore[arg-type]
        else:
            router.add_route(route.path, handler, methods=list(_API_HTTP_METHODS))  # type: ignore[arg-type]

    return router


def _import_module(module_key: str, module_path: Path) -> ModuleType:
    """Import a compiled module located at ``module_path`` under ``module_key``."""

    if module_key in sys.modules:
        del sys.modules[module_key]

    spec = importlib.util.spec_from_file_location(module_key, module_path)
    if spec is None or spec.loader is None:
        raise ApiRouteError(f"Unable to load API module at {module_path!s}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module

    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - bubbled up for clarity
        raise ApiRouteError(f"Failed to import API module {module_key}: {exc}") from exc

    return module


def _resolve_api_handler(module: ModuleType):
    """Return the callable or endpoint class responsible for handling requests."""

    if hasattr(module, "endpoint"):
        handler = getattr(module, "endpoint")
        if callable(handler):
            return handler
        raise ApiRouteError(
            f"API module {module.__name__} exposes 'endpoint' but it is not callable"
        )

    candidates = [
        attribute
        for attribute in module.__dict__.values()
        if inspect.isclass(attribute)
        and issubclass(attribute, HTTPEndpoint)
        and attribute is not HTTPEndpoint
    ]

    if candidates:
        return candidates[0]

    raise ApiRouteError(
        f"API module {module.__name__} must define an 'endpoint' callable or HTTPEndpoint subclass"
    )


def build_page_router(
    routes: Iterable[PageRoute],
    *,
    settings: DevServerSettings,
    renderer: ComponentRenderer,
    overlay: OverlayManager | None = None,
    route_hooks: Sequence[RouteHook] | None = None,
) -> Router:
    """Create a router serving compiled pages via server-side rendering."""

    router = Router()
    hooks = list(route_hooks or [])

    for route in routes:
        handler = _make_page_handler(
            route,
            settings=settings,
            renderer=renderer,
            overlay=overlay,
        )
        context = RouteContext(
            target="page",
            path=route.path,
            source_relative_path=route.source_relative_path,
            source_absolute_path=route.source_absolute_path,
            module_key=route.module_key,
            content_hash=route.content_hash,
            has_loader=route.has_loader,
            head_elements=route.head_elements,
            allowed_methods=("GET",),
        )
        handler = wrap_with_route_hooks(handler, hooks=hooks, context=context)
        router.add_route(route.path, handler, methods=["GET"])

    return router


def _make_page_handler(
    route: PageRoute,
    *,
    settings: DevServerSettings,
    renderer: ComponentRenderer,
    overlay: OverlayManager | None,
):
    async def handler(request: Request):  # pragma: no cover - thin wrapper
        wants_navigation_payload = request.headers.get(_NAVIGATION_HEADER) == "1"
        if wants_navigation_payload:
            return await build_page_navigation_response(
                request=request,
                settings=settings,
                page=route,
                renderer=renderer,
                overlay=overlay,
            )

        return await build_page_response(
            request=request,
            settings=settings,
            page=route,
            renderer=renderer,
            overlay=overlay,
        )

    handler.__name__ = f"page_{route.module_key.replace('.', '_')}"
    return handler


def build_static_files_mount(settings: DevServerSettings) -> Mount:
    """Return a Starlette ``Mount`` serving the project's ``public/`` directory."""

    static_app = StaticFiles(directory=settings.public_dir, check_dir=False)
    return Mount("/", app=static_app, name="pyxle-public")



def create_starlette_app(
    settings: DevServerSettings,
    routes: RouteTable,
    *,
    logger: ConsoleLogger | None = None,
) -> Starlette:
    """Assemble a Starlette application exposing API, page, and static routes."""

    console_logger = logger or ConsoleLogger()

    settings = _maybe_attach_manifest(settings, console_logger)

    _ensure_project_root_on_sys_path(settings.project_root)

    vite_proxy = ViteProxy(settings, logger=console_logger)
    renderer = ComponentRenderer()
    overlay = OverlayManager(logger=console_logger)
    try:
        user_middleware = load_custom_middlewares(settings.custom_middlewares)
    except MiddlewareHookError as exc:
        console_logger.error(str(exc))
        raise

    try:
        page_route_hooks = load_route_hooks(settings.page_route_hooks)
        api_route_hooks = load_route_hooks(settings.api_route_hooks)
    except RouteHookError as exc:
        console_logger.error(str(exc))
        raise

    class _ViteProxyMiddleware(BaseHTTPMiddleware):
        def __init__(self, app):
            super().__init__(app)
            self._proxy = vite_proxy

        async def dispatch(self, request: Request, call_next):  # pragma: no cover - middleware wrapper
            if self._proxy.should_proxy(request):
                return await self._proxy.handle(request)
            return await call_next(request)

    @asynccontextmanager
    async def lifespan(app: Starlette):  # pragma: no cover - lifecycle orchestration
        try:
            yield
        finally:
            await vite_proxy.close()

    middleware_stack = [*user_middleware, Middleware(_ViteProxyMiddleware)]

    app = Starlette(
        debug=settings.debug,
        middleware=middleware_stack,
        lifespan=lifespan,
    )

    app.state.pyxle_started_at = time.time()
    app.state.pyxle_ready = False

    api_router = build_api_router(
        routes.apis,
        route_hooks=[*DEFAULT_API_POLICIES, *api_route_hooks],
    )
    page_router = build_page_router(
        routes.pages,
        settings=settings,
        renderer=renderer,
        overlay=overlay,
        route_hooks=[*DEFAULT_PAGE_POLICIES, *page_route_hooks],
    )
    static_mount = build_static_files_mount(settings)

    app.router.routes.extend(api_router.routes)
    app.router.routes.extend(page_router.routes)
    app.router.routes.append(
        WebSocketRoute("/__pyxle__/overlay", overlay.websocket_endpoint)
    )
    app.router.add_route("/healthz", _healthz_endpoint, methods=["GET"])
    app.router.add_route("/readyz", _readyz_endpoint, methods=["GET"])
    app.router.routes.append(static_mount)

    app.state.vite_proxy = vite_proxy
    app.state.ssr_renderer = renderer
    app.state.overlay = overlay

    return app


def _maybe_attach_manifest(settings: DevServerSettings, logger: ConsoleLogger) -> DevServerSettings:
    if settings.debug or settings.page_manifest is not None:
        return settings

    manifest_path = settings.project_root / "dist" / "page-manifest.json"
    if not manifest_path.exists():
        logger.warning(
            f"Production mode enabled but page-manifest.json not found at {manifest_path}"
        )
        return settings

    from pyxle.build.manifest import load_manifest

    try:
        manifest_data = load_manifest(manifest_path)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Failed to load page-manifest.json: {exc}")
        return settings

    return replace(settings, page_manifest=manifest_data)


def _health_payload(app: Starlette) -> dict[str, object]:
    started_at = getattr(app.state, "pyxle_started_at", None)
    ready = bool(getattr(app.state, "pyxle_ready", False))
    uptime = 0.0
    if isinstance(started_at, (int, float)):
        uptime = max(0.0, time.time() - float(started_at))

    return {
        "status": "ok",
        "ready": ready,
        "uptime": uptime,
    }


async def _healthz_endpoint(request: Request) -> JSONResponse:
    payload = _health_payload(request.app)
    return JSONResponse(payload)


async def _readyz_endpoint(request: Request) -> JSONResponse:
    payload = _health_payload(request.app)
    status_code = 200 if payload["ready"] else 503
    return JSONResponse(payload, status_code=status_code)


__all__ = [
    "build_api_router",
    "build_page_router",
    "build_static_files_mount",
    "create_starlette_app",
    "ApiRouteError",
]
