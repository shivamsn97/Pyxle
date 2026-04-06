from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from pyxle.devserver.routes import PageRoute
from pyxle.devserver.settings import DevServerSettings
from pyxle.ssr import view as ssr_view
from pyxle.ssr.renderer import ComponentRenderError, InlineStyleFragment, RenderResult
from pyxle.ssr.view import (
    HeadEvaluationError,
    build_page_navigation_response,
    build_page_response,
)


@pytest.fixture
def anyio_backend() -> str:  # pragma: no cover - fixture wiring
    return "asyncio"


class StubRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, dict[str, object]]] = []
        self.responses: list[RenderResult] = []

    async def render(self, component_path: Path, props: dict[str, object]) -> RenderResult:
        self.calls.append((component_path, props))
        if self.responses:
            return self.responses.pop(0)
        return RenderResult(html="<div></div>")


class StubOverlay:
    def __init__(self) -> None:
        self.events: list[tuple[str, str] | tuple[str, str, list[dict[str, str]]]] = []

    async def notify_clear(self, route_path: str) -> None:
        self.events.append(("clear", route_path))

    async def notify_error(
        self,
        route_path: str,
        error: BaseException,
        *,
        breadcrumbs: list[dict[str, str]] | None = None,
    ) -> None:
        self.events.append(("error", route_path, breadcrumbs or []))


async def _read_response_body(response) -> bytes:
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is not None:
        chunks = bytearray()
        async for chunk in body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            chunks.extend(chunk)
        return bytes(chunks)

    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body or b"")


@pytest.fixture
def settings(tmp_path: Path) -> DevServerSettings:
    project = tmp_path / "project"
    (project / "pages").mkdir(parents=True)
    (project / "public").mkdir()
    return DevServerSettings.from_project_root(project)


def _page_route(tmp_path: Path, *, loader_name: str | None) -> PageRoute:
    return PageRoute(
        path="/",
        source_relative_path=Path("index.pyx"),
        source_absolute_path=tmp_path / "pages" / "index.pyx",
        server_module_path=tmp_path / "server" / "index.py",
        client_module_path=tmp_path / "client" / "index.jsx",
        metadata_path=tmp_path / "metadata" / "index.json",
        module_key="pyxle.server.pages.index",
        client_asset_path="/pages/index.jsx",
        server_asset_path="/pages/index.py",
        content_hash="hash",
        loader_name=loader_name,
        loader_line=1,
        head_elements=("<title>Home</title>",),
        head_is_dynamic=False,
    )


@pytest.mark.anyio
async def test_build_page_response_without_loader(settings: DevServerSettings, tmp_path: Path) -> None:
    renderer = StubRenderer()
    overlay = StubOverlay()
    overlay = StubOverlay()
    renderer.responses.append(RenderResult(html="<main>empty</main>"))

    page = _page_route(tmp_path, loader_name=None)

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "root_path": "",
            "headers": [],
        }
    )

    overlay = StubOverlay()

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 200
    assert "<main>empty</main>" in body
    assert "<title>Home</title>" in body
    assert "nonce=\"" in body
    assert renderer.calls[-1][0] == page.client_module_path
    assert renderer.calls[-1][1] == {"data": {}}
    assert overlay.events == [("clear", "/")]


@pytest.mark.anyio
async def test_build_page_navigation_response_returns_payload(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<main>empty</main>"))
    overlay = StubOverlay()
    page = _page_route(tmp_path, loader_name=None)

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "root_path": "",
            "headers": [],
        }
    )

    response = await build_page_navigation_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    payload = json.loads(await _read_response_body(response))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["page"]["clientAssetPath"] == page.client_asset_path
    assert payload["props"] == {"data": {}}
    assert "<title>Home</title>" in payload["headMarkup"]
    assert overlay.events == [("clear", "/")]


