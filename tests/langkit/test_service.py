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


def test_outline_maps_jsx_symbol_lines_back_to_source() -> None:
    service = PyxLanguageService()
    text = dedent(
        """
        @server
        async def loader(request):
            return {"message": "ok"}

        export const helper = 1;
        export default function Page() {
            return <main>{helper}</main>;
        }
        """
    ).strip("\n")

    symbols = service.outline_text(text, path="pages/index.pyx")
    helper = next((symbol for symbol in symbols if symbol.name == "helper"), None)
    page = next((symbol for symbol in symbols if symbol.name == "Page"), None)

    assert helper is not None
    assert helper.line == 5
    assert page is not None
    assert page.line == 6
