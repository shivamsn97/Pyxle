"""Pyxle command-line interface package."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from pyxle import __version__
from pyxle.compiler import CompilationResult, compile_file
from pyxle.compiler.exceptions import CompilationError
from pyxle.config import ConfigError, PyxleConfig, load_config
from pyxle.devserver.styles import GlobalStyleConfigError

from .init import log_next_steps as _log_next_steps
from .init import run_init as _run_init
from .logger import ConsoleLogger, LogFormat

# Lazily loaded devserver components to avoid import cycles during test collection.
DevServer = None  # type: ignore[assignment]
DevServerSettings = None  # type: ignore[assignment]

app = typer.Typer(
    name="pyxle",
    add_completion=False,
    no_args_is_help=True,
    help="Pyxle CLI to scaffold and manage full-stack Python web projects.",
)

_logger = ConsoleLogger()
# Placeholder for tests to monkeypatch; resolved lazily at runtime.
run_build = None  # type: ignore[assignment]


def version_callback(value: bool) -> None:
    """Print the package version when ``--version`` is requested."""

    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(  # pragma: no cover - Typer handles option parsing.
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(  # noqa: FBT002 - CLI option signature.
        None,
        "--version",
        help="Show Pyxle version and exit.",
        callback=version_callback,
        is_eager=True,
        is_flag=True,
    ),
    log_format: LogFormat = typer.Option(
        LogFormat.CONSOLE,
        "--log-format",
        help="Formatter for CLI logs (console or json).",
        show_default=True,
    ),
) -> None:
    """Root callback primarily used to expose global options."""

    # The body intentionally does nothing; Typer invokes command functions.
    ctx.ensure_object(dict)  # pragma: no cover - exercised implicitly by Typer
    _logger.set_formatter(log_format)


def get_logger() -> ConsoleLogger:
    """Return the default console logger used across CLI commands."""

    return _logger


def _resolve_run_build():
    if callable(run_build):  # type: ignore[call-arg]
        return run_build  # type: ignore[return-value]

    from pyxle.build import run_build as _run_build  # noqa: PLC0415

    return _run_build


@app.command(help="Create a new Pyxle project scaffold.")
def init(
    name: str = typer.Argument(..., help="Name of the project directory to create."),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite the target directory if it already exists.",
    ),
    template: str = typer.Option(
        "default",
        "--template",
        "-t",
        help="Specify the project template to use (placeholder).",
    ),
    install_deps: bool = typer.Option(
        False,
        "--install/--no-install",
        help="Install Python and Node dependencies after scaffolding completes.",
        show_default=True,
    ),
) -> None:
    """Entry-point for the ``pyxle init`` command."""

    logger = get_logger()
    try:
        project_path = _run_init(
            name,
            force,
            template,
            logger,
            log_steps=not install_deps,
        )
    except typer.Exit:
        raise
    except Exception as exc:  # pragma: no cover - unexpected runtime errors
        logger.error(f"Unexpected error: {exc}")
        raise typer.Exit(code=1) from exc

    if install_deps:
        _install_dependencies(project_path, logger=logger)
        _log_next_steps(logger, project_path, include_install_hint=False)


def _ensure_directory(directory: Path, logger: ConsoleLogger) -> Path:
    resolved = directory.expanduser().resolve()
    if not resolved.exists():
        logger.error(f"Directory '{resolved}' does not exist.")
        raise typer.Exit(code=1)
    if not resolved.is_dir():
        logger.error(f"Path '{resolved}' is not a directory.")
        raise typer.Exit(code=1)
    return resolved


def _run_subprocess(command: list[str], *, cwd: Path, label: str, logger: ConsoleLogger) -> None:
    logger.step(label, " ".join(command))
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        logger.error(f"{label} failed — command '{command[0]}' was not found.")
        raise typer.Exit(code=1) from exc
    except subprocess.CalledProcessError as exc:
        logger.error(f"{label} failed with exit code {exc.returncode}.")
        raise typer.Exit(code=1) from exc


def _install_dependencies(
    project_root: Path,
    *,
    logger: ConsoleLogger,
    install_python: bool = True,
    install_node: bool = True,
) -> None:
    if not install_python and not install_node:
        logger.warning("Skipping dependency installation (both installers disabled).")
        return

    if install_python:
        python_cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        _run_subprocess(
            python_cmd,
            cwd=project_root,
            label="Python dependencies",
            logger=logger,
        )

    if install_node:
        node_cmd = ["npm", "install"]
        _run_subprocess(
            node_cmd,
            cwd=project_root,
            label="Node dependencies",
            logger=logger,
        )

    logger.success("Dependencies installed.")


@app.command(help="Install Python and Node dependencies for a Pyxle project.")
def install(
    directory: Path = typer.Argument(
        Path("."),
        help="Project directory containing requirements.txt and package.json.",
        show_default=True,
    ),
    python_deps: bool = typer.Option(
        True,
        "--python/--no-python",
        help="Install Python dependencies via pip.",
        show_default=True,
    ),
    node_deps: bool = typer.Option(
        True,
        "--node/--no-node",
        help="Install Node dependencies via npm.",
        show_default=True,
    ),
) -> None:
    """Install project dependencies inside the specified directory."""

    logger = get_logger()
    resolved = _ensure_directory(directory, logger)
    _install_dependencies(
        resolved,
        logger=logger,
        install_python=python_deps,
        install_node=node_deps,
    )


@app.command(help="Run the Pyxle development server with hot reload.")
def dev(
    directory: Path = typer.Argument(
        Path("."),
        help="Project root containing pages/ and public/ directories.",
        show_default=True,
    ),
    host: Optional[str] = typer.Option(
        None,
        "--host",
        help="Hostname for the Starlette server (defaults to config or 127.0.0.1).",
        show_default=False,
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        help="Port for the Starlette server (defaults to config or 8000).",
        show_default=False,
    ),
    vite_host: Optional[str] = typer.Option(
        None,
        "--vite-host",
        help="Hostname for the Vite dev server (defaults to config or 127.0.0.1).",
        show_default=False,
    ),
    vite_port: Optional[int] = typer.Option(
        None,
        "--vite-port",
        help="Port for the Vite dev server (defaults to config or 5173).",
        show_default=False,
    ),
    debug: Optional[bool] = typer.Option(
        None,
        "--debug/--no-debug",
        help="Enable debug behaviour for the development server (defaults to config or True).",
        show_default=False,
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to a pyxle.config.json file (defaults to <project>/pyxle.config.json).",
    ),
    print_config: bool = typer.Option(
        False,
        "--print-config/--no-print-config",
        help="Print the merged configuration before starting the dev server.",
        show_default=True,
    ),
) -> None:
    """Entry-point for the ``pyxle dev`` command."""

    logger = get_logger()
    project_root = directory.expanduser().resolve()

    global DevServer, DevServerSettings
    if DevServer is None or DevServerSettings is None:  # noqa: PLC0206 - module-level caching
        from pyxle.devserver import DevServer as _DevServer
        from pyxle.devserver import DevServerSettings as _DevServerSettings

        DevServer = _DevServer
        DevServerSettings = _DevServerSettings

    if not project_root.exists():
        logger.error(f"Project directory '{project_root}' does not exist.")
        raise typer.Exit(code=1)
    if not project_root.is_dir():
        logger.error(f"Path '{project_root}' is not a directory.")
        raise typer.Exit(code=1)

    try:
        file_config: PyxleConfig = load_config(project_root, config_path=config_file)
    except ConfigError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    overrides = _collect_cli_overrides(
        host=host,
        port=port,
        vite_host=vite_host,
        vite_port=vite_port,
        debug=debug,
    )

    effective_config = file_config.apply_overrides(**overrides)

    if print_config:
        pretty = json.dumps(effective_config.to_dict(), indent=2)
        logger.info(f"Effective configuration:\n{pretty}")

    resolved_styles = _resolve_global_style_entries(project_root, effective_config)

    try:
        settings = DevServerSettings.from_project_root(  # type: ignore[union-attr]
            project_root,
            **effective_config.to_devserver_kwargs(),
            global_stylesheets=resolved_styles,
        )
    except GlobalStyleConfigError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    logger.info(
        "Starting Pyxle dev server on http://"
        f"{settings.starlette_host}:{settings.starlette_port}"
        f" with Vite proxy at http://{settings.vite_host}:{settings.vite_port}"
    )

    server = DevServer(settings, logger=logger)  # type: ignore[call-arg]

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:  # pragma: no cover - handled manually during runtime
        logger.warning("Keyboard interrupt received; stopping dev server")
    except Exception as exc:  # pragma: no cover - unexpected runtime errors
        logger.error(f"Dev server encountered an error: {exc}")
        raise typer.Exit(code=1) from exc


@app.command(help="Build production-ready assets for deployment.")
def build(
    directory: Path = typer.Argument(
        Path("."),
        help="Project root containing pages/ and public/ directories.",
        show_default=True,
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to a pyxle.config.json file (defaults to <project>/pyxle.config.json).",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        help="Directory where build artifacts should be written (defaults to <project>/dist).",
    ),
) -> None:
    """Entry-point for the ``pyxle build`` command."""

    logger = get_logger()
    project_root = directory.expanduser().resolve()

    global DevServerSettings
    if DevServerSettings is None:  # noqa: PLC0206 - module-level caching
        from pyxle.devserver import DevServerSettings as _DevServerSettings

        DevServerSettings = _DevServerSettings

    if not project_root.exists():
        logger.error(f"Project directory '{project_root}' does not exist.")
        raise typer.Exit(code=1)
    if not project_root.is_dir():
        logger.error(f"Path '{project_root}' is not a directory.")
        raise typer.Exit(code=1)

    try:
        file_config: PyxleConfig = load_config(project_root, config_path=config_file)
    except ConfigError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    production_config = file_config.apply_overrides(debug=False)
    resolved_styles = _resolve_global_style_entries(project_root, production_config)

    try:
        settings = DevServerSettings.from_project_root(  # type: ignore[union-attr]
            project_root,
            **production_config.to_devserver_kwargs(),
            global_stylesheets=resolved_styles,
        )
    except GlobalStyleConfigError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    resolved_out_dir: Path | None
    if out_dir is None:
        resolved_out_dir = None
    else:
        candidate = out_dir.expanduser()
        if candidate.is_absolute():
            resolved_out_dir = candidate.resolve()
        else:
            resolved_out_dir = (project_root / candidate).resolve()

    logger.info("Building Pyxle project for production")

    runner = _resolve_run_build()

    try:
        result = runner(settings, logger=logger, dist_dir=resolved_out_dir)
    except Exception as exc:  # pragma: no cover - unexpected runtime errors
        logger.error(f"Build failed: {exc}")
        raise typer.Exit(code=1) from exc

    summary = result.summary
    logger.success(
        "Build completed — "
        f"{len(summary.compiled_pages)} page(s) compiled, "
        f"{len(summary.copied_api_modules)} API module(s) copied, "
        f"{len(summary.copied_client_assets)} client asset(s) copied"
    )
    if result.client_manifest_path is not None:
        logger.step("Client manifest", detail=str(result.client_manifest_path))
    if result.page_manifest_path is not None:
        logger.step("Page manifest", detail=str(result.page_manifest_path))
    logger.step("Server modules", detail=str(result.server_dir))
    logger.step("Metadata", detail=str(result.metadata_dir))
    public_detail = str(result.public_dir)
    if not result.public_dir.exists():
        public_detail += " (not generated)"
    logger.step("Public assets", detail=public_detail)
    logger.step("Artifacts", detail=str(result.dist_dir))

@app.command(name="compile", help="Compile a single .pyx file (developer utility).", hidden=True)
def compile_command(
    source: Path = typer.Argument(..., help="Path to the .pyx file to compile."),
    build_root: Path = typer.Option(
        Path(".pyxle-build"),
        "--build-root",
        "-b",
        help="Directory where compiled artifacts should be written.",
        show_default=True,
    ),
) -> None:
    """Invoke the Pyxle compiler for manual verification workflows."""

    logger = get_logger()
    resolved_source = source.expanduser().resolve()
    resolved_build = build_root.expanduser().resolve()

    if not resolved_source.exists():
        logger.error(f"Source file '{resolved_source}' was not found.")
        raise typer.Exit(code=1)

    try:
        result: CompilationResult = compile_file(
            resolved_source,
            build_root=resolved_build,
        )
    except CompilationError as exc:
        logger.error(f"Compilation failed: {exc}")
        raise typer.Exit(code=1) from exc

    logger.step("Client artifact", result.client_output.as_posix())
    logger.step("Server artifact", result.server_output.as_posix())
    logger.step("Metadata", result.metadata_output.as_posix())
    logger.success(result.summary())


def _collect_cli_overrides(
    *,
    host: Optional[str],
    port: Optional[int],
    vite_host: Optional[str],
    vite_port: Optional[int],
    debug: Optional[bool],
) -> dict[str, object]:
    """Return CLI override values for non-null parameters."""

    overrides: dict[str, object] = {}

    if host is not None:
        overrides["starlette_host"] = host

    if port is not None:
        overrides["starlette_port"] = port

    if vite_host is not None:
        overrides["vite_host"] = vite_host

    if vite_port is not None:
        overrides["vite_port"] = vite_port

    if debug is not None:
        overrides["debug"] = debug

    return overrides


def _resolve_global_style_entries(project_root: Path, config: PyxleConfig) -> tuple[str, ...]:
    """Return the configured global styles, auto-detecting defaults when available."""

    entries = list(config.global_styles)
    default_candidate = Path("styles") / "global.css"
    if not entries:
        default_path = project_root / default_candidate
        if default_path.is_file():
            entries.append(default_candidate.as_posix())

    seen: set[str] = set()
    normalized: list[str] = []
    for entry in entries:
        candidate = (Path(entry.strip()).as_posix() if entry else "").strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    return tuple(normalized)
