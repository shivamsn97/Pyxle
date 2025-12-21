from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pyxle.devserver.routes import PageRoute
from pyxle.devserver.settings import DevServerSettings
from pyxle.ssr.renderer import InlineStyleFragment
from pyxle.ssr.template import render_document


@pytest.fixture
def page_route(tmp_path: Path) -> PageRoute:
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
        content_hash="abc",
        loader_name="load_home",
        loader_line=10,
        head_elements=(),
    head_is_dynamic=False,
    )


def test_render_document_injects_expected_scripts(page_route: PageRoute, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<p>Hello</p>",
        props={"data": {"greeting": "</script>"}},
        script_nonce="test-nonce",
        head_elements=page_route.head_elements,
    )

    assert "<!DOCTYPE html>" in html
    assert "<div id=\"root\">" in html
    assert "<p>Hello</p>" in html
    assert "<title>Pyxle</title>" in html
    assert "window.__PYXLE_PAGE_PATH__ = \"/pages/index.jsx\"" in html
    assert "@vite/client" in html
    assert "@react-refresh" in html
    assert "__vite_plugin_react_preamble_installed__" in html
    assert "client-entry.js" in html
    assert '"data":{"greeting":"<\\/script>"}' in html
    assert "<\\/script>" in html  # escaped closing tag in props payload
    assert 'nonce="test-nonce"' in html


def test_render_document_inlines_global_styles(page_route: PageRoute, tmp_path: Path) -> None:
    style_path = tmp_path / "styles" / "base.css"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text("body { color: #444; }\n</style>", encoding="utf-8")

    settings = DevServerSettings.from_project_root(
        tmp_path,
        global_stylesheets=("styles/base.css",),
    )

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<main></main>",
        props={},
        script_nonce="nonce",
        head_elements=page_route.head_elements,
    )

    assert 'data-pyxle-style="' in html
    assert "body { color: #444; }" in html
    # Closing tags should be escaped to avoid terminating the style prematurely.
    assert "<\\/style>" in html
    assert html.index("data-pyxle-style") < html.index("data-pyxle-head-start")


def test_render_document_includes_inline_styles(page_route: PageRoute, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<main></main>",
        props={},
        script_nonce="nonce",
        head_elements=page_route.head_elements,
        inline_styles=(
            InlineStyleFragment(
                identifier="style-inline",
                contents=".hero { color: red; }\n</style>",
                source="pages/components/hero.css",
            ),
            InlineStyleFragment(
                identifier="style-inline",
                contents=".ignored { color: blue; }",
                source="pages/ignored.css",
            ),
            InlineStyleFragment(
                identifier="style-secondary",
                contents="",
                source=None,
            ),
        ),
    )

    assert html.count('data-pyxle-inline-style="style-inline"') == 1
    assert 'data-pyxle-inline-source="pages/components/hero.css"' in html
    assert '.hero { color: red; }' in html
    assert '<\\/style>' in html
    assert 'data-pyxle-inline-style="style-secondary"' in html
    assert 'data-pyxle-inline-source="pages/ignored.css"' not in html
    assert html.index('data-pyxle-inline-style="style-inline"') < html.index('data-pyxle-head-start')


def test_render_document_uses_dynamic_route_asset_path(tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)

    dynamic_page = PageRoute(
        path="/posts/{id}",
        source_relative_path=Path("posts/[id].pyx"),
        source_absolute_path=tmp_path / "pages" / "posts" / "[id].pyx",
        server_module_path=tmp_path / "server" / "posts" / "[id].py",
        client_module_path=tmp_path / "client" / "posts" / "[id].jsx",
        metadata_path=tmp_path / "metadata" / "posts" / "[id].json",
        module_key="pyxle.server.pages.posts.[id]",
        client_asset_path="/pages/posts/[id].jsx",
        server_asset_path="/pages/posts/[id].py",
        content_hash="hash",
        loader_name="load_post",
        loader_line=12,
        head_elements=(),
        head_is_dynamic=False,
    )

    html = render_document(
        settings=settings,
        page=dynamic_page,
        body_html="<article></article>",
        props={},
        script_nonce="nonce",
        head_elements=dynamic_page.head_elements,
    )

    assert 'window.__PYXLE_PAGE_PATH__ = "/pages/posts/[id].jsx"' in html


