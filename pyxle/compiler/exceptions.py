"""Custom exceptions for compiler failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class CompilationError(Exception):
    """Raised when a `.pyx` file cannot be compiled."""

    message: str
    line_number: int | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.line_number is None:
            return self.message
        return f"Line {self.line_number}: {self.message}"
