from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from pages.components import build_head

_GLOBAL_ASSETS = [
    '<link rel="stylesheet" href="/styles/pyxle.css" />',
    '<script type="module" src="/scripts/pyxle-effects.js" defer></script>',
]

_SITE = {
    "name": "Pyxle Starter",
    "tagline": "A calm multi-page demo that mixes Python loaders, React components, and shared middleware.",
    "navigation": [
        {"href": "/", "label": "Overview"},
        {"href": "/projects", "label": "Projects"},
        {"href": "/diagnostics", "label": "Diagnostics"},
    ],
    "resources": [
        {"href": "https://github.com/shivamshekhar/pyxle", "label": "GitHub"},
        {"href": "https://github.com/shivamshekhar/pyxle/tree/main/docs", "label": "Docs"},
        {"href": "https://pypi.org/project/pyxle", "label": "PyPI"},
    ],
}


def site_metadata() -> Dict[str, Any]:
    """Return a copy of the shared site metadata so loaders can customize per page."""

    return deepcopy(_SITE)


def build_page_head(page_title: str, description: str | None = None) -> List[str]:
    """Construct escaped <head> fragments with shared styles and scripts."""

    suffix = f"{page_title} • {_SITE['name']}"
    details = description or _SITE["tagline"]
    return build_head(title=suffix, description=details, extra=list(_GLOBAL_ASSETS))


def base_page_payload(
    request: Any,
    *,
    page_id: str,
    title: str,
    intro: str,
    eyebrow: str | None = None,
) -> Dict[str, Any]:
    """Return consistent metadata for every scaffolded page."""

    payload = {
        "site": site_metadata(),
        "page": {
            "id": page_id,
            "title": title,
            "intro": intro,
            "path": request.url.path,
        },
    }
    if eyebrow:
        payload["page"]["eyebrow"] = eyebrow
    return payload


__all__ = ["base_page_payload", "build_page_head", "site_metadata"]
