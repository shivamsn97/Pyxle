from __future__ import annotations

from pathlib import Path

import pytest

from pyxle.devserver.scanner import SourceKind, scan_source_tree
from pyxle.devserver.settings import DevServerSettings


@pytest.fixture
def project(tmp_path: Path) -> DevServerSettings:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    return DevServerSettings.from_project_root(root)


def write_page(project: DevServerSettings, relative_path: str, content: str) -> Path:
    path = project.pages_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_scan_source_tree_returns_sorted_entries(project: DevServerSettings) -> None:
    write_page(project, "about.pyx", "<div>About</div>\n")
    write_page(project, "api/pulse.py", "async def endpoint(request):\n    return None\n")
    write_page(project, "team/index.pyx", "<div>Team</div>\n")
    write_page(project, "components/layout.jsx", "export const Layout = () => null;\n")

    entries = scan_source_tree(project)

    assert [entry.relative_path.as_posix() for entry in entries] == [
        "about.pyx",
        "api/pulse.py",
        "components/layout.jsx",
        "team/index.pyx",
    ]

    kinds = [entry.kind for entry in entries]
    assert kinds == [SourceKind.PAGE, SourceKind.API, SourceKind.CLIENT_ASSET, SourceKind.PAGE]


def test_scan_source_tree_includes_hashes(project: DevServerSettings) -> None:
    page_path = write_page(project, "about.pyx", "<div>About</div>\n")

    entries = scan_source_tree(project)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind is SourceKind.PAGE
    assert entry.absolute_path == page_path
    assert entry.relative_path.as_posix() == "about.pyx"
    assert len(entry.content_hash) == 64


def test_scan_source_tree_ignores_non_py_or_pyx(project: DevServerSettings) -> None:
    write_page(project, "about.pyx", "<div>About</div>\n")
    write_page(project, "api/pulse.py", "async def endpoint(request): return None\n")
    (project.pages_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

    entries = scan_source_tree(project)

    assert len(entries) == 2
    assert all(entry.relative_path.suffix in {".py", ".pyx"} for entry in entries)


def test_scan_source_tree_ignores_python_outside_api(project: DevServerSettings) -> None:
    write_page(project, "api/pulse.py", "async def endpoint(request): return None\n")
    write_page(project, "components/helpers/__init__.py", "value = 1\n")

    entries = scan_source_tree(project)

    paths = [entry.relative_path.as_posix() for entry in entries]
    assert paths == ["api/pulse.py"]


def test_scan_source_tree_detects_client_assets(project: DevServerSettings) -> None:
    write_page(project, "components/layout.jsx", "export const Layout = () => null;\n")

    entries = scan_source_tree(project)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind is SourceKind.CLIENT_ASSET
    assert entry.relative_path.as_posix() == "components/layout.jsx"


def test_scan_source_tree_ignores_internal_build_cache(project: DevServerSettings) -> None:
    write_page(project, "about.pyx", "<div>About</div>\n")
    build_dir = project.pages_dir / ".pyxle-build" / "server" / "pages"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "about.py").write_text("from pyxle.runtime import server\n", encoding="utf-8")

    entries = scan_source_tree(project)

    assert [entry.relative_path.as_posix() for entry in entries] == ["about.pyx"]


def test_scan_source_tree_returns_empty_when_pages_missing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "public").mkdir()
    settings = DevServerSettings.from_project_root(root)

    assert scan_source_tree(settings) == []
