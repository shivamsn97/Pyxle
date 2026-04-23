from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pyxle.cli.logger import ConsoleLogger
from pyxle.devserver.builder import build_once
from pyxle.devserver.registry import load_metadata_registry
from pyxle.devserver.routes import build_route_table
from pyxle.devserver.settings import DevServerSettings
from pyxle.devserver.starlette_app import (
    ApiRouteError,
    build_api_router,
    build_page_router,
    build_static_files_mount,
    create_starlette_app,
)


@pytest.fixture
def project(tmp_path: Path) -> DevServerSettings:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    settings = DevServerSettings.from_project_root(root)

    write_file(
        settings.pages_dir / "api/pulse.py",
        """from starlette.responses import JSONResponse\n\nasync def endpoint(request):\n    name = request.query_params.get(\"name\", \"World\")\n    return JSONResponse({\"message\": f\"Hello, {name}!\"})\n""",
    )

    write_file(
        settings.pages_dir / "api/posts/[id].py",
        """from starlette.endpoints import HTTPEndpoint\nfrom starlette.responses import JSONResponse\n\nclass PostEndpoint(HTTPEndpoint):\n    async def get(self, request):\n        return JSONResponse({\"id\": request.path_params[\"id\"]})\n""",
    )

    write_file(
        settings.pages_dir / "index.pyxl",
        """

@server
async def load_home(request):
    return {"message": "hi"}

# --- JavaScript/PSX (Client + Server) ---

import React from 'react';

export default function Home({ data }) {
    return <div>{data.message}</div>;
}
""",
    )

    write_file(
        settings.pages_dir / "posts/[id].pyxl",
        """import React from 'react';

export default function Post({ data }) {
    return <article>{data.title}</article>;
}
""",
    )

    return settings


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_api_router_registers_function_and_class(project: DevServerSettings) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    router = build_api_router(table.apis)

    app = Starlette()
    app.router.routes.extend(router.routes)

    client = TestClient(app)

    response = client.get("/api/pulse", params={"name": "Alice"})
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Alice!"}

    response = client.get("/api/posts/42")
    assert response.status_code == 200
    assert response.json() == {"id": "42"}


def test_build_api_router_raises_for_invalid_module(project: DevServerSettings) -> None:
    write_file(project.pages_dir / "api/bad.py", "value = 123\n")

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    bad_route = next(route for route in table.apis if route.path == "/api/bad")

    with pytest.raises(ApiRouteError):
        build_api_router([bad_route])


def test_build_api_router_registers_websocket(project: DevServerSettings) -> None:
    """An API module that exports ``async def websocket(ws)`` is wired
    up as a :class:`WebSocketRoute`. Exists because previously Pyxle had
    no user-facing WS support — every app that wanted live updates had
    to hand-roll an ASGI middleware."""
    write_file(
        project.pages_dir / "api/echo.py",
        "async def websocket(ws):\n"
        "    await ws.accept()\n"
        "    try:\n"
        "        while True:\n"
        "            msg = await ws.receive_text()\n"
        "            await ws.send_text(f'echo:{msg}')\n"
        "    except Exception:\n"
        "        pass\n",
    )

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    router = build_api_router(table.apis)
    app = Starlette()
    app.router.routes.extend(router.routes)

    with TestClient(app) as client:
        with client.websocket_connect("/api/echo") as ws:
            ws.send_text("hello")
            assert ws.receive_text() == "echo:hello"
            ws.send_text("world")
            assert ws.receive_text() == "echo:world"


