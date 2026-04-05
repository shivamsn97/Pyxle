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
from pyxle.ssr.renderer import pool_render_factory
from pyxle.ssr.view import build_not_found_response

from .error_pages import ErrorBoundaryRegistry, build_error_boundary_registry
from .middleware import MiddlewareHookError, load_custom_middlewares
from .overlay import OverlayManager
from .proxy import ViteProxy
from .route_hooks import (
    DEFAULT_API_POLICIES,
    DEFAULT_PAGE_POLICIES,
    RouteContext,
    RouteHookCallable,
    RouteHookError,
    load_route_hooks,
    wrap_with_route_hooks,
)
from .routes import ActionRoute, ApiRoute, PageRoute, RouteTable
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
        original_path = scope.get("path", "")
        if prefix:
            if not original_path.startswith(prefix):
                return False
            stripped = original_path[len(prefix) :] or "/"
            candidate = dict(scope)
            candidate["path"] = stripped
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, (bytes, bytearray)):
                candidate["raw_path"] = stripped.encode("utf-8")
            selected_scope = candidate

        # Determine cache header based on path pattern.
        # Vite hashed assets (e.g. /client/dist/assets/index-a1b2c3d4.js)
        # are immutable and can be cached forever.
        is_hashed_asset = (
            prefix == "/client"
            and "/dist/assets/" in original_path
        )

        async def _send_with_cache_headers(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                if is_hashed_asset:
                    headers.append(
                        (b"cache-control", b"public, max-age=31536000, immutable")
                    )
                else:
                    headers.append(
                        (b"cache-control", b"public, max-age=3600")
                    )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await static_app(selected_scope, receive, _send_with_cache_headers)
            return True
        except HTTPException as exc:
            if exc.status_code == 404:
                return False
            raise


def build_api_router(
    routes: Iterable[ApiRoute],
    *,
    route_hooks: Sequence[RouteHookCallable] | None = None,
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
    """Import a compiled module located at ``module_path`` under ``module_key``.

    Ensures the project root is on ``sys.path`` so that user-level imports
    (e.g. ``from db import ...``) resolve without manual ``sys.path`` hacks.
    """

    if module_key in sys.modules:
        del sys.modules[module_key]

    # Compiled modules live under <project_root>/<build_dir>/server/...
    # Walk up to the build-directory ancestor to find the project root.
    resolved = module_path.resolve()
    for parent in resolved.parents:
        if parent.name.startswith(".pyxle"):
            _root = str(parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            break

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
    route_hooks: Sequence[RouteHookCallable] | None = None,
    error_boundaries: ErrorBoundaryRegistry | None = None,
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
            error_boundaries=error_boundaries,
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
    error_boundaries: ErrorBoundaryRegistry | None = None,
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
                error_boundaries=error_boundaries,
            )

        return await build_page_response(
            request=request,
            settings=settings,
            page=route,
            renderer=renderer,
            overlay=overlay,
            error_boundaries=error_boundaries,
        )

    handler.__name__ = f"page_{route.module_key.replace('.', '_')}"
    return handler


def build_action_router(routes: Iterable[ActionRoute]) -> Router:
    """Create a Starlette ``Router`` for auto-generated ``@action`` endpoints.

    Each action is registered as ``POST /api/__actions/<page_path>/<action_name>``.
    The handler imports the page server module, locates the action function by name,
    validates the ``__pyxle_action__`` tag, and dispatches the request to it.

    For pages with catch-all or dynamic route parameters, a single catch-all
    action route (``is_catchall=True``) is also registered.  It captures the
    trailing path segments and extracts the action name from the last one,
    allowing the client to resolve actions regardless of the active sub-path.
    """

    router = Router()

    for route in routes:
        if route.is_catchall:
            handler = _make_catchall_action_handler(route)
        else:
            handler = _make_action_handler(route)
        router.add_route(route.path, handler, methods=["POST"])

    return router


async def _dispatch_action(
    request: Request,
    module_key: str,
    server_module_path: Path,
    action_name: str,
) -> JSONResponse:
    """Shared dispatch logic for both specific and catch-all action handlers."""
    from pyxle.runtime import ActionError

    try:
        module = _import_module(module_key, server_module_path)
    except ApiRouteError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    action_fn = getattr(module, action_name, None)
    if action_fn is None:
        return JSONResponse(
            {"ok": False, "error": f"Action '{action_name}' not found"},
            status_code=404,
        )

    if not getattr(action_fn, "__pyxle_action__", False):
        return JSONResponse(
            {"ok": False, "error": f"'{action_name}' is not a @action function"},
            status_code=400,
        )

    try:
        result = await action_fn(request)
    except ActionError as exc:
        payload: dict[str, object] = {"ok": False, "error": exc.message}
        if exc.data:
            payload["data"] = exc.data
        return JSONResponse(payload, status_code=exc.status_code)
    except Exception as exc:  # pragma: no cover - surfaced to client as 500
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    if not isinstance(result, dict):
        return JSONResponse(
            {"ok": False, "error": "Action must return a JSON-serializable dict"},
            status_code=500,
        )

    return JSONResponse({"ok": True, **result})


def _make_action_handler(route: ActionRoute):
    async def handler(request: Request):
        return await _dispatch_action(
            request, route.module_key, route.server_module_path, route.action_name,
        )

    handler.__name__ = f"action_{route.module_key.replace('.', '_')}_{route.action_name}"
    return handler


def _make_catchall_action_handler(route: ActionRoute):
    """Create a handler that extracts the action name from a catch-all path.

    The client constructs action URLs using ``window.location.pathname``.
    For catch-all pages (e.g. ``/docs/{slug:path}``), the browser path
    includes dynamic segments (e.g. ``/docs/getting-started/installation``),
    producing an action URL like
    ``/api/__actions/docs/getting-started/installation/search_docs``.

    This handler captures the trailing path via ``{_pyxle_action_path:path}``
    and treats the last segment as the action name.
    """

    async def handler(request: Request):
        action_path = request.path_params.get("_pyxle_action_path", "")
        action_name = action_path.rsplit("/", 1)[-1] if action_path else ""

        if not action_name:
            return JSONResponse(
                {"ok": False, "error": "Action name missing from request path"},
                status_code=400,
            )

        return await _dispatch_action(
            request, route.module_key, route.server_module_path, action_name,
        )

    handler.__name__ = f"action_{route.module_key.replace('.', '_')}_catchall"
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
    pool: object | None = None,
) -> Starlette:
    """Assemble a Starlette application exposing API/page routes and optional static mounts.

    If ``pool`` is an :class:`~pyxle.ssr.worker_pool.SsrWorkerPool`, renders are
    dispatched to the pool instead of spawning a new Node.js process per request.
    The pool is started in the Starlette lifespan and stopped on shutdown.
    """

    console_logger = logger or ConsoleLogger()

    settings = _maybe_attach_manifest(settings, console_logger)

    _ensure_project_root_on_sys_path(settings.project_root)

    if pool is not None:
        renderer = ComponentRenderer(factory=pool_render_factory(pool))
    else:
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

    # --- CORS middleware ---
    cors_middleware: Middleware | None = None

    _ALL_INTERFACES = ("0.0.0.0", "::", "")
    _LOOPBACK_HOSTS = (*_ALL_INTERFACES, "127.0.0.1", "localhost")

    def _vite_dev_cors_kwargs(host: str, port: int) -> dict:
        """Return ``CORSMiddleware`` origin kwargs for the Vite dev server.

        Browsers treat ``localhost`` and ``127.0.0.1`` as distinct origins,
        so both are listed when the server is on a loopback address.  When
        bound to all interfaces (``0.0.0.0`` / ``::``), any hostname on the
        Vite port is allowed via a regex so that LAN access (e.g. from a
        phone) works too.
        """
        import re  # noqa: PLC0415

        if host in _ALL_INTERFACES:
            return {
                "allow_origins": [f"http://localhost:{port}", f"http://127.0.0.1:{port}"],
                "allow_origin_regex": re.compile(rf"^https?://[^:/]+:{port}$").pattern,
            }
        if host in _LOOPBACK_HOSTS:
            return {"allow_origins": [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]}
        return {"allow_origins": [f"http://{host}:{port}"]}

    if settings.cors is not None and getattr(settings.cors, "enabled", False):
        from starlette.middleware.cors import CORSMiddleware

        origins = list(settings.cors.origins)
        cors_extra: dict = {}
        # In debug mode, ensure the Vite dev server origin is always allowed
        # so that HMR and asset requests from the Vite port succeed.
        if settings.debug:
            vite_kwargs = _vite_dev_cors_kwargs(settings.vite_host, settings.vite_port)
            for vite_origin in vite_kwargs.get("allow_origins", []):
                if vite_origin not in origins:
                    origins.append(vite_origin)
            if "allow_origin_regex" in vite_kwargs:
                cors_extra["allow_origin_regex"] = vite_kwargs["allow_origin_regex"]

        cors_middleware = Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=list(settings.cors.methods),
            allow_headers=list(settings.cors.headers),
            allow_credentials=settings.cors.credentials,
            max_age=settings.cors.max_age,
            **cors_extra,
        )
    elif settings.debug:
        # No user-configured CORS, but in dev mode we still need to allow
        # cross-origin requests from the Vite dev server (different port).
        from starlette.middleware.cors import CORSMiddleware

        cors_middleware = Middleware(
            CORSMiddleware,
            **_vite_dev_cors_kwargs(settings.vite_host, settings.vite_port),
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            allow_credentials=True,
            max_age=600,
        )

    # --- CSRF middleware ---
    csrf_middleware: Middleware | None = None
    if settings.csrf is not None and getattr(settings.csrf, "enabled", False):
        import os

        from .csrf import CsrfMiddleware

        csrf_middleware = Middleware(
            CsrfMiddleware,
            secret=os.environ.get("PYXLE_SECRET_KEY", ""),
            cookie_name=settings.csrf.cookie_name,
            header_name=settings.csrf.header_name,
            cookie_secure=settings.csrf.cookie_secure,
            cookie_samesite=settings.csrf.cookie_samesite,
            exempt_paths=settings.csrf.exempt_paths,
        )

    try:
        page_route_hooks = load_route_hooks(settings.page_route_hooks)
        api_route_hooks = load_route_hooks(settings.api_route_hooks)
    except RouteHookError as exc:
        console_logger.error(str(exc))
        raise

    @asynccontextmanager
    async def lifespan(app: Starlette):  # pragma: no cover - lifecycle orchestration
        if pool is not None:
            await pool.start()
        try:
            yield
        finally:
            if pool is not None:
                await pool.stop()
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

    # GZip compression in production mode (reduces bandwidth ~60-70%).
    if not settings.debug:
        from starlette.middleware.gzip import GZipMiddleware  # noqa: PLC0415

        middleware_stack.append(Middleware(GZipMiddleware, minimum_size=500))

    if cors_middleware is not None:
        middleware_stack.append(cors_middleware)
    if csrf_middleware is not None:
        middleware_stack.append(csrf_middleware)
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

    error_boundaries = build_error_boundary_registry(
        list(routes.error_boundary_pages),
    )

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
        error_boundaries=error_boundaries,
    )
    action_router = build_action_router(routes.actions)
    app.router.routes.extend(api_router.routes)
    app.router.routes.extend(action_router.routes)
    app.router.routes.extend(page_router.routes)
    if overlay is not None:
        app.router.routes.append(
            WebSocketRoute("/__pyxle__/overlay", overlay.websocket_endpoint)
        )
    app.router.add_route("/healthz", _healthz_endpoint, methods=["GET"])
    app.router.add_route("/readyz", _readyz_endpoint, methods=["GET"])

    # Register the catch-all 404 handler using not-found.pyx boundaries.
    if error_boundaries.has_not_found_pages:
        not_found_handler = _make_not_found_handler(
            settings=settings,
            renderer=renderer,
            overlay=overlay,
            error_boundaries=error_boundaries,
        )
        app.router.add_route("/{path:path}", not_found_handler, methods=["GET"])

    app.state.vite_proxy = vite_proxy
    app.state.ssr_renderer = renderer
    app.state.overlay = overlay
    app.state.error_boundaries = error_boundaries

    return app


def _make_not_found_handler(
    *,
    settings: DevServerSettings,
    renderer: ComponentRenderer,
    overlay: OverlayManager | None,
    error_boundaries: ErrorBoundaryRegistry,
):
    """Create a catch-all handler that renders the nearest ``not-found.pyx``."""

    from starlette.responses import HTMLResponse as _HTMLResponse

    async def handler(request: Request):  # pragma: no cover - thin wrapper
        response = await build_not_found_response(
            request=request,
            settings=settings,
            renderer=renderer,
            error_boundaries=error_boundaries,
            overlay=overlay,
        )
        if response is not None:
            return response
        # No not-found boundary rendered — return a plain 404.
        return _HTMLResponse("Not Found", status_code=404)

    handler.__name__ = "pyxle_not_found"
    return handler


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
    "build_action_router",
    "build_api_router",
    "build_page_router",
    "build_static_files_mount",
    "build_client_assets_mount",
    "create_starlette_app",
    "ApiRouteError",
]
