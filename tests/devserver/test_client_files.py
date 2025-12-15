from __future__ import annotations

from pathlib import Path

from pyxle.devserver.client_files import (
    CLIENT_ENTRY_FILENAME,
    CLIENT_HTML_FILENAME,
    TSCONFIG_FILENAME,
    VITE_CONFIG_FILENAME,
    _render_client_entry,
    _render_client_index,
    _render_client_runtime_index_types,
    _render_client_runtime_link_types,
    _render_slot_runtime,
    _render_slot_runtime_types,
    _render_tsconfig,
    _render_vite_config,
    write_client_bootstrap_files,
)
from pyxle.devserver.settings import DevServerSettings


def create_project(tmp_path: Path) -> DevServerSettings:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    return DevServerSettings.from_project_root(root)


def test_write_client_bootstrap_files_generates_expected_artifacts(tmp_path: Path) -> None:
    settings = create_project(tmp_path)

    write_client_bootstrap_files(settings)

    client_root = settings.client_build_dir
    index_html = (client_root / CLIENT_HTML_FILENAME).read_text(encoding="utf-8")
    vite_config = (client_root / VITE_CONFIG_FILENAME).read_text(encoding="utf-8")
    client_entry = (client_root / CLIENT_ENTRY_FILENAME).read_text(encoding="utf-8")
    tsconfig = (client_root / TSCONFIG_FILENAME).read_text(encoding="utf-8")
    slot_runtime = (client_root / "pyxle" / "slot.jsx").read_text(encoding="utf-8")
    index_types = (client_root / "pyxle" / "index.d.ts").read_text(encoding="utf-8")
    link_types = (client_root / "pyxle" / "link.d.ts").read_text(encoding="utf-8")
    slot_types = (client_root / "pyxle" / "slot.d.ts").read_text(encoding="utf-8")

    assert index_html == _render_client_index()
    assert vite_config == _render_vite_config(settings)
    assert client_entry == _render_client_entry(settings)
    assert tsconfig == _render_tsconfig()
    assert slot_runtime == _render_slot_runtime()
    assert index_types == _render_client_runtime_index_types()
    assert link_types == _render_client_runtime_link_types()
    assert slot_types == _render_slot_runtime_types()


def test_write_client_bootstrap_files_is_idempotent(tmp_path: Path) -> None:
    settings = create_project(tmp_path)

    write_client_bootstrap_files(settings)
    first_contents = {
        name: (settings.client_build_dir / name).read_text(encoding="utf-8")
        for name in (
            CLIENT_HTML_FILENAME,
            VITE_CONFIG_FILENAME,
            CLIENT_ENTRY_FILENAME,
            TSCONFIG_FILENAME,
            "pyxle/slot.jsx",
            "pyxle/index.d.ts",
            "pyxle/link.d.ts",
            "pyxle/slot.d.ts",
        )
    }

    write_client_bootstrap_files(settings)

    second_contents = {
        name: (settings.client_build_dir / name).read_text(encoding="utf-8")
        for name in (
            CLIENT_HTML_FILENAME,
            VITE_CONFIG_FILENAME,
            CLIENT_ENTRY_FILENAME,
            TSCONFIG_FILENAME,
            "pyxle/slot.jsx",
            "pyxle/index.d.ts",
            "pyxle/link.d.ts",
            "pyxle/slot.d.ts",
        )
    }

    assert first_contents == second_contents


def test_client_entry_includes_global_style_imports(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    style_path = root / "styles" / "theme.css"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text("body { color: hotpink; }\n", encoding="utf-8")

    settings = DevServerSettings.from_project_root(
        root,
        global_stylesheets=("styles/theme.css",),
    )

    write_client_bootstrap_files(settings)

    client_entry = (settings.client_build_dir / CLIENT_ENTRY_FILENAME).read_text(encoding="utf-8")
    import_statement = settings.global_stylesheets[0].import_specifier
    assert f"import '{import_statement}';" in client_entry


def test_client_entry_omits_overlay_in_production(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()

    dev_settings = DevServerSettings.from_project_root(root, debug=True)
    prod_settings = DevServerSettings.from_project_root(root, debug=False)

    dev_entry = _render_client_entry(dev_settings)
    prod_entry = _render_client_entry(prod_settings)

    assert "__PYXLE_ERROR_OVERLAY__" in dev_entry
    assert "/__pyxle__/overlay" in dev_entry
    assert "__PYXLE_ERROR_OVERLAY__" not in prod_entry
    assert "/__pyxle__/overlay" not in prod_entry


def test_vite_config_aliases_cover_client_runtime(tmp_path: Path) -> None:
    settings = create_project(tmp_path)
    vite_config = _render_vite_config(settings)

    assert "find: /^pyxle\\/client$/" in vite_config
    assert "find: /^pyxle\\/client\\/(.+)$/" in vite_config
    assert "find: 'pyxle/client'" not in vite_config


def test_vite_config_respects_base_environment(tmp_path: Path) -> None:
    settings = create_project(tmp_path)
    vite_config = _render_vite_config(settings)

    assert "const base = process.env.PYXLE_VITE_BASE ?? '/';" in vite_config
    assert "base," in vite_config
