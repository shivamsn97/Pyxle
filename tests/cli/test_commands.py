import asyncio
import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

import pyxle.cli as cli
from pyxle import __version__
from pyxle.cli import app, version_callback
from pyxle.cli.assets import default_favicon_bytes
from pyxle.config import PyxleConfig

runner = CliRunner()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_init_scaffolds_project_structure() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init", "My App"], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout

        project_dir = Path("my-app")
        assert project_dir.is_dir()
        assert (project_dir / "pages" / "layout.pyx").exists()
        assert (project_dir / "pages" / "index.pyx").exists()
        assert (project_dir / "pages" / "api" / "pulse.py").exists()
        assert (project_dir / "pages" / "styles" / "tailwind.css").exists()
        assert (project_dir / "tailwind.config.cjs").exists()
        assert (project_dir / "postcss.config.cjs").exists()
        assert (project_dir / "public" / "styles" / "tailwind.css").exists()
        branding_dir = project_dir / "public" / "branding"
        assert (branding_dir / "pyxle-mark.svg").exists()
        assert (branding_dir / "pyxle-wordmark-dark.svg").exists()
        assert (branding_dir / "pyxle-wordmark-light.svg").exists()
        assert (branding_dir / "pyxle-grid.svg").exists()
        assert not (project_dir / "pages" / "components").exists()
        assert (project_dir / "public" / "favicon.ico").read_bytes() == default_favicon_bytes()

        package_json = read_json(project_dir / "package.json")
        assert package_json["name"] == "my-app"

        config_payload = json.loads((project_dir / "pyxle.config.json").read_text(encoding="utf-8"))
        assert config_payload["middleware"] == []

        next_steps = result.stdout.splitlines()
        assert any("Next steps" in line for line in next_steps)
        assert "pyxle install" in result.stdout


