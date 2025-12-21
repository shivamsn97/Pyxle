"""Parser that splits `.pyx` files into Python and JSX segments."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

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

_STRING_PREFIX_CHARS = frozenset("rRuUfFbB")


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
    jsx_line_numbers: Sequence[int]
    head_elements: tuple[str, ...]
    head_is_dynamic: bool


@dataclass(slots=True)
class _LineNode:
    number: int
    text: str


@dataclass(slots=True)
class _SegmentNode:
    kind: Literal["python", "jsx"]
    lines: list[_LineNode]

    def append(self, *, number: int, text: str) -> None:
        self.lines.append(_LineNode(number=number, text=text))


@dataclass(slots=True)
class _StringTracker:
    delimiter: str
    triple: bool


@dataclass(slots=True)
class _DocumentNode:
    segments: list[_SegmentNode]


class PyxParser:
    """Split a `.pyx` source file into Python and JSX sections."""

    def parse(self, source_path: Path, *, tolerant: bool = False) -> PyxParseResult:
        text = source_path.read_text(encoding="utf-8")
        lines = self._normalize_newlines(text)
        return self._parse_from_lines(lines, tolerant=tolerant)

    def parse_text(self, text: str, *, tolerant: bool = False) -> PyxParseResult:
        """Parse raw `.pyx` content without reading from disk."""

        lines = self._normalize_newlines(text)
        return self._parse_from_lines(lines, tolerant=tolerant)

    def _parse_from_lines(self, lines: Sequence[str], *, tolerant: bool = False) -> PyxParseResult:
        document = self._build_document(lines)

        python_lines: list[str] = []
        python_line_numbers: list[int] = []
        jsx_lines: list[str] = []
        jsx_line_numbers: list[int] = []

        for segment in document.segments:
            if segment.kind == "python":
                for entry in segment.lines:
                    python_lines.append(entry.text)
                    python_line_numbers.append(entry.number)
            else:
                for entry in segment.lines:
                    jsx_lines.append(entry.text)
                    jsx_line_numbers.append(entry.number)

        python_code = self._join_lines(python_lines)
        jsx_code = self._join_lines(jsx_lines)
        tree = self._parse_python_ast(python_code, python_line_numbers, tolerant=tolerant)
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
            jsx_line_numbers=tuple(jsx_line_numbers),
            head_elements=head_elements,
            head_is_dynamic=head_is_dynamic,
        )

    def _build_document(self, lines: Sequence[str]) -> _DocumentNode:
        document = _DocumentNode(segments=[])
        current_segment: _SegmentNode | None = None
        python_state = _PythonState(parser=self)
        python_started = False
        mode: str = "auto"

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            toggle = self._detect_mode_toggle(stripped)
            if toggle:
                mode = toggle
                if toggle == "python":
                    python_started = True
                python_state.reset_for_new_segment()
                current_segment = None
                continue

            indent = self._leading_spaces(line)
            classification, mode = self._classify_line(
                stripped=stripped,
                indent=indent,
                python_started=python_started,
                mode=mode,
                python_state=python_state,
            )

            if classification is None:
                continue

            if classification == "python":
                python_started = True

            if current_segment is None or current_segment.kind != classification:
                if classification == "python":
                    python_state.reset_for_new_segment()
                current_segment = _SegmentNode(kind=classification, lines=[])
                document.segments.append(current_segment)

            current_segment.append(number=idx, text=line)

            if classification == "python":
                python_state.advance(
                    line=line,
                    stripped=stripped,
                    indent=indent,
                    line_number=idx,
                )

        return document

    def _classify_line(
        self,
        *,
        stripped: str,
        indent: int,
        python_started: bool,
        mode: str,
        python_state: _PythonState,
    ) -> tuple[str | None, str]:
        if mode == "python":
            if self._should_switch_to_js(stripped, indent, python_state):
                return "jsx", "jsx"
            return "python", "python"

        if mode == "jsx":
            if self._should_switch_to_python(stripped, indent):
                return "python", "python"
            return "jsx", "jsx"

        # mode == auto
        if not stripped and not python_started:
            return None, "auto"

        if self._is_probable_python(stripped, indent, python_started):
            return "python", "python"

        return "jsx", "jsx"

    def _should_switch_to_js(
        self,
        stripped: str,
        indent: int,
        python_state: _PythonState,
    ) -> bool:
        if not stripped:
            return False
        if not python_state.can_switch_segments(indent):
            return False
        return self._is_probable_js(stripped, indent)

    def _should_switch_to_python(self, stripped: str, indent: int) -> bool:
        if not stripped:
            return False
        if indent > 0:
            return False
        if self._is_probable_js(stripped, indent):
            return False
        return self._is_probable_python(stripped, indent, True)

    def _parse_python_ast(
        self,
        python_code: str,
        python_line_numbers: Sequence[int],
        *,
        tolerant: bool,
    ) -> ast.Module | None:
        if not python_code.strip():
            return None

        try:
            return ast.parse(python_code, mode="exec", type_comments=True)
        except SyntaxError as exc:  # pragma: no cover - defensive
            if tolerant:
                return None
            line = self._map_lineno(exc.lineno, python_line_numbers)
            raise CompilationError(exc.msg, line) from exc

    def _update_python_indentation(
        self,
        indent_stack: list[int],
        indent: int,
        stripped: str,
        idx: int,
        expect_indent: bool,
        allow_unexpected_indent: bool,
    ) -> bool:
        if not stripped:
            return expect_indent

        current = indent_stack[-1]

        if indent > current:
            if not (expect_indent or allow_unexpected_indent):
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "HEAD":
                elements = []
                head_is_dynamic = True
                continue

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

    def _update_python_expression_state(
        self,
        line: str,
        current_string: _StringTracker | None,
        paren_depth: int,
        bracket_depth: int,
        brace_depth: int,
    ) -> tuple[_StringTracker | None, int, int, int, bool]:
        idx = 0
        length = len(line)
        string_state = current_string

        while idx < length:
            if string_state is not None:
                idx, string_state = self._consume_python_string(line, idx, string_state)
                continue

            char = line[idx]

            if char == "#":
                break

            if char in _STRING_PREFIX_CHARS:
                prefixed = self._match_prefixed_string(line, idx)
                if prefixed is not None:
                    tracker, literal_index = prefixed
                    if tracker.triple:
                        string_state = tracker
                        idx = literal_index
                    else:
                        idx, string_state = self._consume_python_string(line, literal_index, tracker)
                    continue

            if char in ("'", '"'):
                tracker = _StringTracker(delimiter=char, triple=False)
                idx, string_state = self._consume_python_string(line, idx + 1, tracker)
                continue

            if char in "([{":
                if char == "(":
                    paren_depth += 1
                elif char == "[":
                    bracket_depth += 1
                else:
                    brace_depth += 1
                idx += 1
                continue

            if char in ")]}":
                if char == ")":
                    paren_depth = max(0, paren_depth - 1)
                elif char == "]":
                    bracket_depth = max(0, bracket_depth - 1)
                else:
                    brace_depth = max(0, brace_depth - 1)
                idx += 1
                continue

            idx += 1

        stripped = line.rstrip()
        line_continuation = (
            string_state is None
            and not (paren_depth or bracket_depth or brace_depth)
            and bool(stripped)
            and stripped.endswith("\\")
        )

        return string_state, paren_depth, bracket_depth, brace_depth, line_continuation

    @staticmethod
    def _match_prefixed_string(line: str, index: int) -> tuple[_StringTracker, int] | None:
        idx = index
        length = len(line)

        while idx < length and line[idx] in _STRING_PREFIX_CHARS:
            idx += 1

        if idx >= length:
            return None

        if line.startswith('"""', idx) or line.startswith("'''", idx):
            quote = line[idx : idx + 3]
            return _StringTracker(delimiter=quote, triple=True), idx + 3

        if line[idx] in ("'", '"'):
            quote = line[idx]
            return _StringTracker(delimiter=quote, triple=False), idx + 1

        return None

    @staticmethod
    def _consume_python_string(
        line: str,
        index: int,
        tracker: _StringTracker,
    ) -> tuple[int, _StringTracker | None]:
        i = index
        length = len(line)
        if tracker.triple:
            closing = tracker.delimiter
        else:
            closing = tracker.delimiter

        while i < length:
            char = line[i]
            if char == "\\":
                i = min(i + 2, length)
                continue
            if tracker.triple:
                if line.startswith(closing, i):
                    return i + len(closing), None
                i += 1
                continue
            if char == closing:
                return i + 1, None
            i += 1

        return length, tracker

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


