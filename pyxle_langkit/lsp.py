"""Language Server Protocol (LSP) bridge for Pyxle `.pyx` files."""

from __future__ import annotations

import argparse
from typing import Sequence

from lsprotocol.types import (
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentSymbolParams,
    InitializeParams,
    InitializeResult,
    Position,
    PublishDiagnosticsParams,
    Range,
    ServerCapabilities,
    SymbolKind,
    TextDocumentSyncKind,
    TextDocumentSyncOptions,
)
from lsprotocol.types import (
    DocumentSymbol as LspDocumentSymbol,
)
from pygls.server import LanguageServer
from pygls.workspace import TextDocument

from pyxle import __version__ as PYXLE_VERSION
from pyxle.compiler.exceptions import CompilationError

from .document import PyxDocument
from .lint import LintIssue
from .service import DocumentSymbol as OutlineSymbol
from .service import PyxLanguageService

_LANGUAGE_ID = "pyxle"
_INITIALIZE = "initialize"
_DID_OPEN = "textDocument/didOpen"
_DID_CHANGE = "textDocument/didChange"
_DID_SAVE = "textDocument/didSave"
_DID_CLOSE = "textDocument/didClose"
_DOCUMENT_SYMBOL = "textDocument/documentSymbol"
_SEGMENTS_REQUEST = "pyxle/segments"
_SEVERITY_MAP = {
    "error": DiagnosticSeverity.Error,
    "warning": DiagnosticSeverity.Warning,
    "info": DiagnosticSeverity.Information,
}
_SYMBOL_KIND_MAP = {
    "loader": SymbolKind.Function,
    "async-function": SymbolKind.Function,
    "function": SymbolKind.Function,
    "class": SymbolKind.Class,
    "default-export": SymbolKind.Interface,
    "named-export": SymbolKind.Variable,
}


class PyxleLanguageServer(LanguageServer):
    """Shared language server so every LSP-compatible editor can reuse LangKit."""

    def __init__(self) -> None:
        super().__init__("pyxle-langserver", PYXLE_VERSION)
        self.service = PyxLanguageService()
        self._document_cache: dict[str, PyxDocument] = {}

    def run_stdio(self) -> None:
        self.start_io()

    def run_tcp(self, host: str, port: int) -> None:
        self.start_tcp(host, port)


_server = PyxleLanguageServer()


@_server.feature(_INITIALIZE)
def initialize(server: PyxleLanguageServer, params: InitializeParams) -> InitializeResult:  # pragma: no cover - exercised via editors
    capabilities = ServerCapabilities(
        text_document_sync=TextDocumentSyncOptions(
            open_close=True,
            change=TextDocumentSyncKind.Full,
            save=True,
        ),
        document_symbol_provider=True,
    )
    return InitializeResult(capabilities=capabilities)


@_server.feature(_DID_OPEN)
def did_open(server: PyxleLanguageServer, params: DidOpenTextDocumentParams) -> None:
    _publish_diagnostics(server, params.text_document.uri)


@_server.feature(_DID_CHANGE)
def did_change(server: PyxleLanguageServer, params: DidChangeTextDocumentParams) -> None:
    _publish_diagnostics(server, params.text_document.uri)


@_server.feature(_DID_SAVE)
def did_save(server: PyxleLanguageServer, params: DidSaveTextDocumentParams) -> None:
    _publish_diagnostics(server, params.text_document.uri)


@_server.feature(_DID_CLOSE)
def did_close(server: PyxleLanguageServer, params: DidCloseTextDocumentParams) -> None:
    _send_diagnostics(server, params.text_document.uri, [])


@_server.feature(_DOCUMENT_SYMBOL)
def document_symbol(server: PyxleLanguageServer, params: DocumentSymbolParams) -> Sequence[LspDocumentSymbol] | None:
    document = _get_text_document(server, params.text_document.uri)
    if document is None:
        return []
    try:
        symbols = server.service.outline_text(document.source, path=document.path)
    except CompilationError:
        return []
    return [_build_lsp_symbol(entry) for entry in symbols]


