from __future__ import annotations

from textwrap import dedent

from pyxle_langkit.parser import PyxLanguageParser


def test_parser_tolerates_incomplete_python_blocks() -> None:
    parser = PyxLanguageParser()
    source = dedent(
        """
        @server
        async def loader(request):
            data = (1 + )

        export default function Page() {
            return <div>{data?.value}</div>;
        }
        """
    ).strip("\n")

    document = parser.parse_text(source, path="pages/index.pyx")

    assert document.has_python is True
    assert document.has_jsx is True
    # Loader cannot be detected because the Python block is incomplete, but the
    # segment map should still preserve line information for tooling.
    assert document.loader is None
    assert document.python_line_numbers[:3] == (1, 2, 3)
    assert document.jsx_line_numbers[0] == 5
