"""Utilities for rewriting JSX/TS import specifiers that point at `.pyx` sources."""

from __future__ import annotations

from dataclasses import dataclass

_WHITESPACE = frozenset(" \t\r\n\v\f")
_SUFFIX_DELIMITERS = frozenset("?#")
_IMPORT_STATE_START = "start"
_IMPORT_STATE_AWAITING_FROM = "awaiting_from"


@dataclass(slots=True)
class _DynamicImportState:
    depth: int = 0
    awaiting_specifier: bool = True
    seen_nontrivial_token: bool = False


class _ModuleSpecifierRewriter:
    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.index = 0
        self.replacements: list[tuple[int, int, str]] = []

        self._import_state: str | None = None
        self._awaiting_from_specifier = False
        self._export_clause_pending = False
        self._awaiting_export_specifier = False

        self._dynamic_stack: list[_DynamicImportState] = []

        self._paren_depth = 0
        self._brace_depth = 0
        self._bracket_depth = 0

    def apply(self) -> tuple[str, int]:
        self._scan()
        if not self.replacements:
            return self.source, 0

        chunks: list[str] = []
        cursor = 0
        for start, end, replacement in self.replacements:
            chunks.append(self.source[cursor:start])
            chunks.append(replacement)
            cursor = end
        chunks.append(self.source[cursor:])
        return ("".join(chunks), len(self.replacements))

    def _scan(self) -> None:
        while self.index < self.length:
            char = self.source[self.index]

            if char in _WHITESPACE:
                self.index += 1
                continue

            if char == "/" and self._maybe_skip_comment():
                continue

            if char in ("'", '"'):
                self._consume_string(char)
                continue

            if char == "`":
                self._consume_template()
                continue

            if _is_identifier_start(char):
                self._consume_identifier()
                continue

            if char == "(":
                self._paren_depth += 1
                self._handle_open_paren()
                self.index += 1
                continue

            if char == ")":
                self._paren_depth = max(0, self._paren_depth - 1)
                self._handle_close_paren()
                self.index += 1
                continue

            if char == "{":
                self._brace_depth += 1
                self._mark_import_requires_from()
                self._mark_dynamic_argument_token()
                self.index += 1
                continue

            if char == "}":
                self._brace_depth = max(0, self._brace_depth - 1)
                self.index += 1
                continue

            if char == "[":
                self._bracket_depth += 1
                self._mark_dynamic_argument_token()
                self.index += 1
                continue

            if char == "]":
                self._bracket_depth = max(0, self._bracket_depth - 1)
                self.index += 1
                continue

            if char == ";":
                self._reset_statement_states()
                self.index += 1
                continue

            if char in "*,":
                self._mark_import_requires_from()
                self._mark_dynamic_argument_token()
                self.index += 1
                continue

            if char == ".":
                self._mark_dynamic_argument_token()
                self.index += 1
                continue

            self._mark_dynamic_argument_token()
            self.index += 1

    def _maybe_skip_comment(self) -> bool:
        if self.source.startswith("//", self.index):
            self.index = self._consume_line_comment(self.index)
            return True
        if self.source.startswith("/*", self.index):
            self.index = self._consume_block_comment(self.index)
            return True
        return False

    def _consume_line_comment(self, start: int) -> int:
        idx = start + 2
        while idx < self.length and self.source[idx] not in "\r\n":
            idx += 1
        return idx

    def _consume_block_comment(self, start: int) -> int:
        idx = start + 2
        while idx < self.length - 1:
            if self.source[idx] == "*" and self.source[idx + 1] == "/":
                return idx + 2
            idx += 1
        return self.length

    def _consume_string(self, quote: str) -> None:
        start = self.index
        self.index += 1
        while self.index < self.length:
            char = self.source[self.index]
            if char == "\\":
                self.index += 2
                continue
            if char == quote:
                end = self.index + 1
                self._process_literal(start, end, quote, is_template=False, template_is_simple=True)
                self.index = end
                return
            if char in "\r\n":
                break
            self.index += 1
        self.index = self.length

    def _consume_template(self) -> None:
        start = self.index
        self.index += 1
        brace_depth = 0
        simple_template = True
        while self.index < self.length:
            char = self.source[self.index]
            if char == "`" and brace_depth == 0:
                end = self.index + 1
                self._process_literal(start, end, "`", is_template=True, template_is_simple=simple_template)
                self.index = end
                return
            if char == "\\":
                self.index += 2
                continue
            if char == "$" and self.index + 1 < self.length and self.source[self.index + 1] == "{":
                simple_template = False
                brace_depth += 1
                self.index += 2
                continue
            if char == "}" and brace_depth > 0:
                brace_depth -= 1
                self.index += 1
                continue
            self.index += 1
        self.index = self.length

    def _consume_identifier(self) -> None:
        start = self.index
        self.index += 1
        while self.index < self.length and _is_identifier_part(self.source[self.index]):
            self.index += 1
        value = self.source[start:self.index]
        self._mark_dynamic_argument_token()

        if value == "import":
            if self.index < self.length and self.source[self.index] == ".":
                return
            next_index = self._skip_insignificant(self.index)
            next_char = self.source[next_index] if next_index < self.length else ""
            prev_char = self.source[start - 1] if start > 0 else ""
            if next_char == "(" and prev_char != ".":
                self._start_dynamic_import()
                return
            if (
                self._brace_depth == 0
                and self._paren_depth == 0
                and self._bracket_depth == 0
                and prev_char != "."
            ):
                self._start_static_import()
            return

        if value == "from":
            self._handle_from_keyword()
            return

        if value == "export":
            self._handle_export_keyword()
            return

        self._mark_import_requires_from()

    def _handle_from_keyword(self) -> None:
        if self._import_state in (_IMPORT_STATE_START, _IMPORT_STATE_AWAITING_FROM):
            self._awaiting_from_specifier = True
            return
        if self._export_clause_pending:
            self._awaiting_export_specifier = True
            self._export_clause_pending = False

    def _handle_export_keyword(self) -> None:
        lookahead = self._skip_insignificant(self.index)
        lookahead = self._skip_optional_word(lookahead, "type")
        lookahead = self._skip_insignificant(lookahead)
        if lookahead < self.length and self.source[lookahead] in "{*":
            self._export_clause_pending = True
        else:
            self._export_clause_pending = False

    def _skip_optional_word(self, index: int, word: str) -> int:
        if index >= self.length:
            return index
        if not self.source.startswith(word, index):
            return index
        end = index + len(word)
        if end < self.length and _is_identifier_part(self.source[end]):
            return index
        return end

    def _skip_insignificant(self, index: int) -> int:
        idx = index
        while idx < self.length:
            char = self.source[idx]
            if char in _WHITESPACE:
                idx += 1
                continue
            if char == "/" and self.source.startswith("//", idx):
                idx = self._consume_line_comment(idx)
                continue
            if char == "/" and self.source.startswith("/*", idx):
                idx = self._consume_block_comment(idx)
                continue
            break
        return idx

    def _start_static_import(self) -> None:
        self._import_state = _IMPORT_STATE_START
        self._awaiting_from_specifier = False

    def _mark_import_requires_from(self) -> None:
        if self._import_state == _IMPORT_STATE_START and not self._awaiting_from_specifier:
            self._import_state = _IMPORT_STATE_AWAITING_FROM

    def _start_dynamic_import(self) -> None:
        self._dynamic_stack.append(_DynamicImportState())

    def _handle_open_paren(self) -> None:
        if self._dynamic_stack:
            self._dynamic_stack[-1].depth += 1

    def _handle_close_paren(self) -> None:
        if not self._dynamic_stack:
            return
        state = self._dynamic_stack[-1]
        state.depth = max(0, state.depth - 1)
        if state.depth == 0:
            self._dynamic_stack.pop()

    def _mark_dynamic_argument_token(self) -> None:
        if not self._dynamic_stack:
            return
        state = self._dynamic_stack[-1]
        if state.awaiting_specifier:
            state.seen_nontrivial_token = True

    def _current_literal_context(self) -> str | None:
        if self._awaiting_from_specifier:
            self._awaiting_from_specifier = False
            self._import_state = None
            return "import"
        if self._import_state == _IMPORT_STATE_START:
            self._import_state = None
            return "side_effect"
        if self._awaiting_export_specifier:
            self._awaiting_export_specifier = False
            return "export"
        if self._dynamic_stack:
            state = self._dynamic_stack[-1]
            if state.awaiting_specifier and not state.seen_nontrivial_token:
                state.awaiting_specifier = False
                return "dynamic"
        return None

    def _process_literal(self, start: int, end: int, quote: str, *, is_template: bool, template_is_simple: bool) -> None:
        if is_template and not template_is_simple:
            return
        context = self._current_literal_context()
        if context is None:
            return
        literal_value = self.source[start + 1 : end - 1]
        rewritten = _rewrite_specifier_value(literal_value)
        if rewritten is None:
            return
        replacement = f"{quote}{rewritten}{quote}"
        self.replacements.append((start, end, replacement))

    def _reset_statement_states(self) -> None:
        self._import_state = None
        self._awaiting_from_specifier = False
        self._export_clause_pending = False
        self._awaiting_export_specifier = False


def _rewrite_specifier_value(value: str) -> str | None:
    split_index = len(value)
    for idx, char in enumerate(value):
        if char in _SUFFIX_DELIMITERS:
            split_index = idx
            break
    prefix = value[:split_index]
    suffix = value[split_index:]
    if not prefix.endswith(".pyx"):
        return None
    return f"{prefix[:-4]}.jsx{suffix}"


def _is_identifier_start(char: str) -> bool:
    return char == "_" or char == "$" or char.isalpha()


def _is_identifier_part(char: str) -> bool:
    return char == "_" or char == "$" or char.isalpha() or char.isdigit()


def rewrite_pyx_import_specifiers(source: str) -> tuple[str, int]:
    """Rewrite `.pyx` specifiers inside import/export declarations."""

    rewriter = _ModuleSpecifierRewriter(source)
    return rewriter.apply()


__all__ = ["rewrite_pyx_import_specifiers"]
