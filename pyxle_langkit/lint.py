"""Linting primitives for `.pyx` authoring."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

from pyxle.compiler.jsx_parser import JSXComponent, parse_jsx_components

try:  # pragma: no cover - optional dependency
    from pyflakes.checker import Checker as _PyflakesChecker
except Exception:  # pragma: no cover - tooling-only optional import
    _PyflakesChecker = None

_PYFLAKES_SEVERITY: dict[str, Severity] = {
    "UndefinedName": "error",
    "UndefinedLocal": "error",
    "ReturnOutsideFunction": "error",
    "ContinueOutsideLoop": "error",
    "BreakOutsideLoop": "error",
    "UnusedImport": "info",
    "UnusedVariable": "info",
    "UnusedFunction": "info",
    "UnusedClass": "info",
    "ImportShadowedByLoopVar": "warning",
    "RedefinedWhileUnused": "warning",
    "DuplicateArgument": "warning",
    "MultiValueRepeatedKeyLiteral": "warning",
}

_PYXLE_ALLOWED_GLOBALS = {"server"}
_ALLOWED_SCRIPT_STRATEGIES = {"beforeInteractive", "afterInteractive", "lazyOnload"}

from .document import PyxDocument
from .parser import PyxLanguageParser
from .react_checker import ReactAnalyzer

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class LintIssue:
    source: str
    message: str
    rule: str
    severity: Severity
    line: int | None = None
    column: int | None = None

    def format(self) -> str:
        location = f"{self.line}:{self.column}" if self.line is not None else "?"
        return f"[{self.severity}] {self.rule} ({location}) {self.message}"


class PyxLinter:
    """Runs structural checks by leveraging existing Python/React parsers."""

    def __init__(
        self,
        *,
        parser: PyxLanguageParser | None = None,
        react_analyzer: ReactAnalyzer | None = None,
    ) -> None:
        self._parser = parser or PyxLanguageParser(tolerant=True)
        self._react_analyzer = react_analyzer or ReactAnalyzer()

    def lint_path(self, source: str | Path) -> list[LintIssue]:
        document = self._parser.parse_path(source)
        return self.lint_document(document)

    def lint_text(self, text: str, *, path: str | Path | None = None) -> list[LintIssue]:
        document = self._parser.parse_text(text, path=path)
        return self.lint_document(document)

    def lint_document(self, document: PyxDocument) -> list[LintIssue]:
        return list(self._lint_document(document))

    def _lint_document(self, document: PyxDocument) -> Iterable[LintIssue]:
        issues: list[LintIssue] = []
        issues.extend(self._lint_python(document))
        issues.extend(self._lint_jsx(document))
        return issues

    def _lint_python(self, document: PyxDocument) -> Iterable[LintIssue]:
        if not document.has_python:
            return []

        try:
            tree = ast.parse(document.python_code)
        except SyntaxError as exc:  # pragma: no cover - parser already enforces syntax, defensive only
            return [
                LintIssue(
                    source="python",
                    rule="python/syntax",
                    severity="error",
                    message=exc.msg,
                    line=document.map_python_line(exc.lineno),
                    column=exc.offset,
                )
            ]
        issues: list[LintIssue] = []

        issues.extend(self._pyflakes_issues(tree, document))
        issues.extend(self._detect_unreachable_code(tree, document))

        if document.loader is None:
            issues.append(
                LintIssue(
                    source="python",
                    rule="pyxle/loader-missing",
                    severity="warning",
                    message="Python code detected without an @server loader; static data will never reach the client.",
                    line=None,
                    column=None,
                )
            )
        else:
            loader_node = next(
                (
                    node
                    for node in tree.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == document.loader.name
                ),
                None,
            )
            if loader_node and not self._function_has_return(loader_node):
                issues.append(
                    LintIssue(
                        source="python",
                        rule="pyxle/loader-no-return",
                        severity="warning",
                        message="@server loader never returns a value; hydration will receive `None`.",
                        line=document.map_python_line(loader_node.lineno),
                        column=self._to_one_based_column(loader_node.col_offset),
                    )
                )

        return issues

    def _pyflakes_issues(self, tree: ast.AST, document: PyxDocument) -> Iterable[LintIssue]:
        if _PyflakesChecker is None:
            return []

        checker = _PyflakesChecker(tree, filename=str(document.path))
        issues: list[LintIssue] = []
        for message in checker.messages:
            cls_name = message.__class__.__name__
            missing_name = getattr(message, "name", None)
            if missing_name is None:
                args = getattr(message, "message_args", None)
                if args:
                    missing_name = args[0]
            if cls_name == "UndefinedName" and missing_name in _PYXLE_ALLOWED_GLOBALS:
                continue
            severity = _PYFLAKES_SEVERITY.get(cls_name, "warning")
            line = document.map_python_line(getattr(message, "lineno", None))
            column = self._to_one_based_column(getattr(message, "col", None))
            issues.append(
                LintIssue(
                    source="python",
                    rule=f"pyflakes/{cls_name}",
                    severity=severity,
                    message=self._format_pyflakes_message(message),
                    line=line,
                    column=column,
                )
            )
        return issues

    @staticmethod
    def _format_pyflakes_message(message: object) -> str:
        template = getattr(message, "message", None)
        args = getattr(message, "message_args", None)
        if template:
            try:
                return template % args if args else template
            except Exception:  # pragma: no cover - defensive: fall back to str()
                return template
        return str(message)

    def _detect_unreachable_code(self, tree: ast.AST, document: PyxDocument) -> Iterable[LintIssue]:
        analyzer = _UnreachableAnalyzer(document)
        analyzer.scan(tree)
        return analyzer.issues

    def _lint_jsx(self, document: PyxDocument) -> Iterable[LintIssue]:
        if not document.has_jsx:
            return []

        issues: list[LintIssue] = []
        try:
            analysis = self._react_analyzer.analyze(document.jsx_code)
        except RuntimeError as exc:
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/analyzer-unavailable",
                    severity="warning",
                    message=str(exc),
                    line=self._first_jsx_line(document),
                    column=None,
                )
            )
            return issues

        if analysis.error:
            mapped_line = document.map_jsx_line(analysis.error.line)
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/syntax",
                    severity="error",
                    message=analysis.error.message,
                    line=mapped_line,
                    column=self._to_one_based_column(analysis.error.column),
                )
            )
            return issues

        has_default_export = any(symbol.kind == "default-export" for symbol in analysis.symbols)
        if not has_default_export:
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/default-export",
                    severity="warning",
                    message="Pages should export a default component for SSR + hydration.",
                    line=self._first_jsx_line(document),
                    column=None,
                )
            )

        component_result = parse_jsx_components(
            document.jsx_code,
            target_components={"Script", "Image"},
        )
        if component_result.error:
            issues.append(
                LintIssue(
                    source="react",
                    rule="react/component-analysis",
                    severity="info",
                    message=component_result.error,
                    line=self._first_jsx_line(document),
                    column=None,
                )
            )
            return issues

        for component in component_result.components:
            issues.extend(self._lint_jsx_component(component, document))

        return issues

    @staticmethod
    def _function_has_return(node: ast.AsyncFunctionDef) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                return True
        return False

    @staticmethod
    def _to_one_based_column(column: int | None) -> int | None:
        if column is None:
            return None
        return max(1, column + 1)

    @staticmethod
    def _first_jsx_line(document: PyxDocument) -> int | None:
        if not document.jsx_line_numbers:
            return None
        return document.jsx_line_numbers[0]

    def _lint_jsx_component(self, component: JSXComponent, document: PyxDocument) -> Iterable[LintIssue]:
        if component.name == "Script":
            return self._lint_script_component(component, document)
        if component.name == "Image":
            return self._lint_image_component(component, document)
        return []

    def _lint_script_component(self, component: JSXComponent, document: PyxDocument) -> Iterable[LintIssue]:
        issues: list[LintIssue] = []
        line = document.map_jsx_line(component.line)
        column = self._to_one_based_column(component.column)
        props = component.props

        src = props.get("src")
        if not isinstance(src, str) or not src.strip():
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/script-src-required",
                    severity="error",
                    message="<Script /> requires a non-empty `src` prop.",
                    line=line,
                    column=column,
                )
            )

        strategy = props.get("strategy", "afterInteractive")
        if isinstance(strategy, str):
            if not self._is_dynamic_expression(strategy) and strategy not in _ALLOWED_SCRIPT_STRATEGIES:
                issues.append(
                    LintIssue(
                        source="react",
                        rule="pyxle/script-strategy-invalid",
                        severity="error",
                        message=(
                            "<Script /> strategy must be one of "
                            "`beforeInteractive`, `afterInteractive`, or `lazyOnload`."
                        ),
                        line=line,
                        column=column,
                    )
                )
        elif strategy is not None:
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/script-strategy-invalid",
                    severity="error",
                    message="<Script /> strategy must be a string literal.",
                    line=line,
                    column=column,
                )
            )

        module_value = self._as_bool_literal(props.get("module"))
        no_module_value = self._as_bool_literal(props.get("noModule"))
        if module_value is True and no_module_value is True:
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/script-module-conflict",
                    severity="warning",
                    message="<Script /> cannot set both `module` and `noModule` to true.",
                    line=line,
                    column=column,
                )
            )
        return issues

    def _lint_image_component(self, component: JSXComponent, document: PyxDocument) -> Iterable[LintIssue]:
        issues: list[LintIssue] = []
        line = document.map_jsx_line(component.line)
        column = self._to_one_based_column(component.column)
        props = component.props

        src = props.get("src")
        if not isinstance(src, str) or not src.strip():
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/image-src-required",
                    severity="error",
                    message="<Image /> requires a non-empty `src` prop.",
                    line=line,
                    column=column,
                )
            )

        alt = props.get("alt")
        if not isinstance(alt, str) or not alt.strip():
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/image-alt-required",
                    severity="warning",
                    message="<Image /> should include a meaningful non-empty `alt` prop.",
                    line=line,
                    column=column,
                )
            )

        issues.extend(
            self._lint_required_dimension(
                props=props,
                key="width",
                line=line,
                column=column,
            )
        )
        issues.extend(
            self._lint_required_dimension(
                props=props,
                key="height",
                line=line,
                column=column,
            )
        )

        priority = self._as_bool_literal(props.get("priority"))
        lazy = self._as_bool_literal(props.get("lazy"))
        if priority is True and props.get("lazy") is not None and lazy is True:
            issues.append(
                LintIssue(
                    source="react",
                    rule="pyxle/image-priority-lazy-conflict",
                    severity="warning",
                    message="<Image /> with `priority` should not also set `lazy={true}`.",
                    line=line,
                    column=column,
                )
            )

        return issues

    def _lint_required_dimension(
        self,
        *,
        props: dict[str, object],
        key: str,
        line: int | None,
        column: int | None,
    ) -> Iterable[LintIssue]:
        if key not in props:
            return [
                LintIssue(
                    source="react",
                    rule=f"pyxle/image-{key}-required",
                    severity="error",
                    message=f"<Image /> requires a `{key}` prop.",
                    line=line,
                    column=column,
                )
            ]

        value = props.get(key)
        if self._is_dynamic_expression(value):
            return []
        numeric = self._as_positive_number(value)
        if numeric is not None:
            return []
        return [
            LintIssue(
                source="react",
                rule=f"pyxle/image-{key}-invalid",
                severity="error",
                message=f"<Image /> `{key}` must be a positive numeric literal.",
                line=line,
                column=column,
            )
        ]

    @staticmethod
    def _is_dynamic_expression(value: object) -> bool:
        if not isinstance(value, str):
            return False
        stripped = value.strip()
        return stripped.startswith("{") and stripped.endswith("}")

    @staticmethod
    def _as_positive_number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                parsed = float(stripped)
            except ValueError:
                return None
            return parsed if parsed > 0 else None
        return None

    @staticmethod
    def _as_bool_literal(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        return None


class _UnreachableAnalyzer:
    _TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)

    def __init__(self, document: PyxDocument) -> None:
        self.document = document
        self.issues: list[LintIssue] = []

    def scan(self, tree: ast.AST) -> None:
        body: Sequence[ast.stmt] = getattr(tree, "body", [])  # type: ignore[assignment]
        self._scan_block(body)

    def _scan_block(self, statements: Sequence[ast.stmt]) -> None:
        reachable = True
        for statement in statements:
            if statement is None:
                continue
            if not reachable:
                self._record_unreachable(statement)
                continue
            self._visit_children(statement)
            if isinstance(statement, self._TERMINATORS):
                reachable = False

    def _visit_children(self, statement: ast.stmt) -> None:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._scan_block(statement.body)
            return
        if isinstance(statement, ast.If):
            self._scan_block(statement.body)
            self._scan_block(statement.orelse)
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            self._scan_block(statement.body)
            self._scan_block(statement.orelse)
        elif isinstance(statement, ast.Try):
            self._scan_block(statement.body)
            for handler in statement.handlers:
                self._scan_block(handler.body)
            self._scan_block(statement.orelse)
            self._scan_block(statement.finalbody)
        elif isinstance(statement, ast.With):
            self._scan_block(statement.body)
        elif isinstance(statement, ast.Match):  # Python 3.10+
            for case in statement.cases:  # type: ignore[attr-defined]
                self._scan_block(case.body)

    def _record_unreachable(self, statement: ast.stmt) -> None:
        line = self.document.map_python_line(getattr(statement, "lineno", None))
        column = PyxLinter._to_one_based_column(getattr(statement, "col_offset", None))
        self.issues.append(
            LintIssue(
                source="python",
                rule="pyxle/unreachable-code",
                severity="warning",
                message="Code is unreachable because a previous statement exits the block.",
                line=line,
                column=column,
            )
        )
