"""Utilities for building SSR responses from compiled page routes."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Tuple

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from pyxle.devserver.overlay import OverlayManager
from pyxle.devserver.routes import PageRoute
from pyxle.devserver.settings import DevServerSettings

from .renderer import ComponentRenderer, ComponentRenderError, InlineStyleFragment
from .template import (
    ManifestLookupError,
    build_document_shell,
    render_document,
    render_error_document,
    render_head_markup,
)


class LoaderExecutionError(RuntimeError):
    """Raised when a page loader returns an unexpected value."""


class HeadEvaluationError(RuntimeError):
    """Raised when HEAD cannot be resolved at runtime."""


@dataclass(slots=True)
class PageArtifacts:
    component_props: dict[str, Any]
    body_html: str
    head_elements: tuple[str, ...]
    head_markup: str
    inline_styles: tuple[InlineStyleFragment, ...]
    status_code: int


async def build_page_response(
    *,
    request: Request,
    settings: DevServerSettings,
    page: PageRoute,
    renderer: ComponentRenderer,
    overlay: OverlayManager | None = None,
) -> Response:
    if settings.debug:
        _purge_page_modules(settings.pages_dir)
    loader_breadcrumb = _initial_loader_breadcrumb(page)

    try:
        artifacts = await _create_page_artifacts(
            request=request,
            page=page,
            renderer=renderer,
            loader_breadcrumb=loader_breadcrumb,
        )
        script_nonce = secrets.token_urlsafe(24)
        try:
            shell = build_document_shell(
                settings=settings,
                page=page,
                props=artifacts.component_props,
                script_nonce=script_nonce,
                head_elements=artifacts.head_elements,
                inline_styles=artifacts.inline_styles,
            )
        except ManifestLookupError:
            document = render_document(
                settings=settings,
                page=page,
                body_html=artifacts.body_html,
                props=artifacts.component_props,
                script_nonce=script_nonce,
                head_elements=artifacts.head_elements,
                inline_styles=artifacts.inline_styles,
            )
            if overlay is not None:
                await overlay.notify_clear(route_path=page.path)
            return HTMLResponse(document, status_code=artifacts.status_code)

        async def _document_stream():
            yield shell.prefix.encode("utf-8")
            yield artifacts.body_html.encode("utf-8")
            yield shell.suffix.encode("utf-8")

        if overlay is not None:
            await overlay.notify_clear(route_path=page.path)
        return StreamingResponse(
            _document_stream(),
            status_code=artifacts.status_code,
            media_type="text/html",
        )
    except LoaderExecutionError as exc:
        loader_breadcrumb = _make_loader_breadcrumb(page, status="failed", detail=str(exc))
        fallback = render_error_document(settings=settings, page=page, error=exc)
        if overlay is not None:
            await overlay.notify_error(
                route_path=page.path,
                error=exc,
                breadcrumbs=_compose_breadcrumbs(loader_breadcrumb, stage="loader", message=str(exc)),
            )
        return HTMLResponse(fallback, status_code=500)
    except HeadEvaluationError as exc:
        fallback = render_error_document(settings=settings, page=page, error=exc)
        if overlay is not None:
            await overlay.notify_error(
                route_path=page.path,
                error=exc,
                breadcrumbs=_compose_breadcrumbs(loader_breadcrumb, stage="server", message=str(exc)),
            )
        return HTMLResponse(fallback, status_code=500)
    except ComponentRenderError as exc:
        fallback = render_error_document(settings=settings, page=page, error=exc)
        if overlay is not None:
            await overlay.notify_error(
                route_path=page.path,
                error=exc,
                breadcrumbs=_compose_breadcrumbs(loader_breadcrumb, stage="renderer", message=str(exc)),
            )
        return HTMLResponse(fallback, status_code=500)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        fallback = render_error_document(settings=settings, page=page, error=exc)
        if overlay is not None:
            await overlay.notify_error(
                route_path=page.path,
                error=exc,
                breadcrumbs=_compose_breadcrumbs(loader_breadcrumb, stage="server", message=str(exc)),
            )
        return HTMLResponse(fallback, status_code=500)


async def build_page_navigation_response(
    *,
    request: Request,
    settings: DevServerSettings,
    page: PageRoute,
    renderer: ComponentRenderer,
    overlay: OverlayManager | None = None,
) -> JSONResponse:
    if settings.debug:
        _purge_page_modules(settings.pages_dir)
    loader_breadcrumb = _initial_loader_breadcrumb(page)

    try:
        artifacts = await _create_page_artifacts(
            request=request,
            page=page,
            renderer=renderer,
            loader_breadcrumb=loader_breadcrumb,
        )
        if overlay is not None:
            await overlay.notify_clear(route_path=page.path)
        payload = {
            "ok": True,
            "routePath": page.path,
            "requestedPath": request.url.path,
            "statusCode": artifacts.status_code,
            "page": {
                "clientAssetPath": page.client_asset_path,
                "moduleKey": page.module_key,
            },
            "props": artifacts.component_props,
            "headMarkup": artifacts.head_markup,
        }
        return JSONResponse(payload, status_code=artifacts.status_code)
    except LoaderExecutionError as exc:
        loader_breadcrumb = _make_loader_breadcrumb(page, status="failed", detail=str(exc))
        return await _navigation_error_response(
            request=request,
            page=page,
            overlay=overlay,
            loader_breadcrumb=loader_breadcrumb,
            stage="loader",
            error=exc,
        )
    except HeadEvaluationError as exc:
        return await _navigation_error_response(
            request=request,
            page=page,
            overlay=overlay,
            loader_breadcrumb=loader_breadcrumb,
            stage="server",
            error=exc,
        )
    except ComponentRenderError as exc:
        return await _navigation_error_response(
            request=request,
            page=page,
            overlay=overlay,
            loader_breadcrumb=loader_breadcrumb,
            stage="renderer",
            error=exc,
        )
    except Exception as exc:  # pragma: no cover - defensive guardrail
        return await _navigation_error_response(
            request=request,
            page=page,
            overlay=overlay,
            loader_breadcrumb=loader_breadcrumb,
            stage="server",
            error=exc,
        )


async def _execute_loader(
    page: PageRoute,
    request: Request,
    *,
    module: Any | None,
) -> Tuple[dict[str, Any], int, Any | None]:
    if not page.has_loader:
        return {}, 200, module

    if module is None:
        module = _import_server_module(page.module_key, page.server_module_path)
    loader = getattr(module, page.loader_name or "", None)
    if loader is None:
        raise LoaderExecutionError(
            f"Loader '{page.loader_name}' not found in module {page.module_key}"
        )

    result = loader(request)
    if hasattr(result, "__await__"):
        result = await result  # type: ignore[assignment]

    payload, status_code = _normalize_loader_result(result, page)
    return payload, status_code, module


def _resolve_head_elements(
    page: PageRoute,
    module,
    loader_payload: Mapping[str, Any],
) -> tuple[str, ...]:
    if not page.head_is_dynamic:
        return page.head_elements

    if module is None:
        module = _import_server_module(page.module_key, page.server_module_path)

    head_value = getattr(module, "HEAD", None)
    if head_value is None:
        return tuple()

    if callable(head_value):
        head_value = _evaluate_head_callable(page, head_value, loader_payload)

    return _normalize_head_entries(page, head_value)


def _normalize_loader_result(result: Any, page: PageRoute) -> Tuple[dict[str, Any], int]:
    status_code = 200
    payload = result

    if isinstance(result, tuple) and result:
        payload = result[0]
        if len(result) > 1:
            status_code = int(result[1])

    if not isinstance(payload, Mapping):
        raise LoaderExecutionError(
            f"Loader for {page.path} must return a mapping or (mapping, status_code) tuple"
        )

    return dict(payload), status_code


def _compose_component_props(loader_payload: dict[str, Any]) -> dict[str, Any]:
    return {"data": loader_payload}


async def _create_page_artifacts(
    *,
    request: Request,
    page: PageRoute,
    renderer: ComponentRenderer,
    loader_breadcrumb: dict[str, str],
) -> PageArtifacts:
    module = None
    if page.head_is_dynamic:
        module = _import_server_module(page.module_key, page.server_module_path)

    loader_props, status_code, module = await _execute_loader(
        page,
        request,
        module=module,
    )

    if page.has_loader:
        loader_breadcrumb["status"] = "passed"
        loader_breadcrumb["detail"] = f"Returned {len(loader_props)} key(s) with status {status_code}"

    head_elements = _resolve_head_elements(page, module, loader_props)
    component_props = _compose_component_props(loader_props)
    render_result = await renderer.render(page.client_module_path, component_props)
    body_html = render_result.html
    inline_styles = render_result.inline_styles
    head_markup = render_head_markup(head_elements)

    return PageArtifacts(
        component_props=component_props,
        body_html=body_html,
        head_elements=head_elements,
        head_markup=head_markup,
        inline_styles=inline_styles,
        status_code=status_code,
    )


def _initial_loader_breadcrumb(page: PageRoute) -> dict[str, str]:
    if page.has_loader:
        return _make_loader_breadcrumb(
            page,
            status="pending",
            detail="Awaiting loader execution",
        )
    return _make_loader_breadcrumb(
        page,
        status="skipped",
        detail="No loader defined",
    )


async def _navigation_error_response(
    *,
    request: Request,
    page: PageRoute,
    overlay: OverlayManager | None,
    loader_breadcrumb: dict[str, str],
    stage: str,
    error: BaseException,
) -> JSONResponse:
    breadcrumbs = _compose_breadcrumbs(loader_breadcrumb, stage=stage, message=str(error))
    if overlay is not None:
        await overlay.notify_error(route_path=page.path, error=error, breadcrumbs=breadcrumbs)

    payload = {
        "ok": False,
        "routePath": page.path,
        "requestedPath": request.url.path,
        "stage": stage,
        "error": str(error),
        "errorType": error.__class__.__name__,
    }
    return JSONResponse(payload, status_code=500)


def _import_server_module(module_key: str, module_path: Path):
    if module_key in sys.modules:
        del sys.modules[module_key]

    spec = importlib.util.spec_from_file_location(module_key, module_path)
    if spec is None or spec.loader is None:
        raise LoaderExecutionError(f"Unable to load page module at {module_path!s}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    spec.loader.exec_module(module)
    return module


def _purge_page_modules(pages_dir: Path) -> None:
    try:
        root = pages_dir.resolve()
    except FileNotFoundError:
        return
    removed: list[str] = []
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            module_path = Path(module_file).resolve()
        except (OSError, ValueError):
            continue
        try:
            module_path.relative_to(root)
        except ValueError:
            continue
        removed.append(name)
    if not removed:
        return
    importlib.invalidate_caches()
    for name in removed:
        sys.modules.pop(name, None)


def _evaluate_head_callable(
    page: PageRoute,
    head_callable: Callable[[Mapping[str, Any]], object],
    loader_payload: Mapping[str, Any],
) -> Any:
    try:
        value = head_callable(loader_payload)
    except TypeError as exc:
        raise HeadEvaluationError(
            f"Callable HEAD for {page.path} must accept exactly one argument (loader data)",
        ) from exc

    if inspect.isawaitable(value):
        raise HeadEvaluationError(
            f"Callable HEAD for {page.path} must return synchronously",
        )

    return value


def _normalize_head_entries(page: PageRoute, value: Any) -> tuple[str, ...]:
    if value is None:
        return tuple()

    if isinstance(value, str):
        return (value,)

    if isinstance(value, (list, tuple)):
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise HeadEvaluationError(
                    f"HEAD entries for {page.path} must be strings; got {type(item).__name__}",
                )
            normalized.append(item)
        return tuple(normalized)

    raise HeadEvaluationError(
        f"HEAD for {page.path} must be a string, list of strings, or callable; got {type(value).__name__}",
    )


__all__ = [
    "LoaderExecutionError",
    "build_page_response",
    "build_page_navigation_response",
]


def _make_loader_breadcrumb(page: PageRoute, *, status: str, detail: str) -> dict[str, str]:
    label = "Loader" if not page.loader_name else f"Loader ({page.loader_name})"
    return {"label": label, "status": status, "detail": detail}


def _compose_breadcrumbs(
    loader_breadcrumb: dict[str, str],
    *,
    stage: str,
    message: str,
) -> List[dict[str, str]]:
    if stage == "loader":
        renderer_status = "blocked"
        renderer_detail = "Renderer skipped because the loader failed."
    elif stage == "renderer":
        renderer_status = "failed"
        renderer_detail = message
    else:
        renderer_status = "unknown"
        renderer_detail = "Renderer outcome unknown due to server error."

    hydration_detail = (
        "Hydration never executed because SSR failed."
        if stage in {"loader", "renderer"}
        else "Hydration blocked by unexpected server error."
    )

    return [
        loader_breadcrumb,
        {"label": "Renderer", "status": renderer_status, "detail": renderer_detail},
        {"label": "Hydration", "status": "blocked", "detail": hydration_detail},
    ]
