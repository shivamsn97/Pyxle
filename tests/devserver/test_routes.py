from __future__ import annotations

from pathlib import Path

import pytest

from pyxle.devserver.builder import build_once
from pyxle.devserver.path_utils import (
    route_path_from_relative,
    route_path_variants_from_relative,
)
from pyxle.devserver.registry import load_metadata_registry
from pyxle.devserver.routes import build_route_table
from pyxle.devserver.settings import DevServerSettings


@pytest.fixture
def project(tmp_path: Path) -> DevServerSettings:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    settings = DevServerSettings.from_project_root(root)

    write_file(
        settings.pages_dir / "index.pyx",
        """\n\nHEAD = \"<title>Home</title>\"\n\n@server\nasync def load_home(request):\n    return {\"message\": \"hi\"}\n\n# --- JavaScript/PSX (Client + Server) ---\n\nimport React from 'react';\n\nexport default function Home({ data }) {\n    return <div>{data.message}</div>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "blog/index.pyx",
        """import React from 'react';\n\nexport default function BlogIndex() {\n    return <section>Blog</section>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "posts/[id].pyx",
        """import React from 'react';\n\nexport default function Post({ data }) {\n    return <article>{data.title}</article>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "docs/[[...slug]].pyx",
        """import React from 'react';\n\nexport default function Docs() {\n    return <article>Docs</article>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "(marketing)/about.pyx",
        """import React from 'react';\n\nexport default function About() {\n    return <section>About</section>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "api/greet.py",
        """async def endpoint(request):\n    return {\"message\": \"hello\"}\n""",
    )

    write_file(
        settings.pages_dir / "api/posts/[id].py",
        """async def endpoint(request):\n    return {\"id\": request.path_params.get(\"id\")}\n""",
    )

    write_file(
        settings.pages_dir / "api/files/[[...path]].py",
        """async def endpoint(request):\n    return {\"path\": request.path_params.get(\"path\")}\n""",
    )

    return settings


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_route_path_from_relative_converts_dynamic_segments() -> None:
    assert route_path_from_relative(Path("index.pyx")) == "/"
    assert route_path_from_relative(Path("posts/[id].pyx")) == "/posts/{id}"
    assert route_path_from_relative(Path("blog/index.pyx")) == "/blog"
    assert route_path_from_relative(Path("api/posts/[id].py")) == "/api/posts/{id}"
    assert route_path_from_relative(Path("(marketing)/about.pyx")) == "/about"
    assert route_path_from_relative(Path("docs/[...slug].pyx")) == "/docs/{slug:path}"
    assert route_path_from_relative(Path("[[...slug]].pyx")) == "/"


def test_route_path_variants_include_optional_catchall() -> None:
    spec = route_path_variants_from_relative(Path("docs/[[...slug]].pyx"))
    assert spec.primary == "/docs"
    assert spec.aliases == ("/docs/{slug:path}",)

    root_spec = route_path_variants_from_relative(Path("[[...segments]].pyx"))
    assert root_spec.primary == "/"
    assert root_spec.aliases == ("/{segments:path}",)


def test_build_route_table_generates_expected_descriptors(project: DevServerSettings) -> None:
    build_once(project)
    registry = load_metadata_registry(project)

    table = build_route_table(registry)

    page_paths = {route.path for route in table.pages}
    api_paths = {route.path for route in table.apis}

    assert page_paths == {
        "/",
        "/blog",
        "/posts/{id}",
        "/docs",
        "/docs/{slug:path}",
        "/about",
    }
    assert api_paths == {"/api/greet", "/api/posts/{id}", "/api/files", "/api/files/{path:path}"}

    home_route = table.find_page("/")
    assert home_route is not None
    assert home_route.has_loader is True
    assert home_route.loader_name == "load_home"
    assert home_route.module_key == "pyxle.server.pages.index"
    assert home_route.client_asset_path == "/pages/index.jsx"
    assert home_route.head_elements == ("<title>Home</title>",)

    blog_route = table.find_page("/blog")
    assert blog_route is not None
    assert blog_route.path == "/blog"
    assert blog_route.server_module_path.as_posix().endswith("server/pages/blog/index.py")
    assert blog_route.head_elements == ()

    dynamic_route = table.find_page("/posts/{id}")
    assert dynamic_route is not None
    assert dynamic_route.has_loader is False
    assert dynamic_route.module_key == "pyxle.server.pages.posts.id"
    assert dynamic_route.head_elements == ()

    optional_base = table.find_page("/docs")
    optional_alias = table.find_page("/docs/{slug:path}")
    assert optional_base is not None
    assert optional_alias is not None
    assert optional_base.client_module_path == optional_alias.client_module_path

    grouped_route = table.find_page("/about")
    assert grouped_route is not None
    assert grouped_route.source_relative_path.as_posix() == "(marketing)/about.pyx"

    api_route = table.find_api("/api/posts/{id}")
    assert api_route is not None
    assert api_route.module_key == "pyxle.server.api.posts.id"
    assert api_route.server_module_path.as_posix().endswith("server/api/posts/[id].py")

    optional_api_base = table.find_api("/api/files")
    optional_api_alias = table.find_api("/api/files/{path:path}")
    assert optional_api_base is not None
    assert optional_api_alias is not None
    assert optional_api_base.source_relative_path == optional_api_alias.source_relative_path

    # Ensure dynamic conversion always uses braces regardless of metadata source.
    for route in table.pages + table.apis:
        assert "[" not in route.path and "]" not in route.path


def test_build_route_table_falls_back_to_inferred_path(project: DevServerSettings) -> None:
    build_once(project)

    metadata_path = project.metadata_build_dir / "pages" / "index.json"
    payload = metadata_path.read_text(encoding="utf-8")
    metadata_path.write_text(payload.replace("\"route_path\": \"/\"", "\"route_path\": \"/home-custom\""), encoding="utf-8")

    registry = load_metadata_registry(project)
    table = build_route_table(registry)

    route = table.find_page("/")
    assert route is not None
    assert route.path == "/"

    missing = table.find_api("/does-not-exist")
    assert missing is None

