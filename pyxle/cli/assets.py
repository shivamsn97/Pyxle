"""Binary assets bundled with the CLI."""

from __future__ import annotations

import base64
from functools import lru_cache

_DEFAULT_FAVICON_BASE64 = (
    "AAABAAEAAQEAAAEAIABDAAAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAABAAAAAQgGAAAAHxXEiQAAAA1JREFUeAFjAAEAAAUAAQ0KLbQAAAAASUVORK5CYII="
)


@lru_cache(maxsize=1)
def default_favicon_bytes() -> bytes:
    """Return the default favicon as bytes."""

    return base64.b64decode(_DEFAULT_FAVICON_BASE64)