@pytest.mark.anyio
async def test_build_page_response_with_loader(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "index.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
import json

async def load_home(request):
    return {"value": request.query_params.get("value", "0")}, 202
""",
        encoding="utf-8",
    )

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<p>SSR</p>"))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "root_path": "",
        "headers": [],
        "query_string": b"value=9",
    }
    request = Request(scope)

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
    )

    assert response.status_code == 202
    body_text = (await _read_response_body(response)).decode()
    assert "<p>SSR</p>" in body_text
    assert "<title>Home</title>" in body_text
    assert renderer.calls[-1][0] == page.client_module_path
    assert renderer.calls[-1][1]["data"]["value"] == "9"


@pytest.mark.anyio
async def test_build_page_response_inlines_renderer_styles(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    renderer = StubRenderer()
    renderer.responses.append(
        RenderResult(
            html="<p>Styled</p>",
            inline_styles=(
                InlineStyleFragment(
                    identifier="style-one",
                    contents=".hero { color: red; }",
                    source="pages/index.css",
                ),
            ),
        )
    )

    page = _page_route(tmp_path, loader_name=None)
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
    )

    body_text = (await _read_response_body(response)).decode()
    assert 'data-pyxle-inline-style="style-one"' in body_text
    assert '.hero { color: red; }' in body_text


@pytest.mark.anyio
async def test_build_page_response_validates_loader_return(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "bad.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
async def load_home(request):
    return "oops"
""",
        encoding="utf-8",
    )

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "root_path": "",
        "headers": [],
    }
    request = Request(scope)

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 500
    assert "Server Render Failed" in body
    assert "LoaderExecutionError" in body
    assert overlay.events and overlay.events[0][0] == "error"
    assert overlay.events[0][1] == "/"
    loader_breadcrumbs = overlay.events[0][2]
    assert loader_breadcrumbs[0]["status"] == "failed"
    assert loader_breadcrumbs[1]["status"] == "blocked"
    assert loader_breadcrumbs[2]["label"] == "Hydration"


@pytest.mark.anyio
async def test_build_page_navigation_response_reports_loader_error(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    server_module = tmp_path / "server" / "bad_nav.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
async def load_home(request):
    return "oops"
""",
        encoding="utf-8",
    )

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_navigation_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    payload = json.loads(await _read_response_body(response))
    assert response.status_code == 500
    assert payload["ok"] is False
    assert payload["stage"] == "loader"
    assert overlay.events and overlay.events[0][0] == "error"


@pytest.mark.anyio
async def test_build_page_response_missing_loader(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "missing.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text("async def other(request):\n    return {}\n", encoding="utf-8")

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    renderer = StubRenderer()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 500
    assert "LoaderExecutionError" in body


@pytest.mark.anyio
async def test_build_page_response_handles_renderer_error(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "index.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
async def load_home(request):
    return {}
""",
        encoding="utf-8",
    )

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    class FailingRenderer(StubRenderer):
        async def render(self, component_path: Path, props: dict[str, object]) -> str:  # type: ignore[override]
            raise ComponentRenderError("render boom")

    renderer = FailingRenderer()
    overlay = StubOverlay()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 500
    assert "render boom" in body
    assert overlay.events and overlay.events[0][0] == "error"
    renderer_breadcrumbs = overlay.events[0][2]
    assert renderer_breadcrumbs[0]["status"] == "passed"
    assert renderer_breadcrumbs[1]["status"] == "failed"


