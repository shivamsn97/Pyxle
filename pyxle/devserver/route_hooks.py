"""Route-level middleware hooks and default policies for Pyxle."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable, List, Literal, Sequence

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

RouteHook = Callable[
    ["RouteContext", Request, Callable[[Request], Awaitable[Response]]],
    Awaitable[Response],
]


class RouteHookError(RuntimeError):
    """Raised when a route middleware specification cannot be resolved."""


@dataclass(frozen=True, slots=True)
class RouteContext:
    """Metadata describing the current route for policy enforcement."""

    target: Literal["page", "api"]
    path: str
    source_relative_path: Path
    source_absolute_path: Path
    module_key: str
    content_hash: str
    has_loader: bool = False
    head_elements: tuple[str, ...] = ()
    allowed_methods: tuple[str, ...] = ("GET",)

    def as_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "path": self.path,
            "source": self.source_relative_path.as_posix(),
            "module": self.module_key,
            "contentHash": self.content_hash,
            "hasLoader": self.has_loader,
            "head": list(self.head_elements),
            "allowedMethods": list(self.allowed_methods),
        }


def load_route_hooks(specs: Iterable[str]) -> List[RouteHook]:
    """Resolve module specifications into async route hook callables."""

    loaded: List[RouteHook] = []
    for spec in specs:
        loaded.append(_load_single_hook(spec))
    return loaded


def _load_single_hook(spec: str) -> RouteHook:
    module_name, separator, attribute = spec.partition(":")
    if not module_name or separator == "" or not attribute:
        raise RouteHookError(
            "Route middleware specifications must be of the form 'module:attribute'."
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:  # pragma: no cover - surfaced via unit tests
        raise RouteHookError(f"Unable to import route middleware module '{module_name}'.") from exc

    if not hasattr(module, attribute):
        raise RouteHookError(
            f"Module '{module_name}' does not define attribute '{attribute}' for route middleware."
        )

    candidate = getattr(module, attribute)
    if inspect.iscoroutinefunction(candidate):
        return candidate  # type: ignore[return-value]

    if callable(candidate):
        produced = candidate()
        if inspect.iscoroutinefunction(produced):  # pragma: no branch - simple guard
            return produced  # type: ignore[return-value]

    raise RouteHookError(
        f"Route middleware spec '{spec}' did not resolve to an async callable accepting (context, request, call_next)."
    )


async def attach_route_metadata(context: RouteContext, request: Request, call_next):
    """Default policy wiring route metadata into the ASGI scope for introspection."""

    state = request.scope.setdefault("pyxle", {})  # type: ignore[assignment]
    state["route"] = context.as_dict()
    return await call_next(request)


async def enforce_allowed_methods(context: RouteContext, request: Request, call_next):
    """Default API policy returning 405 for disallowed HTTP verbs."""

    method = request.method.upper()
    allowed = context.allowed_methods or ("GET",)
    if context.target == "api" and method not in allowed:
        detail = {
            "error": "method_not_allowed",
            "allowed": list(allowed),
            "path": context.path,
        }
        return JSONResponse(detail, status_code=405)
    return await call_next(request)


DEFAULT_PAGE_POLICIES: Sequence[RouteHook] = (attach_route_metadata,)
DEFAULT_API_POLICIES: Sequence[RouteHook] = (attach_route_metadata, enforce_allowed_methods)


def wrap_with_route_hooks(
    handler,
    *,
    hooks: Sequence[RouteHook],
    context: RouteContext,
):
    """Wrap a Starlette handler with the provided route hook chain."""

    if not hooks:
        return handler

    async def run_chain(request: Request):
        async def call_next(index: int, current_request: Request):
            if index >= len(hooks):
                return await handler(current_request)
            hook = hooks[index]
            return await hook(context, current_request, lambda req: call_next(index + 1, req))

        return await call_next(0, request)

    run_chain.__name__ = handler.__name__
    return run_chain


__all__ = [
    "DEFAULT_API_POLICIES",
    "DEFAULT_PAGE_POLICIES",
    "RouteContext",
    "RouteHook",
    "RouteHookError",
    "load_route_hooks",
    "wrap_with_route_hooks",
]
