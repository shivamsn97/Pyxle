"""Implementation of the ``pyxle init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import typer

from pyxle import __version__

from .assets import default_favicon_bytes
from .logger import ConsoleLogger
from .scaffold import FilesystemWriter, InvalidProjectName, validate_project_name
from .templates import ScaffoldingTemplate, TemplateRegistry

SUPPORTED_TEMPLATES = {"default"}


def build_template_registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    registry.register(".gitignore", ScaffoldingTemplate(".gitignore"))
    registry.register("package.json", ScaffoldingTemplate("package.json"))
    registry.register("requirements.txt", ScaffoldingTemplate("requirements.txt"))
    registry.register("pyxle.config.json", ScaffoldingTemplate("pyxle.config.json"))
    registry.register("pages/layout.pyx", ScaffoldingTemplate("pages/layout.pyx"))
    registry.register("pages/index.pyx", ScaffoldingTemplate("pages/index.pyx"))
    registry.register("pages/projects/index.pyx", ScaffoldingTemplate("pages/projects/index.pyx"))
    registry.register("pages/projects/template.pyx", ScaffoldingTemplate("pages/projects/template.pyx"))
    registry.register("pages/diagnostics.pyx", ScaffoldingTemplate("pages/diagnostics.pyx"))
    registry.register("pages/[...slug].pyx", ScaffoldingTemplate("pages/[...slug].pyx"))
    registry.register("pages/api/pulse.py", ScaffoldingTemplate("pages/api/pulse.py"))
    registry.register("pages/components/__init__.py", ScaffoldingTemplate("pages/components/__init__.py"))
    registry.register("pages/components/layout.jsx", ScaffoldingTemplate("pages/components/layout.jsx"))
    registry.register("pages/components/head.py", ScaffoldingTemplate("pages/components/head.py"))
    registry.register("pages/components/site.py", ScaffoldingTemplate("pages/components/site.py"))
    registry.register("middlewares/__init__.py", ScaffoldingTemplate("middlewares/__init__.py"))
    registry.register("middlewares/telemetry.py", ScaffoldingTemplate("middlewares/telemetry.py"))
    registry.register("public/styles/pyxle.css", ScaffoldingTemplate("public/styles/pyxle.css"))
    registry.register("public/scripts/pyxle-effects.js", ScaffoldingTemplate("public/scripts/pyxle-effects.js"))
    return registry


def render_templates(
    writer: FilesystemWriter,
    registry: TemplateRegistry,
    context: Mapping[str, str],
    *,
    overwrite: bool = False,
) -> None:
    for output_path, template in registry.items():
        payload = template.render(context)
        writer.write(output_path, payload, binary=template.binary, overwrite=overwrite)


def log_next_steps(
    logger: ConsoleLogger,
    target_path: Path,
    *,
    include_install_hint: bool,
) -> None:
    logger.info("Next steps:")
    logger.info("  1. cd %s" % target_path.as_posix())
    if include_install_hint:
        logger.info("  2. pyxle install   # installs Python + Node dependencies")
        logger.info("     (or run 'pip install -r requirements.txt' and 'npm install')")
        logger.info("  3. pyxle dev")
    else:
        logger.info("  2. pyxle dev")


def run_init(
    project_name: str,
    force: bool,
    template: str,
    logger: ConsoleLogger,
    *,
    log_steps: bool = True,
) -> Path:
    if template not in SUPPORTED_TEMPLATES:
        raise typer.BadParameter(
            f"Unsupported template '{template}'. Available: {', '.join(sorted(SUPPORTED_TEMPLATES))}"
        )

    try:
        project_slug = validate_project_name(project_name)
    except InvalidProjectName as exc:
        raise typer.BadParameter(str(exc), param_hint="name") from exc

    target_path = Path(project_slug)
    writer = FilesystemWriter(target_path)

    try:
        writer.ensure_root(force=force)
    except FileExistsError:
        logger.error(
            "Target directory already exists. Re-run with --force to overwrite."
        )
        raise typer.Exit(code=1)

    logger.step("Creating project directory", target_path.as_posix())
    writer.touch_directory("pages/api")
    writer.touch_directory("pages/components")
    writer.touch_directory("pages/projects")
    writer.touch_directory("middlewares")
    writer.touch_directory("public/styles")
    writer.touch_directory("public/scripts")

    context = {
        "package_name": project_slug,
        "project_name": project_name,
        "pyxle_version": __version__,
    }
    render_templates(writer, build_template_registry(), context, overwrite=force)
    writer.write("public/favicon.ico", default_favicon_bytes(), binary=True, overwrite=force)

    logger.success(f"Project scaffolded at {target_path.as_posix()}")
    if log_steps:
        log_next_steps(logger, target_path, include_install_hint=True)

    return target_path