@pytest.mark.anyio
async def test_build_page_navigation_response_handles_renderer_error(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    server_module = tmp_path / "server" / "renderer_nav.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
async def load_home(request):
    return {}
""",
        encoding="utf-8",
    )

    page = _page_route(tmp_path, loader_name="load_home")
    page = PageRoute(
        path=page.path,
        source_relative_path=page.source_relative_path,
        source_absolute_path=page.source_absolute_path,
        server_module_path=server_module,
        client_module_path=page.client_module_path,
        metadata_path=page.metadata_path,
        module_key=page.module_key,
        client_asset_path=page.client_asset_path,
        server_asset_path=page.server_asset_path,
        content_hash=page.content_hash,
        loader_name=page.loader_name,
        loader_line=page.loader_line,
        head_elements=page.head_elements,
        head_is_dynamic=page.head_is_dynamic,
    )

    class NavFailingRenderer(StubRenderer):
        async def render(self, component_path: Path, props: dict[str, object]) -> str:  # type: ignore[override]
            raise ComponentRenderError("render boom")

    renderer = NavFailingRenderer()
    overlay = StubOverlay()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_navigation_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    payload = json.loads(await _read_response_body(response))
    assert response.status_code == 500
    assert payload["ok"] is False
    assert payload["stage"] == "renderer"
    assert overlay.events and overlay.events[0][0] == "error"


@pytest.mark.anyio
async def test_build_page_response_uses_manifest_assets_in_production(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<section>prod</section>"))

    prod_settings = replace(
        settings,
        debug=False,
        page_manifest={
            "/": {
                "client": {
                    "file": "assets/index.js",
                    "imports": [],
                    "css": ["assets/index.css"],
                }
            }
        },
    )

    page = _page_route(tmp_path, loader_name=None)
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=prod_settings,
        page=page,
        renderer=renderer,
    )

    body = (await _read_response_body(response)).decode()
    assert "/client/assets/index.js" in body
    assert 'rel="stylesheet" href="/client/assets/index.css"' in body
    assert "@vite/client" not in body


@pytest.mark.anyio
async def test_build_page_response_handles_missing_manifest_entry(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<section>prod</section>"))

    prod_settings = replace(settings, debug=False, page_manifest={})

    page = _page_route(tmp_path, loader_name=None)
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=prod_settings,
        page=page,
        renderer=renderer,
    )

    body = (await _read_response_body(response)).decode()
    assert "Missing Manifest Entry" in body


@pytest.mark.anyio
async def test_build_page_response_handles_head_error(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "head.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        "HEAD = ['<title>Ok</title>', 123]\n",
        encoding="utf-8",
    )

    page = replace(
        _page_route(tmp_path, loader_name=None),
        server_module_path=server_module,
        head_elements=(),
        head_is_dynamic=True,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 500
    assert "HeadEvaluationError" in body
    assert overlay.events and overlay.events[0][0] == "error"
    breadcrumbs = overlay.events[0][2]
    assert breadcrumbs[0]["status"] == "skipped"
    assert breadcrumbs[1]["status"] == "unknown"


@pytest.mark.anyio
async def test_build_page_response_supports_callable_head(settings: DevServerSettings, tmp_path: Path) -> None:
    server_module = tmp_path / "server" / "head_callable.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        """
def HEAD(data):
    product = data['product']
    return [
        f"<title>{product['name']} - Pyxle</title>",
        f'<meta name="description" content="{product["description"]}" />',
    ]

async def load_home(request):
    return {
        'product': {
            'name': 'Gizmo',
            'description': 'Callable heads reuse loader data',
        }
    }
""",
        encoding="utf-8",
    )

    page = replace(
        _page_route(tmp_path, loader_name="load_home"),
        server_module_path=server_module,
        head_elements=(),
        head_is_dynamic=True,
    )

    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<main>callable</main>"))
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 200
    assert "<main>callable</main>" in body
    assert "<title>Gizmo - Pyxle</title>" in body
    assert 'content="Callable heads reuse loader data"' in body


@pytest.mark.anyio
async def test_build_page_navigation_response_handles_head_error(
    settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    server_module = tmp_path / "server" / "head_nav.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        "HEAD = ['<title>Ok</title>', 123]\n",
        encoding="utf-8",
    )

    page = replace(
        _page_route(tmp_path, loader_name=None),
        server_module_path=server_module,
        head_elements=(),
        head_is_dynamic=True,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()
    request = Request({"type": "http", "http_version": "1.1", "method": "GET", "path": "/", "root_path": "", "headers": []})

    response = await build_page_navigation_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    payload = json.loads(await _read_response_body(response))
    assert response.status_code == 500
    assert payload["ok"] is False
    assert payload["stage"] == "server"
    assert overlay.events and overlay.events[0][0] == "error"


@pytest.mark.anyio
async def test_build_page_response_refreshes_shared_python_modules(settings: DevServerSettings, tmp_path: Path) -> None:
    project_root = str(settings.project_root)
    added = False
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        added = True
    try:
        (settings.pages_dir / "components").mkdir(parents=True, exist_ok=True)
        (settings.pages_dir / "__init__.py").write_text("from .components import get_value\n", encoding="utf-8")
        (settings.pages_dir / "components" / "__init__.py").write_text(
            "from .head import get_value\n__all__ = ['get_value']\n",
            encoding="utf-8",
        )
        shared_module = settings.pages_dir / "components" / "head.py"
        shared_module.write_text(
            "def get_value():\n    return 'alpha'\n",
            encoding="utf-8",
        )

        server_module = tmp_path / "server" / "index.py"
        server_module.parent.mkdir(parents=True, exist_ok=True)
        server_module.write_text(
            "from pages.components import get_value\n\nasync def load_home(request):\n    return {'value': get_value()}\n",
            encoding="utf-8",
        )

        page = _page_route(tmp_path, loader_name="load_home")
        page = PageRoute(
            path=page.path,
            source_relative_path=page.source_relative_path,
            source_absolute_path=page.source_absolute_path,
            server_module_path=server_module,
            client_module_path=page.client_module_path,
            metadata_path=page.metadata_path,
            module_key=page.module_key,
            client_asset_path=page.client_asset_path,
            server_asset_path=page.server_asset_path,
            content_hash=page.content_hash,
            loader_name=page.loader_name,
            loader_line=page.loader_line,
            head_elements=page.head_elements,
            head_is_dynamic=page.head_is_dynamic,
        )

        renderer = StubRenderer()
        renderer.responses.extend(
            [
                RenderResult(html="<section>first</section>"),
                RenderResult(html="<section>second</section>"),
            ]
        )

        request = Request({
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "root_path": "",
            "headers": [],
        })

        await build_page_response(
            request=request,
            settings=settings,
            page=page,
            renderer=renderer,
        )
        assert renderer.calls[-1][1]["data"]["value"] == "alpha"

        shared_module.write_text(
            "def get_value():\n    return 'beta'\n",
            encoding="utf-8",
        )

        await build_page_response(
            request=request,
            settings=settings,
            page=page,
            renderer=renderer,
        )
        assert renderer.calls[-1][1]["data"]["value"] == "beta"
    finally:
        if added and project_root in sys.path:
            sys.path.remove(project_root)


def test_resolve_head_elements_returns_static(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=("<title>Static</title>",),
        head_is_dynamic=False,
    )

    resolved = ssr_view._resolve_head_elements(page, module=None, loader_payload={})

    assert resolved == ("<title>Static</title>",)


def test_resolve_head_elements_reads_dynamic_module(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=True,
    )

    module = SimpleNamespace(HEAD=["<title>Dynamic</title>"])

    resolved = ssr_view._resolve_head_elements(page, module, loader_payload={})

    assert resolved == ("<title>Dynamic</title>",)


def test_resolve_head_elements_handles_missing_head(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=True,
    )

    module = SimpleNamespace()

    resolved = ssr_view._resolve_head_elements(page, module, loader_payload={})

    assert resolved == ()


def test_resolve_head_elements_validates_entries(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=True,
    )

    module = SimpleNamespace(HEAD=["<title>Ok</title>", 123])

    with pytest.raises(HeadEvaluationError):
        ssr_view._resolve_head_elements(page, module, loader_payload={})


def test_resolve_head_elements_invokes_callable_with_loader_data(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=True,
    )

    captured: dict[str, str] = {}

    def build_head(data: dict[str, object]) -> str:
        captured["title"] = f"{data['product']['name']}"
        return f"<title>{data['product']['name']}</title>"

    module = SimpleNamespace(HEAD=build_head)
    loader_payload = {"product": {"name": "Callables"}}

    resolved = ssr_view._resolve_head_elements(page, module, loader_payload)

    assert resolved == ("<title>Callables</title>",)
    assert captured["title"] == "Callables"


def test_resolve_head_elements_callable_requires_data_argument(tmp_path: Path) -> None:
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=True,
    )

    def build_head_without_args() -> str:
        return "<title>Invalid</title>"

    module = SimpleNamespace(HEAD=build_head_without_args)

    with pytest.raises(HeadEvaluationError):
        ssr_view._resolve_head_elements(page, module, loader_payload={})


@pytest.mark.anyio
async def test_build_page_response_merges_layout_head_blocks(settings: DevServerSettings, tmp_path: Path) -> None:
    """Test that layout head JSX blocks are merged with page head elements."""
    # Create layout.pyx with head blocks
    layout_path = settings.pages_dir / "layout.pyx"
    layout_path.write_text(
        """\n\nimport React from 'react';\n\nexport default function Layout({ children }) {\n    return <div>{children}</div>;\n}\n<Head>\n<meta name='layout-meta' content='from-layout'/>\n</Head>\n""",
        encoding="utf-8",
    )

    # Create index.pyx with head elements and jsx blocks
    page_path = settings.pages_dir / "index.pyx"
    page_path.write_text(
        """HEAD = "<title>Home</title>"\n\nimport React from 'react';\n\nexport default function Home({ data }) {\n    return <div>{data.message}</div>;\n}\n<Head>\n<meta name='page-meta' content='from-page'/>\n</Head>\n""",
        encoding="utf-8",
    )

    # Compile the pages
    from pyxle.devserver.builder import build_once
    build_once(settings)

    # Load route info
    from pyxle.devserver.registry import load_metadata_registry
    from pyxle.devserver.routes import build_route_table
    
    registry = load_metadata_registry(settings)
    routes = build_route_table(registry)
    page = routes.find_page("/")
    assert page is not None

    # Mock renderer
    renderer = StubRenderer()
    renderer.responses.append(RenderResult(html="<div>home</div>"))

    # Create mock request
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
    }
    request = Request(scope)

    # Build response
    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=None,
    )

    # Verify response is successful
    assert response.status_code == 200

    # Parse HTML to check head elements
    body_bytes = await _read_response_body(response)
    html = body_bytes.decode("utf-8")
    assert "<title>Home</title>" in html
    # Layout head block should be in the output
    assert "layout-meta" in html or "from-layout" in html or "from-page" in html


# ---------------------------------------------------------------------------
# Error boundary integration in build_page_response
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_build_page_response_loader_error_hits_error_boundary(
    settings: DevServerSettings, tmp_path: Path
) -> None:
    """LoaderError triggers _try_error_boundary and falls back to error doc."""
    server_module = tmp_path / "server" / "index.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        "from pyxle.runtime import LoaderError\n"
        "async def my_loader(request):\n"
        "    raise LoaderError('Not allowed', status_code=403)\n",
        encoding="utf-8",
    )

    page = PageRoute(
        path="/",
        source_relative_path=Path("index.pyx"),
        source_absolute_path=tmp_path / "pages" / "index.pyx",
        server_module_path=server_module,
        client_module_path=tmp_path / "client" / "index.jsx",
        metadata_path=tmp_path / "metadata" / "index.json",
        module_key="pyxle.server.pages.index_lerr",
        client_asset_path="/pages/index.jsx",
        server_asset_path="/pages/index.py",
        content_hash="hash",
        loader_name="my_loader",
        loader_line=2,
        head_elements=(),
        head_is_dynamic=False,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    assert response.status_code == 403
    body = (await _read_response_body(response)).decode()
    assert "Not allowed" in body
    # Overlay should have received an error event
    assert any(ev[0] == "error" for ev in overlay.events)


@pytest.mark.anyio
async def test_build_page_navigation_response_loader_error_uses_status_code(
    settings: DevServerSettings, tmp_path: Path
) -> None:
    """LoaderError in navigation mode returns the correct status code."""
    server_module = tmp_path / "server" / "nav_lerr.py"
    server_module.parent.mkdir(parents=True, exist_ok=True)
    server_module.write_text(
        "from pyxle.runtime import LoaderError\n"
        "async def my_loader(request):\n"
        "    raise LoaderError('Forbidden', status_code=403)\n",
        encoding="utf-8",
    )

    page = PageRoute(
        path="/nav",
        source_relative_path=Path("nav.pyx"),
        source_absolute_path=tmp_path / "pages" / "nav.pyx",
        server_module_path=server_module,
        client_module_path=tmp_path / "client" / "nav.jsx",
        metadata_path=tmp_path / "metadata" / "nav.json",
        module_key="pyxle.server.pages.nav_lerr",
        client_asset_path="/pages/nav.jsx",
        server_asset_path="/pages/nav.py",
        content_hash="hash",
        loader_name="my_loader",
        loader_line=2,
        head_elements=(),
        head_is_dynamic=False,
    )

    renderer = StubRenderer()
    overlay = StubOverlay()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/nav",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    response = await build_page_navigation_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
        overlay=overlay,
    )

    payload = json.loads(await _read_response_body(response))
    assert response.status_code == 403
    assert payload["ok"] is False
    assert "Forbidden" in payload["error"]


def test_normalize_head_entries_none_returns_empty(tmp_path: Path) -> None:
    """_normalize_head_entries(page, None) returns an empty tuple."""
    from pyxle.ssr.view import _normalize_head_entries

    page = _page_route(tmp_path, loader_name=None)
    assert _normalize_head_entries(page, None) == ()


def test_normalize_head_entries_string_wraps_in_tuple(tmp_path: Path) -> None:
    from pyxle.ssr.view import _normalize_head_entries

    page = _page_route(tmp_path, loader_name=None)
    assert _normalize_head_entries(page, "<title>Hi</title>") == ("<title>Hi</title>",)


def test_normalize_head_entries_list_of_strings(tmp_path: Path) -> None:
    from pyxle.ssr.view import _normalize_head_entries

    page = _page_route(tmp_path, loader_name=None)
    result = _normalize_head_entries(page, ["<title>A</title>", "<meta name='x' />"])
    assert result == ("<title>A</title>", "<meta name='x' />")


def test_normalize_head_entries_bad_type_raises(tmp_path: Path) -> None:
    from pyxle.ssr.view import _normalize_head_entries

    page = _page_route(tmp_path, loader_name=None)
    with pytest.raises(HeadEvaluationError, match="must be a string"):
        _normalize_head_entries(page, 42)


def test_normalize_head_entries_non_string_item_raises(tmp_path: Path) -> None:
    from pyxle.ssr.view import _normalize_head_entries

    page = _page_route(tmp_path, loader_name=None)
    with pytest.raises(HeadEvaluationError, match="must be strings"):
        _normalize_head_entries(page, ["valid", 42])


def test_evaluate_head_callable_async_raises(tmp_path: Path) -> None:
    """Async HEAD callables are rejected."""
    from pyxle.ssr.view import _evaluate_head_callable

    page = _page_route(tmp_path, loader_name=None)

    async def async_head(data):
        return "<title>Async</title>"

    with pytest.raises(HeadEvaluationError, match="must return synchronously"):
        _evaluate_head_callable(page, async_head, {"key": "val"})


def test_purge_page_modules_handles_missing_dir(tmp_path: Path) -> None:
    """_purge_page_modules exits gracefully for non-existent directories."""
    from pyxle.ssr.view import _purge_page_modules

    _purge_page_modules(tmp_path / "nonexistent")


@pytest.mark.anyio
async def test_runtime_head_overrides_static_dynamic_title(
    settings: DevServerSettings, tmp_path: Path,
) -> None:
    """Regression: a dynamic ``<title>{expression}</title>`` inside a
    ``<Head>`` block must render the runtime-evaluated value, not the
    literal source text captured at compile time.

    The compiler stores ``<title>{pageTitle}</title>`` verbatim in
    ``page.head_jsx_blocks``. The Head component, when rendered, calls
    ``renderToStaticMarkup`` and produces ``<title>Installation</title>``,
    which is forwarded as a runtime head block. The merger must give the
    runtime version precedence so the literal ``{pageTitle}`` never
    leaks into the rendered HTML.
    """
    page = replace(
        _page_route(tmp_path, loader_name=None),
        head_elements=(),
        head_is_dynamic=False,
        head_jsx_blocks=("<title>{pageTitle}</title>",),
    )

    renderer = StubRenderer()
    renderer.responses.append(
        RenderResult(
            html="<main>doc</main>",
            head_elements=("<title>Installation - Pyxle Docs</title>",),
        )
    )
    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "root_path": "",
        "headers": [],
    })

    response = await build_page_response(
        request=request,
        settings=settings,
        page=page,
        renderer=renderer,
    )

    body = (await _read_response_body(response)).decode()
    assert response.status_code == 200
    assert "<title>Installation - Pyxle Docs</title>" in body
    assert "{pageTitle}" not in body


def test_import_server_module_loads_and_registers(tmp_path: Path) -> None:
    """_import_server_module loads the module and registers it in sys.modules."""
    from pyxle.ssr.view import _import_server_module

    mod_path = tmp_path / "test_mod.py"
    mod_path.write_text("VALUE = 42\n", encoding="utf-8")
    key = "pyxle._test_import_module"

    module = _import_server_module(key, mod_path)
    assert module.VALUE == 42
    assert sys.modules[key] is module

    # Cleanup
    sys.modules.pop(key, None)


def test_import_server_module_caches_in_production(tmp_path: Path) -> None:
    """In production (debug=False), calling twice returns the cached module."""
    from pyxle.ssr.view import _import_server_module

    mod_path = tmp_path / "test_cached.py"
    mod_path.write_text("COUNTER = 1\n", encoding="utf-8")
    key = "pyxle._test_cached_module"

    first = _import_server_module(key, mod_path, debug=False)
    assert first.COUNTER == 1
    first.COUNTER = 99

    second = _import_server_module(key, mod_path, debug=False)
    assert second is first
    assert second.COUNTER == 99  # State preserved

    sys.modules.pop(key, None)


def test_import_server_module_reimports_in_debug(tmp_path: Path) -> None:
    """In dev mode (debug=True), the module is re-executed every time."""
    from pyxle.ssr.view import _import_server_module

    mod_path = tmp_path / "test_debug.py"
    mod_path.write_text("COUNTER = 0\n", encoding="utf-8")
    key = "pyxle._test_debug_module"

    first = _import_server_module(key, mod_path, debug=True)
    assert first.COUNTER == 0
    first.COUNTER = 42

    second = _import_server_module(key, mod_path, debug=True)
    assert second is not first
    assert second.COUNTER == 0  # Reset — module was re-executed

    sys.modules.pop(key, None)
