from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from pyxle.compiler import writers as compiler_writers
from pyxle.compiler.core import compile_file
from pyxle.compiler.exceptions import CompilationError
from pyxle.compiler.model import CompilationResult, PageMetadata


def write(tmp_path: Path, relative: str, content: str) -> Path:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_compile_dynamic_route_emits_artifacts(tmp_path: Path) -> None:
    content = dedent(
        """
        import httpx

        @server
        async def get_post(request):
            post_id = request.params.get("id")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://example.com/{post_id}")
                response.raise_for_status()
                return response.json()

        import React from 'react';

        export default function PostPage({ data }) {
            return <article>{data.title}</article>;
        }
        """
    )

    source = write(tmp_path, "project/pages/posts/[id].pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    assert result.metadata.route_path == "/posts/{id}"
    assert result.metadata.loader_name == "get_post"
    assert result.metadata.loader_line is not None

    server_file = build_root / "server/pages/posts/[id].py"
    client_file = build_root / "client/pages/posts/[id].jsx"
    metadata_file = build_root / "metadata/pages/posts/[id].json"

    assert server_file.exists()
    assert client_file.exists()
    assert metadata_file.exists()

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["route_path"] == "/posts/{id}"
    assert metadata["loader_name"] == "get_post"
    assert metadata["client_path"] == "/pages/posts/[id].jsx"
    assert metadata["server_path"] == "/pages/posts/[id].py"
    assert metadata["head"] == []
    assert "Compiled [id].pyx" in result.summary()


def test_compile_optional_catchall_adds_alias_route(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "project/pages/docs/[[...slug]].pyx",
        """import React from 'react';\n\nexport default function Docs() {\n    return <div>Docs</div>;\n}\n""",
    )
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    assert result.metadata.route_path == "/docs"
    assert result.metadata.alternate_route_paths == ("/docs/{slug:path}",)

    payload = json.loads(
        (build_root / "metadata/pages/docs/[[...slug]].json").read_text(encoding="utf-8")
    )
    assert payload["route_path"] == "/docs"
    assert payload["alternate_route_paths"] == ["/docs/{slug:path}"]


def test_compile_injects_runtime_server_import(tmp_path: Path) -> None:
    content = dedent(
        """


        @server
        async def loader(request):
            return {"answer": 42}
        """
    )

    source = write(tmp_path, "project/pages/demo.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_text = result.server_output.read_text(encoding="utf-8").splitlines()
    assert "from pyxle.runtime import server" in server_text
    server_index = server_text.index("from pyxle.runtime import server")
    decorator_index = next(i for i, line in enumerate(server_text) if line.strip().startswith("@server"))
    assert server_index < decorator_index


def test_compile_respects_user_defined_server_decorator(tmp_path: Path) -> None:
    content = dedent(
        """
        def server(fn):
            return fn


        @server
        async def loader(request):
            return {"answer": 42}
        """
    )

    source = write(tmp_path, "project/pages/custom.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_text = result.server_output.read_text(encoding="utf-8")
    assert "from pyxle.runtime import server" not in server_text


def test_compile_injects_import_after_docstring(tmp_path: Path) -> None:
    content = dedent(
        '''
        """Demo docstring."""

        @server
        async def loader(request):
            return {"answer": 42}
        

        export default function Component() {
            return null;
        }
        '''
    )

    source = write(tmp_path, "project/pages/doc.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_lines = result.server_output.read_text(encoding="utf-8").splitlines()
    non_empty = [line for line in server_lines if line.strip()]
    assert non_empty[0] == '"""Demo docstring."""'
    assert non_empty[1] == "from pyxle.runtime import server"


def test_compile_preserves_existing_server_import(tmp_path: Path) -> None:
    content = dedent(
        """
        from pyxle.runtime import server


        @server
        async def loader(request):
            return {"answer": 42}
        """
    )

    source = write(tmp_path, "project/pages/imported.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_text = result.server_output.read_text(encoding="utf-8")
    assert server_text.count("from pyxle.runtime import server") == 1


def test_compile_respects_server_assignment(tmp_path: Path) -> None:
    content = dedent(
        """
        from functools import wraps
        from typing import Any, Callable

        def _capture(fn):
            @wraps(fn)
            async def inner(*args, **kwargs):
                return await fn(*args, **kwargs)

            return inner


        server: Callable[[Any], Any] = _capture


        @server
        async def loader(request):
            return {"answer": 42}
        """
    )

    source = write(tmp_path, "project/pages/assigned.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_text = result.server_output.read_text(encoding="utf-8")
    assert server_text.count("from pyxle.runtime import server") == 0


def test_compile_respects_server_import_alias(tmp_path: Path) -> None:
    content = dedent(
        """
        import math as server


        @server
        async def loader(request):
            return {"answer": 42}
        """
    )

    source = write(tmp_path, "project/pages/alias.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    server_text = result.server_output.read_text(encoding="utf-8")
    assert "from pyxle.runtime import server" not in server_text


def test_ensure_server_import_ignores_whitespace_only_source() -> None:
    assert compiler_writers.ensure_server_import("   \n") == "   \n"


def test_ensure_server_import_handles_parse_failure_with_leading_blanks() -> None:
    raw_source = "\n \n@@"
    result = compiler_writers.ensure_server_import(raw_source)
    lines = result.splitlines()
    assert lines[2] == "from pyxle.runtime import server"


def test_ensure_server_import_follows_future_imports() -> None:
    source = dedent(
        """
        from __future__ import annotations

        value = 1
        """
    ).lstrip("\n")

    result = compiler_writers.ensure_server_import(source)
    lines = result.splitlines()

    assert lines[0] == "from __future__ import annotations"
    assert lines[1] == "from pyxle.runtime import server"
    assert lines[2] == ""
    assert lines[3] == "value = 1"


def test_ensure_server_import_handles_docstring_and_future() -> None:
    source = dedent(
        '''
        """Example module."""

        from __future__ import annotations

        answer = 42
        '''
    ).lstrip("\n")

    result = compiler_writers.ensure_server_import(source)
    lines = result.splitlines()

    assert lines[0] == '"""Example module."""'
    assert lines[1] == ""
    assert lines[2] == "from __future__ import annotations"
    assert lines[3] == "from pyxle.runtime import server"
    assert lines[4] == ""
    assert lines[5] == "answer = 42"


def test_ensure_server_import_reports_insert_position() -> None:
    source = dedent(
        '''
        """Example."""

        value = 1
        '''
    ).lstrip("\n")

    result, index = compiler_writers.ensure_server_import(source, return_insert_position=True)
    assert "from pyxle.runtime import server" in result
    assert index == 1


def test_compile_persists_head_elements(tmp_path: Path) -> None:
    content = dedent(
        """
        HEAD = [
            "<title>Meta</title>",
            '<link rel="icon" href="/favicon.ico" />',
        ]

        # --- JavaScript/PSX ---
        import React from 'react';

        export default function MetaPage() {
            return <span>Meta</span>;
        }
        """
    )

    source = write(tmp_path, "project/pages/meta.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    assert result.metadata.head_elements == (
        "<title>Meta</title>",
        '<link rel="icon" href="/favicon.ico" />',
    )
    assert result.metadata.head_is_dynamic is False

    metadata_file = build_root / "metadata/pages/meta.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert payload["head"] == [
        "<title>Meta</title>",
        '<link rel="icon" href="/favicon.ico" />',
    ]
    assert payload["head_dynamic"] is False


def test_compile_marks_dynamic_head(tmp_path: Path) -> None:
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

    source = write(tmp_path, "project/pages/dynamic.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    assert result.metadata.head_elements == ()
    assert result.metadata.head_is_dynamic is True

    metadata_file = build_root / "metadata/pages/dynamic.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert payload["head"] == []
    assert payload["head_dynamic"] is True


def test_compile_static_page_uses_stub(tmp_path: Path) -> None:
    content = dedent(
        """
        import React from 'react';

        export default function Landing() {
            return <main>Landing</main>;
        }
        """
    )

    source = write(tmp_path, "project/pages/index.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    assert result.metadata.route_path == "/"
    assert result.metadata.loader_name is None

    server_text = result.server_output.read_text(encoding="utf-8")
    assert "Generated by Pyxle" in server_text

    client_text = result.client_output.read_text(encoding="utf-8")
    assert "Landing" in client_text


def test_compile_rewrites_pyx_imports_in_client_output(tmp_path: Path) -> None:
    content = dedent(
        """
        import React from 'react';

        import Layout from './layout.pyx';
        import { Hero } from '../components/hero.pyx';
        export { Footer } from '../components/footer.pyx';

        const Lazy = React.lazy(() => import('../chunks/hero.pyx'));
        const Skip = import(condition ? '../chunks/skip.pyx' : '../chunks/unused.pyx');

        export default function Page() {
            return (
                <div>
                    <Layout />
                    <Hero />
                </div>
            );
        }
        """
    )

    source = write(tmp_path, "project/pages/index.pyx", content)
    build_root = tmp_path / "project/.pyxle-build"

    result = compile_file(source, build_root=build_root)

    client_text = result.client_output.read_text(encoding="utf-8")
    assert "./layout.jsx" in client_text
    assert "../components/hero.jsx" in client_text
    assert "../chunks/hero.jsx" in client_text
    # Conditional dynamic import should not change because the specifier isn't a literal.
    assert "../chunks/skip.pyx" in client_text


def test_compile_rejects_non_pyx_files(tmp_path: Path) -> None:
    source = write(tmp_path, "project/pages/index.jsx", "console.log('hi');")
    build_root = tmp_path / "project/.pyxle-build"

    with pytest.raises(CompilationError) as excinfo:
        compile_file(source, build_root=build_root)

    assert "Only `.pyx`" in str(excinfo.value)


def test_compile_requires_pages_directory(tmp_path: Path) -> None:
    source = write(tmp_path, "project/index.pyx", "export default function Demo() { return <div />; }")
    build_root = tmp_path / "project/.pyxle-build"

    with pytest.raises(CompilationError) as excinfo:
        compile_file(source, build_root=build_root)

    assert "pages" in str(excinfo.value)


def test_compilation_result_validates_output_paths(tmp_path: Path) -> None:
    metadata = PageMetadata(
        route_path="/demo",
        alternate_route_paths=(),
        client_path="/pages/demo.jsx",
        server_path="/pages/demo.py",
        loader_name=None,
        loader_line=None,
        head_elements=(),
        head_is_dynamic=False,
    )

    with pytest.raises(ValueError):
        CompilationResult(
            source_path=tmp_path / "pages/demo.pyx",
            python_code="",
            jsx_code="",
            server_output=tmp_path,  # directory
            client_output=tmp_path / "client/demo.jsx",
            metadata_output=tmp_path / "metadata/demo.json",
            metadata=metadata,
        )


def test_page_metadata_helpers() -> None:
    metadata = PageMetadata(
        route_path="/demo",
        alternate_route_paths=(),
        client_path="/pages/demo.jsx",
        server_path="/pages/demo.py",
        loader_name="loader",
        loader_line=5,
        head_elements=("<title>Demo</title>",),
        head_is_dynamic=False,
    )

    assert metadata.has_loader is True
    payload = metadata.to_json()
    assert payload["loader_line"] == 5
    assert payload["head"] == ["<title>Demo</title>"]
    assert payload["head_dynamic"] is False