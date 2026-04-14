from __future__ import annotations

from pathlib import Path

from pyxle.devserver.client_files import (
    CLIENT_ENTRY_FILENAME,
    CLIENT_HTML_FILENAME,
    TSCONFIG_FILENAME,
    VITE_CONFIG_FILENAME,
    _build_public_env_defines,
    _render_client_entry,
    _render_client_index,
    _render_client_runtime_index_types,
    _render_client_runtime_link_types,
    _render_slot_runtime,
    _render_slot_runtime_types,
    _render_tsconfig,
    _render_use_pathname_component,
    _render_use_pathname_component_types,
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


def test_client_entry_includes_global_script_imports_before_styles(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()
    script_path = root / "scripts" / "analytics.js"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("console.log('analytics');\n", encoding="utf-8")
    style_path = root / "styles" / "theme.css"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text("body { color: rebeccapurple; }\n", encoding="utf-8")

    settings = DevServerSettings.from_project_root(
        root,
        global_scripts=("scripts/analytics.js",),
        global_stylesheets=("styles/theme.css",),
    )

    write_client_bootstrap_files(settings)

    client_entry = (settings.client_build_dir / CLIENT_ENTRY_FILENAME).read_text(encoding="utf-8")
    script_import = f"import '{settings.global_scripts[0].import_specifier}';"
    style_import = f"import '{settings.global_stylesheets[0].import_specifier}';"

    assert script_import in client_entry
    assert style_import in client_entry
    assert client_entry.index(script_import) < client_entry.index("import React from 'react';")
    assert client_entry.index(script_import) < client_entry.index(style_import)


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


def test_client_entry_includes_nav_progress_bar(tmp_path: Path) -> None:
    """Client runtime ships a navigation progress bar IIFE that
    ``markNavigating`` calls on start/finish. The bar is always
    present (dev AND prod) and integrates transparently — no user
    opt-in required."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    # Module initialised as a top-level const IIFE — keeps state
    # encapsulated so nothing leaks onto window.
    assert "const navProgress = (function initNavProgress()" in entry
    assert "return { start: start, finish: finish };" in entry

    # Stable DOM ids — users can style the bar by targeting these
    # directly, so changing them is a breaking change.
    assert "__pyxle_nav_progress__" in entry
    assert "__pyxle_nav_progress_style__" in entry

    # CSS custom properties for user overrides.
    assert "--pyxle-nav-progress-height" in entry
    assert "--pyxle-nav-progress-color" in entry
    assert "--pyxle-nav-progress-shadow" in entry

    # markNavigating is wired up to the progress bar on both
    # edges of every navigation.
    assert "navProgress.start()" in entry
    assert "navProgress.finish()" in entry


def test_client_entry_nav_progress_includes_opt_out_hooks(tmp_path: Path) -> None:
    """Two opt-out mechanisms must be present: a window global
    checked lazily (so it can be set before the runtime loads) and
    a data attribute on <html> (so SSR-side rendering can disable
    it per-page without JS)."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    assert "window.__pyxle_disable_progress__ === true" in entry
    assert "data-pyxle-progress" in entry
    assert "'off'" in entry  # the attribute value that disables the bar


def test_client_entry_nav_progress_accessibility(tmp_path: Path) -> None:
    """The progress bar element carries ARIA progressbar semantics
    so screen readers announce navigation as 'Loading page' with a
    live 0-100 value."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    assert "'role', 'progressbar'" in entry
    assert "'aria-label', 'Loading page'" in entry
    assert "'aria-valuemin', '0'" in entry
    assert "'aria-valuemax', '100'" in entry
    assert "aria-valuenow" in entry


def test_client_entry_nav_progress_respects_reduced_motion(tmp_path: Path) -> None:
    """Users with `prefers-reduced-motion: reduce` see a static bar
    (snap to 30%, no ticking decay) instead of animated progress."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    assert "prefers-reduced-motion: reduce" in entry
    assert "prefersReducedMotion" in entry


def test_client_entry_nav_progress_is_present_in_both_dev_and_prod(tmp_path: Path) -> None:
    """The progress bar is a user-experience feature, not a debug
    tool — it must ship in both dev and production builds."""
    root = tmp_path / "project"
    (root / "pages").mkdir(parents=True)
    (root / "public").mkdir()

    dev_entry = _render_client_entry(
        DevServerSettings.from_project_root(root, debug=True)
    )
    prod_entry = _render_client_entry(
        DevServerSettings.from_project_root(root, debug=False)
    )

    for entry in (dev_entry, prod_entry):
        assert "const navProgress = (function initNavProgress()" in entry
        assert "navProgress.start()" in entry
        assert "navProgress.finish()" in entry


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


def test_build_public_env_defines_empty(monkeypatch) -> None:
    """No PYXLE_PUBLIC_ vars means no define block."""

    # Clear any existing PYXLE_PUBLIC_ vars
    for key in list(k for k in __import__("os").environ if k.startswith("PYXLE_PUBLIC_")):
        monkeypatch.delenv(key, raising=False)

    result = _build_public_env_defines()
    assert result == ""


def test_build_public_env_defines_injects_vars(monkeypatch) -> None:
    """PYXLE_PUBLIC_ vars are injected as import.meta.env defines."""

    monkeypatch.setenv("PYXLE_PUBLIC_API_URL", "https://api.example.com")
    monkeypatch.setenv("PYXLE_PUBLIC_APP_NAME", "MyApp")

    result = _build_public_env_defines()
    assert "define:" in result
    assert "'import.meta.env.PYXLE_PUBLIC_API_URL': \"https://api.example.com\"" in result
    assert "'import.meta.env.PYXLE_PUBLIC_APP_NAME': \"MyApp\"" in result


def test_vite_config_includes_public_env_defines(tmp_path: Path, monkeypatch) -> None:
    """Full Vite config includes the define block when PYXLE_PUBLIC_ vars are set."""

    monkeypatch.setenv("PYXLE_PUBLIC_SITE_NAME", "TestSite")

    settings = create_project(tmp_path)
    vite_config = _render_vite_config(settings)

    assert "define:" in vite_config
    assert "import.meta.env.PYXLE_PUBLIC_SITE_NAME" in vite_config
    assert '"TestSite"' in vite_config


def test_vite_config_no_define_block_without_public_vars(tmp_path: Path, monkeypatch) -> None:
    """Vite config omits define block when no PYXLE_PUBLIC_ vars exist."""

    for key in list(k for k in __import__("os").environ if k.startswith("PYXLE_PUBLIC_")):
        monkeypatch.delenv(key, raising=False)

    settings = create_project(tmp_path)
    vite_config = _render_vite_config(settings)

    assert "define:" not in vite_config


def test_build_public_env_defines_escapes_special_chars(monkeypatch) -> None:
    """Values with special characters are properly JSON-escaped."""

    monkeypatch.setenv("PYXLE_PUBLIC_MSG", 'Hello "World" & <Friends>')

    result = _build_public_env_defines()
    assert "define:" in result
    # JSON encoding should escape the double quotes
    assert r'\"World\"' in result


# ---------------------------------------------------------------------------
# BFCache restore handler
# ---------------------------------------------------------------------------


def test_client_entry_includes_bfcache_pageshow_handler(tmp_path: Path) -> None:
    """The client runtime registers a ``pageshow`` listener so that a
    BFCache restore triggers ``router.refresh()``. Without this a user
    who backgrounds a tab for a long time and comes back can see stale
    content (or raw JSON if the browser's HTTP cache confused the
    HTML/JSON variants for the same URL)."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    assert "addEventListener('pageshow'" in entry or 'addEventListener("pageshow"' in entry
    assert "event.persisted" in entry
    assert "router.refresh()" in entry


# ---------------------------------------------------------------------------
# usePathname hook
# ---------------------------------------------------------------------------


def test_client_entry_dispatches_route_change_event(tmp_path: Path) -> None:
    """The client runtime dispatches a ``pyxle:routechange`` custom event
    after both ``navigateTo`` and ``refreshCurrentPage`` complete.  This
    is the signal consumed by ``usePathname()``."""
    settings = create_project(tmp_path)
    entry = _render_client_entry(settings)

    assert "pyxle:routechange" in entry
    # Must appear at least twice: once in navigateTo, once in refreshCurrentPage.
    assert entry.count("pyxle:routechange") >= 2


def test_use_pathname_component_is_ssr_safe() -> None:
    """The generated usePathname hook must guard window access for SSR."""
    source = _render_use_pathname_component()
    assert "typeof window" in source
    assert "usePathname" in source
    assert "pyxle:routechange" in source


def test_use_pathname_component_types() -> None:
    """Type definition declares usePathname returning a string."""
    types = _render_use_pathname_component_types()
    assert "usePathname" in types
    assert "string" in types


def test_write_client_bootstrap_files_generates_use_pathname(tmp_path: Path) -> None:
    """Bootstrap writes both the JSX hook and its type declaration."""
    settings = create_project(tmp_path)
    write_client_bootstrap_files(settings)

    hook = (settings.client_build_dir / "pyxle" / "use-pathname.jsx").read_text(encoding="utf-8")
    assert "usePathname" in hook
    assert "pyxle:routechange" in hook

    types = (settings.client_build_dir / "pyxle" / "use-pathname.d.ts").read_text(encoding="utf-8")
    assert "usePathname" in types
