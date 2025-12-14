from __future__ import annotations

from html import escape
from typing import Iterable, List


def build_head(*, title: str, description: str, extra: Iterable[str] | None = None) -> List[str]:
    """Return escaped <head> fragments for reuse across pages."""

    base = [
        f"<title>{escape(title)}</title>",
        f"<meta name=\"description\" content=\"{escape(description)}\" />",
        "<meta property=\"og:type\" content=\"website\" />",
        f"<meta property=\"og:title\" content=\"{escape(title)}\" />",
        f"<meta property=\"og:description\" content=\"{escape(description)}\" />",
    ]

    if extra:
        base.extend(extra)
    return base


__all__ = ["build_head"]
