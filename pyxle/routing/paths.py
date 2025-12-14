"""Route path derivation helpers shared across compiler and dev server."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RoutePathSpec:
    """Describes the primary and alternate Starlette paths for a route."""

    primary: str
    aliases: tuple[str, ...] = ()


def route_path_from_relative(relative_path: Path) -> str:
    """Return the primary route path for ``relative_path`` within ``pages/``."""

    return route_path_variants_from_relative(relative_path).primary


def route_path_variants_from_relative(relative_path: Path) -> RoutePathSpec:
    """Compute all Starlette route path variants for ``relative_path``.

    The first entry represents the canonical path; any additional entries are
    alias paths that should resolve to the same handler (for example optional
    catch-all routes derived from ``[[...slug]].pyx`` files).
    """

    parts = list(relative_path.parts)
    if not parts:
        return RoutePathSpec(primary="/")

    primary_segments: List[str] = []
    alias_paths: List[str] = []

    for index, raw_segment in enumerate(parts):
        segment = Path(raw_segment).stem if index == len(parts) - 1 else raw_segment
        if not segment:
            continue
        if _is_route_group(segment):
            continue
        if segment == "index":
            # ``index`` collapses to the parent route.
            continue
        optional_param = _parse_optional_catchall(segment)
        if optional_param:
            alias_segments = primary_segments + [optional_param]
            alias_paths.append(_join_segments(alias_segments))
            continue
        catchall_param = _parse_catchall(segment)
        if catchall_param:
            primary_segments.append(catchall_param)
            continue
        dynamic_param = _parse_dynamic(segment)
        if dynamic_param:
            primary_segments.append(dynamic_param)
            continue
        primary_segments.append(segment)

    primary_path = _join_segments(primary_segments)
    aliases = tuple(_dedupe(alias_paths))
    return RoutePathSpec(primary=primary_path, aliases=aliases)


def _join_segments(segments: Sequence[str]) -> str:
    filtered = [segment for segment in segments if segment]
    if not filtered:
        return "/"
    return "/" + "/".join(filtered)


def _is_route_group(segment: str) -> bool:
    return segment.startswith("(") and segment.endswith(")")


def _parse_optional_catchall(segment: str) -> str | None:
    if not (segment.startswith("[[...") and segment.endswith("]]")):
        return None
    name = segment[5:-2].strip()
    return _format_param(name or "slug", converter="path")


def _parse_catchall(segment: str) -> str | None:
    if not (segment.startswith("[...") and segment.endswith("]")):
        return None
    name = segment[4:-1].strip()
    return _format_param(name or "slug", converter="path")


def _parse_dynamic(segment: str) -> str | None:
    if not (segment.startswith("[") and segment.endswith("]")):
        return None
    name = segment[1:-1].strip()
    return _format_param(name or "param")


def _format_param(name: str, *, converter: str | None = None) -> str:
    sanitized = _sanitize_param_name(name)
    if converter:
        return f"{{{sanitized}:{converter}}}"
    return f"{{{sanitized}}}"


def _sanitize_param_name(name: str) -> str:
    cleaned = name.replace("...", "").replace("/", "").replace("\\", "")
    cleaned = cleaned.replace("-", "_").replace(" ", "_")
    cleaned = cleaned.replace("(", "").replace(")", "")
    cleaned = cleaned.replace("[", "").replace("]", "")
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = cleaned.replace(".", "_")
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = "param"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = [
    "RoutePathSpec",
    "route_path_from_relative",
    "route_path_variants_from_relative",
]
