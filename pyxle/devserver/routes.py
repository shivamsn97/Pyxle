"""Route manifest builders for Starlette integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .path_utils import route_path_from_relative
from .registry import ApiRegistryEntry, MetadataRegistry, PageRegistryEntry


@dataclass(frozen=True, slots=True)
class PageRoute:
    """Descriptor for a Starlette page route."""

    path: str
    source_relative_path: Path
    source_absolute_path: Path
    server_module_path: Path
    client_module_path: Path
    metadata_path: Path
    module_key: str
    client_asset_path: str
    server_asset_path: str
    content_hash: str
    loader_name: Optional[str]
    loader_line: Optional[int]
    head_elements: tuple[str, ...]
    head_is_dynamic: bool

    @property
    def has_loader(self) -> bool:
        return self.loader_name is not None


@dataclass(frozen=True, slots=True)
class ApiRoute:
    """Descriptor for a Starlette API route."""

    path: str
    source_relative_path: Path
    source_absolute_path: Path
    server_module_path: Path
    module_key: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class RouteTable:
    """Aggregated routing descriptors for Starlette registration."""

    pages: List[PageRoute]
    apis: List[ApiRoute]

    def find_page(self, path: str) -> Optional[PageRoute]:
        for entry in self.pages:
            if entry.path == path:
                return entry
        return None

    def find_api(self, path: str) -> Optional[ApiRoute]:
        for entry in self.apis:
            if entry.path == path:
                return entry
        return None


def build_route_table(registry: MetadataRegistry) -> RouteTable:
    """Construct Starlette-friendly route descriptors from registry metadata."""

    page_routes: List[PageRoute] = []
    for entry in registry.pages:
        page_routes.extend(_page_routes(entry))

    api_routes: List[ApiRoute] = []
    for entry in registry.apis:
        api_routes.extend(_api_routes(entry))

    page_routes.sort(key=lambda route: route.path)
    api_routes.sort(key=lambda route: route.path)

    return RouteTable(pages=page_routes, apis=api_routes)


def _page_routes(entry: PageRegistryEntry) -> List[PageRoute]:
    candidates = [entry.route_path, *entry.alternate_route_paths]
    routes: List[PageRoute] = []
    for index, candidate in enumerate(candidates):
        routes.append(_page_route(entry, candidate, allow_inferred_fallback=index == 0))
    return routes


def _page_route(
    entry: PageRegistryEntry,
    candidate_path: str,
    *,
    allow_inferred_fallback: bool,
) -> PageRoute:
    normalized_path = candidate_path
    if allow_inferred_fallback:
        inferred = route_path_from_relative(entry.source_relative_path)
        if entry.route_path != inferred:
            normalized_path = inferred

    return PageRoute(
        path=normalized_path,
        source_relative_path=entry.source_relative_path,
        source_absolute_path=entry.source_absolute_path,
        server_module_path=entry.server_module_path,
        client_module_path=entry.client_module_path,
        metadata_path=entry.metadata_path,
        module_key=entry.module_key,
        client_asset_path=entry.client_asset_path,
        server_asset_path=entry.server_asset_path,
        content_hash=entry.content_hash,
        loader_name=entry.loader_name,
        loader_line=entry.loader_line,
        head_elements=entry.head_elements,
        head_is_dynamic=entry.head_is_dynamic,
    )


def _api_routes(entry: ApiRegistryEntry) -> List[ApiRoute]:
    candidates = [entry.route_path, *entry.alternate_route_paths]
    routes: List[ApiRoute] = []
    for index, candidate in enumerate(candidates):
        routes.append(_api_route(entry, candidate, allow_inferred_fallback=index == 0))
    return routes


def _api_route(
    entry: ApiRegistryEntry,
    candidate_path: str,
    *,
    allow_inferred_fallback: bool,
) -> ApiRoute:
    normalized_path = candidate_path
    if allow_inferred_fallback:
        inferred = route_path_from_relative(entry.source_relative_path)
        if entry.route_path != inferred:
            normalized_path = inferred

    return ApiRoute(
        path=normalized_path,
        source_relative_path=entry.source_relative_path,
        source_absolute_path=entry.source_absolute_path,
        server_module_path=entry.server_module_path,
        module_key=entry.module_key,
        content_hash=entry.content_hash,
    )


__all__ = [
    "ApiRoute",
    "PageRoute",
    "RouteTable",
    "build_route_table",
]