def test_build_api_router_supports_http_and_ws_in_same_module(
    project: DevServerSettings,
) -> None:
    """A module can export both ``endpoint`` and ``websocket`` to serve
    the same path over both protocols — e.g. a REST GET alongside a
    live-updates WS channel."""
    write_file(
        project.pages_dir / "api/dual.py",
        "from starlette.responses import JSONResponse\n"
        "\n"
        "async def endpoint(request):\n"
        "    return JSONResponse({'ok': True})\n"
        "\n"
        "async def websocket(ws):\n"
        "    await ws.accept()\n"
        "    await ws.send_text('ws-hello')\n"
        "    await ws.close()\n",
    )

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    router = build_api_router(table.apis)
    app = Starlette()
    app.router.routes.extend(router.routes)

    with TestClient(app) as client:
        assert client.get("/api/dual").json() == {"ok": True}
        with client.websocket_connect("/api/dual") as ws:
            assert ws.receive_text() == "ws-hello"


def test_build_page_router_invokes_build_page_response(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    captured: list[str] = []

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        captured.append((page.path, overlay))
        return PlainTextResponse(f"SSR:{page.path}")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    router = build_page_router(
        table.pages,
        settings=project,
        renderer=object(),  # type: ignore[arg-type]
    )

    app = Starlette()
    app.router.routes.extend(router.routes)

    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "SSR:/"

    dynamic_response = client.get("/posts/123")
    assert dynamic_response.status_code == 200
    assert dynamic_response.text == "SSR:/posts/{id}"
    assert captured == [("/", None), ("/posts/{id}", None)]


def test_page_handler_sets_vary_and_cache_control_headers(
    project: DevServerSettings, monkeypatch
) -> None:
    """Page handlers set ``Vary: x-pyxle-navigation`` on both HTML
    and JSON responses so the browser's HTTP cache stores them as
    separate entries for the same URL. Without this, a browser that
    served cached navigation JSON during a tab-restore would show
    raw JSON to the user instead of the HTML page.

    HTML responses also get ``Cache-Control: private, no-cache``.
    JSON nav responses get ``Cache-Control: no-store``."""
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    async def fake_html(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse(f"HTML:{page.path}")

    async def fake_json(*, request, settings, page, renderer, overlay=None, **_kw):
        from starlette.responses import JSONResponse

        return JSONResponse({"ok": True, "routePath": page.path})

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_html,
    )
    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_navigation_response",
        fake_json,
    )

    router = build_page_router(
        table.pages, settings=project, renderer=object()  # type: ignore[arg-type]
    )
    app = Starlette()
    app.router.routes.extend(router.routes)
    client = TestClient(app)

    # HTML response (no nav header)
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert html_resp.headers["vary"] == "x-pyxle-navigation"
    assert "private" in html_resp.headers.get("cache-control", "")
    assert "no-cache" in html_resp.headers.get("cache-control", "")

    # JSON nav response (with nav header)
    json_resp = client.get("/", headers={"x-pyxle-navigation": "1"})
    assert json_resp.status_code == 200
    assert json_resp.headers["vary"] == "x-pyxle-navigation"
    assert "no-store" in json_resp.headers.get("cache-control", "")


def test_build_static_files_mount_serves_public_directory(project: DevServerSettings) -> None:
    mount = build_static_files_mount(project)

    assert mount.path in {"", "/"}
    assert mount.name == "pyxle-public"
    assert isinstance(mount.app, StaticFiles)
    assert Path(mount.app.directory) == project.public_dir


def test_build_static_files_mount_rejects_websocket_scope(project: DevServerSettings) -> None:
    mount = build_static_files_mount(project)

    app = Starlette()
    app.router.routes.append(mount)

    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/__pyxle__/overlay"):
            pass

    assert getattr(excinfo.value, "code", None) == 4404


def test_create_starlette_app_combines_routes(project: DevServerSettings, monkeypatch) -> None:
    static_file = project.public_dir / "robots.txt"
    static_file.write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        assert overlay is not None
        return HTMLResponse(f"<div>{page.path}</div>")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    app = create_starlette_app(project, table)
    client = TestClient(app)

    response = client.get("/api/pulse")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello, World!"

    page_response = client.get("/posts/5")
    assert page_response.status_code == 200
    assert "<div>/posts/{id}</div>" in page_response.text

    asset_response = client.get("/robots.txt")
    assert asset_response.status_code == 200
    assert "User-agent" in asset_response.text

    assert app.state.ssr_renderer is renderer
    assert app.state.overlay is not None

    with client.websocket_connect("/__pyxle__/overlay") as websocket:
        websocket.close()


