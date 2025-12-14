"""Utilities supporting the ``pyxle init`` scaffolding command."""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "InvalidProjectName",
    "slugify_project_name",
    "validate_project_name",
    "FilesystemWriter",
]


class InvalidProjectName(ValueError):
    """Raised when the provided project name is not filesystem safe."""


_SLUG_PATTERN = re.compile(r"[^a-z0-9-]+")
_MULTIPLE_HYPHENS = re.compile(r"-{2,}")


def slugify_project_name(value: str) -> str:
    """Convert arbitrary input into a filesystem-safe slug.

    The slug contains lowercase ASCII letters, digits, and ``-``. Leading and
    trailing hyphens are stripped. An empty slug raises :class:`InvalidProjectName`.
    """

    if not value or not value.strip():
        raise InvalidProjectName("Project name cannot be blank.")

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = ascii_only.lower().replace("_", "-").replace(" ", "-")
    cleaned = _SLUG_PATTERN.sub("-", cleaned)
    cleaned = _MULTIPLE_HYPHENS.sub("-", cleaned).strip("-")

    if not cleaned:
        raise InvalidProjectName("Project name must contain alphanumeric characters.")

    return cleaned


def validate_project_name(value: str) -> str:
    """Validate the project name and return the filesystem-safe slug."""

    stripped = value.strip()
    if stripped.startswith(".") or stripped.startswith("-"):
        raise InvalidProjectName("Project name cannot start with '.' or '-'.")

    slug = slugify_project_name(value)
    if slug in {"con", "prn", "aux", "nul"}:
        raise InvalidProjectName("Project name conflicts with reserved system names.")
    return slug


@dataclass
class FilesystemWriter:
    """Helper encapsulating safe file and directory writes."""

    root: Path

    def ensure_root(self, force: bool = False) -> None:
        if self.root.exists() and not force:
            raise FileExistsError(f"Target directory '{self.root}' already exists.")
        if force and self.root.exists():
            if self.root.is_dir():
                shutil.rmtree(self.root)
            else:
                self.root.unlink()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        relative_path: str | Path,
        content: bytes | str,
        *,
        binary: bool = False,
        overwrite: bool = False,
    ) -> None:
        path = self.root / Path(relative_path)
        if path.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            data = content if isinstance(content, bytes) else str(content).encode("utf-8")
            path.write_bytes(data)
        else:
            text = content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else str(content)
            path.write_text(text, encoding="utf-8")

    def touch_directory(self, relative_path: str | Path) -> Path:
        path = self.root / Path(relative_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
