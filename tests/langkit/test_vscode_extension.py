from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_ROOT = REPO_ROOT / "editors" / "vscode-pyxle"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_language_configuration_json_is_valid() -> None:
    config = _load_json(EXTENSION_ROOT / "language-configuration.json")

    assert config["comments"]["lineComment"] == "#"
    assert config["comments"]["blockComment"] == ["/*", "*/"]


def test_syntax_grammar_uses_segment_patterns() -> None:
    grammar = _load_json(EXTENSION_ROOT / "syntaxes" / "pyx.tmLanguage.json")
    includes = [entry.get("include") for entry in grammar.get("patterns", [])]

    assert includes == ["#python-block", "#jsx-block"]


def test_extension_manifest_declares_language_server_settings() -> None:
    manifest = _load_json(EXTENSION_ROOT / "package.json")
    properties = manifest["contributes"]["configuration"][0]["properties"]

    assert properties["pyxleLangserver.command"]["default"] == "pyxle-langserver"
    assert properties["pyxleLangserver.args"]["default"] == ["--stdio"]
