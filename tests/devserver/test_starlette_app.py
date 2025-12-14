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
        settings.pages_dir / "index.pyx",
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
        settings.pages_dir / "posts/[id].pyx",
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


def test_build_page_router_invokes_build_page_response(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    captured: list[str] = []

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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


def test_build_static_files_mount_serves_public_directory(project: DevServerSettings) -> None:
    mount = build_static_files_mount(project)

    assert mount.path in {"", "/"}
    assert mount.name == "pyxle-public"
    assert isinstance(mount.app, StaticFiles)
    assert Path(mount.app.directory) == project.public_dir


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

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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


def test_create_starlette_app_uses_vite_proxy(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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


def test_health_endpoints_reflect_readiness(project: DevServerSettings, monkeypatch) -> None:
    build_once(project)
    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
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

    async def fake_build_page_response(*, settings, **_):
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
