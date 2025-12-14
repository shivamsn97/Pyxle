from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from pyxle.devserver.route_hooks import (
    RouteContext,
    RouteHookError,
    load_route_hooks,
    wrap_with_route_hooks,
)


def _make_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
    }

    async def _receive():  # pragma: no cover - helper used in async tests
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive=_receive)


def test_load_route_hooks_accepts_async_callable():
    hooks = load_route_hooks(["tests.devserver.sample_middlewares:record_route_hook"])
    assert len(hooks) == 1


def test_load_route_hooks_supports_factory():
    hooks = load_route_hooks(["tests.devserver.sample_middlewares:build_target_hook"])
    assert len(hooks) == 1


def test_load_route_hooks_rejects_bad_spec():
    with pytest.raises(RouteHookError):
        load_route_hooks(["invalid-spec"])


def test_load_route_hooks_require_async_callables():
    with pytest.raises(RouteHookError):
        load_route_hooks(["tests.devserver.sample_middlewares:invalid_route_hook_factory"])


def test_wrap_with_route_hooks_runs_chain_in_order():
    order: list[str] = []

    async def first(context, request, call_next):
        order.append(f"first:{context.path}")
        response = await call_next(request)
        response.headers["x-first"] = "1"
        return response

    async def second(context, request, call_next):
        order.append(f"second:{context.target}")
        return await call_next(request)

    async def handler(request):
        return PlainTextResponse("ok")

    context = RouteContext(
        target="page",
        path="/",
        source_relative_path=Path("index.pyx"),
        source_absolute_path=Path("/tmp/index.pyx"),
        module_key="pyxle.server.pages.index",
        content_hash="abc",
    )

    async def _run():
        wrapped = wrap_with_route_hooks(handler, hooks=[first, second], context=context)
        response = await wrapped(_make_request())
        assert response.headers["x-first"] == "1"

    asyncio.run(_run())
    assert order == ["first:/", "second:page"]
