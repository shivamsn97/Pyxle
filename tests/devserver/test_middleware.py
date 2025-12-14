from __future__ import annotations

import pytest
from starlette.middleware import Middleware

from pyxle.devserver.middleware import MiddlewareHookError, load_custom_middlewares


def test_load_custom_middlewares_supports_classes_and_factories() -> None:
    middlewares = load_custom_middlewares(
        [
            "tests.devserver.sample_middlewares:HeaderCaptureMiddleware",
            "tests.devserver.sample_middlewares:create_rate_limit_middleware",
            "tests.devserver.sample_middlewares:tuple_middleware_factory",
        ]
    )

    assert len(middlewares) == 3
    assert all(isinstance(item, Middleware) for item in middlewares)
    assert middlewares[-1].cls.__name__ == "ConfigurableSuffixMiddleware"


def test_load_custom_middlewares_raises_for_invalid_spec() -> None:
    with pytest.raises(MiddlewareHookError):
        load_custom_middlewares(["tests.devserver.sample_middlewares:missing"])

    with pytest.raises(MiddlewareHookError):
        load_custom_middlewares(["tests.devserver.sample_middlewares:invalid_factory"])

    with pytest.raises(MiddlewareHookError):
        load_custom_middlewares(["not-a-valid-spec"])
