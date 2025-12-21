"""Linting primitives for `.pyx` authoring."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

try:  # pragma: no cover - optional dependency
    from pyflakes.checker import Checker as _PyflakesChecker
except Exception:  # pragma: no cover - tooling-only optional import
    _PyflakesChecker = None

_PYFLAKES_SEVERITY: dict[str, Severity] = {
    "UndefinedName": "error",
    "UndefinedLocal": "error",
    "ReturnOutsideFunction": "error",
    "ContinueOutsideLoop": "error",
    "BreakOutsideLoop": "error",
    "UnusedImport": "info",
    "UnusedVariable": "info",
    "UnusedFunction": "info",
    "UnusedClass": "info",
    "ImportShadowedByLoopVar": "warning",
    "RedefinedWhileUnused": "warning",
    "DuplicateArgument": "warning",
    "MultiValueRepeatedKeyLiteral": "warning",
}

_PYXLE_ALLOWED_GLOBALS = {"server"}

from .document import PyxDocument
from .parser import PyxLanguageParser
from .react_checker import ReactAnalyzer

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class LintIssue:
    source: str
    message: str
    rule: str
    severity: Severity
    line: int | None = None
    column: int | None = None

    def format(self) -> str:
        location = f"{self.line}:{self.column}" if self.line is not None else "?"
        return f"[{self.severity}] {self.rule} ({location}) {self.message}"


class PyxLinter:
    """Runs structural checks by leveraging existing Python/React parsers."""

    def __init__(
        self,
        *,
        parser: PyxLanguageParser | None = None,
        react_analyzer: ReactAnalyzer | None = None,
    ) -> None:
        self._parser = parser or PyxLanguageParser(tolerant=True)
        self._react_analyzer = react_analyzer or ReactAnalyzer()

    def lint_path(self, source: str | Path) -> list[LintIssue]:
        document = self._parser.parse_path(source)
        return self.lint_document(document)

    def lint_text(self, text: str, *, path: str | Path | None = None) -> list[LintIssue]:
        document = self._parser.parse_text(text, path=path)
        return self.lint_document(document)

    def lint_document(self, document: PyxDocument) -> list[LintIssue]:
        return list(self._lint_document(document))

    def _lint_document(self, document: PyxDocument) -> Iterable[LintIssue]:
        issues: list[LintIssue] = []
        issues.extend(self._lint_python(document))
        issues.extend(self._lint_jsx(document))
        return issues

    def _lint_python(self, document: PyxDocument) -> Iterable[LintIssue]:
        if not document.has_python:
            return []

        try:
            tree = ast.parse(document.python_code)
        except SyntaxError as exc:  # pragma: no cover - parser already enforces syntax, defensive only
            return [
                LintIssue(
                    source="python",
                    rule="python/syntax",
                    severity="error",
                    message=exc.msg,
                    line=document.map_python_line(exc.lineno),
                    column=exc.offset,
                )
            ]
        issues: list[LintIssue] = []

        issues.extend(self._pyflakes_issues(tree, document))
        issues.extend(self._detect_unreachable_code(tree, document))

        if document.loader is None:
            issues.append(
                LintIssue(
                    source="python",
                    rule="pyxle/loader-missing",
                    severity="warning",
                    message="Python code detected without an @server loader; static data will never reach the client.",
                    line=None,
                    column=None,
                )
            )
        else:
            loader_node = next(
                (
                    node
                    for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == document.loader.name
                ),
                None,
            )
            if loader_node and not self._function_has_return(loader_node):
                issues.append(
                    LintIssue(
                        source="python",
                        rule="pyxle/loader-no-return",
                        severity="warning",
                        message="@server loader never returns a value; hydration will receive `None`.",
                        line=document.map_python_line(loader_node.lineno),
                        column=loader_node.col_offset,
                    )
                )

        return issues

    def _pyflakes_issues(self, tree: ast.AST, document: PyxDocument) -> Iterable[LintIssue]:
        if _PyflakesChecker is None:
            return []

        checker = _PyflakesChecker(tree, filename=str(document.path))
        issues: list[LintIssue] = []
        for message in checker.messages:
            cls_name = message.__class__.__name__
            missing_name = getattr(message, "name", None)
            if missing_name is None:
                args = getattr(message, "message_args", None)
                if args:
                    missing_name = args[0]
            if cls_name == "UndefinedName" and missing_name in _PYXLE_ALLOWED_GLOBALS:
                continue
            severity = _PYFLAKES_SEVERITY.get(cls_name, "warning")
            line = document.map_python_line(getattr(message, "lineno", None))
            column = getattr(message, "col", None)
            issues.append(
                LintIssue(
                    source="python",
                    rule=f"pyflakes/{cls_name}",
                    severity=severity,
                    message=self._format_pyflakes_message(message),
                    line=line,
                    column=column,
                )
            )
        return issues

    @staticmethod
    def _format_pyflakes_message(message: object) -> str:
        template = getattr(message, "message", None)
        args = getattr(message, "message_args", None)
        if template:
            try:
                return template % args if args else template
            except Exception:  # pragma: no cover - defensive: fall back to str()
                return template
        return str(message)

    def _detect_unreachable_code(self, tree: ast.AST, document: PyxDocument) -> Iterable[LintIssue]:
        analyzer = _UnreachableAnalyzer(document)
        analyzer.scan(tree)
        return analyzer.issues

    def _lint_jsx(self, document: PyxDocument) -> Iterable[LintIssue]:
        if not document.has_jsx:
            return []

        analysis = self._react_analyzer.analyze(document.jsx_code)
        issues: list[LintIssue] = []

        if analysis.error:
            mapped_line = document.map_jsx_line(analysis.error.line)
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/syntax",
                    severity="error",
                    message=analysis.error.message,
                    line=mapped_line,
                    column=analysis.error.column,
                )
            )
            return issues

        has_default_export = any(symbol.kind == "default-export" for symbol in analysis.symbols)
        if not has_default_export:
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/default-export",
                    severity="warning",
                    message="Pages should export a default component for SSR + hydration.",
                    line=None,
                    column=None,
                )
            )

        return issues

    @staticmethod
    def _function_has_return(node: ast.AsyncFunctionDef) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                return True
        return False


class _UnreachableAnalyzer:
    _TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)

    def __init__(self, document: PyxDocument) -> None:
        self.document = document
        self.issues: list[LintIssue] = []

    def scan(self, tree: ast.AST) -> None:
        body: Sequence[ast.stmt] = getattr(tree, "body", [])  # type: ignore[assignment]
        self._scan_block(body)

    def _scan_block(self, statements: Sequence[ast.stmt]) -> None:
        reachable = True
        for statement in statements:
            if statement is None:
                continue
            if not reachable:
                self._record_unreachable(statement)
                continue
            self._visit_children(statement)
            if isinstance(statement, self._TERMINATORS):
                reachable = False

    def _visit_children(self, statement: ast.stmt) -> None:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._scan_block(statement.body)
            return
        if isinstance(statement, ast.If):
            self._scan_block(statement.body)
            self._scan_block(statement.orelse)
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            self._scan_block(statement.body)
            self._scan_block(statement.orelse)
        elif isinstance(statement, ast.Try):
            self._scan_block(statement.body)
            for handler in statement.handlers:
                self._scan_block(handler.body)
            self._scan_block(statement.orelse)
            self._scan_block(statement.finalbody)
        elif isinstance(statement, ast.With):
            self._scan_block(statement.body)
        elif isinstance(statement, ast.Match):  # Python 3.10+
            for case in statement.cases:  # type: ignore[attr-defined]
                self._scan_block(case.body)

    def _record_unreachable(self, statement: ast.stmt) -> None:
        line = self.document.map_python_line(getattr(statement, "lineno", None))
        column = getattr(statement, "col_offset", None)
        self.issues.append(
            LintIssue(
                source="python",
                rule="pyxle/unreachable-code",
                severity="warning",
                message="Code is unreachable because a previous statement exits the block.",
                line=line,
                column=column,
            )
        )
