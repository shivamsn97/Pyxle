"""Configuration loading utilities for Pyxle projects."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

DEFAULT_CONFIG_FILENAME = "pyxle.config.json"


class ConfigError(Exception):
    """Raised when a configuration file cannot be parsed or validated."""


@dataclass(frozen=True, slots=True)
class PyxleConfig:
    """Resolved configuration values for a Pyxle project."""

    pages_dir: str = "pages"
    public_dir: str = "public"
    build_dir: str = ".pyxle-build"
    starlette_host: str = "127.0.0.1"
    starlette_port: int = 8000
    vite_host: str = "127.0.0.1"
    vite_port: int = 5173
    debug: bool = True
    middleware: tuple[str, ...] = ()
    page_route_middleware: tuple[str, ...] = ()
    api_route_middleware: tuple[str, ...] = ()
    global_styles: tuple[str, ...] = ()

    def to_devserver_kwargs(self) -> Dict[str, Any]:
        """Return keyword arguments for :class:`pyxle.devserver.DevServerSettings`."""

        return {
            "pages_dir": self.pages_dir,
            "public_dir": self.public_dir,
            "build_dir": self.build_dir,
            "starlette_host": self.starlette_host,
            "starlette_port": self.starlette_port,
            "vite_host": self.vite_host,
            "vite_port": self.vite_port,
            "debug": self.debug,
            "custom_middlewares": self.middleware,
            "page_route_hooks": self.page_route_middleware,
            "api_route_hooks": self.api_route_middleware,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialisable dictionary of the configuration."""

        return {
            "pagesDir": self.pages_dir,
            "publicDir": self.public_dir,
            "buildDir": self.build_dir,
            "starlette": {"host": self.starlette_host, "port": self.starlette_port},
            "vite": {"host": self.vite_host, "port": self.vite_port},
            "debug": self.debug,
            "middleware": list(self.middleware),
            "routeMiddleware": {
                "pages": list(self.page_route_middleware),
                "apis": list(self.api_route_middleware),
            },
            "styling": {
                "globalStyles": list(self.global_styles),
            },
        }

    def apply_overrides(
        self,
        *,
        pages_dir: Optional[str] = None,
        public_dir: Optional[str] = None,
        build_dir: Optional[str] = None,
        starlette_host: Optional[str] = None,
        starlette_port: Optional[int] = None,
        vite_host: Optional[str] = None,
        vite_port: Optional[int] = None,
        debug: Optional[bool] = None,
    ) -> "PyxleConfig":
        """Return a new configuration with optional overrides applied."""

        updated = self
        if pages_dir is not None:
            updated = replace(updated, pages_dir=pages_dir)
        if public_dir is not None:
            updated = replace(updated, public_dir=public_dir)
        if build_dir is not None:
            updated = replace(updated, build_dir=build_dir)
        if starlette_host is not None:
            updated = replace(updated, starlette_host=starlette_host)
        if starlette_port is not None:
            _validate_port(starlette_port, "--port")
            updated = replace(updated, starlette_port=starlette_port)
        if vite_host is not None:
            updated = replace(updated, vite_host=vite_host)
        if vite_port is not None:
            _validate_port(vite_port, "--vite-port")
            updated = replace(updated, vite_port=vite_port)
        if debug is not None:
            updated = replace(updated, debug=debug)
        return updated


def load_config(
    project_root: Path,
    *,
    config_path: Optional[Path] = None,
) -> PyxleConfig:
    """Load ``pyxle.config.json`` from ``project_root`` if present."""

    root = project_root.expanduser().resolve()
    if config_path is not None:
        candidate = config_path.expanduser().resolve()
    else:
        candidate = root / DEFAULT_CONFIG_FILENAME

    if not candidate.exists():
        return PyxleConfig()

    if not candidate.is_file():
        raise ConfigError(f"Configuration path '{candidate}' is not a file.")

    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - exercised via unit tests
        raise ConfigError(f"Failed to parse configuration: {exc.msg} (line {exc.lineno}).") from exc

    if not isinstance(payload, Mapping):
        raise ConfigError("Configuration file must contain a JSON object at the top level.")

    return _parse_config_dict(dict(payload), source=candidate)


