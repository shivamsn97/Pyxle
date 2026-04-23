"""Tests for ``pyxle.plugins`` — the Django-style plugin system.

Plugin resolution, service registry semantics, and lifecycle ordering
are all covered here. The scenarios intentionally exercise failure
modes (missing modules, bad attribute names, duplicate service names)
because plugin authors hit those the most often and deserve clear
errors.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from pyxle.plugins import (
    PluginContext,
    PluginError,
    PluginResolutionError,
    PluginServiceError,
    PluginSpec,
    PyxlePlugin,
    active_context,
    load_plugins,
    plugin,
    run_shutdown,
    run_startup,
    set_active_context,
)


# ---------------------------------------------------------------------------
# PluginSpec.from_config_entry


class TestPluginSpecFromConfigEntry:
    def test_bare_string_derives_module_from_name(self) -> None:
        spec = PluginSpec.from_config_entry("pyxle-auth")
        assert spec.name == "pyxle-auth"
        assert spec.module == "pyxle_auth.plugin"
        assert spec.attribute == "plugin"
        assert spec.settings == {}

    def test_object_uses_provided_module_override(self) -> None:
        spec = PluginSpec.from_config_entry(
            {"name": "myapp", "module": "elsewhere.custom", "attribute": "Plugin"}
        )
        assert spec.module == "elsewhere.custom"
        assert spec.attribute == "Plugin"

    def test_object_carries_settings(self) -> None:
        spec = PluginSpec.from_config_entry(
            {"name": "pyxle-auth", "settings": {"cookieDomain": ".pyxle.app"}}
        )
        assert spec.settings == {"cookieDomain": ".pyxle.app"}

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(PluginError, match="Empty plugin name"):
            PluginSpec.from_config_entry("")

    def test_object_missing_name_rejected(self) -> None:
        with pytest.raises(PluginError, match="missing a non-empty 'name'"):
            PluginSpec.from_config_entry({"module": "foo.plugin"})

    def test_wrong_entry_type_rejected(self) -> None:
        with pytest.raises(PluginError, match="must be a string or object"):
            PluginSpec.from_config_entry(42)  # type: ignore[arg-type]

    def test_settings_must_be_object(self) -> None:
        with pytest.raises(PluginError, match="'settings' must be an object"):
            PluginSpec.from_config_entry(
                {"name": "x", "settings": ["not", "an", "object"]}
            )


# ---------------------------------------------------------------------------
# PluginContext service registry


class TestPluginContext:
    def test_register_and_retrieve(self) -> None:
        ctx = PluginContext()
        ctx.register("db.database", "<database>")
        assert ctx.get("db.database") == "<database>"
        assert ctx.require("db.database") == "<database>"
        assert ctx.has("db.database")

    def test_require_missing_raises_with_available_names(self) -> None:
        ctx = PluginContext()
        ctx.register("a", 1)
        ctx.register("b", 2)
        with pytest.raises(PluginServiceError, match=r"Available: \['a', 'b'\]"):
            ctx.require("c")

    def test_double_register_rejected(self) -> None:
        ctx = PluginContext()
        ctx.register("x", 1)
        with pytest.raises(PluginServiceError, match="already registered"):
            ctx.register("x", 2)

    def test_replace_overwrites_without_error(self) -> None:
        ctx = PluginContext()
        ctx.register("x", 1)
        ctx.replace("x", 2)
        assert ctx.require("x") == 2

    def test_get_returns_default_when_absent(self) -> None:
        ctx = PluginContext()
        assert ctx.get("nope", "fallback") == "fallback"

    def test_empty_name_rejected(self) -> None:
        ctx = PluginContext()
        with pytest.raises(PluginServiceError):
            ctx.register("", "anything")
        with pytest.raises(PluginServiceError):
            ctx.replace("", "anything")

    def test_names_are_sorted(self) -> None:
        ctx = PluginContext()
        ctx.register("b", 1)
        ctx.register("a", 1)
        ctx.register("c", 1)
        assert ctx.names() == ("a", "b", "c")


# ---------------------------------------------------------------------------
# load_plugins


def _install_fake_module(name: str, attributes: dict[str, Any]) -> None:
    """Drop a synthetic module into sys.modules for load_plugins to resolve.

    Tests clean up in a finalizer to keep the global namespace tidy.
    """
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module


@pytest.fixture
def cleanup_modules():
    installed: list[str] = []
    yield installed
    for name in installed:
        sys.modules.pop(name, None)


class _RecorderPlugin(PyxlePlugin):
    name = "recorder"
    version = "0.0.1"

    def __init__(self) -> None:
        self.started = False
        self.shutdown = False

    async def on_startup(self, ctx: PluginContext) -> None:
        self.started = True
        ctx.register(f"{self.name}.service", self)

    async def on_shutdown(self, ctx: PluginContext) -> None:
        self.shutdown = True


class TestLoadPlugins:
    def test_instance_attribute_used_as_is(self, cleanup_modules) -> None:
        instance = _RecorderPlugin()
        _install_fake_module("fake_plugin_a.plugin", {"plugin": instance})
        cleanup_modules.extend(["fake_plugin_a.plugin"])

        spec = PluginSpec.from_config_entry("fake-plugin-a")
        [loaded] = load_plugins([spec])
        assert loaded is instance

    def test_class_attribute_instantiated(self, cleanup_modules) -> None:
        _install_fake_module("fake_plugin_b.plugin", {"plugin": _RecorderPlugin})
        cleanup_modules.extend(["fake_plugin_b.plugin"])

        spec = PluginSpec.from_config_entry("fake-plugin-b")
        [loaded] = load_plugins([spec])
        assert isinstance(loaded, _RecorderPlugin)

    def test_non_pyxle_plugin_class_rejected(self, cleanup_modules) -> None:
        class NotAPlugin:
            pass

        _install_fake_module("fake_plugin_c.plugin", {"plugin": NotAPlugin})
        cleanup_modules.extend(["fake_plugin_c.plugin"])

        with pytest.raises(PluginResolutionError, match="doesn't subclass"):
            load_plugins([PluginSpec.from_config_entry("fake-plugin-c")])

    def test_missing_module_raises(self) -> None:
        with pytest.raises(PluginResolutionError, match="could not import module"):
            load_plugins([PluginSpec.from_config_entry("no-such-plugin-never-installed")])

    def test_missing_attribute_raises(self, cleanup_modules) -> None:
        _install_fake_module("fake_plugin_d.plugin", {"other": object()})
        cleanup_modules.extend(["fake_plugin_d.plugin"])

        with pytest.raises(PluginResolutionError, match="no attribute 'plugin'"):
            load_plugins([PluginSpec.from_config_entry("fake-plugin-d")])

    def test_settings_propagated_to_instance(self, cleanup_modules) -> None:
        _install_fake_module("fake_plugin_e.plugin", {"plugin": _RecorderPlugin})
        cleanup_modules.extend(["fake_plugin_e.plugin"])

        spec = PluginSpec.from_config_entry(
            {"name": "fake-plugin-e", "settings": {"k": "v"}}
        )
        [loaded] = load_plugins([spec])
        assert loaded.settings == {"k": "v"}


# ---------------------------------------------------------------------------
# Lifecycle


@pytest.fixture
def anyio_backend() -> str:  # pragma: no cover - fixture wiring
    return "asyncio"


@pytest.mark.anyio
class TestLifecycle:
    async def test_startup_runs_in_declaration_order(self) -> None:
        order: list[str] = []

        class A(PyxlePlugin):
            name = "a"

            async def on_startup(self, ctx: PluginContext) -> None:
                order.append("a")

        class B(PyxlePlugin):
            name = "b"

            async def on_startup(self, ctx: PluginContext) -> None:
                order.append("b")

        await run_startup([A(), B()], PluginContext())
        assert order == ["a", "b"]

    async def test_shutdown_runs_in_reverse_order(self) -> None:
        order: list[str] = []

        class A(PyxlePlugin):
            name = "a"

            async def on_shutdown(self, ctx: PluginContext) -> None:
                order.append("a")

        class B(PyxlePlugin):
            name = "b"

            async def on_shutdown(self, ctx: PluginContext) -> None:
                order.append("b")

        await run_shutdown([A(), B()], PluginContext())
        assert order == ["b", "a"]

    async def test_startup_failure_wrapped_in_plugin_error(self) -> None:
        class Bad(PyxlePlugin):
            name = "bad"

            async def on_startup(self, ctx: PluginContext) -> None:
                raise RuntimeError("database unreachable")

        with pytest.raises(PluginError, match="bad.*on_startup failed.*database unreachable"):
            await run_startup([Bad()], PluginContext())

    async def test_shutdown_failure_swallowed(self, caplog) -> None:
        class Bad(PyxlePlugin):
            name = "bad"

            async def on_shutdown(self, ctx: PluginContext) -> None:
                raise RuntimeError("flush failed")

        class Good(PyxlePlugin):
            name = "good"

            def __init__(self) -> None:
                self.called = False

            async def on_shutdown(self, ctx: PluginContext) -> None:
                self.called = True

        good = Good()
        # Shouldn't raise. The good plugin still runs in reverse order
        # despite the bad plugin throwing.
        await run_shutdown([good, Bad()], PluginContext())
        # good ran — confirming "best-effort teardown" semantics.
        assert good.called is True


# ---------------------------------------------------------------------------
# Config integration


class TestConfigIntegration:
    """Verify ``pyxle.config.load_config`` accepts the ``plugins`` array
    in both sugar forms and rejects malformed entries."""

    def test_accepts_mixed_sugar(self, tmp_path) -> None:
        from pyxle.config import load_config

        config_file = tmp_path / "pyxle.config.json"
        config_file.write_text(
            '{"plugins": ["pyxle-db", {"name": "pyxle-auth", "settings": {"x": 1}}]}',
            encoding="utf-8",
        )
        config = load_config(tmp_path)
        assert config.plugins[0] == "pyxle-db"
        assert config.plugins[1] == {"name": "pyxle-auth", "settings": {"x": 1}}

    def test_default_is_empty_tuple(self, tmp_path) -> None:
        from pyxle.config import load_config

        (tmp_path / "pyxle.config.json").write_text("{}", encoding="utf-8")
        assert load_config(tmp_path).plugins == ()

    def test_rejects_non_list(self, tmp_path) -> None:
        from pyxle.config import ConfigError, load_config

        (tmp_path / "pyxle.config.json").write_text(
            '{"plugins": "pyxle-db"}', encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="expected a list"):
            load_config(tmp_path)

    def test_rejects_object_without_name(self, tmp_path) -> None:
        from pyxle.config import ConfigError, load_config

        (tmp_path / "pyxle.config.json").write_text(
            '{"plugins": [{"settings": {}}]}', encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="non-empty 'name' string"):
            load_config(tmp_path)


# ---------------------------------------------------------------------------
# Module-level ``plugin(name)`` shortcut


class TestActiveContextShortcut:
    """The ``plugin(name)`` helper is the short form of
    ``request.app.state.pyxle_plugins.require(name)``. It reads from
    a module-level ``_active_context`` that the devserver installs at
    lifespan startup and clears at shutdown.
    """

    def _fresh_ctx(self) -> PluginContext:
        ctx = PluginContext()
        ctx.register("auth.service", "<auth>")
        ctx.register("db.database", "<db>")
        return ctx

    def test_plugin_returns_registered_service(self) -> None:
        ctx = self._fresh_ctx()
        set_active_context(ctx)
        try:
            assert plugin("auth.service") == "<auth>"
            assert plugin("db.database") == "<db>"
        finally:
            set_active_context(None)

    def test_plugin_with_default_returns_default_when_missing(self) -> None:
        set_active_context(self._fresh_ctx())
        try:
            assert plugin("nonexistent", "fallback") == "fallback"
            # Explicit None is also a valid default.
            assert plugin("nonexistent", None) is None
        finally:
            set_active_context(None)

    def test_plugin_raises_when_no_active_context(self) -> None:
        # Ensure clean state even if a prior test left something behind.
        set_active_context(None)
        with pytest.raises(PluginServiceError, match="No active plugin context"):
            plugin("anything")

    def test_plugin_raises_for_missing_service_without_default(self) -> None:
        set_active_context(self._fresh_ctx())
        try:
            with pytest.raises(PluginServiceError, match="not registered"):
                plugin("nonexistent")
        finally:
            set_active_context(None)

    def test_active_context_exposes_installed_context(self) -> None:
        ctx = self._fresh_ctx()
        set_active_context(ctx)
        try:
            assert active_context() is ctx
        finally:
            set_active_context(None)

    def test_active_context_without_install_raises(self) -> None:
        set_active_context(None)
        with pytest.raises(PluginServiceError):
            active_context()
