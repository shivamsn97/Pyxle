"""Data models for the Pyxle compiler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class PageMetadata:
    """Metadata emitted for each compiled page."""

    route_path: str
    alternate_route_paths: tuple[str, ...]
    client_path: str
    server_path: str
    loader_name: str | None
    loader_line: int | None
    head_elements: tuple[str, ...]
    head_is_dynamic: bool

    def to_json(self) -> Dict[str, Any]:
        return {
            "route_path": self.route_path,
            "alternate_route_paths": list(self.alternate_route_paths),
            "client_path": self.client_path,
            "server_path": self.server_path,
            "loader_name": self.loader_name,
            "loader_line": self.loader_line,
            "head": list(self.head_elements),
            "head_dynamic": self.head_is_dynamic,
        }

    @property
    def has_loader(self) -> bool:
        return self.loader_name is not None


@dataclass(frozen=True)
class CompilationResult:
    """Represents the outcome of compiling a `.pyx` file."""

    source_path: Path
    python_code: str
    jsx_code: str
    server_output: Path
    client_output: Path
    metadata_output: Path
    metadata: PageMetadata

    def __post_init__(self) -> None:
        if self.server_output.is_dir() or self.client_output.is_dir():
            raise ValueError("Output paths must point to files, not directories.")

    def summary(self) -> str:
        loader = self.metadata.loader_name or "<none>"
        return (
            f"Compiled {self.source_path.name} ({self.metadata.route_path}): "
            f"loader={loader} -> server={self.server_output} client={self.client_output}"
        )