def _parse_config_dict(data: Dict[str, Any], *, source: Path) -> PyxleConfig:
    allowed_top_keys = {
        "pagesDir",
        "publicDir",
        "buildDir",
        "starlette",
        "vite",
        "debug",
        "middleware",
        "routeMiddleware",
        "styling",
    }
    unknown_keys = set(data) - allowed_top_keys
    if unknown_keys:
        formatted = ", ".join(sorted(unknown_keys))
        raise ConfigError(f"Unknown configuration keys in '{source}': {formatted}.")

    pages_dir = _validate_directory_value(data.get("pagesDir", "pages"), "pagesDir")
    public_dir = _validate_directory_value(data.get("publicDir", "public"), "publicDir")
    build_dir = _validate_directory_value(data.get("buildDir", ".pyxle-build"), "buildDir")

    starlette = data.get("starlette", {})
    starlette_host, starlette_port = _parse_network_block(starlette, "starlette", source)

    vite = data.get("vite", {})
    vite_host, vite_port = _parse_network_block(vite, "vite", source)

    debug_value = data.get("debug", True)
    if not isinstance(debug_value, bool):
        raise ConfigError(
            f"Invalid value for 'debug' in '{source}': expected boolean, got {type(debug_value).__name__}."
        )

    middleware_specs = _parse_middleware_list(data.get("middleware"), source=source)
    page_route_specs, api_route_specs = _parse_route_middleware_block(
        data.get("routeMiddleware"),
        source=source,
    )
    global_styles = _parse_styling_block(data.get("styling"), source=source)

    return PyxleConfig(
        pages_dir=pages_dir,
        public_dir=public_dir,
        build_dir=build_dir,
        starlette_host=starlette_host,
        starlette_port=starlette_port,
        vite_host=vite_host,
        vite_port=vite_port,
        debug=debug_value,
        middleware=middleware_specs,
        page_route_middleware=page_route_specs,
        api_route_middleware=api_route_specs,
        global_styles=global_styles,
    )


def _parse_styling_block(value: Any, *, source: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ConfigError(
            f"Invalid value for 'styling' in '{source}': expected object with 'globalStyles' list."
        )

    global_styles = value.get("globalStyles")
    if global_styles is None:
        return ()
    if not isinstance(global_styles, list):
        raise ConfigError(
            f"Invalid value for 'styling.globalStyles' in '{source}': expected list of file paths."
        )

    normalized: list[str] = []
    for index, entry in enumerate(global_styles):
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(
                f"Invalid entry at index {index} in 'styling.globalStyles' within '{source}': expected non-empty string."
            )
        normalized.append(entry.strip())

    return tuple(normalized)


def _validate_directory_value(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Invalid value for '{key}': expected non-empty string.")
    return value


def _parse_network_block(value: Any, key: str, source: Path) -> tuple[str, int]:
    if value is None:
        return ("127.0.0.1", 8000) if key == "starlette" else ("127.0.0.1", 5173)
    if not isinstance(value, Mapping):
        raise ConfigError(
            f"Invalid value for '{key}' in '{source}': expected object with 'host' and 'port'."
        )

    host = value.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError(
            f"Invalid host in '{key}' block of '{source}': expected non-empty string."
        )

    port = value.get("port", 8000 if key == "starlette" else 5173)
    _validate_port(port, f"{key}.port")

    return host, port


def _validate_port(value: Any, key: str) -> int:
    if not isinstance(value, int):
        raise ConfigError(f"Invalid value for '{key}': expected integer port value.")
    if value <= 0 or value > 65535:
        raise ConfigError(f"Port for '{key}' must be between 1 and 65535 (got {value}).")
    return value


def _parse_route_middleware_block(value: Any, *, source: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if value is None:
        return ((), ())
    if not isinstance(value, Mapping):
        raise ConfigError(
            f"Invalid value for 'routeMiddleware' in '{source}': expected object with 'pages'/'apis' arrays."
        )

    pages = _parse_middleware_list(value.get("pages"), source=source, field_name="routeMiddleware.pages")
    apis = _parse_middleware_list(value.get("apis"), source=source, field_name="routeMiddleware.apis")
    return (pages, apis)


def _parse_middleware_list(value: Any, *, source: Path, field_name: str = "middleware") -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError(
            f"Invalid value for '{field_name}' in '{source}': expected a list of module paths."
        )

    specs: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(
                f"Invalid middleware entry at index {index} in '{source}' for '{field_name}': expected non-empty string."
            )
        specs.append(entry.strip())

    return tuple(specs)


__all__ = ["PyxleConfig", "ConfigError", "load_config", "DEFAULT_CONFIG_FILENAME"]
