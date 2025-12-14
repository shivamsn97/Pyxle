"""Runtime helpers exposed to compiled Pyxle artifacts."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def server(function: F) -> F:
    """Mark a function as a Pyxle loader and return it unchanged.

    The decorator intentionally performs no wrapping so the original coroutine
    signature and attributes remain available to the runtime. It simply tags the
    function for future inspection by attaching ``__pyxle_loader__ = True``.
    """

    setattr(function, "__pyxle_loader__", True)
    return function


__all__ = ["server"]
