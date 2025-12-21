"""Global script helpers for the Pyxle dev server."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class GlobalScriptConfigError(ValueError):
    """Raised when global script configuration is invalid."""


@dataclass(frozen=True, slots=True)
class GlobalScript:
    """Descriptor for a configured global script file."""

    source_path: Path
    relative_path: Path
    identifier: str

    @property
    def client_relative_path(self) -> Path:
        suffix = self.relative_path.suffix or ".js"
        return Path("scripts") / f"{self.identifier}{suffix}"

    @property
    def import_specifier(self) -> str:
        return f"./{self.client_relative_path.as_posix()}"

    def as_dict(self) -> dict[str, str]:
        return {
            "source_path": str(self.source_path),
            "relative_path": self.relative_path.as_posix(),
            "identifier": self.identifier,
            "client_relative_path": self.client_relative_path.as_posix(),
        }


def resolve_global_scripts(
    project_root: Path,
    entries: Sequence[str] | Iterable[str] | None,
) -> tuple[GlobalScript, ...]:
    """Validate and resolve configured global script paths."""

    if not entries:
        return ()

    root = project_root.expanduser().resolve()
    resolved: list[GlobalScript] = []
    seen: set[str] = set()

    for raw_entry in entries:
        if raw_entry is None:
            continue
        if not isinstance(raw_entry, str):
            raise GlobalScriptConfigError(
                f"Global script entries must be strings; got {type(raw_entry).__name__}."
            )
        entry = raw_entry.strip()
        if not entry:
            continue
        relative = _normalize_relative_path(entry)
        key = relative.as_posix()
        if key in seen:
            continue
        seen.add(key)
        source_path = (root / relative).resolve()
        if not source_path.exists():
            raise GlobalScriptConfigError(
                f"Global script '{entry}' was not found under project root '{root}'."
            )
        if not source_path.is_file():
            raise GlobalScriptConfigError(
                f"Global script '{entry}' must be a file, not a directory."
            )
        identifier = _make_identifier(key)
        resolved.append(
            GlobalScript(
                source_path=source_path,
                relative_path=relative,
                identifier=identifier,
            )
        )

    return tuple(resolved)


def sync_global_scripts(
    scripts: Sequence[GlobalScript],
    *,
    client_root: Path,
) -> list[str]:
    """Copy configured scripts into the client build directory."""

    updated: list[str] = []
    for script in scripts:
        destination = client_root / script.client_relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = script.source_path.read_bytes()
        except OSError as exc:  # pragma: no cover - surface helpful context
            raise GlobalScriptConfigError(
                f"Unable to read global script '{script.source_path}': {exc}"
            ) from exc

        if destination.exists():
            try:
                existing = destination.read_bytes()
            except OSError:
                existing = b""
            if existing == payload:
                continue

        destination.write_bytes(payload)
        updated.append(script.relative_path.as_posix())

    return updated


def _normalize_relative_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise GlobalScriptConfigError(
            f"Global script '{value}' must be a relative path inside the project root."
        )

    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise GlobalScriptConfigError(
                f"Global script '{value}' cannot navigate outside the project root."
            )
        parts.append(part)

    if not parts:
        raise GlobalScriptConfigError(
            "Global script paths must reference a file (received only separators)."
        )

    return Path(*parts)


def _make_identifier(value: str) -> str:
    digest = hashlib.blake2s(value.encode("utf-8"), digest_size=12).hexdigest()
    safe = value.replace("/", "-").replace(".", "-")
    safe = "-".join(filter(None, safe.split("-")))
    return f"pyxle-script-{safe}-{digest}"


__all__ = [
    "GlobalScriptConfigError",
    "GlobalScript",
    "resolve_global_scripts",
    "sync_global_scripts",
]
