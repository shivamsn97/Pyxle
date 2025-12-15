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
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Router, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

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


class HttpOnlyStaticFiles(StaticFiles):
    """Static files app that gracefully rejects non-HTTP scopes."""

    def __init__(self, *args, close_code: int = 4404, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._close_code = close_code

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type != "http":
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": self._close_code})
                return
            return
        await super().__call__(scope, receive, send)


class StaticAssetsMiddleware:
    """Serve client + public assets ahead of dynamic catch-all routes."""

    def __init__(
        self,
        app,
        *,
        public_directory: Path | None = None,
        client_directory: Path | None = None,
    ) -> None:
        self.app = app
        self._public_static = (
            HttpOnlyStaticFiles(directory=public_directory, check_dir=False)
            if public_directory is not None
            else None
        )
        self._client_static = (
            HttpOnlyStaticFiles(directory=client_directory, check_dir=False)
            if client_directory is not None
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if self._client_static is not None and path.startswith("/client"):
            if await self._try_static(
                self._client_static,
                scope,
                receive,
                send,
                prefix="/client",
            ):
                return

        if self._public_static is not None and not path.startswith("/client"):
            if await self._try_static(self._public_static, scope, receive, send):
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _try_static(
        static_app: HttpOnlyStaticFiles,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        prefix: str = "",
    ) -> bool:
        selected_scope = scope
        if prefix:
            path = scope.get("path", "")
            if not path.startswith(prefix):
                return False
            stripped = path[len(prefix) :] or "/"
            candidate = dict(scope)
            candidate["path"] = stripped
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, (bytes, bytearray)):
                candidate["raw_path"] = stripped.encode("utf-8")
            selected_scope = candidate
        try:
            await static_app(selected_scope, receive, send)
            return True
        except HTTPException as exc:
            if exc.status_code == 404:
                return False
            raise


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


def build_static_files_mount(
    settings: DevServerSettings,
    *,
    directory: Path | None = None,
    mount_path: str = "/",
) -> Mount:
    """Return a Starlette ``Mount`` serving static assets."""

    target = directory or settings.public_dir
    static_app = HttpOnlyStaticFiles(directory=target, check_dir=False)
    return Mount(mount_path, app=static_app, name="pyxle-public")


def build_client_assets_mount(directory: Path, *, mount_path: str = "/client") -> Mount:
    """Serve built client bundles (e.g., ``dist/client``) under ``/client``."""

    static_app = HttpOnlyStaticFiles(directory=directory, check_dir=False)
    return Mount(mount_path, app=static_app, name="pyxle-client-assets")



def create_starlette_app(
    settings: DevServerSettings,
    routes: RouteTable,
    *,
    logger: ConsoleLogger | None = None,
    public_static_dir: Path | None = None,
    client_static_dir: Path | None = None,
    serve_static: bool = True,
) -> Starlette:
    """Assemble a Starlette application exposing API/page routes and optional static mounts."""

    console_logger = logger or ConsoleLogger()

    settings = _maybe_attach_manifest(settings, console_logger)

    _ensure_project_root_on_sys_path(settings.project_root)

    renderer = ComponentRenderer()
    overlay: OverlayManager | None = None
    vite_proxy: ViteProxy | None = None
    proxy_middleware: Middleware | None = None
    static_middleware: Middleware | None = None

    if settings.debug:
        vite_proxy = ViteProxy(settings, logger=console_logger)
        overlay = OverlayManager(logger=console_logger)

        class _ViteProxyMiddleware(BaseHTTPMiddleware):
            def __init__(self, app):
                super().__init__(app)
                self._proxy = vite_proxy

            async def dispatch(self, request: Request, call_next):  # pragma: no cover - middleware wrapper
                if self._proxy.should_proxy(request):
                    return await self._proxy.handle(request)
                return await call_next(request)

        proxy_middleware = Middleware(_ViteProxyMiddleware)

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

    @asynccontextmanager
    async def lifespan(app: Starlette):  # pragma: no cover - lifecycle orchestration
        try:
            yield
        finally:
            if vite_proxy is not None:
                await vite_proxy.close()

    if serve_static:
        public_directory = public_static_dir or settings.public_dir
        static_middleware = Middleware(
            StaticAssetsMiddleware,
            public_directory=public_directory if public_directory.exists() else None,
            client_directory=client_static_dir if client_static_dir and client_static_dir.exists() else None,
        )

    middleware_stack: list[Middleware] = []
    if static_middleware is not None:
        middleware_stack.append(static_middleware)
    middleware_stack.extend(user_middleware)
    if proxy_middleware is not None:
        middleware_stack.append(proxy_middleware)

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
    app.router.routes.extend(api_router.routes)
    app.router.routes.extend(page_router.routes)
    if overlay is not None:
        app.router.routes.append(
            WebSocketRoute("/__pyxle__/overlay", overlay.websocket_endpoint)
        )
    app.router.add_route("/healthz", _healthz_endpoint, methods=["GET"])
    app.router.add_route("/readyz", _readyz_endpoint, methods=["GET"])

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
    "build_client_assets_mount",
    "create_starlette_app",
    "ApiRouteError",
]
