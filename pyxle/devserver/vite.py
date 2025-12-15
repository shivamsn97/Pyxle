"""Management helpers for the Vite development server subprocess."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from asyncio.subprocess import PIPE
from contextlib import suppress
from typing import Awaitable, Callable, Iterable

from pyxle.cli.logger import ConsoleLogger

from .client_files import VITE_CONFIG_FILENAME
from .settings import DevServerSettings

_ViteProbe = Callable[[str, int], Awaitable[bool]]


class ViteProcess:
    """Launch and supervise the Vite dev server."""

    def __init__(
        self,
        settings: DevServerSettings,
        *,
        logger: ConsoleLogger | None = None,
        command: Iterable[str] | None = None,
        process_factory=None,
        stop_timeout: float = 5.0,
        readiness_timeout: float = 10.0,
        readiness_interval: float = 0.1,
        probe: _ViteProbe | None = None,
        restart_delay: float = 0.5,
    ) -> None:
        self._settings = settings
        self._logger = logger or ConsoleLogger()
        self._custom_command = list(command) if command is not None else None
        self._process_factory = process_factory or asyncio.create_subprocess_exec
        self._process: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._stop_timeout = stop_timeout
        self._readiness_timeout = readiness_timeout
        self._readiness_interval = readiness_interval
        self._probe = probe or self._default_probe
        self._latest_ready_elapsed: float | None = None
        self._stopping: bool = False
        self._restart_task: asyncio.Task[None] | None = None
        self._restart_delay = restart_delay
        self._command_override: list[str] | None = None
        self._npm_install_attempted = False

    @property
    def running(self) -> bool:
        process = self._process
        return process is not None and process.returncode is None

    async def start(self) -> None:
        if self.running:
            return

        self._stopping = False
        restart_task = self._restart_task
        current_task = asyncio.current_task()
        if restart_task is not None and restart_task is not current_task:
            restart_task.cancel()
            with suppress(asyncio.CancelledError):
                await restart_task
            self._restart_task = None

        command = self._build_launch_command()
        self._logger.info("Launching Vite dev server: " + " ".join(command))
        env = self._build_env()

        try:
            process = await self._process_factory(
                *command,
                stdout=PIPE,
                stderr=PIPE,
                cwd=str(self._settings.project_root),
                env=env,
            )
        except FileNotFoundError as exc:
            if not await self._recover_missing_vite():
                raise RuntimeError(
                    "Unable to find 'vite'. Install Node.js dependencies with 'npm install' or provide a custom command."
                ) from exc

            command = self._build_launch_command()
            self._logger.info("Retrying Vite launch with resolved command: " + " ".join(command))
            process = await self._process_factory(
                *command,
                stdout=PIPE,
                stderr=PIPE,
                cwd=str(self._settings.project_root),
                env=env,
            )

        self._process = process
        self._monitor_task = asyncio.create_task(self._monitor_process(process))

    async def wait_until_ready(self) -> None:
        """Block until Vite accepts TCP connections or the timeout elapses."""

        if not self.running:
            raise RuntimeError("Vite process is not running")

        host = self._settings.vite_host
        port = self._settings.vite_port
        timeout = self._readiness_timeout
        interval = self._readiness_interval
        deadline = asyncio.get_running_loop().time() + timeout
        logged_wait = False
        start = time.perf_counter()
        already_reported = self._latest_ready_elapsed is not None

        while True:
            if await self._probe(host, port):
                if not already_reported:
                    self._latest_ready_elapsed = time.perf_counter() - start
                    self._logger.success(
                        f"Vite dev server ready at http://{host}:{port} "
                        f"({self._latest_ready_elapsed:.2f}s)"
                    )
                return

            if not self.running:
                raise RuntimeError("Vite process exited before becoming ready")

            now = asyncio.get_running_loop().time()
            if now >= deadline:
                raise RuntimeError(
                    f"Timed out waiting for Vite dev server on http://{host}:{port}"
                )

            if not logged_wait:
                self._logger.info(
                    f"Waiting for Vite dev server on http://{host}:{port}"
                )
                logged_wait = True

            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self._stopping = True

        if self._restart_task is not None:
            self._restart_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._restart_task
            self._restart_task = None

        process = self._process
        if process is None:
            return

        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=self._stop_timeout)
            except asyncio.TimeoutError:
                self._logger.warning("Vite process did not exit after SIGTERM; killing")
                process.kill()
                await process.wait()

        if self._monitor_task is not None:
            with suppress(asyncio.CancelledError):
                await self._monitor_task

        self._logger.info("Vite dev server stopped")
        self._process = None
        self._monitor_task = None

    def _build_command(self) -> tuple[str, ...]:
        config_path = self._settings.client_build_dir / VITE_CONFIG_FILENAME
        return (
            "vite",
            "dev",
            "--config",
            str(config_path),
            "--host",
            self._settings.vite_host,
            "--port",
            str(self._settings.vite_port),
        )

    def _build_launch_command(self) -> list[str]:
        if self._custom_command is not None:
            return list(self._custom_command)
        if self._command_override is not None:
            return list(self._command_override)
        return list(self._build_command())

    async def _recover_missing_vite(self) -> bool:
        if self._custom_command is not None:
            return False

        base_command = list(self._build_command())
        local_command = self._local_vite_command()
        if local_command is not None:
            self._command_override = [*local_command, *base_command[1:]]
            return True

        project_root = self._settings.project_root
        package_json = project_root / "package.json"
        if (
            not self._npm_install_attempted
            and package_json.exists()
        ):
            self._npm_install_attempted = True
            await self._run_npm_install()
            local_command = self._local_vite_command()
            if local_command is not None:
                self._command_override = [*local_command, *base_command[1:]]
                return True

        npx_prefix = self._npx_prefix()
        if npx_prefix is not None:
            self._command_override = [*npx_prefix, *base_command[1:]]
            return True

        return False

    def _local_vite_command(self) -> list[str] | None:
        project_root = self._settings.project_root
        node_exec = shutil.which("node")

        vite_bin = project_root / "node_modules" / "vite" / "bin" / "vite.js"
        if node_exec is not None and vite_bin.exists():
            return [node_exec, str(vite_bin)]

        candidates = [
            project_root / "node_modules" / ".bin" / "vite",
            project_root / "node_modules" / ".bin" / "vite.cmd",
        ]
        for candidate in candidates:
            if candidate.exists():
                return [str(candidate)]

        return None

    async def _run_npm_install(self) -> bool:
        npm_exec = shutil.which("npm")
        if npm_exec is None:
            self._logger.error("Cannot run 'npm install': 'npm' executable not found in PATH.")
            return False

        self._logger.info("Installing Node dependencies via 'npm install'")
        try:
            process = await self._process_factory(
                npm_exec,
                "install",
                stdout=PIPE,
                stderr=PIPE,
                cwd=str(self._settings.project_root),
            )
        except FileNotFoundError:
            self._logger.error("Failed to execute 'npm install': 'npm' executable is unavailable.")
            return False

        stdout_bytes, stderr_bytes = await process.communicate()
        self._log_process_output(stdout_bytes, stderr_bytes, prefix="npm")

        if process.returncode not in (0, None):
            self._logger.error(f"'npm install' exited with code {process.returncode}")
            return False

        self._logger.success("npm install completed successfully")
        return True

    def _npx_prefix(self) -> tuple[str, ...] | None:
        npx_exec = shutil.which("npx")
        if npx_exec is None:
            return None
        return (npx_exec, "--yes", "vite")

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYXLE_VITE_BASE", "/")
        return env

    def _log_process_output(self, stdout: bytes, stderr: bytes, *, prefix: str) -> None:
        stdout_text = stdout.decode(errors="ignore") if stdout else ""
        stderr_text = stderr.decode(errors="ignore") if stderr else ""

        for line in stdout_text.splitlines():
            line = line.strip()
            if line:
                self._logger.info(f"[{prefix}] {line}")

        for line in stderr_text.splitlines():
            line = line.strip()
            if line:
                self._logger.error(f"[{prefix}] {line}")

    async def _monitor_process(self, process: asyncio.subprocess.Process) -> None:
        stdout = process.stdout
        stderr = process.stderr

        tasks: list[asyncio.Task[None]] = []
        if stdout is not None:
            tasks.append(asyncio.create_task(self._pipe_stream(stdout, is_error=False)))
        if stderr is not None:
            tasks.append(asyncio.create_task(self._pipe_stream(stderr, is_error=True)))

        try:
            if tasks:
                await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        returncode = await process.wait()
        crashed = returncode not in (0, None) and not self._stopping

        if returncode not in (0, None):
            self._logger.error(f"[vite] process exited with code {returncode}")
        else:
            self._logger.info("[vite] process exited")

        if crashed:
            self._logger.warning("Vite process exited unexpectedly; attempting restart")
            self._process = None
            self._restart_task = asyncio.create_task(self._restart_after_exit())

    async def _pipe_stream(self, stream: asyncio.StreamReader, *, is_error: bool) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            message = line.decode(errors="replace").rstrip()
            if not message:
                continue
            if is_error:
                self._logger.error(f"[vite] {message}")
            else:
                self._logger.info(f"[vite] {message}")

    async def _restart_after_exit(self) -> None:
        try:
            await asyncio.sleep(self._restart_delay)
            if self._stopping:
                return
            await self.start()
            await self.wait_until_ready()
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.error(f"Failed to restart Vite dev server: {exc}")
        finally:
            self._restart_task = None

    @staticmethod
    async def _default_probe(host: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError:
            return False
        else:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            return True


__all__ = ["ViteProcess"]
