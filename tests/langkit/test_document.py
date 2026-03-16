from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from pyxle.compiler.parser import LoaderDetails
from pyxle_langkit.document import PyxDocument


def _doc(python: str, jsx: str = "", *, python_lines: tuple[int, ...] | None = None) -> PyxDocument:
    loader = LoaderDetails(name="loader", line_number=3, is_async=True, parameters=("request",))
    python_line_numbers = python_lines or tuple(range(1, len(python.splitlines()) + 1))
    return PyxDocument(
        path=Path("pages/index.pyx"),
        python_code=python,
        python_line_numbers=python_line_numbers,
        jsx_code=jsx,
        jsx_line_numbers=tuple(range(1, len(jsx.splitlines()) + 1)),
        loader=loader,
        head_elements=(),
        head_is_dynamic=False,
    )


def test_editor_python_segments_injects_runtime_import() -> None:
    python = dedent(
        """
        @server
        async def loader(request):
            return {"value": 1}
        """
    ).strip("\n")
    document = _doc(python)

    code, mapping = document.editor_python_segments()

    assert code.splitlines()[0] == "from pyxle.runtime import server"
    assert len(mapping) == len(code.splitlines())
    assert mapping[0] == 0  # synthetic helper import has no source line
    assert mapping[1] == 1


def test_editor_jsx_segments_rewrite_pyx_imports() -> None:
    jsx = "import Layout from './layout.pyx';\nexport default function Page() { return <Layout />; }"
    document = _doc("", jsx)

    code, mapping = document.editor_jsx_segments()

    assert "./layout.jsx" in code
    assert mapping == tuple(range(1, len(jsx.splitlines()) + 1))
