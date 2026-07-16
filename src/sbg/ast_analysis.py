"""AST-based static analysis for Python source.

These analyzers operate on a parsed :mod:`ast` tree instead of raw text, so they
can reason about real program structure (functions, exception handlers, call
targets, nesting) with far fewer false positives than regular expressions.

Each analyzer has the signature ``analyzer(rule, tree, relative_path)`` and
returns a list of ``(line, message)`` findings. The engine converts those into
:class:`~sbg.engine.Violation` records.
"""

from __future__ import annotations

import ast
from typing import Any

Finding = tuple[int | None, str]

_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)
_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _name_of(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def analyze_bare_except(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del rule, relative_path
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append((node.lineno, "bare 'except:' clause hides every error; catch a specific exception type"))
    return findings


def analyze_broad_except(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del relative_path
    names = set(rule.get("names") or ["Exception", "BaseException"])
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            handler_type = node.type
            targets = handler_type.elts if isinstance(handler_type, ast.Tuple) else [handler_type]
            for target in targets:
                name = _name_of(target)
                if name in names:
                    findings.append(
                        (node.lineno, f"overly broad 'except {name}'; catch the specific exceptions you expect")
                    )
    return findings


def analyze_mutable_default(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del rule, relative_path
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, _FUNCTION_NODES):
            continue
        defaults = list(node.args.defaults) + [default for default in node.args.kw_defaults if default is not None]
        for default in defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(default, ast.Call) and _name_of(default.func) in {"list", "dict", "set"}
            ):
                line = getattr(default, "lineno", node.lineno)
                findings.append(
                    (line, f"mutable default argument in '{node.name}' is shared across calls; use None instead")
                )
    return findings


def analyze_eval_exec(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del relative_path
    banned = set(rule.get("names") or ["eval", "exec"])
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _name_of(node.func)
            if name in banned:
                findings.append((node.lineno, f"use of '{name}' is a code-injection risk; avoid dynamic execution"))
    return findings


def analyze_function_args(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del relative_path
    max_args = int(rule.get("max_args", 6))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, _FUNCTION_NODES):
            continue
        args = node.args
        positional = list(args.posonlyargs) + list(args.args)
        count = len(positional) + len(args.kwonlyargs)
        if positional and positional[0].arg in {"self", "cls"}:
            count -= 1
        if count > max_args:
            findings.append((node.lineno, f"function '{node.name}' takes {count} parameters (max {max_args})"))
    return findings


def analyze_function_length(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del relative_path
    max_lines = int(rule.get("max_lines", 60))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, _FUNCTION_NODES):
            continue
        end_lineno = getattr(node, "end_lineno", None)
        if end_lineno is None:
            continue
        length = end_lineno - node.lineno + 1
        if length > max_lines:
            findings.append((node.lineno, f"function '{node.name}' is {length} lines long (max {max_lines})"))
    return findings


def analyze_nesting_depth(rule: dict[str, Any], tree: ast.AST, relative_path: str) -> list[Finding]:
    del relative_path
    max_depth = int(rule.get("max_depth", 4))
    findings: list[Finding] = []

    def visit(node: ast.AST, depth: int, function_name: str, reported: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPE_BOUNDARIES):
                continue
            if isinstance(child, _NESTING_NODES):
                new_depth = depth + 1
                if new_depth > max_depth and function_name not in reported:
                    findings.append(
                        (child.lineno, f"nesting depth {new_depth} exceeds {max_depth} in '{function_name}'")
                    )
                    reported.add(function_name)
                visit(child, new_depth, function_name, reported)
            else:
                visit(child, depth, function_name, reported)

    for node in ast.walk(tree):
        if isinstance(node, _FUNCTION_NODES):
            visit(node, 0, node.name, set())
    return findings


AST_ANALYZERS = {
    "python-bare-except": analyze_bare_except,
    "python-broad-except": analyze_broad_except,
    "python-mutable-default": analyze_mutable_default,
    "python-eval-exec": analyze_eval_exec,
    "python-function-args": analyze_function_args,
    "python-function-length": analyze_function_length,
    "python-nesting-depth": analyze_nesting_depth,
}


def parse_module(content: str) -> tuple[ast.AST | None, SyntaxError | None]:
    """Parse Python source, returning ``(tree, None)`` or ``(None, error)``."""

    try:
        return ast.parse(content), None
    except SyntaxError as error:
        return None, error