class _PythonState:
    """Track indentation and string state for Python segments."""

    def __init__(self, *, parser: PyxParser):
        self._parser = parser
        self.reset_for_new_segment()

    def reset_for_new_segment(self) -> None:
        self.indent_stack: list[int] = [0]
        self.expect_indent = False
        self.string_state: _StringTracker | None = None
        self.paren_depth = 0
        self.bracket_depth = 0
        self.brace_depth = 0
        self.line_continuation = False

    def advance(
        self,
        *,
        line: str,
        stripped: str,
        indent: int,
        line_number: int,
    ) -> None:
        self.expect_indent = self._parser._update_python_indentation(
            self.indent_stack,
            indent,
            stripped,
            line_number,
            self.expect_indent,
            bool(
                self.line_continuation
                or self.paren_depth
                or self.bracket_depth
                or self.brace_depth
            ),
        )
        (
            self.string_state,
            self.paren_depth,
            self.bracket_depth,
            self.brace_depth,
            self.line_continuation,
        ) = self._parser._update_python_expression_state(
            line,
            self.string_state,
            self.paren_depth,
            self.bracket_depth,
            self.brace_depth,
        )

    def can_switch_segments(self, indent: int) -> bool:
        if self.string_state is not None:
            return False
        if self.expect_indent:
            return False
        if self.line_continuation:
            return False
        if self.paren_depth or self.bracket_depth or self.brace_depth:
            return False
        if indent == 0:
            return True
        return len(self.indent_stack) == 1 and self.indent_stack[0] == indent
