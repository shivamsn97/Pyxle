from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.testclient import TestClient

from pyxle.cli.logger import ConsoleLogger
from pyxle.devserver import (
    DevServer,
    DevServerSettings,
    _maybe_schedule_reload,
    _set_app_ready_flag,
)
from pyxle.devserver.builder import BuildSummary
from pyxle.devserver.registry import MetadataRegistry
from pyxle.devserver.routes import RouteTable
from pyxle.devserver.watcher import WatcherStatistics

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def anyio_backend() -> str:  # pragma: no cover - fixture wiring
    return "asyncio"


class LogCapture:
    def __init__(self) -> None:
        self.messages: List[str] = []

    def __call__(self, message: str, fg: str | None = None, bold: bool = False) -> None:  # pragma: no cover - formatting only
        self.messages.append(message)


async def test_devserver_start_configures_uvicorn_and_watcher(anyio_backend, monkeypatch, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)
    build_calls: List[Dict[str, Any]] = []
    watcher_instances: List["StubWatcher"] = []
    captured_config: Dict[str, Any] = {}
    server_state: Dict[str, Any] = {}
    capture = LogCapture()
    logger = ConsoleLogger(secho=capture)
    bootstrap_calls: List[DevServerSettings] = []
    vite_instances: List["StubVite"] = []

    def fake_build_once(config: DevServerSettings, *, force_rebuild: bool = False) -> BuildSummary:
        build_calls.append({"settings": config, "force": force_rebuild})
        return BuildSummary(compiled_pages=["pages/index.pyx"], copied_api_modules=["api/pulse.py"], removed=[])

    monkeypatch.setattr("pyxle.devserver.build_once", fake_build_once)
    monkeypatch.setattr(
        "pyxle.devserver.build_metadata_registry",
        lambda cfg: MetadataRegistry(pages=[], apis=[]),
    )
    monkeypatch.setattr(
        "pyxle.devserver.build_route_table",
        lambda registry: RouteTable(pages=[], apis=[]),
    )

    class DummyApp:
        def __init__(self) -> None:
            self.state = SimpleNamespace()

    dummy_app = DummyApp()
    monkeypatch.setattr(
        "pyxle.devserver.create_starlette_app",
        lambda cfg, routes, *, logger: dummy_app,
    )
    monkeypatch.setattr(
        "pyxle.devserver.write_client_bootstrap_files",
        lambda cfg: bootstrap_calls.append(cfg),
    )

    class StubVite:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            self.settings = cfg
            self.logger = logger
            self.started = False
            self.ready = False
            self.stopped = False
            vite_instances.append(self)

        async def start(self) -> None:
            self.started = True

        async def wait_until_ready(self) -> None:
            self.ready = True

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("pyxle.devserver.ViteProcess", StubVite)

    class StubWatcher:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            self.settings = cfg
            self.logger = logger
            self.started = False
            self.closed = False
            watcher_instances.append(self)

        def start(self) -> None:
            self.started = True

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("pyxle.devserver.ProjectWatcher", StubWatcher)

    class StubConfig:
        def __init__(self, app: object, **kwargs: Any) -> None:
            captured_config["app"] = app
            captured_config["kwargs"] = kwargs

    class StubServer:
        def __init__(self, config: StubConfig) -> None:
            server_state["config"] = config
            self.should_exit = False

        async def serve(self) -> None:
            server_state["served"] = True
            server_state["ready_during_serve"] = getattr(dummy_app.state, "pyxle_ready", None)

    monkeypatch.setattr("pyxle.devserver.uvicorn.Config", StubConfig)
    monkeypatch.setattr("pyxle.devserver.uvicorn.Server", StubServer)

    server = DevServer(settings=settings, logger=logger)

    await server.start()

    assert build_calls == [{"settings": server.settings, "force": True}]
    assert watcher_instances and watcher_instances[0].started is True
    assert watcher_instances[0].closed is True
    assert captured_config["app"] is dummy_app
    assert captured_config["kwargs"]["host"] == server.settings.starlette_host
    assert captured_config["kwargs"]["port"] == server.settings.starlette_port
    assert captured_config["kwargs"]["loop"] == "asyncio"
    assert captured_config["kwargs"]["reload"] is False
    assert server_state.get("served") is True
    assert server_state.get("ready_during_serve") is True
    assert server._watcher is None
    assert any("Initial build completed" in message for message in capture.messages)
    assert bootstrap_calls == [server.settings]
    assert vite_instances and vite_instances[0].started is True
    assert vite_instances[0].ready is True
    assert vite_instances[0].stopped is True
    assert getattr(dummy_app.state, "pyxle_ready", False) is False


