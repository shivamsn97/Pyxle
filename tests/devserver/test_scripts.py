from __future__ import annotations

from pathlib import Path

import pytest

from pyxle.devserver.scripts import (
    GlobalScript,
    GlobalScriptConfigError,
    _make_identifier,
    _normalize_relative_path,
    resolve_global_scripts,
    sync_global_scripts,
)


def test_global_script_properties(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "analytics.js"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("console.log('hi');\n", encoding="utf-8")

    script = GlobalScript(
        source_path=source,
        relative_path=Path("scripts/analytics.js"),
        identifier="analytics",
    )

    assert script.client_relative_path == Path("scripts/analytics.js")
    assert script.import_specifier == "./scripts/analytics.js"
    assert script.as_dict()["client_relative_path"] == "scripts/analytics.js"


def test_resolve_global_scripts_filters_duplicates(tmp_path: Path) -> None:
    assets = tmp_path / "scripts"
    assets.mkdir()
    track = assets / "track.js"
    track.write_text("console.log('track');", encoding="utf-8")
    metrics = assets / "metrics.js"
    metrics.write_text("console.log('metrics');", encoding="utf-8")

    result = resolve_global_scripts(
        tmp_path,
        [" scripts/track.js ", "", None, "scripts/track.js", "scripts/metrics.js"],
    )

    assert {script.relative_path.as_posix() for script in result} == {
        "scripts/track.js",
        "scripts/metrics.js",
    }
    identifiers = {script.identifier for script in result}
    assert all(identifier.startswith("pyxle-script-") for identifier in identifiers)


def test_resolve_global_scripts_validates_entries(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    assert resolve_global_scripts(tmp_path, None) == ()
    with pytest.raises(GlobalScriptConfigError):
        resolve_global_scripts(tmp_path, [object()])
    with pytest.raises(GlobalScriptConfigError):
        resolve_global_scripts(tmp_path, ["missing.js"])
    with pytest.raises(GlobalScriptConfigError):
        resolve_global_scripts(tmp_path, ["folder"])


def test_normalize_relative_path_rejects_out_of_tree(tmp_path: Path) -> None:
    with pytest.raises(GlobalScriptConfigError):
        _normalize_relative_path(str(tmp_path / "absolute.js"))
    with pytest.raises(GlobalScriptConfigError):
        _normalize_relative_path("../outside.js")
    with pytest.raises(GlobalScriptConfigError):
        _normalize_relative_path("//")
    with pytest.raises(GlobalScriptConfigError):
        _normalize_relative_path("./")

    assert _normalize_relative_path("scripts/./track.js") == Path("scripts/track.js")
    assert _normalize_relative_path("./analytics.js") == Path("analytics.js")


def test_make_identifier_is_deterministic() -> None:
    first = _make_identifier("scripts/track.js")
    second = _make_identifier("scripts/track.js")
    other = _make_identifier("scripts/metrics.js")

    assert first == second
    assert first != other


def test_sync_global_scripts_writes_only_changed_files(tmp_path: Path) -> None:
    assets = tmp_path / "scripts"
    assets.mkdir()
    script_path = assets / "track.js"
    script_path.write_text("console.log('track');", encoding="utf-8")
    [script] = resolve_global_scripts(tmp_path, ["scripts/track.js"])

    client_root = tmp_path / "client"
    first = sync_global_scripts([script], client_root=client_root)
    assert first == ["scripts/track.js"]

    second = sync_global_scripts([script], client_root=client_root)
    assert second == []

    script_path.write_text("console.log('updated');", encoding="utf-8")
    third = sync_global_scripts([script], client_root=client_root)
    assert third == ["scripts/track.js"]


def test_sync_global_scripts_handles_unreadable_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assets = tmp_path / "scripts"
    assets.mkdir()
    script_path = assets / "track.js"
    script_path.write_text("console.log('track');", encoding="utf-8")
    [script] = resolve_global_scripts(tmp_path, ["scripts/track.js"])

    client_root = tmp_path / "client"
    sync_global_scripts([script], client_root=client_root)

    destination = client_root / script.client_relative_path
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(self: Path) -> bytes:  # pragma: no cover - helper for test only
        if self == destination:
            raise OSError("cannot read")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    script_path.write_text("console.log('updated');", encoding="utf-8")
    updated = sync_global_scripts([script], client_root=client_root)

    assert updated == ["scripts/track.js"]
