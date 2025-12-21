from __future__ import annotations

from types import SimpleNamespace

import pytest

from pyxle.compiler.exceptions import CompilationError
from pyxle_langkit import lsp


class FakeWorkspace:
    def __init__(self, document) -> None:
        self.document = document

    def get_text_document(self, uri):
        if uri != self.document.uri:
            raise KeyError(uri)
        return self.document


def test_publish_diagnostics_surfaces_compilation_errors(monkeypatch):
    document = SimpleNamespace(uri="file:///pages/index.pyx", path="pages/index.pyx", source="bad indent")

    class FakeService:
        def parse_text(self, *_args, **_kwargs):
            raise CompilationError(message="Unexpected indentation in Python block", line_number=38)

        def lint_document(self, *_args, **_kwargs):
            pytest.fail("lint_document should not be called when parse_text fails")

    published = []

    def fake_send(server, uri, diagnostics):
        published.append((uri, diagnostics))

    server = SimpleNamespace(
        workspace=FakeWorkspace(document),
        service=FakeService(),
        _document_cache={},
        text_document_publish_diagnostics=None,
    )

    monkeypatch.setattr(lsp, "_send_diagnostics", fake_send)

    lsp._publish_diagnostics(server, document.uri)

    assert published, "diagnostics should be published"
    uri, diagnostics = published[0]
    assert uri == document.uri
    assert diagnostics[0].message == "Unexpected indentation in Python block"
    assert diagnostics[0].source == "pyxle-compiler"
    assert server._document_cache == {}
