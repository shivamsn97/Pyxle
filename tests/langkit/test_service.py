from __future__ import annotations

from textwrap import dedent

from pyxle_langkit.service import PyxLanguageService


def test_outline_tolerates_invalid_python_blocks() -> None:
    service = PyxLanguageService()
    text = dedent(
        """
        @server
        async def loader(request):
            return {"message": "ok"}

        def broken():
            now = datetime.now(tz=timezone.utc)lf
            return now
        """
    ).strip("\n")

    symbols = service.outline_text(text, path="pages/index.pyx")

    # Even though parsing fails, tolerant outline should degrade gracefully.
    assert symbols == []
