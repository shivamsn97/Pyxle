from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

import pytest

from pyxle.compiler.exceptions import CompilationError
from pyxle.compiler.parser import PyxParser


def write(tmp_path: Path, relative: str, content: str) -> Path:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_parse_static_page(tmp_path: Path) -> None:
    content = dedent(
        """
        import React from 'react';

        export default function About() {
            return <div>About</div>;
        }
        """
    ).strip("\n")

    source = write(tmp_path, "pages/about.pyx", content)

    result = PyxParser().parse(source)

    assert result.python_code == ""
    assert "About" in result.jsx_code
    assert result.loader is None
    assert result.python_line_numbers == ()
    assert result.head_elements == ()


def test_parse_text_round_trip(tmp_path: Path) -> None:
    source_text = dedent(
        """
        import React from 'react';

        export default function About() {
            return <div>About</div>;
        }
        """
    ).strip("\n")

    source_path = write(tmp_path, "pages/about.pyx", source_text)
    parser = PyxParser()

    from_disk = parser.parse(source_path)
    in_memory = parser.parse_text(source_text)

    assert in_memory.python_code == from_disk.python_code
    assert in_memory.jsx_code == from_disk.jsx_code
    assert in_memory.loader == from_disk.loader


def test_parse_loader_detection(tmp_path: Path) -> None:
    content = "\n".join(
        [
            "import random",
            "",
            "@server",
            "async def get_lucky(request):",
            "    number = random.randint(1, 10)",
            "    return {\"number\": number}",
            "",
            "import React from 'react';",
            "",
            "export default function Page({ data }) {",
            "    return <span>{data.number}</span>;",
            "}",
            "",
        ]
    )

    source = write(tmp_path, "pages/index.pyx", content)
    result = PyxParser().parse(source)

    assert result.loader is not None
    assert result.loader.name == "get_lucky"
    assert result.loader.line_number == 4
    assert result.python_code.startswith("import random")
    assert "return <span>" in result.jsx_code
    assert result.head_elements == ()


