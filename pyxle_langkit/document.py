"""Shared document abstractions for Pyxle language tooling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pyxle.compiler.jsx_imports import rewrite_pyx_import_specifiers
from pyxle.compiler.parser import LoaderDetails
from pyxle.compiler.writers import ensure_server_import


@dataclass(frozen=True)
class PyxDocument:
    """Represents a parsed `.pyx` file with helper utilities."""

    path: Path
    python_code: str
    python_line_numbers: Sequence[int]
    jsx_code: str
    jsx_line_numbers: Sequence[int]
    loader: LoaderDetails | None
    head_elements: tuple[str, ...]
    head_is_dynamic: bool

    def map_python_line(self, lineno: int | None) -> int | None:
        """Map a virtual Python line number back to the original `.pyx` file."""

        if lineno is None:
            return None
        if lineno < 1 or lineno > len(self.python_line_numbers):
            return None
        return self.python_line_numbers[lineno - 1]

    def map_jsx_line(self, lineno: int | None) -> int | None:
        """Map a virtual JSX line number back to the original `.pyx` file."""

        if lineno is None:
            return None
        if lineno < 1 or lineno > len(self.jsx_line_numbers):
            return None
        return self.jsx_line_numbers[lineno - 1]

    @property
    def has_jsx(self) -> bool:
        return bool(self.jsx_code.strip())

    @property
    def has_python(self) -> bool:
        return bool(self.python_code.strip())

    def editor_python_segments(self) -> tuple[str, tuple[int, ...]]:
        """Return Python code tailored for editor tooling with updated line mapping."""

        code = self.python_code
        line_numbers = list(self.python_line_numbers)

        if self.loader and code.strip():
            code, insert_at = ensure_server_import(code, return_insert_position=True)
            if insert_at is not None:
                anchor = self._line_anchor_for_insertion(line_numbers, insert_at)
                line_numbers.insert(insert_at, anchor)

        return code, tuple(line_numbers)

    def editor_jsx_segments(self) -> tuple[str, tuple[int, ...]]:
        """Return JSX code with specifier rewrites for editor tooling."""

        rewritten, _ = rewrite_pyx_import_specifiers(self.jsx_code)
        return rewritten, tuple(self.jsx_line_numbers)

    def _line_anchor_for_insertion(self, mapping: list[int], insert_at: int) -> int:
        if not mapping:
            if self.loader and self.loader.line_number:
                return self.loader.line_number
            return 1

        if insert_at <= 0:
            return mapping[0]

        if insert_at - 1 < len(mapping):
            return mapping[insert_at - 1]

        return mapping[-1]
