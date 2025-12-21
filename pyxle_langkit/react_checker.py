"""Bridge helpers that reuse Babel for JSX/React analysis."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ReactSymbol:
    name: str
    kind: str
    line: int | None
    column: int | None


@dataclass(frozen=True)
class ReactSyntaxError:
    message: str
    line: int | None
    column: int | None


@dataclass(frozen=True)
class ReactAnalysis:
    symbols: Sequence[ReactSymbol]
    error: ReactSyntaxError | None


class ReactAnalyzer:
    """Runs the Node-powered JSX parser so IDE tools stay in sync with React."""

    def __init__(
        self,
        *,
        node_command: Sequence[str] | None = None,
        runner_path: Path | None = None,
    ) -> None:
        self._node_command = tuple(node_command or ("node",))
        base = Path(__file__).resolve().parent
        self._runner_path = runner_path or base / "js" / "react_parser_runner.mjs"

    def analyze(self, source: str) -> ReactAnalysis:
        if not source.strip():
            return ReactAnalysis(symbols=(), error=None)

        temp_file = tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False, encoding="utf-8")
        try:
            temp_file.write(source)
            temp_file.flush()
            temp_file.close()
            payload = self._run_node(temp_file.name)
        finally:
            try:
                os.unlink(temp_file.name)
            except FileNotFoundError:
                pass

        if not payload.get("ok", False):
            error = ReactSyntaxError(
                message=payload.get("message", "React parser error"),
                line=payload.get("line"),
                column=payload.get("column"),
            )
            return ReactAnalysis(symbols=(), error=error)

        symbols = tuple(
            ReactSymbol(
                name=entry.get("name", "unknown"),
                kind=entry.get("kind", "named-export"),
                line=entry.get("line"),
                column=entry.get("column"),
            )
            for entry in payload.get("symbols", [])
        )
        return ReactAnalysis(symbols=symbols, error=None)

    def _run_node(self, source_path: str) -> dict[str, object]:
        command = [*self._node_command, str(self._runner_path), source_path]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "Node.js is required to analyze JSX. Please install Node >=18 and rerun."
            ) from exc

        if proc.returncode not in (0, 1):  # treat >=2 as infrastructure failure
            raise RuntimeError(
                "React parser runner failed: "
                f"{proc.stdout.strip() or proc.stderr.strip() or proc.returncode}"
            )

        text = proc.stdout.strip() or proc.stderr.strip() or "{}"
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError(
                "React parser runner produced invalid JSON output: "
                f"{text}"
            ) from exc
