"""Tests for parser hardening: JSX import detection, ambiguous-line
edge cases, and full-file edge cases.

Originally added in Phase 1.7 of the Pyxle roadmap. After the parser
rewrite to AST-driven multi-section detection, the tests that exercised
the (now-removed) heuristic repair pass, internal helpers, and
``# ---`` fence markers were replaced by behavior-equivalent tests
that exercise the same patterns through the public
``PyxParser.parse_text`` API.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from pyxle.compiler.parser import PyxParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(text: str):
    """Parse text and return the result."""
    return PyxParser().parse_text(dedent(text).strip("\n"))


# ---------------------------------------------------------------------------
# AST-driven segmentation behavior (replaces the removed heuristic repair tests)
# ---------------------------------------------------------------------------


class TestAstSegmentationBehavior:
    """Behavior tests that replace the removed _try_repair_document tests.

    Each test exercises an input pattern that the old heuristic+repair
    pipeline had to "fix up" via backtracking. The new AST-driven walker
    handles them correctly in one pass.
    """

    def test_assignment_like_jsx_classified_as_jsx(self):
        """A line like ``config = <Provider value={ctx}>`` (which has '='
        and used to be misclassified as Python by the old heuristics)
        ends up in the JSX section."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {}

            config = <Provider value={ctx}>;

            export default function Page() {
                return <div />;
            }
        """)
        assert "config = <Provider value={ctx}>;" in result.jsx_code
        assert "config = <Provider value={ctx}>;" not in result.python_code

    def test_strong_python_markers_stay_python(self):
        """Lines starting with ``import``, ``def``, ``class``, ``@`` are
        Python and don't get reclassified even when surrounded by
        JSX-shaped content."""
        result = _parse("""
            from math import sqrt

            export default function Page() {
                return <div>{sqrt(4)}</div>;
            }
        """)
        assert "from math import sqrt" in result.python_code

    def test_repair_reclassifies_misidentified_jsx(self):
        """End-to-end: a file with both server logic and client-side JSX
        cleanly splits via the AST walker."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {"key": "val"}

            import React from 'react';

            export default function Page({ data }) {
                return <div>{data.key}</div>;
            }
        """)
        assert "from pyxle.runtime import server" in result.python_code
        assert result.loader is not None
        assert "export default" in result.jsx_code

    def test_unparseable_input_in_tolerant_mode_does_not_crash(self):
        """Tolerant-mode parsing of complete junk doesn't raise — it
        emits a diagnostic and returns whatever could be salvaged."""
        result = PyxParser().parse_text("???\n@@@", tolerant=True)
        assert result is not None
        assert isinstance(result.diagnostics, tuple)

    def test_unterminated_python_string_routed_to_python_diagnostic(self):
        """An unterminated Python string literal must produce a
        ``[python]`` diagnostic, not silently flow into the JSX
        section. Regression test for the manual-tests audit bug where
        ``x = "this string never closes`` followed by valid JSX would
        be absorbed into the first JSX segment and never reported.
        """
        src = (
            'x = "this string never closes\n'
            'y = 1\n'
            '\n'
            "import React from 'react';\n"
            "export default function Page() { return <div />; }\n"
        )
        result = PyxParser().parse_text(src, tolerant=True)
        assert any(
            d.section == "python" and "unterminated string" in d.message
            for d in result.diagnostics
        ), f"expected [python] unterminated string diagnostic, got {result.diagnostics!r}"

    def test_unterminated_python_string_strict_mode_raises(self):
        """Strict-mode parsing of the same broken input raises
        ``CompilationError`` instead of silently succeeding."""
        from pyxle.compiler.exceptions import CompilationError

        src = (
            'x = "this string never closes\n'
            'y = 1\n'
            '\n'
            "import React from 'react';\n"
            "export default function Page() { return <div />; }\n"
        )
        with pytest.raises(CompilationError):
            PyxParser().parse_text(src)

    def test_bare_assignment_with_unknown_jsx_starter_flagged(self):
        """A bare assignment that isn't a JSX element and doesn't match
        any JSX top-level starter is suspicious — if it fails to parse
        as Python, the error is reported as a Python diagnostic.
        """
        src = (
            'data = {"broken": \n'  # unterminated dict/string
            "import React from 'react';\n"
            "export default function Page() { return <div />; }\n"
        )
        result = PyxParser().parse_text(src, tolerant=True)
        assert any(
            d.section == "python" for d in result.diagnostics
        ), f"expected [python] diagnostic, got {result.diagnostics!r}"

    def test_jsx_segment_with_less_than_before_element_not_flagged(self):
        """A JSX segment whose first non-blank line is a bare-identifier
        assignment containing a less-than comparison before the actual
        JSX element tag should still be recognized as JSX. The element
        scanner walks past non-element ``<`` characters so a later
        ``<Component`` is still picked up. Exercises the continuation
        branch in ``_contains_jsx_element_marker``.
        """
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {}

            guard = x < 10 ? <Warning /> : <Safe />;

            export default function Page() { return <div />; }
        """)
        assert "guard = x < 10" in result.jsx_code
        assert not result.diagnostics

    def test_deeply_nested_source_emits_diagnostic_not_crash(self):
        """A source with extreme nesting depth exhausts CPython's
        parser stack (``MemoryError`` / ``RecursionError``). The
        parser must catch these at the outer boundary and emit a
        structured diagnostic rather than letting them propagate and
        crash the CLI mid-scan.

        The combination of deep nesting AND a trailing non-Python
        section (the JSX) is what triggers ``MemoryError``: CPython
        cannot recover from the JSX syntax error when its parser
        stack is already exhausted by the nested expression.
        """
        nested_loader = (
            "@server\n"
            "async def loader(request):\n"
            "    return " + "[" * 200 + "1" + "]" * 200 + "\n"
            "\n"
            "import React from 'react';\n"
            "export default function Page() { return <div />; }\n"
        )
        result = PyxParser().parse_text(nested_loader, tolerant=True)
        # Should not crash, and should emit a [python] diagnostic
        # about parser exhaustion.
        assert any(
            d.section == "python" and "exhausted" in d.message
            for d in result.diagnostics
        ), f"expected parser-exhausted diagnostic, got {result.diagnostics!r}"

    def test_jsx_segment_starting_with_async_function_recognized(self):
        """A JSX segment whose first non-blank line begins with
        ``async function`` is valid JSX top-level and must not trigger
        the broken-Python heuristic. Exercises the ``async function``
        branch in ``_looks_like_jsx_toplevel``."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {}

            async function helper() { return 1; }

            export default function Page() { return <div />; }
        """)
        assert "async function helper()" in result.jsx_code
        assert not result.diagnostics


