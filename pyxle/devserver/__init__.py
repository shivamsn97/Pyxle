"""Dev server orchestration components."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import uvicorn

from .builder import BuildSummary, build_once
from .client_files import write_client_bootstrap_files
from .registry import build_metadata_registry
from .routes import build_route_table
from .settings import DevServerSettings
from .starlette_app import create_starlette_app
from .vite import ViteProcess
from .watcher import ProjectWatcher, WatcherStatistics

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from pyxle.cli.logger import ConsoleLogger


def _default_logger() -> "ConsoleLogger":
    from pyxle.cli.logger import ConsoleLogger as _ConsoleLogger

    return _ConsoleLogger()


@dataclass(slots=True)
class DevServer:
    """High-level orchestrator coordinating Pyxle's development workflow."""

    settings: DevServerSettings
    logger: "ConsoleLogger" = field(default_factory=_default_logger)
    _watcher: Optional[ProjectWatcher] = field(default=None, init=False, repr=False)
    vite_port_search_limit: int = 10

    async def start(self) -> None:
        """Run the development server until the underlying uvicorn server exits."""

        logger = self.logger
        settings = self._ensure_vite_port_available(self.settings)
        self.settings = settings

        logger.info("Preparing Pyxle development server")

        summary = self._run_initial_build(settings)
        self._log_initial_build(summary)

        write_client_bootstrap_files(settings)

        registry = build_metadata_registry(settings)
        route_table = build_route_table(registry)
        logger.info(
            f"Discovered {len(route_table.pages)} page route(s) and {len(route_table.apis)} API route(s)"
        )

        app = create_starlette_app(settings, route_table, logger=logger)
        overlay = _resolve_overlay(app)
        loop = asyncio.get_running_loop()

        def _handle_rebuild(stats: WatcherStatistics) -> None:
            _maybe_schedule_reload(overlay, loop, stats)
        config = uvicorn.Config(
            app,
            host=settings.starlette_host,
            port=settings.starlette_port,
            loop="asyncio",
            reload=False,
            lifespan="auto",
            log_config=None,
        )
        server = uvicorn.Server(config)

        watcher: ProjectWatcher | None = None
        vite_process: ViteProcess | None = None

        try:
            vite_process = ViteProcess(settings, logger=logger)
            await vite_process.start()
            await vite_process.wait_until_ready()

            watcher = ProjectWatcher(settings, logger=logger, on_rebuild=_handle_rebuild)
            self._watcher = watcher

            logger.info(
                "Starting Starlette on http://"
                f"{settings.starlette_host}:{settings.starlette_port} "
                f"(Vite proxy at http://{settings.vite_host}:{settings.vite_port})"
            )

            watcher.start()
            _set_app_ready_flag(app, True)
            try:
                await server.serve()
            except asyncio.CancelledError:
                logger.warning("Dev server cancellation requested; shutting down")
                server.should_exit = True
                raise
        finally:
            _set_app_ready_flag(app, False)
            if watcher is not None:
                watcher.close()
                self._watcher = None
            if vite_process is not None:
                await vite_process.stop()
            logger.info("Dev server stopped")

    # Internal helpers -------------------------------------------------

    def _run_initial_build(self, settings: DevServerSettings) -> BuildSummary:
        try:
            summary = build_once(settings, force_rebuild=True)
        except Exception as exc:
            self.logger.error(f"Initial build failed: {exc}")
            raise
        return summary

    def _log_initial_build(self, summary: BuildSummary) -> None:
        total_compiled = len(summary.compiled_pages)
        total_api_copied = len(summary.copied_api_modules)
        total_assets = len(summary.copied_client_assets)
        total_styles = len(summary.synced_stylesheets)
        total_removed = len(summary.removed)

        if summary.any_changes():
            parts = [
                f"{total_compiled} page(s) compiled",
                f"{total_api_copied} API module(s) copied",
                f"{total_assets} client asset(s) copied",
                f"{total_styles} global stylesheet(s) synced",
                f"{total_removed} artifact(s) removed",
            ]
            message = "; ".join(parts)
            self.logger.success(f"Initial build completed — {message}")
        else:
            self.logger.info("Initial build completed with no changes detected")

    def _ensure_vite_port_available(self, settings: DevServerSettings) -> DevServerSettings:
        host = settings.vite_host
        base_port = settings.vite_port

        for offset in range(self.vite_port_search_limit):
            candidate = base_port + offset
            if self._is_port_available(host, candidate):
                if candidate != base_port:
                    self.logger.warning(
                        f"Vite port {base_port} in use; retrying on {candidate}"
                    )
                    return replace(settings, vite_port=candidate)
                return settings

        raise RuntimeError(
            f"Unable to find available Vite port after {self.vite_port_search_limit} attempts"
        )

    @staticmethod
    def _is_port_available(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            result = sock.connect_ex((host, port))
            return result != 0


def _set_app_ready_flag(app: object, ready: bool) -> None:
    state = getattr(app, "state", None)
    if state is None:
        return
    setattr(state, "pyxle_ready", ready)


def _resolve_overlay(app: object):
    state = getattr(app, "state", None)
    if state is None:
        return None
    return getattr(state, "overlay", None)


def _maybe_schedule_reload(overlay, loop, stats: WatcherStatistics) -> bool:
    if overlay is None:
        return False
    if stats.error is not None or stats.summary is None:
        return False
    summary = stats.summary
    changed_paths: list[str] = [
        *summary.compiled_pages,
        *summary.copied_api_modules,
        *summary.removed,
    ]
    if not changed_paths and stats.changed_paths:
        changed_paths = [
            path.as_posix() if isinstance(path, Path) else str(path)
            for path in stats.changed_paths
        ]
    if not changed_paths:
        return False
    coroutine = overlay.notify_reload(changed_paths=changed_paths)
    try:
        asyncio.run_coroutine_threadsafe(coroutine, loop)
    except RuntimeError:
        if hasattr(coroutine, "close"):
            coroutine.close()
        return False
    return True


__all__ = ["DevServer", "DevServerSettings", "ProjectWatcher"]