def test_static_assets_middleware_handles_catchall_routes(project: DevServerSettings, monkeypatch, tmp_path: Path) -> None:
    write_file(
        project.pages_dir / "[...slug].pyxl",
        """
import React from 'react';

export default function Fallback() {
    return <div>fallback</div>;
}
""",
    )

    public_styles = project.public_dir / "styles"
    public_styles.mkdir(parents=True, exist_ok=True)
    (public_styles / "site.css").write_text("body { color: red; }", encoding="utf-8")

    client_assets = tmp_path / "dist-client"
    (client_assets / "assets").mkdir(parents=True)
    (client_assets / "assets" / "bundle.js").write_text("console.log('hi')", encoding="utf-8")

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    async def fake_build_page_response(*_, **__):  # pragma: no cover - deterministic HTML
        return HTMLResponse("<div>page</div>")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    prod_settings = replace(project, debug=False, page_manifest={})

    app = create_starlette_app(
        prod_settings,
        table,
        serve_static=True,
        client_static_dir=client_assets,
    )

    client = TestClient(app)

    css_response = client.get("/styles/site.css")
    assert css_response.status_code == 200
    assert "color: red" in css_response.text

    bundle_response = client.get("/client/assets/bundle.js")
    assert bundle_response.status_code == 200
    assert "console.log" in bundle_response.text

    fallback_response = client.get("/unknown/path")
    assert fallback_response.status_code == 200
    assert "page" in fallback_response.text