# ---------------------------------------------------------------------------
# JSX import detection
# ---------------------------------------------------------------------------


class TestJsxImportDetection:
    """``import X from 'path'`` (with quotes) is always JSX, never Python."""

    @pytest.mark.parametrize(
        "import_stmt",
        [
            "import React from 'react'",
            'import React from "react"',
            "import { useState } from 'react'",
            "import './styles.css'",
            'import "./styles.css"',
            "import 'normalize.css'",
            'import "lodash"',
            "import type { FC } from 'react'",
            "import * as React from 'react'",
        ],
    )
    def test_js_imports_classified_as_jsx(self, import_stmt: str):
        """Each JS-style import lands in jsx_code, never python_code."""
        result = _parse(
            f"{import_stmt};\n\nexport default function P() {{ return <div />; }}"
        )
        assert import_stmt in result.jsx_code
        assert import_stmt not in result.python_code

    @pytest.mark.parametrize("import_stmt", ["import os", "import sys"])
    def test_python_imports_classified_as_python(self, import_stmt: str):
        """Stdlib-style ``import NAME`` (no quotes) is Python."""
        result = _parse(
            f"{import_stmt}\n\nimport React from 'react';\n"
            "export default function P() { return <div />; }"
        )
        assert import_stmt in result.python_code

    def test_side_effect_import_classified_as_jsx(self):
        """Side-effect imports should end up in jsx_code, not python_code."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {}

            import 'normalize.css'
            import React from 'react';

            export default function Page() {
                return <div>Hello</div>;
            }
        """)
        assert "import 'normalize.css'" in result.jsx_code
        assert "import 'normalize.css'" not in result.python_code


