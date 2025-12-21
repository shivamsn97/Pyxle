from __future__ import annotations

from pathlib import Path

import pytest

from pyxle.devserver.styles import (
    GlobalStyleConfigError,
    GlobalStylesheet,
    _make_identifier,
    _normalize_relative_path,
    load_inline_stylesheets,
    resolve_global_stylesheets,
    sync_global_stylesheets,
)


def test_global_stylesheet_properties(tmp_path: Path) -> None:
    source = tmp_path / "assets" / "theme.css"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("body {}", encoding="utf-8")

    sheet = GlobalStylesheet(
        source_path=source,
        relative_path=Path("assets/theme.css"),
        identifier="shared-theme",
    )

    assert sheet.client_relative_path == Path("styles/shared-theme.css")
    assert sheet.import_specifier == "./styles/shared-theme.css"
    assert sheet.vite_url == "/styles/shared-theme.css"
    assert sheet.as_dict()["client_relative_path"] == "styles/shared-theme.css"


def test_resolve_global_stylesheets_filters_duplicates(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    base = assets / "base.css"
    base.write_text("body {}", encoding="utf-8")
    theme = assets / "theme.css"
    theme.write_text("h1 {}", encoding="utf-8")

    result = resolve_global_stylesheets(
        tmp_path,
        [" assets/base.css ", "", None, "assets/base.css", "assets/theme.css"],
    )

    assert {sheet.relative_path.as_posix() for sheet in result} == {
        "assets/base.css",
        "assets/theme.css",
    }
    identifiers = {sheet.identifier for sheet in result}
    assert all(identifier.startswith("pyxle-style-") for identifier in identifiers)


def test_resolve_global_stylesheets_validates_entries(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    assert resolve_global_stylesheets(tmp_path, None) == ()
    with pytest.raises(GlobalStyleConfigError):
        resolve_global_stylesheets(tmp_path, [object()])
    with pytest.raises(GlobalStyleConfigError):
        resolve_global_stylesheets(tmp_path, ["missing.css"])
    with pytest.raises(GlobalStyleConfigError):
        resolve_global_stylesheets(tmp_path, ["folder"])


def test_normalize_relative_path_rejects_out_of_tree(tmp_path: Path) -> None:
    with pytest.raises(GlobalStyleConfigError):
        _normalize_relative_path(str(tmp_path / "absolute.css"))
    with pytest.raises(GlobalStyleConfigError):
        _normalize_relative_path("../outside.css")
    with pytest.raises(GlobalStyleConfigError):
        _normalize_relative_path("//")
    with pytest.raises(GlobalStyleConfigError):
        _normalize_relative_path("./")

    assert _normalize_relative_path("styles/./main.css") == Path("styles/main.css")
    assert _normalize_relative_path("./styles.css") == Path("styles.css")


def test_make_identifier_is_deterministic() -> None:
    first = _make_identifier("styles/main.css")
    second = _make_identifier("styles/main.css")
    other = _make_identifier("styles/other.css")

    assert first == second
    assert first != other


def test_sync_global_stylesheets_writes_only_changed_files(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    sheet_path = assets / "base.css"
    sheet_path.write_text("body {}", encoding="utf-8")
    [sheet] = resolve_global_stylesheets(tmp_path, ["assets/base.css"])

    client_root = tmp_path / "client"
    first = sync_global_stylesheets([sheet], client_root=client_root)
    assert first == ["assets/base.css"]

    # Second sync with identical contents should no-op
    second = sync_global_stylesheets([sheet], client_root=client_root)
    assert second == []

    sheet_path.write_text("body { color: red; }", encoding="utf-8")
    third = sync_global_stylesheets([sheet], client_root=client_root)
    assert third == ["assets/base.css"]


def test_sync_global_stylesheets_handles_unreadable_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    sheet_path = assets / "base.css"
    sheet_path.write_text("body {}", encoding="utf-8")
    [sheet] = resolve_global_stylesheets(tmp_path, ["assets/base.css"])
    client_root = tmp_path / "client"
    sync_global_stylesheets([sheet], client_root=client_root)

    destination = client_root / sheet.client_relative_path
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(self: Path) -> bytes:  # pragma: no cover - helper for test only
        if self == destination:
            raise OSError("cannot read")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    sheet_path.write_text("body { color: blue; }", encoding="utf-8")
    updated = sync_global_stylesheets([sheet], client_root=client_root)

    assert updated == ["assets/base.css"]


def test_load_inline_stylesheets_skips_missing_files(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    existing_path = assets / "inline.css"
    existing_path.write_text("body {}", encoding="utf-8")
    [existing] = resolve_global_stylesheets(tmp_path, ["assets/inline.css"])
    missing = GlobalStylesheet(
        source_path=tmp_path / "missing.css",
        relative_path=Path("missing.css"),
        identifier="missing",
    )

    payloads = load_inline_stylesheets([existing, missing])

    assert payloads == [(existing, "body {}")]