def test_init_requires_force_for_existing_directory() -> None:
    with runner.isolated_filesystem():
        project_dir = Path("demo")
        project_dir.mkdir()
        result = runner.invoke(app, ["init", "demo"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Target directory already exists" in result.stdout

        (project_dir / "old.txt").write_text("legacy")
        result_force = runner.invoke(app, ["init", "demo", "--force"], catch_exceptions=False)
        assert result_force.exit_code == 0, result_force.stdout
        assert not (project_dir / "old.txt").exists()


def test_init_rejects_unknown_template() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init", "demo", "--template", "fancy"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Unsupported template" in result.stdout


def test_init_rejects_invalid_name() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init", "!!!"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Project name" in result.stdout


def test_install_invokes_dependency_helper(monkeypatch) -> None:
    with runner.isolated_filesystem():
        Path("demo").mkdir()

        called: dict[str, object] = {}

        def fake_install(
            project_root,
            *,
            logger,
            install_python=True,
            install_node=True,
        ):
            called["root"] = project_root.resolve()
            called["python"] = install_python
            called["node"] = install_node

        monkeypatch.setattr(cli, "_install_dependencies", fake_install)

        result = runner.invoke(
            app,
            ["install", "demo", "--no-node"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert called["root"] == Path("demo").resolve()
        assert called["python"] is True
        assert called["node"] is False


def test_install_fails_when_directory_missing() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["install", "missing"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "does not exist" in result.stdout


def test_install_rejects_file_path() -> None:
    with runner.isolated_filesystem():
        file_path = Path("demo.txt")
        file_path.write_text("demo", encoding="utf-8")

        result = runner.invoke(app, ["install", "demo.txt"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "not a directory" in result.stdout


def test_install_dependencies_executes_commands(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd, check):
        calls.append((command, cwd))

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    logger = cli.ConsoleLogger()

    cli._install_dependencies(tmp_path, logger=logger)

    assert calls[0][0][0] == sys.executable
    assert calls[0][0][-2:] == ["-r", "requirements.txt"]
    assert calls[1][0] == ["npm", "install"]
    assert calls[0][1] == tmp_path
    assert calls[1][1] == tmp_path


def test_run_subprocess_handles_missing_binary(monkeypatch, tmp_path) -> None:
    def fake_run(*_, **__):
        raise FileNotFoundError("missing binary")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    logger = cli.ConsoleLogger()

    with pytest.raises(typer.Exit):
        cli._run_subprocess(["npm", "install"], cwd=tmp_path, label="Node", logger=logger)


def test_serve_command_runs_build_and_uvicorn(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        dist_root = project / "dist"
        client_dir = dist_root / "client"
        public_dir = dist_root / "public"
        client_dir.mkdir(parents=True, exist_ok=True)
        public_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = dist_root / "page-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text('{"/": {"client": {"file": "client/bundle.js"}}}', encoding="utf-8")

        captured: dict[str, object] = {}

        def fake_run_build(settings, *, logger, dist_dir=None, force_rebuild=True):
            captured["build_settings"] = settings
            captured["dist_dir"] = dist_dir
            captured["force_rebuild"] = force_rebuild

        monkeypatch.setattr(cli, "run_build", fake_run_build)

        registry_sentinel = object()
        route_table_sentinel = object()

        monkeypatch.setattr(cli, "build_metadata_registry", lambda settings: registry_sentinel)
        monkeypatch.setattr(cli, "build_route_table", lambda registry: route_table_sentinel)

        app_instance = SimpleNamespace(state=SimpleNamespace(pyxle_ready=False))

        def fake_create_app(settings, routes, **kwargs):
            captured["create_settings"] = settings
            captured["routes"] = routes
            captured["create_kwargs"] = kwargs
            return app_instance

        monkeypatch.setattr(cli, "create_starlette_app", fake_create_app)

        class StubServer:
            def __init__(self, config):
                captured["uvicorn_config"] = config

            async def serve(self):
                captured["served"] = True

        monkeypatch.setattr(cli.uvicorn, "Server", StubServer)

        def fake_asyncio_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        monkeypatch.setattr(cli.asyncio, "run", fake_asyncio_run)

        result = runner.invoke(
            app,
            [
                "serve",
                "demo",
                "--host",
                "0.0.0.0",
                "--port",
                "8200",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.stdout
        assert captured["dist_dir"] == (project / "dist").resolve()
        assert captured["force_rebuild"] is True
        assert captured["routes"] is route_table_sentinel
        assert captured["create_kwargs"]["public_static_dir"] == public_dir.resolve()
        assert captured["create_kwargs"]["client_static_dir"] == client_dir.resolve()
        assert app_instance.state.pyxle_ready is True
        assert captured.get("served") is True


def test_serve_command_can_disable_static_mounts(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        dist_root = project / "dist"
        dist_root.mkdir(parents=True, exist_ok=True)
        (dist_root / "page-manifest.json").write_text('{}', encoding="utf-8")

        monkeypatch.setattr(cli, "run_build", lambda *_, **__: None)
        monkeypatch.setattr(cli, "build_metadata_registry", lambda settings: object())
        monkeypatch.setattr(cli, "build_route_table", lambda registry: object())

        captured: dict[str, object] = {}

        def fake_create_app(*_, **kwargs):
            captured.update(kwargs)
            app_instance = SimpleNamespace(state=SimpleNamespace(pyxle_ready=False))
            return app_instance

        monkeypatch.setattr(cli, "create_starlette_app", fake_create_app)

        class StubServer:
            def __init__(self, config):
                pass

            async def serve(self):
                return None

        monkeypatch.setattr(cli.uvicorn, "Server", StubServer)
        def fake_asyncio_run(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        monkeypatch.setattr(cli.asyncio, "run", fake_asyncio_run)

        result = runner.invoke(app, ["serve", "demo", "--no-serve-static"], catch_exceptions=False)

        assert result.exit_code == 0
        assert captured["public_static_dir"] is None
        assert captured["client_static_dir"] is None
        assert captured["serve_static"] is False


def test_serve_command_requires_manifest_when_skipping_build(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        # Ensure run_build is not invoked when skipping
        def fake_run_build(*_, **__):  # pragma: no cover - should not be called
            raise AssertionError("run_build should not run when --skip-build is set")

        monkeypatch.setattr(cli, "run_build", fake_run_build)

        result = runner.invoke(
            app,
            ["serve", "demo", "--skip-build"],
            catch_exceptions=False,
        )

        assert result.exit_code == 1
        assert "page-manifest" in result.stdout


def test_install_dependencies_flag_skips(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, cwd, check):
        calls.append(command)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    logger = cli.ConsoleLogger()

    cli._install_dependencies(tmp_path, logger=logger, install_python=False, install_node=True)
    assert calls == [["npm", "install"]]

    calls.clear()
    cli._install_dependencies(tmp_path, logger=logger, install_python=True, install_node=False)
    assert calls[0][0] == sys.executable


def test_install_dependencies_warns_when_disabled(monkeypatch, tmp_path) -> None:
    def fake_run(*_, **__):  # pragma: no cover - should not be called
        raise AssertionError("Should not run installers when both disabled")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    logger = cli.ConsoleLogger()
    warnings: list[str] = []
    monkeypatch.setattr(logger, "warning", lambda message: warnings.append(message))

    cli._install_dependencies(tmp_path, logger=logger, install_python=False, install_node=False)
    assert warnings and "Skipping dependency installation" in warnings[0]


def test_run_subprocess_handles_failed_exit(monkeypatch, tmp_path) -> None:
    def fake_run(command, *, cwd, check):
        raise subprocess.CalledProcessError(returncode=2, cmd=command)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    logger = cli.ConsoleLogger()

    with pytest.raises(typer.Exit):
        cli._run_subprocess(["npm", "install"], cwd=tmp_path, label="Node", logger=logger)


def test_resolve_run_build_prefers_overridden_callable(monkeypatch) -> None:
    def fake_run_build(*_, **__):
        return "ok"

    monkeypatch.setattr(cli, "run_build", fake_run_build)

    resolved = cli._resolve_run_build()
    assert resolved is fake_run_build


def test_init_optionally_installs_dependencies(monkeypatch) -> None:
    with runner.isolated_filesystem():
        called: dict[str, Path] = {}

        def fake_install(
            project_root,
            *,
            logger,
            install_python=True,
            install_node=True,
        ):
            called["root"] = project_root.resolve()

        monkeypatch.setattr(cli, "_install_dependencies", fake_install)

        result = runner.invoke(app, ["init", "demo", "--install"], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout
        assert called["root"] == Path("demo").resolve()
        assert "Next steps" in result.stdout
        assert "pyxle install" not in result.stdout
        assert "pyxle dev" in result.stdout


def test_dev_command_requires_existing_directory() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["dev", "missing"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "does not exist" in result.stdout


def test_dev_command_rejects_file_path() -> None:
    with runner.isolated_filesystem():
        file_path = Path("not-a-dir.txt")
        file_path.write_text("demo", encoding="utf-8")

        result = runner.invoke(app, ["dev", "not-a-dir.txt"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "not a directory" in result.stdout


def test_dev_command_invokes_devserver(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        captured: dict[str, object] = {}

        class StubDevServer:
            def __init__(self, settings, logger):
                captured["settings"] = settings
                captured["logger"] = logger

            async def start(self) -> None:
                captured["started"] = True

        def fake_run(coro):
            captured["run_invoked"] = True
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        monkeypatch.setattr("pyxle.cli.DevServer", StubDevServer)
        monkeypatch.setattr("pyxle.cli.asyncio.run", fake_run)

        result = runner.invoke(
            app,
            [
                "dev",
                "demo",
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--vite-host",
                "localhost",
                "--vite-port",
                "1234",
                "--no-debug",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.stdout
        settings = captured["settings"]
        assert settings.project_root == project.resolve()
        assert settings.starlette_host == "0.0.0.0"
        assert settings.starlette_port == 9000
        assert settings.vite_host == "localhost"
        assert settings.vite_port == 1234
        assert settings.debug is False
        assert captured.get("started") is True
        assert captured.get("run_invoked") is True
        assert captured.get("logger").__class__.__name__ == "ConsoleLogger"


def test_dev_command_respects_config_file(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "src" / "pages").mkdir(parents=True)
        (project / "static").mkdir(parents=True)

        config_payload = {
            "pagesDir": "src/pages",
            "publicDir": "static",
            "buildDir": ".pyxle-dist",
            "starlette": {"host": "0.0.0.0", "port": 9100},
            "vite": {"host": "localhost", "port": 6200},
            "debug": False,
        }
        (project / "pyxle.config.json").write_text(json.dumps(config_payload), encoding="utf-8")

        captured: dict[str, object] = {}

        class StubDevServer:
            def __init__(self, settings, logger):
                captured["settings"] = settings
                captured["logger"] = logger

            async def start(self) -> None:
                captured["started"] = True

        def fake_run(coro):
            captured["run_invoked"] = True
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        monkeypatch.setattr("pyxle.cli.DevServer", StubDevServer)
        monkeypatch.setattr("pyxle.cli.asyncio.run", fake_run)

        result = runner.invoke(app, ["dev", "demo"], catch_exceptions=False)

        assert result.exit_code == 0, result.stdout
        settings = captured["settings"]
        assert settings.project_root == project.resolve()
        assert settings.pages_dir == (project / "src" / "pages").resolve()
        assert settings.public_dir == (project / "static").resolve()
        assert settings.build_root == (project / ".pyxle-dist").resolve()
        assert settings.starlette_host == "0.0.0.0"
        assert settings.starlette_port == 9100
        assert settings.vite_host == "localhost"
        assert settings.vite_port == 6200
        assert settings.debug is False
        assert captured.get("started") is True
        assert captured.get("run_invoked") is True


def test_build_command_invokes_pipeline(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        captured: dict[str, object] = {}

        def fake_run_build(settings, *, logger, dist_dir=None, force_rebuild=True):
            captured["settings"] = settings
            captured["logger"] = logger
            captured["dist_dir"] = dist_dir
            captured["force_rebuild"] = force_rebuild
            from pyxle.build.pipeline import BuildResult
            from pyxle.devserver.builder import BuildSummary
            from pyxle.devserver.registry import MetadataRegistry

            summary = BuildSummary()
            result_dist = dist_dir or settings.project_root / "dist"
            (result_dist / "client").mkdir(parents=True, exist_ok=True)
            (result_dist / "server").mkdir(parents=True, exist_ok=True)
            (result_dist / "metadata").mkdir(parents=True, exist_ok=True)
            (result_dist / "public").mkdir(parents=True, exist_ok=True)
            client_manifest_path = result_dist / "client" / "manifest.json"
            client_manifest_path.write_text("{}", encoding="utf-8")
            page_manifest_path = result_dist / "page-manifest.json"
            page_manifest_path.write_text("{}", encoding="utf-8")
            return BuildResult(
                dist_dir=result_dist,
                client_dir=result_dist / "client",
                server_dir=result_dist / "server",
                metadata_dir=result_dist / "metadata",
                public_dir=result_dist / "public",
                client_manifest_path=client_manifest_path,
                page_manifest={"/": {"client": {"file": "client/index.js", "imports": []}}},
                page_manifest_path=page_manifest_path,
                summary=summary,
                registry=MetadataRegistry(pages=[], apis=[]),
            )

        monkeypatch.setattr("pyxle.cli.run_build", fake_run_build)

        result = runner.invoke(
            app,
            [
                "build",
                "demo",
                "--out-dir",
                "dist-prod",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.stdout
        settings = captured["settings"]
        assert settings.project_root == project.resolve()
        expected_out_dir = (project / "dist-prod").resolve()
        assert captured["dist_dir"] == expected_out_dir
        assert captured["force_rebuild"] is True
        assert "Build completed" in result.stdout
        assert "Artifacts" in result.stdout
        assert "Client manifest" in result.stdout
        assert "Page manifest" in result.stdout
        assert "Server modules" in result.stdout
        assert "Metadata" in result.stdout
        assert "Public assets" in result.stdout


def test_build_command_supports_incremental_flag(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        captured: dict[str, object] = {}

        def fake_run_build(settings, *, logger, dist_dir=None, force_rebuild=True):
            captured["force_rebuild"] = force_rebuild
            from pyxle.build.pipeline import BuildResult
            from pyxle.devserver.builder import BuildSummary
            from pyxle.devserver.registry import MetadataRegistry

            summary = BuildSummary()
            result_dist = settings.project_root / "dist"
            (result_dist / "client").mkdir(parents=True, exist_ok=True)
            (result_dist / "server").mkdir(parents=True, exist_ok=True)
            (result_dist / "metadata").mkdir(parents=True, exist_ok=True)
            (result_dist / "public").mkdir(parents=True, exist_ok=True)
            client_manifest_path = result_dist / "client" / "manifest.json"
            client_manifest_path.write_text("{}", encoding="utf-8")
            page_manifest_path = result_dist / "page-manifest.json"
            page_manifest_path.write_text("{}", encoding="utf-8")
            return BuildResult(
                dist_dir=result_dist,
                client_dir=result_dist / "client",
                server_dir=result_dist / "server",
                metadata_dir=result_dist / "metadata",
                public_dir=result_dist / "public",
                client_manifest_path=client_manifest_path,
                page_manifest={},
                page_manifest_path=page_manifest_path,
                summary=summary,
                registry=MetadataRegistry(pages=[], apis=[]),
            )

        monkeypatch.setattr("pyxle.cli.run_build", fake_run_build)

        result = runner.invoke(app, ["build", "demo", "--incremental"], catch_exceptions=False)

        assert result.exit_code == 0, result.stdout
        assert captured.get("force_rebuild") is False


def test_build_command_logs_missing_public_assets(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        def fake_run_build(settings, *, logger, dist_dir=None, force_rebuild=True):
            from pyxle.build.pipeline import BuildResult
            from pyxle.devserver.builder import BuildSummary
            from pyxle.devserver.registry import MetadataRegistry

            summary = BuildSummary()
            result_dist = settings.project_root / "dist"
            (result_dist / "client").mkdir(parents=True, exist_ok=True)
            (result_dist / "server").mkdir(parents=True, exist_ok=True)
            (result_dist / "metadata").mkdir(parents=True, exist_ok=True)
            client_manifest_path = result_dist / "client" / "manifest.json"
            client_manifest_path.write_text("{}", encoding="utf-8")
            page_manifest_path = result_dist / "page-manifest.json"
            page_manifest_path.write_text("{}", encoding="utf-8")
            missing_public = result_dist / "public-missing"
            return BuildResult(
                dist_dir=result_dist,
                client_dir=result_dist / "client",
                server_dir=result_dist / "server",
                metadata_dir=result_dist / "metadata",
                public_dir=missing_public,
                client_manifest_path=client_manifest_path,
                page_manifest={"/": {"client": {"file": "client/index.js", "imports": []}}},
                page_manifest_path=page_manifest_path,
                summary=summary,
                registry=MetadataRegistry(pages=[], apis=[]),
            )

        monkeypatch.setattr("pyxle.cli.run_build", fake_run_build)

        result = runner.invoke(app, ["build", "demo"], catch_exceptions=False)

        assert result.exit_code == 0, result.stdout
        assert "Public assets" in result.stdout
        assert "(not generated)" in result.stdout


def test_dev_command_prints_effective_config(monkeypatch) -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        (project / "pages").mkdir(parents=True)
        (project / "public").mkdir(parents=True)

        (project / "pyxle.config.json").write_text(
            json.dumps(
                {
                    "starlette": {"host": "127.0.0.1", "port": 8300},
                    "vite": {"host": "127.0.0.1", "port": 5400},
                }
            ),
            encoding="utf-8",
        )

        captured: dict[str, object] = {}

        class StubDevServer:
            def __init__(self, settings, logger):
                captured["settings"] = settings
                captured["logger"] = logger

            async def start(self) -> None:
                captured["started"] = True

        monkeypatch.setattr("pyxle.cli.DevServer", StubDevServer)

        def fake_run(coro):
            captured["run_invoked"] = True
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        monkeypatch.setattr("pyxle.cli.asyncio.run", fake_run)

        result = runner.invoke(
            app,
            [
                "dev",
                "demo",
                "--print-config",
                "--vite-port",
                "6000",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.stdout
        assert "Effective configuration" in result.stdout
        assert "\"vite\": {" in result.stdout
        assert "6000" in result.stdout
        assert captured.get("run_invoked") is True


def test_dev_command_fails_with_invalid_config() -> None:
    with runner.isolated_filesystem():
        project = Path("demo")
        project.mkdir()
        (project / "pages").mkdir()
        (project / "public").mkdir()
        (project / "pyxle.config.json").write_text("[]", encoding="utf-8")

        result = runner.invoke(app, ["dev", "demo"], catch_exceptions=False)

        assert result.exit_code == 1
        assert "Configuration file" in result.stdout


def test_build_command_requires_existing_directory() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["build", "missing"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "does not exist" in result.stdout


def test_build_command_rejects_file_path() -> None:
    with runner.isolated_filesystem():
        file_path = Path("not-a-dir.txt")
        file_path.write_text("demo", encoding="utf-8")

        result = runner.invoke(app, ["build", "not-a-dir.txt"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "not a directory" in result.stdout


class _StubLogger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.steps: list[tuple[str, str | None]] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def success(self, message: str) -> None:
        self.infos.append(message)

    def warning(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def step(self, label: str, detail: str | None = None) -> None:
        self.steps.append((label, detail))


def test_build_function_errors_when_directory_missing(monkeypatch, tmp_path: Path) -> None:
    from pyxle.cli import build

    logger = _StubLogger()
    monkeypatch.setattr("pyxle.cli.get_logger", lambda: logger)

    with pytest.raises(typer.Exit):
        build(directory=tmp_path / "missing")

    assert logger.errors and "does not exist" in logger.errors[0]


def test_build_function_errors_when_path_not_directory(monkeypatch, tmp_path: Path) -> None:
    from pyxle.cli import build

    logger = _StubLogger()
    monkeypatch.setattr("pyxle.cli.get_logger", lambda: logger)

    file_path = tmp_path / "file.txt"
    file_path.write_text("demo", encoding="utf-8")

    with pytest.raises(typer.Exit):
        build(directory=file_path)

    assert logger.errors and "not a directory" in logger.errors[0]


def test_compile_hidden_command_invokes_compiler() -> None:
    with runner.isolated_filesystem():
        source_dir = Path("pages/posts")
        source_dir.mkdir(parents=True)
        source_file = source_dir / "[id].pyx"
        source_file.write_text(
            dedent(
                """
                
                @server
                async def loader(request):
                    return {"id": request.params.get("id")}

                # --- JavaScript/PSX ---
                import React from 'react';

                export default function Page({ data }) {
                    return <div>{data.id}</div>;
                }
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["compile", str(source_file)], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout
        assert "Compiled" in result.stdout

        build_root = Path(".pyxle-build")
        server_artifact = build_root / "server/pages/posts/[id].py"
        client_artifact = build_root / "client/pages/posts/[id].jsx"
        metadata_artifact = build_root / "metadata/pages/posts/[id].json"

        assert server_artifact.exists()
        assert client_artifact.exists()
        metadata = read_json(metadata_artifact)
        assert metadata["route_path"] == "/posts/{id}"
        assert metadata["loader_name"] == "loader"
    assert metadata["alternate_route_paths"] == []
    assert metadata["head"] == []


def test_resolve_run_build_returns_existing_callable(monkeypatch):
    sentinel = object()

    def fake_run_build(*args, **kwargs):  # pragma: no cover - function body unused
        return sentinel

    monkeypatch.setattr(cli, "run_build", fake_run_build)

    resolved = cli._resolve_run_build()

    assert resolved is fake_run_build


def test_resolve_run_build_imports_when_placeholder(monkeypatch):
    def stub_run_build(*args, **kwargs):  # pragma: no cover - function body unused
        raise AssertionError("Should not be invoked during resolution")

    monkeypatch.setattr(cli, "run_build", None)
    monkeypatch.setattr("pyxle.build.run_build", stub_run_build)

    resolved = cli._resolve_run_build()

    assert resolved is stub_run_build


    def test_cli_version_option_displays_version() -> None:
        result = runner.invoke(app, ["--version"], catch_exceptions=False)
        assert result.exit_code == 0
        assert __version__ in result.stdout


    def test_version_callback_handles_flag_values(capsys) -> None:
        with pytest.raises(typer.Exit):
            version_callback(True)

        captured = capsys.readouterr()
        assert __version__ in captured.out

        assert version_callback(False) is None


def test_compile_command_errors_when_source_missing() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["compile", "pages/missing.pyx"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "was not found" in result.stdout


def test_compile_command_surfaces_compiler_failure() -> None:
    with runner.isolated_filesystem():
        source_dir = Path("pages")
        source_dir.mkdir()
        source_file = source_dir / "bad.pyx"
        source_file.write_text(
            dedent(
                """
                @server
                def loader(request):
                    return {}

                export default function Demo() {
                    return <div />;
                }
                """
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["compile", str(source_file)], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Compilation failed" in result.stdout


def test_resolve_global_script_entries_deduplicates(tmp_path: Path) -> None:
    config = PyxleConfig(
        global_scripts=(
            " scripts/track.js ",
            "",
            "scripts/track.js",
            "scripts/analytics.js",
        )
    )

    result = cli._resolve_global_script_entries(tmp_path, config)

    assert result == ("scripts/track.js", "scripts/analytics.js")
