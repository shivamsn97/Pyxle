"""Source scanning utilities for the Pyxle development server."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from .settings import DevServerSettings


class SourceKind(str, Enum):
    """Types of source files discovered within the project."""

    PAGE = "page"
    API = "api"
    CLIENT_ASSET = "client_asset"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Representation of a discovered source file."""

    kind: SourceKind
    absolute_path: Path
    relative_path: Path
    content_hash: str

    def as_dict(self) -> dict[str, str]:
        """Serialise the source description into primitives."""

        return {
            "kind": self.kind.value,
            "absolute_path": str(self.absolute_path),
            "relative_path": self.relative_path.as_posix(),
            "content_hash": self.content_hash,
        }


_HASH_CHUNK_SIZE = 64 * 1024  # 64KiB
_CLIENT_ASSET_SUFFIXES = {".jsx", ".js", ".tsx", ".ts", ".mjs", ".cjs", ".json", ".css"}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_source_tree(settings: DevServerSettings) -> List[SourceFile]:
    """Walk the project's ``pages/`` directory and record relevant sources."""

    pages_dir = settings.pages_dir
    if not pages_dir.exists():
        return []

    entries: list[SourceFile] = []

    for file_path in pages_dir.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(pages_dir)

        # Ignore build artefacts that may live under the source tree (e.g. legacy
        # `.pyxle-build/` directories from older workflows). These files mirror
        # compiled output and should not be treated as fresh sources.
        if any(part == ".pyxle-build" for part in relative_path.parts):
            continue

        suffix = file_path.suffix.lower()
        if suffix == ".pyx":
            kind = SourceKind.PAGE
        elif suffix == ".py":
            parts = relative_path.parts
            if not parts or parts[0] != "api":
                continue
            kind = SourceKind.API
        elif suffix in _CLIENT_ASSET_SUFFIXES:
            parts = relative_path.parts
            if parts and parts[0] == "api":
                # Client assets under pages/api are not copied to the client build.
                continue
            kind = SourceKind.CLIENT_ASSET
        else:
            continue

        entries.append(
            SourceFile(
                kind=kind,
                absolute_path=file_path,
                relative_path=relative_path,
                content_hash=_hash_file(file_path),
            )
        )

    entries.sort(key=lambda entry: entry.relative_path.as_posix())
    return entries
