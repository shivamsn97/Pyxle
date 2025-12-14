"""Server-side rendering utilities for Pyxle."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time helpers
    from .renderer import ComponentRenderer, ComponentRenderError
    from .template import render_document, render_error_document
    from .view import build_page_response

__all__ = [
    "ComponentRenderError",
    "ComponentRenderer",
    "render_document",
    "render_error_document",
    "build_page_response",
    "build_page_navigation_response",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - module-level indirection
    if name in {"ComponentRenderer", "ComponentRenderError"}:
        module = import_module(".renderer", __name__)
        return getattr(module, name)
    if name in {"render_document", "render_error_document"}:
        module = import_module(".template", __name__)
        return getattr(module, name)
    if name in {"build_page_response", "build_page_navigation_response"}:
        module = import_module(".view", __name__)
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
