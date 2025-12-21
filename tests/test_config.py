from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyxle.config import ConfigError, PyxleConfig, load_config


def write_config(root: Path, payload: dict) -> Path:
    config_path = root / "pyxle.config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def test_load_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    result = load_config(tmp_path)
    assert result == PyxleConfig()


def test_load_config_parses_custom_values(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {
            "pagesDir": "src/pages",
            "publicDir": "static",
            "buildDir": ".pyxle-dist",
            "starlette": {"host": "0.0.0.0", "port": 9001},
            "vite": {"host": "localhost", "port": 6001},
            "debug": False,
        },
    )

    config = load_config(tmp_path)
    assert config.pages_dir == "src/pages"
    assert config.public_dir == "static"
    assert config.build_dir == ".pyxle-dist"
    assert config.starlette_host == "0.0.0.0"
    assert config.starlette_port == 9001
    assert config.vite_host == "localhost"
    assert config.vite_port == 6001
    assert config.debug is False


def test_load_config_rejects_unknown_keys(tmp_path: Path) -> None:
    write_config(tmp_path, {"unknown": "value"})

    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path)

    assert "Unknown configuration keys" in str(excinfo.value)


def test_load_config_validates_types(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {
            "pagesDir": "",
        },
    )

    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path)

    assert "pagesDir" in str(excinfo.value)


def test_apply_overrides_updates_values() -> None:
    config = PyxleConfig()
    overrides = config.apply_overrides(
        pages_dir="src/pages",
        public_dir="web",
        build_dir=".cache",
        starlette_host="0.0.0.0",
        starlette_port=9000,
        vite_host="localhost",
        vite_port=5555,
        debug=False,
    )

    assert overrides.pages_dir == "src/pages"
    assert overrides.public_dir == "web"
    assert overrides.build_dir == ".cache"
    assert overrides.starlette_host == "0.0.0.0"
    assert overrides.starlette_port == 9000
    assert overrides.vite_host == "localhost"
    assert overrides.vite_port == 5555
    assert overrides.debug is False


def test_apply_overrides_validates_ports() -> None:
    config = PyxleConfig()

    with pytest.raises(ConfigError):
        config.apply_overrides(starlette_port=0)

    with pytest.raises(ConfigError):
        config.apply_overrides(vite_port=70000)


def test_load_config_parses_middleware_list(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {
            "middleware": [
                "package.auth:AuthMiddleware",
                "package.rate:rate_limit",
            ]
        },
    )

    config = load_config(tmp_path)
    assert config.middleware == (
        "package.auth:AuthMiddleware",
        "package.rate:rate_limit",
    )
    assert config.to_devserver_kwargs()["custom_middlewares"] == config.middleware
    assert config.to_dict()["middleware"] == list(config.middleware)


def test_load_config_rejects_invalid_middleware_entries(tmp_path: Path) -> None:
    write_config(tmp_path, {"middleware": ["", 123]})

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_config_rejects_non_list_middleware(tmp_path: Path) -> None:
    write_config(tmp_path, {"middleware": "not-a-list"})

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_config_parses_route_middleware_block(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {
            "routeMiddleware": {
                "pages": ["package.pages:policy"],
                "apis": ["package.apis:policy"],
            }
        },
    )

    config = load_config(tmp_path)
    assert config.page_route_middleware == ("package.pages:policy",)
    assert config.api_route_middleware == ("package.apis:policy",)
    dev_kwargs = config.to_devserver_kwargs()
    assert dev_kwargs["page_route_hooks"] == config.page_route_middleware
    assert dev_kwargs["api_route_hooks"] == config.api_route_middleware
    representation = config.to_dict()["routeMiddleware"]
    assert representation["pages"] == ["package.pages:policy"]
    assert representation["apis"] == ["package.apis:policy"]


def test_load_config_rejects_invalid_route_middleware_block(tmp_path: Path) -> None:
    write_config(tmp_path, {"routeMiddleware": []})

    with pytest.raises(ConfigError):
        load_config(tmp_path)

    write_config(tmp_path, {"routeMiddleware": {"pages": ["" ]}})

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_config_parses_styling_block(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {
            "styling": {
                "globalStyles": [
                    "styles/global.css",
                    "styles/theme/dark.css",
                ],
                "globalScripts": [
                    "scripts/analytics.js",
                ],
            }
        },
    )

    config = load_config(tmp_path)
    assert config.global_styles == ("styles/global.css", "styles/theme/dark.css")
    assert config.global_scripts == ("scripts/analytics.js",)
    representation = config.to_dict()["styling"]
    assert representation["globalStyles"] == ["styles/global.css", "styles/theme/dark.css"]
    assert representation["globalScripts"] == ["scripts/analytics.js"]


def test_load_config_rejects_invalid_styling_block(tmp_path: Path) -> None:
    write_config(tmp_path, {"styling": []})

    with pytest.raises(ConfigError):
        load_config(tmp_path)

    write_config(tmp_path, {"styling": {"globalStyles": "not-a-list"}})

    with pytest.raises(ConfigError):
        load_config(tmp_path)

    write_config(tmp_path, {"styling": {"globalStyles": [""]}})

    with pytest.raises(ConfigError):
        load_config(tmp_path)

    write_config(tmp_path, {"styling": {"globalScripts": "not-a-list"}})

    with pytest.raises(ConfigError):
        load_config(tmp_path)

    write_config(tmp_path, {"styling": {"globalScripts": [""]}})

    with pytest.raises(ConfigError):
        load_config(tmp_path)