@_server.feature(_SEGMENTS_REQUEST)
def document_segments(server: PyxleLanguageServer, params: object | None) -> dict[str, object] | None:
    uri = _extract_uri(params)
    if not uri:
        return None
    document = _get_text_document(server, uri)
    if document is None:
        return None
    pyx_document = server._document_cache.get(uri)
    if pyx_document is None:
        try:
            pyx_document = server.service.parse_text(document.source, path=document.path)
        except CompilationError:
            return None
        server._document_cache[uri] = pyx_document
    python_code, python_lines = pyx_document.editor_python_segments()
    jsx_code, jsx_lines = pyx_document.editor_jsx_segments()
    return {
        "python": {
            "code": python_code,
            "lineNumbers": list(python_lines),
        },
        "jsx": {
            "code": jsx_code,
            "lineNumbers": list(jsx_lines),
        },
    }


def _build_lsp_symbol(symbol: OutlineSymbol) -> LspDocumentSymbol:
    line = _zero_index(symbol.line)
    range_ = Range(
        start=Position(line=line, character=0),
        end=Position(line=line, character=max(1, len(symbol.name))),
    )
    kind = _SYMBOL_KIND_MAP.get(symbol.kind, SymbolKind.Object)
    detail = symbol.detail or ""
    return LspDocumentSymbol(name=symbol.name, kind=kind, range=range_, selection_range=range_, detail=detail)


def _publish_diagnostics(server: PyxleLanguageServer, uri: str) -> None:
    document = _get_text_document(server, uri)
    if document is None:
        return
    try:
        pyx_document = server.service.parse_text(document.source, path=document.path)
    except CompilationError as exc:
        server._document_cache.pop(uri, None)
        diagnostics = [_compilation_error_to_diagnostic(exc)]
        _send_diagnostics(server, uri, diagnostics)
        return
    server._document_cache[uri] = pyx_document
    try:
        issues = server.service.lint_document(pyx_document)
        diagnostics = [_issue_to_diagnostic(issue) for issue in issues]
    except CompilationError as exc:
        diagnostics = [_compilation_error_to_diagnostic(exc)]
    _send_diagnostics(server, uri, diagnostics)


def _issue_to_diagnostic(issue: LintIssue) -> Diagnostic:
    line = _zero_index(issue.line)
    column = _zero_index(issue.column)
    rng = Range(
        start=Position(line=line, character=column),
        end=Position(line=line, character=column + 1),
    )
    severity = _SEVERITY_MAP.get(issue.severity, DiagnosticSeverity.Information)
    return Diagnostic(
        range=rng,
        message=issue.message,
        source=issue.source,
        code=issue.rule,
        severity=severity,
    )


def _compilation_error_to_diagnostic(exc: CompilationError) -> Diagnostic:
    line = _zero_index(exc.line_number)
    rng = Range(
        start=Position(line=line, character=0),
        end=Position(line=line, character=1),
    )
    return Diagnostic(
        range=rng,
        message=exc.message,
        source="pyxle-compiler",
        severity=DiagnosticSeverity.Error,
    )


def _zero_index(value: int | None) -> int:
    if value is None:
        return 0
    return max(0, value - 1)


def _get_text_document(server: PyxleLanguageServer, uri: str) -> TextDocument | None:
    try:
        return server.workspace.get_text_document(uri)
    except KeyError:
        return None


def _send_diagnostics(server: PyxleLanguageServer, uri: str, diagnostics: Sequence[Diagnostic]) -> None:
    params = PublishDiagnosticsParams(uri=uri, diagnostics=list(diagnostics))
    server.text_document_publish_diagnostics(params)


def _extract_uri(params: object | None) -> str | None:
    if params is None:
        return None
    if isinstance(params, dict):
        return params.get("uri")
    return getattr(params, "uri", None)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Pyxle language server entry point")
    parser.add_argument("--tcp", nargs=2, metavar=("HOST", "PORT"), help="Run the server over TCP instead of stdio.")
    parser.add_argument("--stdio", action="store_true", help="Force stdio mode (default)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.tcp:
        host, port = args.tcp
        _server.run_tcp(host, int(port))
        return

    _server.run_stdio()


if __name__ == "__main__":  # pragma: no cover
    main()
