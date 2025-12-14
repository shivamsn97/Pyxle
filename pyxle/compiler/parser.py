"""Parser that splits `.pyx` files into Python and JSX segments."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .exceptions import CompilationError

_PYTHON_PREFIXES = (
    "import ",
    "from ",
    "def ",
    "async def ",
    "class ",
    "@",
    "if ",
    "with ",
    "for ",
    "while ",
    "try:",
    "except",
    "finally:",
)


@dataclass(frozen=True)
class LoaderDetails:
    name: str
    line_number: int
    is_async: bool
    parameters: Sequence[str]


@dataclass(frozen=True)
class PyxParseResult:
    python_code: str
    jsx_code: str
    loader: LoaderDetails | None
    python_line_numbers: Sequence[int]
    head_elements: tuple[str, ...]
    head_is_dynamic: bool


class PyxParser:
    """Split a `.pyx` source file into Python and JSX sections."""

    def parse(self, source_path: Path) -> PyxParseResult:
        text = source_path.read_text(encoding="utf-8")
        lines = self._normalize_newlines(text)

        python_lines: list[str] = []
        python_line_numbers: list[int] = []
        jsx_lines: list[str] = []

        mode: str = "auto"  # auto | python | jsx
        python_started = False
        indent_stack: list[int] = [0]
        expect_indent = False

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            toggle = self._detect_mode_toggle(stripped)
            if toggle:
                mode = toggle
                if mode == "python":
                    python_started = True
                    indent_stack = [0]
                    expect_indent = False
                else:
                    expect_indent = False
                continue

            indent = self._leading_spaces(line)

            if mode == "python":
                if self._is_probable_js(stripped, indent):
                    mode = "jsx"
                    expect_indent = False
                    jsx_lines.append(line)
                    continue
                expect_indent = self._update_python_indentation(
                    indent_stack,
                    indent,
                    stripped,
                    idx,
                    expect_indent,
                )
                python_lines.append(line)
                python_line_numbers.append(idx)
                continue

            if mode == "jsx":
                jsx_lines.append(line)
                continue

            # mode == auto
            if not stripped and not python_started:
                # Skip leading blank lines
                continue

            if self._is_probable_python(stripped, indent, python_started):
                python_lines.append(line)
                python_line_numbers.append(idx)
                python_started = True
                mode = "python"
                indent_stack = [indent] if indent > 0 else [0]
                expect_indent = self._line_expects_indent(stripped)
            else:
                mode = "jsx"
                jsx_lines.append(line)

        python_code = self._join_lines(python_lines)
        jsx_code = self._join_lines(jsx_lines)
        tree = self._parse_python_ast(python_code, python_line_numbers)
        loader = self._detect_loader(tree, python_line_numbers)
        head_elements, head_is_dynamic = self._collect_head_elements(
            tree,
            python_line_numbers,
        )

        return PyxParseResult(
            python_code=python_code,
            jsx_code=jsx_code,
            loader=loader,
            python_line_numbers=tuple(python_line_numbers),
            head_elements=head_elements,
            head_is_dynamic=head_is_dynamic,
        )

    def _parse_python_ast(
        self,
        python_code: str,
        python_line_numbers: Sequence[int],
    ) -> ast.Module | None:
        if not python_code.strip():
            return None

        try:
            return ast.parse(python_code, mode="exec", type_comments=True)
        except SyntaxError as exc:  # pragma: no cover - defensive
            line = self._map_lineno(exc.lineno, python_line_numbers)
            raise CompilationError(exc.msg, line) from exc

    def _update_python_indentation(
        self,
        indent_stack: list[int],
        indent: int,
        stripped: str,
        idx: int,
        expect_indent: bool,
    ) -> bool:
        if not stripped:
            return expect_indent

        current = indent_stack[-1]

        if indent > current:
            if not expect_indent:
                raise CompilationError("Unexpected indentation in Python block", idx)
            indent_stack.append(indent)
        else:
            while indent < indent_stack[-1]:
                indent_stack.pop()
                if not indent_stack:
                    indent_stack.append(0)
                    break
            if indent != indent_stack[-1]:
                raise CompilationError("Inconsistent indentation in Python block", idx)

        return self._line_expects_indent(stripped)

    @staticmethod
    def _line_opens_block(stripped: str) -> bool:
        code = stripped.split("#", 1)[0].rstrip()
        return bool(code) and code.endswith(":")

    @staticmethod
    def _line_expects_indent(stripped: str) -> bool:
        if PyxParser._line_opens_block(stripped):
            return True

        code = stripped.split("#", 1)[0].rstrip()
        if not code:
            return False

        return code.endswith("(") or code.endswith("[") or code.endswith("{")

    @staticmethod
    def _normalize_newlines(text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.split("\n")

    @staticmethod
    def _leading_spaces(line: str) -> int:
        i = 0
        for char in line:
            if char == " ":
                i += 1
            elif char == "\t":  # treat tabs as four spaces
                i += 4
            else:
                break
        return i

    @staticmethod
    def _detect_mode_toggle(stripped: str) -> str | None:
        if stripped.startswith("# ---"):
            lowered = stripped.lower()
            if "python" in lowered or "server" in lowered:
                return "python"
            if "javascript" in lowered or "client" in lowered:
                return "jsx"
        return None

    def _is_probable_python(self, stripped: str, indent: int, python_started: bool) -> bool:
        if not stripped:
            return python_started  # blank lines belong with python once started
        if stripped.startswith("#"):
            return True
        if indent > 0:
            return True
        if stripped.startswith(('"""', "'''")):
            return True
        for prefix in _PYTHON_PREFIXES:
            if stripped.startswith(prefix):
                if prefix == "import " and self._looks_like_js_import(stripped):
                    return False
                if prefix == "if " and not stripped.endswith(":"):
                    return False
                if prefix in {"with ", "for ", "while ", "try:", "except", "finally:"} and not stripped.endswith(":"):
                    return False
                return True
        if stripped.endswith(":") and stripped[0].isalpha():
            return True
        if "=" in stripped and not stripped.rstrip().endswith(";"):
            left, _ = stripped.split("=", 1)
            identifier = left.strip()
            if identifier.isidentifier():
                return True
        return False

    def _is_probable_js(self, stripped: str, indent: int) -> bool:
        if indent > 0:
            return False
        if not stripped:
            return False
        lowered = stripped.lower()
        if stripped.startswith("export "):
            return True
        if stripped.startswith(("const ", "let ", "var ", "function ", "async function ", "import type ", "type ", "interface ")):
            return True
        if stripped.startswith("return ") and stripped.endswith(";"):
            return True
        if stripped.startswith("<"):
            return True
        if stripped.startswith("//") or stripped.startswith("/*"):
            return True
        if stripped.startswith("import ") and self._looks_like_js_import(stripped):
            return True
        if stripped.endswith(";"):
            return True
        if lowered.startswith("await "):
            return True
        return False

    @staticmethod
    def _looks_like_js_import(line: str) -> bool:
        if " from " in line and ("'" in line or '"' in line):
            return True
        if line.endswith(";"):
            return True
        if "{" in line or "}" in line:
            return True
        if line.startswith("import type "):
            return True
        return False

    @staticmethod
    def _join_lines(lines: Iterable[str]) -> str:
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def _detect_loader(
        self,
        tree: ast.Module | None,
        python_line_numbers: Sequence[int],
    ) -> LoaderDetails | None:
        if tree is None:
            return None

        loader_node: ast.AsyncFunctionDef | None = None

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and self._has_server_decorator(node.decorator_list):
                line = self._map_lineno(node.lineno, python_line_numbers)
                raise CompilationError("@server loader must be declared as async", line)

            if isinstance(node, ast.ClassDef) and self._has_server_decorator(node.decorator_list):
                line = self._map_lineno(node.lineno, python_line_numbers)
                raise CompilationError("@server decorator can only be applied to functions", line)

            if isinstance(node, ast.AsyncFunctionDef) and self._has_server_decorator(node.decorator_list):
                if loader_node is not None:
                    line = self._map_lineno(node.lineno, python_line_numbers)
                    raise CompilationError("Multiple @server loaders detected", line)
                loader_node = node

        if loader_node is None:
            return None

        if loader_node.col_offset != 0:
            line = self._map_lineno(loader_node.lineno, python_line_numbers)
            raise CompilationError("@server loader must be defined at module scope", line)

        if not loader_node.args.args:
            line = self._map_lineno(loader_node.lineno, python_line_numbers)
            raise CompilationError("@server loader must accept a `request` argument", line)

        first_arg = loader_node.args.args[0].arg
        if first_arg != "request":
            line = self._map_lineno(loader_node.lineno, python_line_numbers)
            raise CompilationError("First argument of @server loader must be named 'request'", line)

        parameters = tuple(arg.arg for arg in loader_node.args.args)
        line = self._map_lineno(loader_node.lineno, python_line_numbers)
        return LoaderDetails(
            name=loader_node.name,
            line_number=line,
            is_async=True,
            parameters=parameters,
        )

    def _collect_head_elements(
        self,
        tree: ast.Module | None,
        python_line_numbers: Sequence[int],
    ) -> tuple[tuple[str, ...], bool]:
        if tree is None:
            return tuple(), False

        elements: list[str] = []
        head_is_dynamic = False

        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue

            if not any(isinstance(target, ast.Name) and target.id == "HEAD" for target in node.targets):
                continue

            line = self._map_lineno(node.lineno, python_line_numbers)
            literal = self._extract_head_literal(node.value, line)
            if literal is None:
                elements = []
                head_is_dynamic = True
                continue

            elements = literal
            head_is_dynamic = False

        return tuple(elements), head_is_dynamic

    def _extract_head_literal(self, value: ast.AST, line: int | None) -> list[str] | None:
        """Return literal HEAD entries or ``None`` when the assignment is dynamic."""

        if isinstance(value, ast.Constant):
            literal = value.value
            if literal is None:
                return []
            if isinstance(literal, str):
                return [literal]
            raise CompilationError("HEAD must be assigned a string or list of strings", line)

        if isinstance(value, (ast.List, ast.Tuple)):
            normalized: list[str] = []
            for element in value.elts:
                if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                    return None
                normalized.append(element.value)
            return normalized

        return None

    @staticmethod
    def _map_lineno(lineno: int | None, python_line_numbers: Sequence[int]) -> int | None:
        if lineno is None or lineno < 1:
            return lineno
        if not python_line_numbers:
            return lineno
        index = min(lineno - 1, len(python_line_numbers) - 1)
        return python_line_numbers[index]

    @staticmethod
    def _has_server_decorator(decorators: Sequence[ast.expr]) -> bool:
        for deco in decorators:
            target = deco
            if isinstance(deco, ast.Call):
                target = deco.func
            if isinstance(target, ast.Name) and target.id == "server":
                return True
            if isinstance(target, ast.Attribute) and target.attr == "server":
                return True
        return False