async def test_devserver_start_builds_routes_and_creates_app(anyio_backend, monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    settings = DevServerSettings.from_project_root(project_root)
    (settings.pages_dir / "api").mkdir(parents=True, exist_ok=True)
    (settings.pages_dir / "api" / "pulse.py").write_text(
        """from starlette.responses import JSONResponse\n\nasync def endpoint(request):\n    return JSONResponse({\"message\": \"Hello\"})\n""",
        encoding="utf-8",
    )
    (settings.pages_dir / "index.pyx").write_text(
        """\n\n@server\nasync def load_home(request):\n    return {\"message\": \"hi\"}\n\n# --- JavaScript/PSX (Client + Server) ---\n\nimport React from 'react';\n\nexport default function Home({ data }) {\n    return <div>{data.message}</div>;\n}\n""",
        encoding="utf-8",
    )

    watcher_instances: List["StubWatcher"] = []
    bootstrap_calls: List[DevServerSettings] = []
    vite_instances: List["StubVite"] = []

    class StubWatcher:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            self.started = False
            self.closed = False
            watcher_instances.append(self)

        def start(self) -> None:
            self.started = True

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("pyxle.devserver.ProjectWatcher", StubWatcher)

    served_config: Dict[str, Any] = {}

    class StubConfig:
        def __init__(self, app: Starlette, **kwargs: Any) -> None:
            served_config["app"] = app
            served_config["kwargs"] = kwargs

    class StubServer:
        def __init__(self, config: StubConfig) -> None:
            self.config = config

        async def serve(self) -> None:
            served_config["served"] = True

    monkeypatch.setattr("pyxle.devserver.uvicorn.Config", StubConfig)
    monkeypatch.setattr("pyxle.devserver.uvicorn.Server", StubServer)
    monkeypatch.setattr(
    "pyxle.devserver.write_client_bootstrap_files",
    lambda cfg: bootstrap_calls.append(cfg),
    )
    renderer = object()

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: renderer,
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
        assert overlay is not None
        return HTMLResponse(f"<h1>{page.path}</h1>")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    class StubVite:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            self.started = False
            self.ready = False
            self.stopped = False
            vite_instances.append(self)

        async def start(self) -> None:
            self.started = True

        async def wait_until_ready(self) -> None:
            self.ready = True

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("pyxle.devserver.ViteProcess", StubVite)

    capture = LogCapture()
    logger = ConsoleLogger(secho=capture)

    server = DevServer(settings=settings, logger=logger)

    await server.start()

    assert watcher_instances and watcher_instances[0].started is True
    assert watcher_instances[0].closed is True
    assert served_config.get("served") is True

    app = served_config["app"]
    assert isinstance(app, Starlette)

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "<h1>/</h1>" in response.text

        api_response = client.get("/api/pulse")
        assert api_response.status_code == 200
        assert api_response.json()["message"] == "Hello"

    assert bootstrap_calls == [server.settings]
    assert vite_instances and vite_instances[0].started is True
    assert vite_instances[0].ready is True
    assert vite_instances[0].stopped is True


async def test_devserver_retries_vite_port(monkeypatch, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)
    capture = LogCapture()
    logger = ConsoleLogger(secho=capture)

    bootstrap_calls: List[DevServerSettings] = []
    vite_instances: List["StubVite"] = []

    monkeypatch.setattr(
        "pyxle.devserver.build_once",
        lambda cfg, **_: BuildSummary(compiled_pages=[], copied_api_modules=[], removed=[]),
    )
    monkeypatch.setattr(
        "pyxle.devserver.build_metadata_registry",
        lambda cfg: MetadataRegistry(pages=[], apis=[]),
    )
    monkeypatch.setattr(
        "pyxle.devserver.build_route_table",
        lambda registry: RouteTable(pages=[], apis=[]),
    )
    monkeypatch.setattr(
        "pyxle.devserver.write_client_bootstrap_files",
        lambda cfg: bootstrap_calls.append(cfg),
    )

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.ComponentRenderer",
        lambda: object(),
    )

    async def fake_build_page_response(*, request, settings, page, renderer, overlay=None):
        return HTMLResponse("<div></div>")

    monkeypatch.setattr(
        "pyxle.devserver.starlette_app.build_page_response",
        fake_build_page_response,
    )

    class StubVite:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            self.settings = cfg
            self.started = False
            self.ready = False
            self.stopped = False
            vite_instances.append(self)

        async def start(self) -> None:
            self.started = True

        async def wait_until_ready(self) -> None:
            self.ready = True

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr("pyxle.devserver.ViteProcess", StubVite)

    class StubWatcher:
        def __init__(self, cfg: DevServerSettings, *, logger: ConsoleLogger, **_: Any) -> None:
            pass

        def start(self) -> None:  # pragma: no cover - no-op stub
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("pyxle.devserver.ProjectWatcher", StubWatcher)

    class StubConfig:
        def __init__(self, app: object, **kwargs: Any) -> None:
            pass

    class StubServer:
        def __init__(self, config: StubConfig) -> None:
            self.should_exit = False

        async def serve(self) -> None:
            return None

    monkeypatch.setattr("pyxle.devserver.uvicorn.Config", StubConfig)
    monkeypatch.setattr("pyxle.devserver.uvicorn.Server", StubServer)

    attempts: List[int] = []

    def fake_is_port_available(host: str, port: int) -> bool:
        attempts.append(port)
        base = settings.vite_port
        return port == base + 2

    monkeypatch.setattr(
        DevServer,
        "_is_port_available",
        staticmethod(fake_is_port_available),
    )

    server = DevServer(settings=settings, logger=logger)
    server.vite_port_search_limit = 5

    await server.start()

    assert attempts[:3] == [settings.vite_port, settings.vite_port + 1, settings.vite_port + 2]
    assert bootstrap_calls and bootstrap_calls[0].vite_port == settings.vite_port + 2
    assert vite_instances and vite_instances[0].settings.vite_port == settings.vite_port + 2
    assert vite_instances[0].ready is True
    assert any("retrying" in message for message in capture.messages)


