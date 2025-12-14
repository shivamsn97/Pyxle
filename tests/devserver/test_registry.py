from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyxle.devserver.build import load_build_metadata
from pyxle.devserver.builder import build_once
from pyxle.devserver.registry import build_metadata_registry, load_metadata_registry
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
        settings.pages_dir / "posts/[id].pyx",
        """import React from 'react';\n\nexport default function Post({ data }) {\n    return <article>{data.title}</article>;\n}\n""",
    )

    write_file(
        settings.pages_dir / "api/greet.py",
        """async def endpoint(request):\n    return {\"message\": \"hello\"}\n""",
    )

    write_file(
        settings.pages_dir / "api/posts/[id].py",
        """async def endpoint(request):\n    return {\"id\": request.path_params.get(\"id\")}\n""",
    )

    return settings


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_metadata_registry_includes_pages_and_apis(project: DevServerSettings) -> None:
    build_once(project)

    registry = load_metadata_registry(project)
    metadata = load_build_metadata(project.build_root)

    assert {entry.route_path for entry in registry.pages} == {"/", "/posts/{id}"}
    assert {entry.route_path for entry in registry.apis} == {"/api/greet", "/api/posts/{id}"}
    assert all(entry.alternate_route_paths == tuple() for entry in registry.pages)
    assert all(entry.alternate_route_paths == tuple() for entry in registry.apis)

    home = registry.find_page("/")
    assert home is not None
    assert home.has_loader is True
    assert home.loader_name == "load_home"
    assert isinstance(home.loader_line, int)
    assert home.client_asset_path == "/pages/index.jsx"
    assert home.server_asset_path == "/pages/index.py"
    assert home.module_key == "pyxle.server.pages.index"
    assert home.head_elements == ("<title>Home</title>",)
    assert metadata.sources["index.pyx"].content_hash == home.content_hash

    dynamic_page = registry.find_page("/posts/{id}")
    assert dynamic_page is not None
    assert dynamic_page.loader_name is None
    assert dynamic_page.module_key == "pyxle.server.pages.posts.id"
    assert dynamic_page.head_elements == ()
    assert metadata.sources["posts/[id].pyx"].content_hash == dynamic_page.content_hash

    api_entry = registry.find_api("/api/greet")
    assert api_entry is not None
    assert api_entry.module_key == "pyxle.server.api.greet"
    assert metadata.sources["api/greet.py"].content_hash == api_entry.content_hash

    dynamic_api = registry.find_api("/api/posts/{id}")
    assert dynamic_api is not None
    assert dynamic_api.module_key == "pyxle.server.api.posts.id"
    assert metadata.sources["api/posts/[id].py"].content_hash == dynamic_api.content_hash

    assert registry.find_page("/missing") is None
    assert registry.find_api("/missing") is None

    serialized = registry.to_dict()
    assert {page["route_path"] for page in serialized["pages"]} == {"/", "/posts/{id}"}
    assert all(not page.get("alternate_route_paths") for page in serialized["pages"])
    assert {api["route_path"] for api in serialized["apis"]} == {"/api/greet", "/api/posts/{id}"}
    assert all(not api.get("alternate_route_paths") for api in serialized["apis"])


def test_registry_skips_missing_artifacts(project: DevServerSettings) -> None:
    build_once(project)
    metadata = load_build_metadata(project.build_root)

    # Remove metadata JSON and server artifact for specific entries to simulate partial builds.
    (project.metadata_build_dir / "pages" / "index.json").unlink(missing_ok=True)
    (project.server_build_dir / "api" / "greet.py").unlink(missing_ok=True)

    registry = build_metadata_registry(project, metadata)

    page_routes = {entry.route_path for entry in registry.pages}
    api_routes = {entry.route_path for entry in registry.apis}

    assert page_routes == {"/posts/{id}"}
    assert api_routes == {"/api/posts/{id}"}


def test_registry_recovers_from_invalid_loader_metadata(project: DevServerSettings) -> None:
    build_once(project)
    metadata_path = project.metadata_build_dir / "pages" / "index.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["loader_line"] = "not-an-int"
    payload["loader_name"] = ["not-a-string"]
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    metadata = load_build_metadata(project.build_root)
    registry = build_metadata_registry(project, metadata)

    entry = registry.find_page("/")
    assert entry is not None
    assert entry.loader_line is None
    assert entry.loader_name is None


def test_module_key_sanitizes_segments() -> None:
    from pyxle.devserver import registry as registry_module

    key = registry_module._module_key(
        Path("api/[1-2]/123 slug-lives/[]/file.name.py"),
        prefix="pyxle.server.api",
        drop_leading="api",
    )

    assert key == "pyxle.server.api._1_2._123_slug_lives._.file_name"


def test_load_page_metadata_handles_non_dict_payload(tmp_path: Path) -> None:
    from pyxle.devserver import registry as registry_module

    path = tmp_path / "meta.json"
    path.write_text("[]", encoding="utf-8")

    assert registry_module._load_page_metadata(path) is None


def test_load_page_metadata_handles_decode_errors(tmp_path: Path) -> None:
    from pyxle.devserver import registry as registry_module

    path = tmp_path / "broken.json"
    path.write_text("{invalid", encoding="utf-8")

    assert registry_module._load_page_metadata(path) is None


def test_load_page_metadata_rejects_non_string_fields(tmp_path: Path) -> None:
    from pyxle.devserver import registry as registry_module

    path = tmp_path / "meta.json"
    payload = {
        "route_path": 123,
        "client_path": "/client",
        "server_path": "/server",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert registry_module._load_page_metadata(path) is None


def test_load_page_metadata_rejects_invalid_head(tmp_path: Path) -> None:
    from pyxle.devserver import registry as registry_module

    path = tmp_path / "meta.json"
    payload = {
        "route_path": "/",
        "client_path": "/pages/index.jsx",
        "server_path": "/pages/index.py",
        "head": ["<title>Home</title>", 123],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert registry_module._load_page_metadata(path) is None


def test_load_page_metadata_defaults_head_when_missing(tmp_path: Path) -> None:
    from pyxle.devserver import registry as registry_module

    path = tmp_path / "meta.json"
    payload = {
        "route_path": "/",
        "client_path": "/pages/index.jsx",
        "server_path": "/pages/index.py",
        "loader_name": "load_home",
        "loader_line": 10,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    metadata = registry_module._load_page_metadata(path)

    assert metadata is not None
    assert metadata.head_elements == ()
