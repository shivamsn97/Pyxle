"""Entry points that expose the compiler parser to IDE tooling."""

from __future__ import annotations

from pathlib import Path

from pyxle.compiler.parser import PyxParser

from .document import PyxDocument


class PyxLanguageParser:
    """Parses `.pyx` files into a consumable document representation."""

    def __init__(self, parser: PyxParser | None = None, *, tolerant: bool = True) -> None:
        self._parser = parser or PyxParser()
        self._tolerant = tolerant

    def parse_path(self, source: str | Path) -> PyxDocument:
        path = Path(source)
        result = self._parser.parse(path, tolerant=self._tolerant)
        return PyxDocument(
            path=path,
            python_code=result.python_code,
            python_line_numbers=result.python_line_numbers,
            jsx_code=result.jsx_code,
            jsx_line_numbers=result.jsx_line_numbers,
            loader=result.loader,
            head_elements=result.head_elements,
            head_is_dynamic=result.head_is_dynamic,
        )

    def parse_text(self, text: str, *, path: str | Path | None = None) -> PyxDocument:
        result = self._parser.parse_text(text, tolerant=self._tolerant)
        resolved = Path(path) if path is not None else Path("<memory>")
        return PyxDocument(
            path=resolved,
            python_code=result.python_code,
            python_line_numbers=result.python_line_numbers,
            jsx_code=result.jsx_code,
            jsx_line_numbers=result.jsx_line_numbers,
            loader=result.loader,
            head_elements=result.head_elements,
            head_is_dynamic=result.head_is_dynamic,
        )
