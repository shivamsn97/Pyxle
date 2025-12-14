"""Console logger helper ensuring consistent CLI output formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

import typer

_LogFunction = Callable[[str], None]


class LogFormat(str, Enum):
    """Output format for CLI logs."""

    CONSOLE = "console"
    JSON = "json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConsoleLogger:
    """Simple console logger using Typer styling for consistent output.

    Parameters
    ----------
    secho:
        Callable that mirrors :func:`typer.secho`. This indirection allows tests
        to capture output without touching global state.
    formatter:
        Output format for log lines, either ``"console"`` (default) or ``"json"``.
    timestamp_factory:
        Callable returning ISO8601 timestamps for JSON log entries.
    """

    secho: _LogFunction = typer.secho
    formatter: LogFormat = LogFormat.CONSOLE
    timestamp_factory: Callable[[], str] = _utc_timestamp

    def set_formatter(self, formatter: LogFormat) -> None:
        """Switch the log formatter used by the console logger."""

        self.formatter = formatter

    # Console emitters -------------------------------------------------

    def _emit_console(self, message: str, style: str, bold: bool = False) -> None:
        self.secho(message, fg=style, bold=bold)

    def _emit_json(self, level: str, message: str, extra: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {
            "level": level,
            "message": message,
            "timestamp": self.timestamp_factory(),
        }
        if extra:
            payload.update(extra)
        self.secho(json.dumps(payload, ensure_ascii=False))

    def _emit(self, *, level: str, console_message: str, style: str, bold: bool = False, extra: dict[str, object] | None = None) -> None:
        if self.formatter == LogFormat.JSON:
            self._emit_json(level, console_message, extra)
            return
        self._emit_console(console_message, style, bold=bold)

    def info(self, message: str) -> None:
        """Emit an informational message."""

        self._emit(level="info", console_message=f"ℹ️  {message}", style="cyan")

    def success(self, message: str) -> None:
        """Emit a success message."""

        self._emit(level="success", console_message=f"✅ {message}", style="green", bold=True)

    def warning(self, message: str) -> None:
        """Emit a warning message."""

        self._emit(level="warning", console_message=f"⚠️  {message}", style="yellow")

    def error(self, message: str) -> None:
        """Emit an error message."""

        self._emit(level="error", console_message=f"❌ {message}", style="red", bold=True)

    def step(self, label: str, detail: str | None = None) -> None:
        """Emit a step headline with optional detail."""

        suffix = f" — {detail}" if detail else ""
        message = f"▶️  {label}{suffix}"
        extra: dict[str, object] | None = None
        if detail is not None:
            extra = {"label": label, "detail": detail}
        else:
            extra = {"label": label}
        self._emit(level="step", console_message=message, style="magenta", extra=extra)


__all__ = ["ConsoleLogger", "LogFormat"]