def test_devserver_logs_initial_build_without_changes(tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)
    capture = LogCapture()
    logger = ConsoleLogger(secho=capture)
    server = DevServer(settings=settings, logger=logger)

    summary = BuildSummary(compiled_pages=[], copied_api_modules=[], removed=[])
    server._log_initial_build(summary)

    assert any("no changes" in message.lower() for message in capture.messages)


def test_devserver_ensure_vite_port_available_exhausted(monkeypatch, tmp_path: Path) -> None:
    settings = DevServerSettings.from_project_root(tmp_path)
    server = DevServer(settings=settings)
    server.vite_port_search_limit = 3

    monkeypatch.setattr(
        DevServer,
        "_is_port_available",
        staticmethod(lambda host, port: False),
    )

    with pytest.raises(RuntimeError):
        server._ensure_vite_port_available(settings)


async def test_maybe_schedule_reload_dispatches(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    captured: list[list[str]] = []

    class StubOverlay:
        async def notify_reload(self, *, changed_paths: list[str]) -> None:
            captured.append(changed_paths)

    summary = BuildSummary(compiled_pages=["pages/index.pyx"], copied_api_modules=[], removed=[])
    stats = WatcherStatistics(elapsed_seconds=0.01, summary=summary, error=None, changed_paths=[])

    monkeypatch.setattr(
        "pyxle.devserver.asyncio.run_coroutine_threadsafe",
        lambda coro, loop: loop.create_task(coro),
    )

    overlay = StubOverlay()
    assert _maybe_schedule_reload(overlay, loop, stats) is True
    await asyncio.sleep(0)
    assert captured == [["pages/index.pyx"]]


async def test_maybe_schedule_reload_handles_guard_paths(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    summary_with_change = BuildSummary(compiled_pages=["pages/about.pyx"], copied_api_modules=[], removed=[])
    stats_with_change = WatcherStatistics(
        elapsed_seconds=0.01,
        summary=summary_with_change,
        error=None,
        changed_paths=[Path("pages/about.pyx")],
    )

    summary_empty = BuildSummary()
    stats_empty = WatcherStatistics(
        elapsed_seconds=0.01,
        summary=summary_empty,
        error=None,
        changed_paths=[],
    )

    class StubOverlay:
        async def notify_reload(self, *, changed_paths: list[str]) -> None:  # pragma: no cover - not called
            raise AssertionError("should not be invoked")

    overlay = StubOverlay()

    assert _maybe_schedule_reload(None, loop, stats_with_change) is False
    stats_error = WatcherStatistics(
        elapsed_seconds=0.01,
        summary=summary_with_change,
        error=RuntimeError("boom"),
        changed_paths=[],
    )
    assert _maybe_schedule_reload(overlay, loop, stats_error) is False
    assert _maybe_schedule_reload(overlay, loop, stats_empty) is False


async def test_maybe_schedule_reload_handles_runtime_error(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    class StubOverlay:
        async def notify_reload(self, *, changed_paths: list[str]) -> None:
            pass

    summary = BuildSummary(compiled_pages=["pages/index.pyx"], copied_api_modules=[], removed=[])
    stats = WatcherStatistics(elapsed_seconds=0.01, summary=summary, error=None, changed_paths=[])

    def raise_runtime(coro, loop):
        raise RuntimeError("boom")

    monkeypatch.setattr("pyxle.devserver.asyncio.run_coroutine_threadsafe", raise_runtime)

    assert _maybe_schedule_reload(StubOverlay(), loop, stats) is False


async def test_maybe_schedule_reload_uses_changed_paths_fallback(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    captured: list[list[str]] = []

    class StubOverlay:
        async def notify_reload(self, *, changed_paths: list[str]) -> None:
            captured.append(changed_paths)

    stats = WatcherStatistics(
        elapsed_seconds=0.02,
        summary=BuildSummary(),
        error=None,
        changed_paths=[Path("foo/bar.py"), "api/pulse.py"],
    )

    monkeypatch.setattr(
        "pyxle.devserver.asyncio.run_coroutine_threadsafe",
        lambda coro, loop: loop.create_task(coro),
    )

    overlay = StubOverlay()
    assert _maybe_schedule_reload(overlay, loop, stats) is True
    await asyncio.sleep(0)
    assert captured == [["foo/bar.py", "api/pulse.py"]]


def test_set_app_ready_flag_handles_missing_state() -> None:
    class Dummy:
        pass

    dummy = Dummy()

    _set_app_ready_flag(dummy, True)  # should be a no-op without errors


def test_set_app_ready_flag_sets_and_unsets_flag() -> None:
    class Dummy:
        def __init__(self) -> None:
            self.state = SimpleNamespace()

    dummy = Dummy()

    _set_app_ready_flag(dummy, True)
    assert getattr(dummy.state, "pyxle_ready", False) is True

    _set_app_ready_flag(dummy, False)
    assert getattr(dummy.state, "pyxle_ready", True) is False