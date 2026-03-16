"""High-level helpers intended for IDE/LSP integrations."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .document import PyxDocument
from .lint import LintIssue, PyxLinter
from .parser import PyxLanguageParser
from .react_checker import ReactAnalyzer, ReactSymbol


@dataclass(frozen=True)
class DocumentSymbol:
    name: str
    kind: str
    line: int | None
    detail: str | None = None


class PyxLanguageService:
    """Bundles parsing, linting, and symbol extraction for `.pyx` files."""

    def __init__(
        self,
        *,
        parser: PyxLanguageParser | None = None,
        react_analyzer: ReactAnalyzer | None = None,
        linter: PyxLinter | None = None,
    ) -> None:
        self._parser = parser or PyxLanguageParser(tolerant=True)
        self._react_analyzer = react_analyzer or ReactAnalyzer()
        self._linter = linter or PyxLinter(
            parser=self._parser,
            react_analyzer=self._react_analyzer,
        )

    def parse(self, source: str | Path) -> PyxDocument:
        return self._parser.parse_path(source)

    def parse_text(self, text: str, *, path: str | Path | None = None) -> PyxDocument:
        return self._parser.parse_text(text, path=path)

    def outline(self, source: str | Path) -> Sequence[DocumentSymbol]:
        document = self.parse(source)
        return self._outline_document(document)

    def outline_text(self, text: str, *, path: str | Path | None = None) -> Sequence[DocumentSymbol]:
        document = self.parse_text(text, path=path)
        return self._outline_document(document)

    def _outline_document(self, document: PyxDocument) -> Sequence[DocumentSymbol]:
        symbols: list[DocumentSymbol] = []

        if document.loader is not None:
            symbols.append(
                DocumentSymbol(
                    name=document.loader.name,
                    kind="loader",
                    line=document.loader.line_number,
                    detail="@server loader",
                )
            )

        if document.has_python:
            try:
                tree = ast.parse(document.python_code)
            except SyntaxError:
                tree = None
            if tree is not None:
                symbols.extend(self._python_symbols(tree, document))

        if document.has_jsx:
            try:
                analysis = self._react_analyzer.analyze(document.jsx_code)
            except RuntimeError:
                analysis = None
            if analysis is not None:
                symbols.extend(self._react_symbols(analysis.symbols, document))

        return symbols

    def lint(self, source: str | Path) -> Sequence[LintIssue]:
        return self._linter.lint_path(source)

    def lint_text(self, text: str, *, path: str | Path | None = None) -> Sequence[LintIssue]:
        return self._linter.lint_text(text, path=path)

    def lint_document(self, document: PyxDocument) -> Sequence[LintIssue]:
        return self._linter.lint_document(document)

    def _python_symbols(self, tree: ast.AST, document: PyxDocument) -> Sequence[DocumentSymbol]:
        entries: list[DocumentSymbol] = []
        for node in tree.body:  # type: ignore[attr-defined]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if document.loader and node.name == document.loader.name:
                    continue  # loader already surfaced explicitly
                entries.append(
                    DocumentSymbol(
                        name=node.name,
                        kind="async-function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                        line=document.map_python_line(node.lineno),
                        detail="async" if isinstance(node, ast.AsyncFunctionDef) else "sync",
                    )
                )
            elif isinstance(node, ast.ClassDef):
                entries.append(
                    DocumentSymbol(
                        name=node.name,
                        kind="class",
                        line=document.map_python_line(node.lineno),
                        detail=f"{len(node.body)} members",
                    )
                )
        return entries

    @staticmethod
    def _react_symbols(symbols: Sequence[ReactSymbol], document: PyxDocument) -> Sequence[DocumentSymbol]:
        return [
            DocumentSymbol(
                name=symbol.name,
                kind=symbol.kind,
                line=document.map_jsx_line(symbol.line),
                detail="React export",
            )
            for symbol in symbols
        ]