def test_create_starlette_app_uses_vite_proxy(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        assert overlay is not None
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    app = create_starlette_app(project, table)
    proxy = app.state.vite_proxy

    captured: list[str] = []
    shutdown_flag: list[bool] = []

    async def fake_handle(request):
        captured.append(request.url.path)
        return PlainTextResponse("ok")

    async def fake_close():
        shutdown_flag.append(True)

    proxy.handle = fake_handle  # type: ignore[assignment]
    proxy.should_proxy = lambda request: request.url.path.startswith("/@vite")  # type: ignore[assignment]
    proxy.close = fake_close  # type: ignore[assignment]

    with TestClient(app) as client:
        response = client.get("/@vite/client")
        assert response.status_code == 200
        assert response.text == "ok"

    assert captured == ["/@vite/client"]
    assert shutdown_flag == [True]


def test_create_starlette_app_serves_client_assets_in_production(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()
    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    dist_root = project.project_root / "dist"
    client_dir = dist_root / "client"
    public_dir = dist_root / "public"
    client_dir.mkdir(parents=True, exist_ok=True)
    public_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "assets").mkdir(exist_ok=True)
    (client_dir / "assets" / "bundle.js").write_text("console.log('prod');", encoding="utf-8")
    (public_dir / "robots.txt").write_text("Prod robots", encoding="utf-8")

    prod_settings = replace(project, debug=False, page_manifest={})

    app = create_starlette_app(
        prod_settings,
        table,
        public_static_dir=public_dir,
        client_static_dir=client_dir,
    )

    assert getattr(app.state, "vite_proxy", None) is None
    assert getattr(app.state, "overlay", None) is None

    with TestClient(app) as client:
        asset = client.get("/client/assets/bundle.js")
        assert asset.status_code == 200
        assert "prod" in asset.text

        robots = client.get("/robots.txt")
        assert robots.status_code == 200
        assert "Prod robots" in robots.text


def test_create_starlette_app_can_disable_static_mounts(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()
    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    (project.public_dir / "robots.txt").write_text("ok", encoding="utf-8")

    app = create_starlette_app(project, table, serve_static=False)
    client = TestClient(app)

    response = client.get("/robots.txt")
    assert response.status_code == 404

def test_health_endpoints_reflect_readiness(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        assert overlay is not None
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    app = create_starlette_app(project, table)
    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["ready"] is False
    assert payload["uptime"] >= 0

    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["ready"] is False

    app.state.pyxle_ready = True
    ready_after = client.get("/readyz")
    assert ready_after.status_code == 200
    assert ready_after.json()["ready"] is True


def test_create_starlette_app_applies_custom_middleware(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    custom = replace(
        project,
        custom_middlewares=("tests.devserver.sample_middlewares:HeaderCaptureMiddleware",),
    )

    app = create_starlette_app(custom, table)
    client = TestClient(app)

    response = client.get("/api/pulse", headers={"x-auth-token": "secret"})

    assert response.status_code == 200
    assert response.headers["x-auth-token"] == "secret"


def test_create_starlette_app_injects_project_root_into_sys_path(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    project_root = str(project.project_root)
    sanitized_path = [entry for entry in sys.path if entry != project_root]
    monkeypatch.setattr(sys, "path", sanitized_path)

    create_starlette_app(project, table)

    assert sys.path[0] == project_root


def test_create_starlette_app_loads_page_manifest(project: DevServerSettings, monkeypatch) -> None:
    dist_dir = project.project_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dist_dir / "page-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "/": {
                    "client": {
                        "file": "assets/index.js",
                        "imports": [],
                        "css": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    captured: dict[str, object] = {}

    async def fake_build_page_response(*, settings, **_kw):
        captured["manifest"] = settings.page_manifest
        return PlainTextResponse("ok")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    prod_settings = replace(project, debug=False)
    app = create_starlette_app(prod_settings, table)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert captured["manifest"] is not None
    assert captured["manifest"]["/"]["client"]["file"] == "assets/index.js"


def test_create_starlette_app_warns_when_manifest_missing(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    warnings: list[str] = []

    class StubLogger(ConsoleLogger):
        def warning(self, message: str) -> None:  # type: ignore[override]
            warnings.append(message)

    async def fake_build_page_response(*args, **kwargs):
        return PlainTextResponse("ok")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    prod_settings = replace(project, debug=False)
    create_starlette_app(prod_settings, table, logger=StubLogger())

    assert warnings


def test_route_hooks_attach_metadata_and_custom_policies(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    write_file(
        project.pages_dir / "api/hook_check.py",
        """from starlette.responses import JSONResponse\n\nasync def endpoint(request):\n    route = request.scope.get(\"pyxle\", {}).get(\"route\", {})\n    targets = getattr(request.state, \"route_targets\", [])\n    return JSONResponse({\"route\": route, \"targets\": targets})\n""",
    )

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def capture_page_response(*, request, **_):
        metadata = request.scope.get("pyxle", {}).get("route")
        payload = {
            "recorded": getattr(request.state, "recorded_route", None),
            "metadata": metadata,
        }
        return JSONResponse(payload)

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        capture_page_response,
    )

    custom = replace(
        project,
        page_route_hooks=("tests.devserver.sample_middlewares:record_route_hook",),
        api_route_hooks=("tests.devserver.sample_middlewares:build_target_hook",),
    )

    app = create_starlette_app(custom, table)
    client = TestClient(app)

    page_response = client.get("/")
    assert page_response.status_code == 200
    page_json = page_response.json()
    assert page_json["recorded"] == "/"
    assert page_json["metadata"]["path"] == "/"
    assert page_json["metadata"]["target"] == "page"

    api_response = client.get("/api/hook_check")
    assert api_response.status_code == 200
    assert api_response.json()["targets"] == ["api"]


def test_dev_mode_adds_vite_cors_origin_automatically(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    """In debug mode the Vite dev server origin should be allowed even without
    explicit CORS configuration, so that HMR and asset requests succeed."""
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: object(),
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    # debug=True is the default from the fixture
    assert project.debug is True
    # Default vite_host is 127.0.0.1
    assert project.vite_host == "127.0.0.1"

    app = create_starlette_app(project, table)
    client = TestClient(app)

    vite_port = project.vite_port

    # 127.0.0.1 origin should be allowed
    response = client.get(
        "/api/pulse",
        headers={"Origin": f"http://127.0.0.1:{vite_port}"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == f"http://127.0.0.1:{vite_port}"

    # localhost should also be allowed (browsers treat them as different origins)
    response = client.get(
        "/api/pulse",
        headers={"Origin": f"http://localhost:{vite_port}"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == f"http://localhost:{vite_port}"


def test_dev_mode_cors_merges_with_user_config(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    """When the user configures CORS origins, the Vite origin should be merged
    in during debug mode without duplicating it."""
    from pyxle.config import CorsConfig

    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: object(),
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    user_origin = "https://example.com"
    settings_with_cors = replace(
        project,
        cors=CorsConfig(origins=(user_origin,)),
    )

    app = create_starlette_app(settings_with_cors, table)
    client = TestClient(app)

    # User-configured origin should work
    response = client.get("/api/pulse", headers={"Origin": user_origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == user_origin

    # Vite origin should also work (auto-merged)
    vite_origin = f"http://{project.vite_host}:{project.vite_port}"
    response = client.get("/api/pulse", headers={"Origin": vite_origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == vite_origin


def test_production_mode_does_not_add_vite_cors(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    """In production mode, no automatic Vite CORS origin should be injected."""
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    prod_settings = replace(project, debug=False)
    app = create_starlette_app(prod_settings, table)
    client = TestClient(app)

    vite_origin = f"http://{prod_settings.vite_host}:{prod_settings.vite_port}"
    response = client.get("/api/pulse", headers={"Origin": vite_origin})
    assert response.status_code == 200
    # No CORS header should be present — no CORS middleware in prod without config
    assert response.headers.get("access-control-allow-origin") is None


def test_dev_mode_cors_allows_localhost_when_bound_to_all_interfaces(
    project: DevServerSettings,
    monkeypatch,
) -> None:
    """When vite_host is 0.0.0.0, browsers send Origin as localhost or
    127.0.0.1 — never the literal 0.0.0.0.  Both must be allowed."""
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: object(),
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None, **_kw):
        return PlainTextResponse("page")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    wildcard_settings = replace(project, vite_host="0.0.0.0")
    app = create_starlette_app(wildcard_settings, table)
    client = TestClient(app)

    vite_port = wildcard_settings.vite_port

    # localhost origin should be allowed
    resp_localhost = client.get(
        "/api/pulse",
        headers={"Origin": f"http://localhost:{vite_port}"},
    )
    assert resp_localhost.status_code == 200
    assert resp_localhost.headers.get("access-control-allow-origin") == f"http://localhost:{vite_port}"

    # 127.0.0.1 origin should also be allowed
    resp_loopback = client.get(
        "/api/pulse",
        headers={"Origin": f"http://127.0.0.1:{vite_port}"},
    )
    assert resp_loopback.status_code == 200
    assert resp_loopback.headers.get("access-control-allow-origin") == f"http://127.0.0.1:{vite_port}"

    # LAN IP origin should also be allowed (regex match on port)
    resp_lan = client.get(
        "/api/pulse",
        headers={"Origin": f"http://192.168.1.42:{vite_port}"},
    )
    assert resp_lan.status_code == 200
    assert resp_lan.headers.get("access-control-allow-origin") == f"http://192.168.1.42:{vite_port}"

    # Wrong port should NOT match
    resp_wrong_port = client.get(
        "/api/pulse",
        headers={"Origin": f"http://localhost:{vite_port + 1}"},
    )
    assert resp_wrong_port.headers.get("access-control-allow-origin") is None
