from __future__ import annotations

from textwrap import dedent

from pyxle_langkit.lint import PyxLinter
from pyxle_langkit.parser import PyxLanguageParser
from pyxle_langkit.react_checker import ReactAnalysis, ReactSyntaxError


class FakeReactAnalyzer:
    def __init__(self, *, line: int, column: int | None = None) -> None:
        self._line = line
        self._column = column

    def analyze(self, source: str) -> ReactAnalysis:  # pragma: no cover - simple fake
        error = ReactSyntaxError(message="Invalid JSX", line=self._line, column=self._column)
        return ReactAnalysis(symbols=(), error=error)


def test_react_syntax_error_maps_back_to_original_line() -> None:
    text = dedent(
        """
        @server
        async def loader(request):
            return {}

        export default function Page() {
            return (
                <main>
                    <section>
                        <span>Missing closing tag
                </main>
            );
        }
        """
    ).strip("\n")

    linter = PyxLinter(
        parser=PyxLanguageParser(),
        react_analyzer=FakeReactAnalyzer(line=5, column=11),
    )

    issues = linter.lint_text(text, path="pages/index.pyx")
    react_issue = next((issue for issue in issues if issue.source == "react"), None)
    assert react_issue is not None
    assert react_issue.line == 9  # fifth JSX line maps back to original document line


def test_pyflakes_reports_undefined_name_and_unused_import() -> None:
    text = dedent(
        """
        @server
        async def loader(request):
            import math
            return missing_value + math.pi
        """
    ).strip("\n")

    linter = PyxLinter(parser=PyxLanguageParser())
    issues = linter.lint_text(text, path="pages/index.pyx")

    rules = {issue.rule for issue in issues}
    assert "pyflakes/UndefinedName" in rules
    assert "pyflakes/UnusedImport" not in rules  # math is used via math.pi


def test_pyflakes_detects_unused_import() -> None:
    text = dedent(
        """
        @server
        async def loader(request):
            import os
            return {}
        """
    ).strip("\n")

    linter = PyxLinter(parser=PyxLanguageParser())
    issues = linter.lint_text(text, path="pages/index.pyx")

    assert any(issue.rule == "pyflakes/UnusedImport" for issue in issues)


def test_server_decorator_is_whitelisted() -> None:
    text = dedent(
        """
        @server
        async def loader(request):
            return {"value": 1}
        """
    ).strip("\n")

    linter = PyxLinter(parser=PyxLanguageParser())

    issues = linter.lint_text(text, path="pages/index.pyx")

    assert all(issue.rule != "pyflakes/UndefinedName" for issue in issues)


def test_unreachable_code_is_reported() -> None:
    text = dedent(
        """
        @server
        async def loader(request):
            return {"value": 1}
            print("never runs")

        export default function Page() {
            return null;
        }
        """
    ).strip("\n")

    linter = PyxLinter(parser=PyxLanguageParser())
    issues = linter.lint_text(text, path="pages/index.pyx")

    assert any(issue.rule == "pyxle/unreachable-code" for issue in issues)
