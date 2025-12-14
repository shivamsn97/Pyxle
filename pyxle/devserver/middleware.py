"""Utilities for loading user-provided middleware hooks."""

from __future__ import annotations

import importlib
import inspect
from typing import Iterable, List, Mapping

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware


class MiddlewareHookError(RuntimeError):
    """Raised when a middleware specification cannot be resolved."""


def load_custom_middlewares(specs: Iterable[str]) -> List[Middleware]:
    """Resolve middleware specifications into Starlette ``Middleware`` objects."""

    loaded: List[Middleware] = []
    for spec in specs:
        loaded.append(_load_single_middleware(spec))
    return loaded


def _load_single_middleware(spec: str) -> Middleware:
    module_name, separator, attribute = spec.partition(":")
    if not module_name or separator == "" or not attribute:
        raise MiddlewareHookError(
            "Middleware specifications must be of the form 'module:attribute'."
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:  # pragma: no cover - surfaced via tests
        raise MiddlewareHookError(f"Unable to import middleware module '{module_name}'.") from exc

    if not hasattr(module, attribute):
        raise MiddlewareHookError(
            f"Module '{module_name}' does not define attribute '{attribute}' for middleware."
        )

    value = getattr(module, attribute)
    middleware = _coerce_to_middleware(value, spec)
    if middleware is None:
        raise MiddlewareHookError(
            f"Middleware spec '{spec}' did not resolve to a valid Middleware or BaseHTTPMiddleware."
        )
    return middleware


def _coerce_to_middleware(value: object, spec: str) -> Middleware | None:
    if isinstance(value, Middleware):
        return value

    if inspect.isclass(value) and issubclass(value, BaseHTTPMiddleware):
        return Middleware(value)

    if callable(value):  # factory returning middleware or tuple
        produced = value()
        return _coerce_to_middleware(produced, spec)

    if isinstance(value, tuple) and len(value) == 2:
        candidate, options = value
        if (
            inspect.isclass(candidate)
            and issubclass(candidate, BaseHTTPMiddleware)
            and isinstance(options, Mapping)
        ):
            return Middleware(candidate, **options)

    return None


__all__ = ["MiddlewareHookError", "load_custom_middlewares"]