# ---------------------------------------------------------------------------
# Ambiguous line edge cases (now via behavior tests)
# ---------------------------------------------------------------------------


_JSX_TAIL = "\n\nexport default function P() { return <div />; }"


def _assert_in_python(snippet: str):
    result = _parse(snippet + _JSX_TAIL)
    assert snippet in result.python_code, (
        f"{snippet!r} should be Python but ended up in jsx_code"
    )


def _assert_in_jsx(snippet: str):
    result = _parse(snippet + _JSX_TAIL)
    assert snippet in result.jsx_code, (
        f"{snippet!r} should be JSX but ended up in python_code"
    )


class TestAmbiguousLines:
    """Edge cases where lines could be Python or JSX. All assertions go
    through the public ``parse_text`` API; no calls to internal helpers."""

    def test_import_from_with_quotes_is_jsx(self):
        """``import X from 'path'`` is JSX, not Python ``from … import``."""
        result = _parse("""
            import React from 'react';

            export default function Page() {
                return <div>Hello</div>;
            }
        """)
        assert "import React" in result.jsx_code
        assert result.python_code.strip() == ""

    def test_python_import_is_python(self):
        """``import os`` (no quotes) is Python."""
        result = _parse("""
            import os

            import React from 'react';

            export default function Page() {
                return <div>Hello</div>;
            }
        """)
        assert "import os" in result.python_code

    def test_assignment_with_semicolon_is_jsx(self):
        """JS-style assignments (``const`` / ``let`` / ``var``) are JSX.

        Note: a plain ``value = something;`` IS valid Python (the semicolon
        separates statements), so we use a JS-only construct here.
        """
        _assert_in_jsx("const value = something;")

    def test_comment_hash_is_python(self):
        """``#`` comments at module level are Python."""
        # A standalone Python comment is consumed by the Python segment.
        result = _parse(
            "# this is a comment\nx = 1\n\n"
            "export default function P() { return <div />; }"
        )
        assert "# this is a comment" in result.python_code

    def test_comment_double_slash_is_jsx(self):
        """``//`` comments are JSX."""
        _assert_in_jsx("// this is a comment")

    def test_if_with_colon_is_python(self):
        """``if condition:`` is Python."""
        _assert_in_python("if True:\n    x = 1")

    def test_angle_bracket_is_jsx(self):
        """Lines starting with ``<`` are JSX."""
        result = _parse(
            "import React from 'react';\n\n"
            "export default function P() {\n"
            "    return <Component />;\n"
            "}"
        )
        assert "<Component />" in result.jsx_code

    def test_export_is_jsx(self):
        _assert_in_jsx("export default function Page() {}")

    @pytest.mark.parametrize(
        "snippet",
        [
            "const x = 1;",
            "let y = 2;",
            "var z = 3;",
        ],
    )
    def test_const_let_var_are_jsx(self, snippet: str):
        _assert_in_jsx(snippet)

    def test_triple_quoted_string_is_python(self):
        """A bare triple-quoted string is a Python expression statement
        (typically a docstring)."""
        result = _parse(
            '"""docstring"""\nx = 1\n\n'
            "export default function P() { return <div />; }"
        )
        assert '"""docstring"""' in result.python_code

    def test_decorator_is_python(self):
        result = _parse("""
            from dataclasses import dataclass

            @dataclass
            class Foo:
                x: int = 1

            export default function P() { return <div />; }
        """)
        assert "@dataclass" in result.python_code
        assert "class Foo" in result.python_code

    def test_template_literal_not_misidentified(self):
        """Template literals (backtick strings) should stay JSX."""
        result = _parse("""
            import React from 'react';

            export default function Page() {
                const name = `hello world`;
                return <div>{name}</div>;
            }
        """)
        assert "const name = `hello world`" in result.jsx_code

    def test_async_function_keyword_is_jsx(self):
        """``async function`` (JS style) is JSX."""
        result = _parse("""
            import React from 'react';

            export default function P() {
                async function handleClick() { return 1; }
                return <button onClick={handleClick} />;
            }
        """)
        assert "async function handleClick" in result.jsx_code

    def test_function_keyword_is_jsx(self):
        """Standalone ``function`` keyword is JSX."""
        result = _parse("""
            import React from 'react';

            function helper() { return 1; }

            export default function P() { return <div>{helper()}</div>; }
        """)
        assert "function helper" in result.jsx_code