def test_render_document_includes_custom_head(page_route: PageRoute, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)

    custom_page = replace(
        page_route,
        head_elements=(
            "<title>Custom Title</title>",
            '<meta name="description" content="Demo" />',
        ),
    )

    html = render_document(
        settings=settings,
        page=custom_page,
        body_html="<p>Body</p>",
        props={},
        script_nonce="another",
        head_elements=custom_page.head_elements,
    )

    assert "<title>Custom Title</title>" in html
    assert '<meta name="description" content="Demo" />' in html
    assert "<title>Pyxle</title>" not in html
    vite_index = html.index("@vite/client")
    custom_index = html.index("<title>Custom Title</title>")
    assert custom_index > vite_index


def test_render_document_allows_empty_nonce(page_route: PageRoute, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div></div>",
        props={},
        script_nonce="",
        head_elements=page_route.head_elements,
    )

    assert "nonce=\"" not in html


def test_render_document_uses_manifest_assets_in_production(page_route: PageRoute, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(
        tmp_path,
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

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div>Prod</div>",
        props={},
        script_nonce="secure",
        head_elements=page_route.head_elements,
    )

    assert "/client/assets/index.js" in html
    assert 'rel="stylesheet" href="/client/assets/index.css"' in html
    assert "@vite/client" not in html
    assert "client-entry.js" not in html


def test_render_document_missing_manifest_entry_shows_fallback(
    page_route: PageRoute, tmp_path: Path
) -> None:
    settings = DevServerSettings.from_project_root(
        tmp_path,
        debug=False,
        page_manifest={},
    )

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div>Prod</div>",
        props={},
        script_nonce="secure",
        head_elements=page_route.head_elements,
    )

    assert "Missing Manifest Entry" in html


def test_render_document_invalid_manifest_client_shows_fallback(
    page_route: PageRoute, tmp_path: Path
) -> None:
    settings = DevServerSettings.from_project_root(
        tmp_path,
        debug=False,
        page_manifest={"/": {"client": "oops"}},
    )

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div>Prod</div>",
        props={},
        script_nonce="secure",
        head_elements=page_route.head_elements,
    )

    assert "Missing Manifest Entry" in html


def test_render_document_missing_manifest_file_shows_fallback(
    page_route: PageRoute, tmp_path: Path
) -> None:
    settings = DevServerSettings.from_project_root(
        tmp_path,
        debug=False,
        page_manifest={"/": {"client": {"file": ""}}},
    )

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div>Prod</div>",
        props={},
        script_nonce="secure",
        head_elements=page_route.head_elements,
    )

    assert "Missing Manifest Entry" in html


def test_render_document_ignores_non_list_css_assets(
    page_route: PageRoute, tmp_path: Path
) -> None:
    settings = DevServerSettings.from_project_root(
        tmp_path,
        debug=False,
        page_manifest={
            "/": {
                "client": {
                    "file": "assets/index.js",
                    "css": "not-a-list",
                }
            }
        },
    )

    html = render_document(
        settings=settings,
        page=page_route,
        body_html="<div>Prod</div>",
        props={},
        script_nonce="secure",
        head_elements=page_route.head_elements,
    )

    assert "/client/assets/index.js" in html
    assert 'rel="stylesheet"' not in html


def test_render_document_skips_blank_head_fragments(
    page_route: PageRoute, tmp_path: Path
) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)
    custom = replace(
        page_route,
        head_elements=(
            "",
            '<meta name="description" content="Demo" />\n<link rel="icon" href="/favicon.ico" />',
        ),
    )

    html = render_document(
        settings=settings,
        page=custom,
        body_html="<div>Body</div>",
        props={},
        script_nonce="nonce",
        head_elements=custom.head_elements,
    )

    assert '<meta name="description" content="Demo" />' in html
    assert '<link rel="icon" href="/favicon.ico" />' in html
    assert html.count('<link rel="icon" href="/favicon.ico" />') == 1