def test_parse_non_async_loader_raises(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        def bad_loader(request):
            return {}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/bad.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "async" in str(excinfo.value)


def test_parse_multiple_loaders_raises(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        async def first(request):
            return {}

        @server
        async def second(request):
            return {}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/multi.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "Multiple" in str(excinfo.value)


def test_parse_nested_loader_not_allowed(tmp_path: Path) -> None:
    content = dedent(
        """
        async def outer():
            @server
            async def inner(request):
                return {}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/nested.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "module scope" in str(excinfo.value)


def test_parse_windows_newlines_normalized(tmp_path: Path) -> None:
    base = dedent(
        """
        @server
        async def loader(request):
            return {"hello": "world"}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/windows.pyx", base)
    result = PyxParser().parse(source)

    assert "\r" not in result.python_code
    assert "\r" not in result.jsx_code


def test_parse_nested_blocks_and_decorators(tmp_path: Path) -> None:
    content = dedent(
        """
        
        import httpx

        def log(message):
            return message.upper()

        def decorator(fn):
            return fn

        @decorator
        @server
        async def fetch_post(request):
            post_id = request.params.get("id")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://example.com/{post_id}")
                if response.status_code == 404:
                    return {"error": log("missing")}, 404
                return response.json()

        # --- JavaScript/PSX ---
        import React from 'react';

        export default function Post({ data }) {
            return <article>{data.title}</article>;
        }
        """
    )

    source = write(tmp_path, "pages/posts/[id].pyx", content)
    result = PyxParser().parse(source)

    assert result.loader is not None
    assert result.loader.name == "fetch_post"
    assert any("async with httpx.AsyncClient" in line for line in result.python_code.splitlines())
    assert any("return {\"error\"" in line for line in result.python_code.splitlines())
    assert result.loader.line_number == 13
    assert result.head_elements == ()


def test_parse_tuple_return_loaders_supported(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        async def loader(request):
            data = {"status": "ok"}
            return data, 201

        export default function Demo({ data }) {
            return <div>{data.status}</div>;
        }
        """
    )

    source = write(tmp_path, "pages/tuple.pyx", content)
    result = PyxParser().parse(source)

    assert result.loader is not None
    assert "return data, 201" in result.python_code
    assert result.head_elements == ()


def test_parse_allows_interleaved_python_and_js_sections(tmp_path: Path) -> None:
    content = dedent(
        """
        from __future__ import annotations

        import React, { useEffect, useState } from 'react';
        import { Link } from 'pyxle/client';

        HEAD = "<title>Mixed</title>"

        @server
        async def load_home(request):
            return {"message": "hello"}

        const THEME_KEY = 'pyxle-theme-preference';

        def helper():
            return "extra"

        export default function Page({ data }) {
            return (
                <div>
                    <Link href="/">Hello {data.message}</Link>
                </div>
            );
        }
        """
    ).strip("\n")

    source = write(tmp_path, "pages/mixed.pyx", content)
    result = PyxParser().parse(source)

    assert result.loader is not None
    assert result.loader.name == "load_home"
    assert "const THEME_KEY" in result.jsx_code
    assert "import React" in result.jsx_code
    assert "def helper" in result.python_code
    assert "HEAD =" in result.python_code
    assert "export default function Page" in result.jsx_code
    assert result.head_elements == ("<title>Mixed</title>",)


def test_parse_python_multiline_string_with_js_content(tmp_path: Path) -> None:
    content = dedent(
        """
        test = (" \\
        import React, { useEffect, useState } from 'react'; \\
        const VALUE = 1; \\
        ")

        export default function Demo() {
            return <div />;
        }
        """
    ).lstrip("\n")

    source = write(tmp_path, "pages/stringy.pyx", content)
    result = PyxParser().parse(source)

    assert "import React, { useEffect, useState } from 'react';" in result.python_code
    assert "const VALUE = 1;" in result.python_code
    assert "import React, { useEffect, useState } from 'react';" not in result.jsx_code
    assert "export default function Demo" in result.jsx_code


def test_parse_python_line_continuation_not_treated_as_js(tmp_path: Path) -> None:
    content = dedent(
        """
        value = 1 + \\
            2

        export default function Demo() {
            return <div />;
        }
        """
    ).lstrip("\n")

    source = write(tmp_path, "pages/continuation.pyx", content)
    result = PyxParser().parse(source)

    assert "value = 1 +" in result.python_code
    assert "2" in result.python_code
    assert "export default function Demo" in result.jsx_code


def test_parse_inconsistent_indentation_raises(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        async def loader(request):
            value = 1
                return value

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/bad_indent.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "unexpected" in str(excinfo.value).lower()


def test_parse_inconsistent_dedent_raises(tmp_path: Path) -> None:
    content = "\n".join(
        [
            "@server",
            "async def loader(request):",
            "    if request:",
            "        value = 1",
            "   return {'value': value}",
            "",
            "export default function Demo() {",
            "    return <div />;",
            "}",
            "",
        ]
    )

    source = write(tmp_path, "pages/bad_dedent.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "inconsistent" in str(excinfo.value).lower()


def test_parser_helper_methods_cover_branches() -> None:
    parser = PyxParser()

    # Mode toggles
    assert parser._detect_mode_toggle("") is None
    assert parser._detect_mode_toggle("# --- Client Bundle ---") == "jsx"
    assert parser._detect_mode_toggle("# regular comment") is None
    assert parser._detect_mode_toggle("# --- Notes ---") is None

    # Indentation tracking
    indent_stack = [0]
    expect = parser._update_python_indentation(indent_stack, 0, "async def loader():", 1, False, False)
    assert expect is True
    expect = parser._update_python_indentation(indent_stack, 4, "    return {}", 2, True, False)
    assert expect is False
    # Blank line short-circuit
    assert parser._update_python_indentation(indent_stack, 4, "", 3, False, False) is False
    # Dedent restoring stack with default zero
    temp_stack = [4]
    expect = parser._update_python_indentation(temp_stack, 0, "return {}", 4, False, False)
    assert expect is False
    # Continuation indent allowance
    expect = parser._update_python_indentation(indent_stack, 8, "        42", 5, False, True)
    assert expect is False

    # Python heuristics
    assert parser._is_probable_python("if ready:", 0, False) is True
    assert parser._is_probable_python("with open(path):", 0, False) is True
    assert parser._is_probable_python("# comment", 0, False) is True
    assert parser._is_probable_python("", 0, False) is False
    assert parser._is_probable_python("if invalid", 0, False) is False
    assert parser._is_probable_python("import React from 'react';", 0, False) is False
    assert parser._is_probable_python("value = 1", 4, False) is True
    assert parser._is_probable_python("value = 1", 0, False) is True
    assert parser._is_probable_python("for item in items", 0, False) is False
    assert parser._is_probable_python("Else:", 0, False) is True
    assert parser._is_probable_python("value-with-hyphen = 1", 0, False) is False

    # JavaScript heuristics
    assert parser._is_probable_js("export default function Foo() {}", 0) is True
    assert parser._is_probable_js("const value = 1;", 0) is True
    assert parser._is_probable_js("return value;", 0) is True
    assert parser._is_probable_js("<div />", 0) is True
    assert parser._is_probable_js("// comment", 0) is True
    assert parser._is_probable_js("import { useState } from 'react';", 0) is True
    assert parser._is_probable_js("await fetch('/api')", 0) is True
    assert parser._is_probable_js("value", 1) is False
    assert parser._is_probable_js("value;", 0) is True
    assert parser._is_probable_js("", 0) is False

    # Import detection helper
    assert parser._looks_like_js_import("import type { Foo } from './foo';") is True
    assert parser._looks_like_js_import("import styles from './foo.css';") is True
    assert parser._looks_like_js_import("import util") is False
    assert parser._looks_like_js_import("import styles;") is True
    assert parser._looks_like_js_import("import {thing}") is True
    assert parser._looks_like_js_import("importmodule") is False
    assert parser._looks_like_js_import("import type Foo") is True

    # Misc helpers
    assert parser._line_opens_block("for item in items:") is True
    assert parser._line_opens_block("value = 1") is False
    assert parser._line_expects_indent("# comment") is False
    assert parser._leading_spaces("  \tindent") == 6
    assert parser._normalize_newlines("line1\r\nline2\rline3") == ["line1", "line2", "line3"]
    assert parser._detect_mode_toggle("# --- JavaScript Section ---") == "jsx"

    # Line number mapping
    assert parser._map_lineno(2, (10, 20, 30)) == 20
    assert parser._map_lineno(5, (10, 20, 30)) == 30
    assert parser._map_lineno(3, ()) == 3
    assert parser._map_lineno(None, ()) is None

    # Decorator detection
    decorators = [ast.Name(id="server")]
    assert parser._has_server_decorator(decorators) is True
    decorators_attr = [ast.Attribute(value=ast.Name(id="loader"), attr="server")]
    assert parser._has_server_decorator(decorators_attr) is True
    decorators_call = [ast.Call(func=ast.Name(id="server"), args=[], keywords=[])]
    assert parser._has_server_decorator(decorators_call) is True
    assert parser._has_server_decorator([]) is False

    # Expression state helper edge cases
    triple_match = parser._match_prefixed_string("r'''value", 0)
    assert triple_match is not None
    tracker, literal_index = triple_match
    assert tracker.triple is True
    idx, string_state = parser._consume_python_string("value'''rest", literal_index, tracker)
    assert idx == len("value'''")
    assert string_state is None
    string_state, paren_depth, _, _, line_cont = parser._update_python_expression_state(
        "value = (",
        None,
        0,
        0,
        0,
    )
    assert string_state is None
    assert paren_depth == 1
    assert line_cont is False
    string_state, _, _, _, line_cont = parser._update_python_expression_state(
        "continued \\",
        None,
        0,
        0,
        0,
    )
    assert string_state is None
    assert line_cont is True
    # Comments short-circuit expression scanning
    string_state, _, _, _, _ = parser._update_python_expression_state(
        "# comment",
        None,
        0,
        0,
        0,
    )
    assert string_state is None
    # Prefixed triple-quoted strings transition into tracked state
    string_state, _, _, _, _ = parser._update_python_expression_state(
        'r"""unterminated',
        None,
        0,
        0,
        0,
    )
    assert string_state is not None
    assert string_state.triple is True


def test_parse_server_decorator_on_class_raises(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        class Handler:
            pass

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/class.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "functions" in str(excinfo.value)


def test_parse_loader_requires_request_argument(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        async def loader():
            return {}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/no_request.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "request" in str(excinfo.value)


def test_parse_loader_requires_request_name(tmp_path: Path) -> None:
    content = dedent(
        """
        @server
        async def loader(req):
            return {}

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/bad_request_name.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "First argument" in str(excinfo.value)


def test_parse_python_helpers_without_loader(tmp_path: Path) -> None:
    content = dedent(
        """
        def helper():
            return "ok"

        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/helper_only.pyx", content)
    result = PyxParser().parse(source)

    assert result.loader is None
    assert "helper" in result.python_code
    assert result.head_elements == ()


def test_parse_head_elements_from_literal(tmp_path: Path) -> None:
    content = dedent(
        """
        
        HEAD = [
            "<title>Custom</title>",
            '<meta name="description" content="Demo" />',
        ]

        @server
        async def loader(request):
            return {}

        # --- JavaScript/PSX ---
        import React from 'react';

        export default function Demo({ data }) {
            return <div>{data.message}</div>;
        }
        """
    )

    source = write(tmp_path, "pages/meta.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == (
        "<title>Custom</title>",
        '<meta name="description" content="Demo" />',
    )
    assert result.head_is_dynamic is False


def test_parse_preserves_multiline_triple_quoted_python(tmp_path: Path) -> None:
    content = dedent(
        '''
        HEAD = """
        <title>Example</title>
        <meta name="description" content="Example" />
        """

        @server
        async def loader(request):
            message = """
            Hello from Pyxle
            """
            return {"message": message}

        # --- JavaScript/PSX ---
        export default function Demo({ data }) {
            return <div>{data.message}</div>;
        }
        '''
    )

    source = write(tmp_path, "pages/multiline.pyx", content)
    result = PyxParser().parse(source)

    assert '<title>Example</title>' in result.python_code
    assert 'message = """' in result.python_code
    assert "Hello from Pyxle" in result.python_code
    assert "return <div>" in result.jsx_code
    assert result.loader is not None


def test_parse_head_none_returns_empty_literal(tmp_path: Path) -> None:
    content = dedent(
        """
        HEAD = None

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/head_none.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ()
    assert result.head_is_dynamic is False


def test_parse_head_tuple_literal(tmp_path: Path) -> None:
    content = dedent(
        """
        HEAD = ("<title>Tuple</title>",)

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/head_tuple.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ("<title>Tuple</title>",)
    assert result.head_is_dynamic is False


def test_parse_marks_head_dynamic_when_expression(tmp_path: Path) -> None:
    content = dedent(
        """
        from pages.components import build_head

        HEAD = build_head(title="Dynamic", description="Demo")

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/dynamic_head.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ()
    assert result.head_is_dynamic is True


def test_parse_head_list_with_non_string_marks_dynamic(tmp_path: Path) -> None:
    content = dedent(
        """
        HEAD = [
            "<title>Demo</title>",
            123,
        ]

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/head_mixed.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ()
    assert result.head_is_dynamic is True


def test_parse_head_function_marks_dynamic(tmp_path: Path) -> None:
    content = dedent(
        """
        def HEAD(data):
            return "<title>Callable</title>"

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/head_function.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ()
    assert result.head_is_dynamic is True


def test_parse_head_skips_other_assignments(tmp_path: Path) -> None:
    content = dedent(
        """
        TITLE = "<title>Ignored</title>"
        HEAD = "<title>Chosen</title>"

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/head_with_title.pyx", content)
    result = PyxParser().parse(source)

    assert result.head_elements == ("<title>Chosen</title>",)
    assert result.head_is_dynamic is False


def test_parse_head_elements_invalid_type_raises(tmp_path: Path) -> None:
    content = dedent(
        """
        
        HEAD = 123

        # --- JavaScript/PSX ---
        export default function Demo() {
            return <div />;
        }
        """
    )

    source = write(tmp_path, "pages/invalid_head.pyx", content)

    with pytest.raises(CompilationError) as excinfo:
        PyxParser().parse(source)

    assert "HEAD" in str(excinfo.value)