# ---------------------------------------------------------------------------
# Full file parsing edge cases
# ---------------------------------------------------------------------------


class TestFullFileParsing:
    """End-to-end parsing of complete .pyx files with tricky content."""

    def test_python_string_containing_jsx_is_not_jsx(self):
        """Python strings that contain JSX-like content stay in Python."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                template = "<div>hello</div>"
                return {"html": template}

            import React from 'react';

            export default function Page({ data }) {
                return <div dangerouslySetInnerHTML={{__html: data.html}} />;
            }
        """)
        assert 'template = "<div>hello</div>"' in result.python_code

    def test_python_multiline_string_not_split(self):
        """Multiline Python strings should stay together."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                query = \"\"\"
                    SELECT * FROM users
                    WHERE active = true
                \"\"\"
                return {"query": query}

            import React from 'react';

            export default function Page() {
                return <div>Page</div>;
            }
        """)
        assert "SELECT * FROM users" in result.python_code

    def test_empty_file_produces_empty_result(self):
        result = _parse("")
        assert result.python_code == ""
        assert result.jsx_code == ""
        assert result.loader is None

    def test_python_only_file(self):
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {"key": "value"}
        """)
        assert "from pyxle.runtime import server" in result.python_code
        assert result.jsx_code.strip() == ""
        assert result.loader is not None

    def test_jsx_only_file(self):
        result = _parse("""
            import React from 'react';

            export default function Page() {
                return <div>Hello World</div>;
            }
        """)
        assert result.python_code.strip() == ""
        assert "export default" in result.jsx_code
        assert result.loader is None

    def test_file_with_loader_and_actions(self):
        result = _parse("""
            from pyxle.runtime import server, action

            @server
            async def loader(request):
                return {"items": []}

            @action
            async def add_item(request):
                return {"ok": True}

            import React from 'react';

            export default function Page({ data }) {
                return <ul>{data.items.map(i => <li key={i}>{i}</li>)}</ul>;
            }
        """)
        assert result.loader is not None
        assert len(result.actions) == 1
        assert result.actions[0].name == "add_item"
        assert "export default" in result.jsx_code

    def test_comment_only_python_section(self):
        result = _parse("""
            # This page has no server logic

            import React from 'react';

            export default function Page() {
                return <div>Static page</div>;
            }
        """)
        # Comments at the top should be Python
        assert "# This page has no server logic" in result.python_code

    def test_inline_comment_in_python(self):
        result = _parse("""
            from pyxle.runtime import server  # import the decorator

            @server
            async def loader(request):
                x = 1  # inline comment
                return {"x": x}

            import React from 'react';
            export default function Page() { return <div />; }
        """)
        assert "# import the decorator" in result.python_code
        assert "# inline comment" in result.python_code

    def test_python_dict_with_jsx_like_values(self):
        """Python dicts can have string values that look like JSX."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                return {
                    "title": "<h1>Hello</h1>",
                    "body": "<p>World</p>",
                }

            export default function Page({ data }) {
                return <div>{data.title}</div>;
            }
        """)
        assert '"<h1>Hello</h1>"' in result.python_code
        assert '"<p>World</p>"' in result.python_code

    def test_parenthesized_python_expression_not_split(self):
        """Multi-line parenthesized expressions stay together."""
        result = _parse("""
            from pyxle.runtime import server

            @server
            async def loader(request):
                result = (
                    some_function(
                        arg1,
                        arg2,
                    )
                )
                return {"data": result}

            import React from 'react';
            export default function Page() { return <div />; }
        """)
        assert "some_function(" in result.python_code
        assert "arg1," in result.python_code
