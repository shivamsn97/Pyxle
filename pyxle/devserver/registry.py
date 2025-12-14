"""Metadata registry assembly for the Pyxle development server."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from pyxle.compiler.model import PageMetadata

from .build import BuildMetadata, load_build_metadata
from .path_utils import route_path_variants_from_relative
from .scanner import SourceKind
from .settings import DevServerSettings


@dataclass(frozen=True, slots=True)
class PageRegistryEntry:
    """Description of a compiled page available to the dev server."""

    route_path: str
    alternate_route_paths: tuple[str, ...]
    source_relative_path: Path
    source_absolute_path: Path
    server_module_path: Path
    client_module_path: Path
    metadata_path: Path
    client_asset_path: str
    server_asset_path: str
    module_key: str
    content_hash: str
    loader_name: Optional[str]
    loader_line: Optional[int]
    head_elements: tuple[str, ...]
    head_is_dynamic: bool

    @property
    def has_loader(self) -> bool:
        return self.loader_name is not None


@dataclass(frozen=True, slots=True)
class ApiRegistryEntry:
    """Description of a compiled API endpoint."""

    route_path: str
    alternate_route_paths: tuple[str, ...]
    source_relative_path: Path
    source_absolute_path: Path
    server_module_path: Path
    module_key: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class MetadataRegistry:
    """Aggregated view of pages and APIs for routing purposes."""

    pages: List[PageRegistryEntry]
    apis: List[ApiRegistryEntry]

    def find_page(self, route_path: str) -> Optional[PageRegistryEntry]:
        for entry in self.pages:
            if entry.route_path == route_path or route_path in entry.alternate_route_paths:
                return entry
        return None

    def find_api(self, route_path: str) -> Optional[ApiRegistryEntry]:
        for entry in self.apis:
            if entry.route_path == route_path or route_path in entry.alternate_route_paths:
                return entry
        return None

    def to_dict(self) -> Dict[str, object]:
        return {
            "pages": [
                {
                    "route_path": entry.route_path,
                    "alternate_route_paths": list(entry.alternate_route_paths),
                    "source": entry.source_relative_path.as_posix(),
                    "client_asset_path": entry.client_asset_path,
                    "server_asset_path": entry.server_asset_path,
                    "module_key": entry.module_key,
                    "content_hash": entry.content_hash,
                    "loader_name": entry.loader_name,
                    "loader_line": entry.loader_line,
                    "head": list(entry.head_elements),
                    "head_dynamic": entry.head_is_dynamic,
                }
                for entry in self.pages
            ],
            "apis": [
                {
                    "route_path": entry.route_path,
                    "alternate_route_paths": list(entry.alternate_route_paths),
                    "source": entry.source_relative_path.as_posix(),
                    "module_key": entry.module_key,
                    "content_hash": entry.content_hash,
                }
                for entry in self.apis
            ],
        }


def build_metadata_registry(
    settings: DevServerSettings,
    metadata: BuildMetadata | None = None,
) -> MetadataRegistry:
    """Derive routing metadata for pages and APIs."""

    metadata = metadata or load_build_metadata(settings.build_root)

    pages: List[PageRegistryEntry] = []
    apis: List[ApiRegistryEntry] = []

    for relative_key, record in sorted(metadata.sources.items()):
        relative_path = Path(relative_key)
        if record.kind == SourceKind.PAGE.value:
            page_entry = _build_page_entry(settings, relative_path, record.content_hash)
            if page_entry:
                pages.append(page_entry)
        elif record.kind == SourceKind.API.value:
            api_entry = _build_api_entry(settings, relative_path, record.content_hash)
            if api_entry:
                apis.append(api_entry)

    pages.sort(key=lambda entry: entry.route_path)
    apis.sort(key=lambda entry: entry.route_path)

    return MetadataRegistry(pages=pages, apis=apis)


def load_metadata_registry(settings: DevServerSettings) -> MetadataRegistry:
    """Convenience wrapper that loads metadata from disk and assembles the registry."""

    return build_metadata_registry(settings, load_build_metadata(settings.build_root))


def _build_page_entry(
    settings: DevServerSettings,
    relative_path: Path,
    content_hash: str,
) -> Optional[PageRegistryEntry]:
    filename = relative_path.name.lower()
    if filename in {"layout.pyx", "template.pyx"}:
        return None

    metadata_path = settings.metadata_build_dir / "pages" / relative_path.with_suffix(".json")
    metadata = _load_page_metadata(metadata_path)
    if metadata is None:
        return None

    source_absolute = settings.pages_dir / relative_path
    server_module = settings.server_build_dir / "pages" / relative_path.with_suffix(".py")
    client_module = _resolve_client_module_path(settings.client_build_dir, metadata.client_path)

    if not server_module.exists() or not client_module.exists():
        return None

    return PageRegistryEntry(
        route_path=metadata.route_path,
        alternate_route_paths=metadata.alternate_route_paths,
        source_relative_path=relative_path,
        source_absolute_path=source_absolute,
        server_module_path=server_module,
        client_module_path=client_module,
        metadata_path=metadata_path,
        client_asset_path=metadata.client_path,
        server_asset_path=metadata.server_path,
        module_key=_module_key(relative_path, prefix="pyxle.server.pages"),
        content_hash=content_hash,
        loader_name=metadata.loader_name,
        loader_line=metadata.loader_line,
        head_elements=metadata.head_elements,
        head_is_dynamic=metadata.head_is_dynamic,
    )


def _build_api_entry(
    settings: DevServerSettings,
    relative_path: Path,
    content_hash: str,
) -> Optional[ApiRegistryEntry]:
    server_module = settings.server_build_dir / relative_path
    if not server_module.exists():
        return None

    source_absolute = settings.pages_dir / relative_path

    route_spec = route_path_variants_from_relative(relative_path)

    return ApiRegistryEntry(
        route_path=route_spec.primary,
        alternate_route_paths=route_spec.aliases,
        source_relative_path=relative_path,
        source_absolute_path=source_absolute,
        server_module_path=server_module,
        module_key=_module_key(
            relative_path,
            prefix="pyxle.server.api",
            drop_leading="api",
        ),
        content_hash=content_hash,
    )


def _load_page_metadata(path: Path) -> Optional[PageMetadata]:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    route_path = payload.get("route_path")
    client_path = payload.get("client_path")
    server_path = payload.get("server_path")

    if not all(isinstance(value, str) for value in (route_path, client_path, server_path)):
        return None

    loader_name = payload.get("loader_name")
    if loader_name is not None and not isinstance(loader_name, str):
        loader_name = None

    loader_line = payload.get("loader_line")
    if not isinstance(loader_line, int):
        loader_line = None

    alternate_paths_payload = payload.get("alternate_route_paths", [])
    alternate_route_paths: tuple[str, ...]
    if isinstance(alternate_paths_payload, list) and all(isinstance(item, str) for item in alternate_paths_payload):
        alternate_route_paths = tuple(alternate_paths_payload)
    else:
        alternate_route_paths = tuple()

    head_payload = payload.get("head")
    head_elements: tuple[str, ...]
    if head_payload is None:
        head_elements = tuple()
    elif isinstance(head_payload, list) and all(isinstance(item, str) for item in head_payload):
        head_elements = tuple(head_payload)
    else:
        return None

    head_dynamic_payload = payload.get("head_dynamic", False)
    head_is_dynamic = head_dynamic_payload if isinstance(head_dynamic_payload, bool) else False

    return PageMetadata(
        route_path=route_path,
    alternate_route_paths=alternate_route_paths,
        client_path=client_path,
        server_path=server_path,
        loader_name=loader_name,
        loader_line=loader_line,
        head_elements=head_elements,
        head_is_dynamic=head_is_dynamic,
    )


def _resolve_client_module_path(client_root: Path, client_asset_path: str) -> Path:
    relative = client_asset_path.lstrip("/")
    return client_root / relative


def _module_key(relative_path: Path, *, prefix: str, drop_leading: str | None = None) -> str:
    parts = [segment for segment in prefix.split(".") if segment]
    segments = list(relative_path.with_suffix("").parts)
    if drop_leading and segments and segments[0] == drop_leading:
        segments = segments[1:]

    for segment in segments:
        cleaned = segment.replace("[", "").replace("]", "")
        cleaned = cleaned.replace("(", "").replace(")", "")
        cleaned = cleaned.replace("...", "")
        cleaned = cleaned.replace("-", "_").replace(" ", "_")
        cleaned = cleaned.replace(".", "_")
        if not cleaned:
            cleaned = "_"
        if cleaned[0].isdigit():
            cleaned = "_" + cleaned
        parts.append(cleaned)
    return ".".join(parts)
