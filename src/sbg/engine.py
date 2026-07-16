from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .manifest import load_manifest
from .ast_analysis import AST_ANALYZERS, parse_module


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "target",
    "fixtures",
}


KNOWN_RULE_TYPES = {
    "placeholder-comments",
    "marker-spam",
    "empty-files",
    "long-lines",
    "file-size",
    "button-actions",
    "button-types",
    "form-labels",
    "asset-links",
    "fully-defined-rules",
    "source-loadable",
    "dynamic-config",
    "merge-conflict-markers",
    "secret-scan",
    "debug-artifacts",
    "trailing-whitespace",
    "final-newline",
    "python-syntax",
    "python-bare-except",
    "python-broad-except",
    "python-mutable-default",
    "python-eval-exec",
    "python-function-args",
    "python-function-length",
    "python-nesting-depth",
    "composite",
}


def validate_manifest(manifest: Any) -> list[str]:
    """Return a list of human-readable problems with a manifest definition.

    An empty list means the manifest is structurally valid. This is the
    programmatic guard that keeps dead or malformed policy from silently
    no-opping inside the engine.
    """

    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object with a 'rules' array"]
    rules = manifest.get("rules")
    if not isinstance(rules, list):
        return ["manifest must contain a 'rules' array"]
    seen_ids: set[str] = set()
    for index, rule in enumerate(rules):
        label = f"rule {index + 1}"
        if not isinstance(rule, dict):
            errors.append(f"{label} is not a JSON object")
            continue
        rule_id = rule.get("id")
        if isinstance(rule_id, str) and rule_id.strip():
            label = f"rule '{rule_id}'"
            if rule_id in seen_ids:
                errors.append(f"{label} has a duplicate id")
            seen_ids.add(rule_id)
        else:
            errors.append(f"{label} is missing a non-empty 'id'")
        rule_type = rule.get("type")
        if not isinstance(rule_type, str) or not rule_type.strip():
            errors.append(f"{label} is missing a non-empty 'type'")
        elif rule_type not in KNOWN_RULE_TYPES:
            errors.append(f"{label} has unknown type '{rule_type}'")
        elif rule_type == "composite":
            errors.extend(_validate_composite_shape(label, rule))
        severity = rule.get("severity")
        if severity is not None and (
            not isinstance(severity, str) or severity.strip().lower() not in {"error", "warning"}
        ):
            errors.append(f"{label} has invalid 'severity' (must be 'error' or 'warning')")
    return errors


def _validate_composite_shape(label: str, rule: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    child_rules = rule.get("rules")
    if not isinstance(child_rules, list) or not child_rules:
        problems.append(f"{label} (composite) must define a non-empty 'rules' array")
    logic = rule.get("logic", "all")
    if not isinstance(logic, str) or logic.strip().lower() not in {"all", "any"}:
        problems.append(f"{label} (composite) 'logic' must be 'all' or 'any'")
    match_value = rule.get("match")
    if match_value is not None and not isinstance(match_value, (str, list)):
        problems.append(f"{label} (composite) 'match' must be a string or list of globs")
    return problems


_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "AWS temporary access key id"),
    (re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"), "GitHub fine-grained token"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b"), "Stripe live secret key"),
)


_DEBUG_ARTIFACT_PATTERNS: tuple[tuple[frozenset[str], tuple[tuple[re.Pattern[str], str], ...]], ...] = (
    (
        frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue"}),
        (
            (re.compile(r"(?<![A-Za-z0-9_.])debugger\s*;"), "debugger statement"),
            (re.compile(r"(?<![A-Za-z0-9_.])console\.(?:log|debug|trace)\s*\("), "console debug call"),
        ),
    ),
    (
        frozenset({".py"}),
        (
            (re.compile(r"(?<![A-Za-z0-9_.])breakpoint\s*\("), "breakpoint call"),
            (re.compile(r"(?<![A-Za-z0-9_.])pdb\.set_trace\s*\("), "pdb trace call"),
        ),
    ),
)


_DYNAMIC_CONFIG_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            (
                r"(?<![A-Za-z0-9_./-])"
                r"/(?:home|Users|tmp|var|opt|etc|srv|mnt|private|Volumes|Applications|Library)"
                r"(?:/|\\)"
            ),
            re.IGNORECASE,
        ),
        "absolute filesystem path",
    ),
    (
        re.compile(r"(?<![A-Za-z0-9_./-])~(?:/|\\)", re.IGNORECASE),
        "home-relative path",
    ),
    (
        re.compile(
            (
                r"(?<![A-Za-z0-9_./-])"
                r"[A-Za-z]:\\(?:Users|Program Files|"
                r"Program Files \(x86\)|Windows|Temp|tmp|Documents|Desktop|Library)"
                r"(?:\\|/)"
            ),
            re.IGNORECASE,
        ),
        "absolute Windows path",
    ),
    (
        re.compile(
            (
                r"(?<![A-Za-z0-9_./-])"
                r"https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/|$)"
            ),
            re.IGNORECASE,
        ),
        "loopback endpoint",
    ),
)


def _fix_trailing_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+(\r\n|\r|\n|$)", r"\1", text)


def _fix_final_newline(text: str) -> str:
    if not text or text.endswith(("\n", "\r")):
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    return text + newline


FIXABLE_RULE_TYPES: dict[str, Any] = {
    "trailing-whitespace": _fix_trailing_whitespace,
    "final-newline": _fix_final_newline,
}



@dataclass(frozen=True)
class Violation:
    rule_id: str
    path: str
    line: int | None
    message: str
    severity: str = "error"

    def format(self) -> str:
        location = self.path
        if self.line is not None:
            location = f"{location}:{self.line}"
        severity_marker = "" if self.severity == "error" else f" ({self.severity})"
        return f"{location}: [{self.rule_id}]{severity_marker} {self.message}"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rule_id": self.rule_id,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }
        if self.line is not None:
            payload["line"] = self.line
        return payload


class RuleEngine:
    def __init__(self, manifest: dict[str, Any] | None = None):
        self.manifest = manifest or {"rules": []}
        self._composite_depth = 0

    @classmethod
    def from_manifest_path(cls, path: str | Path | None = None) -> "RuleEngine":
        return cls(load_manifest(path))

    def scan_repository(self, repo_root: str | Path) -> list[Violation]:
        repo_root = Path(repo_root).expanduser().resolve()
        files = self._collect_files(repo_root)
        return self.scan_paths(repo_root, [path for path, _ in files])

    def scan_paths(
        self,
        repo_root: str | Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
    ) -> list[Violation]:
        repo_root = Path(repo_root).expanduser().resolve()
        violations: list[Violation] = []
        rules = [rule for rule in self.manifest.get("rules", []) if rule.get("enabled", True)]
        ignore_selectors = self._load_ignore_selectors(repo_root)
        if ignore_selectors:
            file_paths = [
                raw_path
                for raw_path in file_paths
                if raw_path is not None and not self._is_ignored(repo_root, raw_path, ignore_selectors)
            ]
        repo_context = self._build_repo_context(repo_root, file_paths)

        for rule in rules:
            severity = self._rule_severity(rule)
            if rule.get("type") == "composite":
                violations.extend(
                    self._stamp_severity(self._apply_composite_rule(rule, repo_root, file_paths), severity)
                )
                continue

            include_selectors = self._normalize_selectors(rule.get("include"))
            exclude_selectors = self._normalize_selectors(rule.get("exclude"))
            for raw_path in file_paths:
                if raw_path is None:
                    continue
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = (repo_root / candidate).resolve()
                else:
                    candidate = candidate.expanduser().resolve()
                if not candidate.exists() or not candidate.is_file():
                    continue
                try:
                    relative_path = candidate.relative_to(repo_root).as_posix()
                except ValueError:
                    relative_path = candidate.as_posix()
                if include_selectors and not any(selector.match(relative_path) for selector in include_selectors):
                    continue
                if exclude_selectors and any(selector.match(relative_path) for selector in exclude_selectors):
                    continue
                file_size = candidate.stat().st_size
                if relative_path in repo_context["files"]:
                    content = repo_context["files"][relative_path]
                else:
                    content = self._read_text(candidate)
                violations.extend(
                    self._stamp_severity(
                        self._apply_rule(
                            rule,
                            repo_root,
                            candidate,
                            relative_path,
                            content,
                            file_size,
                            repo_context,
                        ),
                        severity,
                    )
                )

        return sorted(
            violations,
            key=lambda violation: (violation.path, violation.line or 0, violation.rule_id),
        )

    @staticmethod
    def _rule_severity(rule: dict[str, Any]) -> str:
        severity = str(rule.get("severity", "error")).strip().lower()
        return severity if severity in {"error", "warning"} else "error"

    @staticmethod
    def _stamp_severity(violations: list[Violation], severity: str) -> list[Violation]:
        if severity == "error":
            return violations
        return [replace(violation, severity=severity) for violation in violations]

    def scan_staged_files(self, repo_root: str | Path) -> list[Violation]:
        staged = self._staged_file_list(repo_root)
        if staged is None:
            return []
        git_root, staged_paths = staged
        return self.scan_paths(git_root, staged_paths)

    def _staged_file_list(self, repo_root: str | Path) -> tuple[Path, list[str]] | None:
        repo_root = Path(repo_root).expanduser().resolve()
        try:
            root_result = subprocess.run(
                ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            )
            git_root = Path(root_result.stdout.strip()).expanduser().resolve()
            result = subprocess.run(
                ["git", "-C", str(git_root), "diff", "--cached", "--name-only"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            return None

        staged_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return git_root, staged_paths

    def autofix_repository(self, repo_root: str | Path) -> list[str]:
        repo_root = Path(repo_root).expanduser().resolve()
        files = [path for path, _ in self._collect_files(repo_root)]
        return self.autofix_paths(repo_root, files)

    def autofix_staged_files(self, repo_root: str | Path) -> list[str]:
        staged = self._staged_file_list(repo_root)
        if staged is None:
            return []
        git_root, staged_paths = staged
        return self.autofix_paths(git_root, staged_paths)

    def autofix_paths(
        self,
        repo_root: str | Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
    ) -> list[str]:
        repo_root = Path(repo_root).expanduser().resolve()
        ignore_selectors = self._load_ignore_selectors(repo_root)
        fixable_rules = [
            rule
            for rule in self.manifest.get("rules", [])
            if rule.get("enabled", True) and rule.get("type") in FIXABLE_RULE_TYPES
        ]
        if not fixable_rules:
            return []

        changed: list[str] = []
        for raw_path in file_paths:
            if raw_path is None:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = (repo_root / candidate).resolve()
            else:
                candidate = candidate.expanduser().resolve()
            if not candidate.exists() or not candidate.is_file():
                continue
            if ignore_selectors and self._is_ignored(repo_root, candidate, ignore_selectors):
                continue
            relative_path = self._relative_posix(repo_root, candidate)
            try:
                original = candidate.read_bytes().decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            text = original
            for rule in fixable_rules:
                include_selectors = self._normalize_selectors(rule.get("include"))
                exclude_selectors = self._normalize_selectors(rule.get("exclude"))
                if include_selectors and not any(selector.match(relative_path) for selector in include_selectors):
                    continue
                if exclude_selectors and any(selector.match(relative_path) for selector in exclude_selectors):
                    continue
                text = FIXABLE_RULE_TYPES[rule["type"]](text)
            if text != original:
                candidate.write_bytes(text.encode("utf-8"))
                changed.append(relative_path)
        return sorted(changed)

    def _collect_files(self, repo_root: Path) -> list[tuple[Path, str]]:
        collected: list[tuple[Path, str]] = []
        for current_root, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [dirname for dirname in dirnames if dirname not in IGNORED_DIRS]
            for filename in filenames:
                file_path = Path(current_root, filename)
                if not file_path.is_file() or file_path.is_symlink():
                    continue
                relative_path = file_path.relative_to(repo_root).as_posix()
                collected.append((file_path, relative_path))
        return collected

    def _read_text(self, file_path: Path) -> str | None:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    def _build_repo_context(
        self,
        repo_root: Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
    ) -> dict[str, Any]:
        context: dict[str, Any] = {"files": {}}
        for raw_path in file_paths:
            if raw_path is None:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = (repo_root / candidate).resolve()
            else:
                candidate = candidate.expanduser().resolve()
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                relative_path = candidate.relative_to(repo_root).as_posix()
            except ValueError:
                relative_path = candidate.as_posix()
            context["files"][relative_path] = self._read_text(candidate)
        return context

    def _apply_composite_rule(
        self,
        rule: dict[str, Any],
        repo_root: Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
    ) -> list[Violation]:
        rule_id = rule.get("id", rule.get("type", "composite"))
        if self._composite_depth > 4:
            return []
        child_rules = rule.get("rules")
        if not isinstance(child_rules, list) or not child_rules:
            return []
        logic = str(rule.get("logic", "all")).strip().lower()
        selectors = self._normalize_selectors(rule.get("match"))
        scoped_paths = self._select_paths(repo_root, file_paths, selectors)
        if not scoped_paths:
            return []

        child_results: list[tuple[str, list[Violation]]] = []
        for child in child_rules:
            if not isinstance(child, dict):
                continue
            child_engine = RuleEngine({"rules": [{**child, "enabled": True}]})
            child_engine._composite_depth = self._composite_depth + 1
            child_violations = child_engine.scan_paths(repo_root, scoped_paths)
            child_id = str(child.get("id") or child.get("type") or "child")
            child_results.append((child_id, child_violations))

        if not child_results:
            return []
        if logic == "any":
            return self._combine_any_logic(rule_id, child_results)
        return self._combine_all_logic(rule_id, child_results)

    def _combine_all_logic(
        self,
        rule_id: str,
        child_results: list[tuple[str, list[Violation]]],
    ) -> list[Violation]:
        violations: list[Violation] = []
        for child_id, child_violations in child_results:
            for violation in child_violations:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=violation.path,
                        line=violation.line,
                        message=f"[{child_id}] {violation.message}",
                    )
                )
        return violations

    def _combine_any_logic(
        self,
        rule_id: str,
        child_results: list[tuple[str, list[Violation]]],
    ) -> list[Violation]:
        flagged_sets = [{violation.path for violation in child_violations} for _, child_violations in child_results]
        child_ids = [child_id for child_id, _ in child_results]
        failing = set.intersection(*flagged_sets) if flagged_sets else set()
        violations: list[Violation] = []
        for path in sorted(failing):
            violations.append(
                Violation(
                    rule_id=rule_id,
                    path=path,
                    line=None,
                    message=f"no acceptable form satisfied; failed all of: {', '.join(child_ids)}",
                )
            )
        return violations

    def _normalize_selectors(self, match_value: Any) -> list[re.Pattern[str]]:
        if not match_value:
            return []
        if isinstance(match_value, str):
            globs = [match_value]
        elif isinstance(match_value, list):
            globs = [str(item) for item in match_value]
        else:
            return []
        return [self._glob_to_regex(glob) for glob in globs if glob.strip()]

    def _load_ignore_selectors(self, repo_root: Path) -> list[re.Pattern[str]]:
        ignore_file = repo_root / ".sbgignore"
        try:
            text = ignore_file.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            return []
        selectors: list[re.Pattern[str]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            trailing_dir = line.endswith("/")
            base = line.rstrip("/")
            if not base:
                continue
            patterns: list[str] = []
            if trailing_dir:
                patterns.append(f"{base}/**")
            else:
                patterns.append(base)
                if "*" not in base and "?" not in base:
                    patterns.append(f"{base}/**")
            for pattern in patterns:
                selectors.append(self._glob_to_regex(pattern))
        return selectors

    def _is_ignored(self, repo_root: Path, raw_path: str | Path, selectors: list[re.Pattern[str]]) -> bool:
        relative_path = self._relative_posix(repo_root, raw_path)
        return any(selector.match(relative_path) for selector in selectors)

    def _select_paths(
        self,
        repo_root: Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
        selectors: list[re.Pattern[str]],
    ) -> list[str | Path]:
        if not selectors:
            return list(file_paths)
        selected: list[str | Path] = []
        for raw_path in file_paths:
            if raw_path is None:
                continue
            relative_path = self._relative_posix(repo_root, raw_path)
            if any(selector.match(relative_path) for selector in selectors):
                selected.append(raw_path)
        return selected

    def _relative_posix(self, repo_root: Path, raw_path: str | Path) -> str:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        else:
            candidate = candidate.expanduser().resolve()
        try:
            return candidate.relative_to(repo_root).as_posix()
        except ValueError:
            return candidate.as_posix()

    def _glob_to_regex(self, pattern: str) -> re.Pattern[str]:
        out: list[str] = ["^"]
        index = 0
        length = len(pattern)
        while index < length:
            char = pattern[index]
            if char == "*":
                if index + 1 < length and pattern[index + 1] == "*":
                    if index + 2 < length and pattern[index + 2] == "/":
                        out.append("(?:.*/)?")
                        index += 3
                        continue
                    out.append(".*")
                    index += 2
                    continue
                out.append("[^/]*")
            elif char == "?":
                out.append("[^/]")
            elif char in ".()[]{}+^$|\\":
                out.append("\\" + char)
            else:
                out.append(char)
            index += 1
        out.append("$")
        return re.compile("".join(out))

    def _apply_rule(
        self,
        rule: dict[str, Any],
        repo_root: Path,
        file_path: Path,
        relative_path: str,
        content: str | None,
        file_size: int,
        repo_context: dict[str, Any] | None = None,
    ) -> list[Violation]:
        rule_type = rule.get("type")
        rule_id = rule.get("id", rule_type)
        if rule_type == "placeholder-comments":
            return self._apply_placeholder_comments(rule, relative_path, content, rule_id)
        if rule_type == "marker-spam":
            return self._apply_marker_spam(rule, relative_path, content, rule_id)
        if rule_type == "empty-files":
            return self._apply_empty_files(rule, relative_path, file_size, rule_id)
        if rule_type == "long-lines":
            return self._apply_long_lines(rule, relative_path, content, rule_id)
        if rule_type == "file-size":
            return self._apply_file_size(rule, relative_path, file_size, rule_id)
        if rule_type == "button-actions":
            return self._apply_button_actions(rule, relative_path, content, rule_id)
        if rule_type == "button-types":
            return self._apply_button_types(rule, relative_path, content, rule_id)
        if rule_type == "form-labels":
            return self._apply_form_labels(rule, relative_path, content, rule_id)
        if rule_type == "asset-links":
            return self._apply_asset_links(rule, relative_path, content, rule_id, repo_context)
        if rule_type == "fully-defined-rules":
            return self._apply_fully_defined_rules(rule, relative_path, content, rule_id)
        if rule_type == "source-loadable":
            return self._apply_source_loadable(rule, repo_root, relative_path, content, rule_id)
        if rule_type == "dynamic-config":
            return self._apply_dynamic_config(rule, relative_path, content, rule_id)
        if rule_type == "merge-conflict-markers":
            return self._apply_merge_conflict_markers(rule, relative_path, content, rule_id)
        if rule_type == "secret-scan":
            return self._apply_secret_scan(rule, relative_path, content, rule_id)
        if rule_type == "debug-artifacts":
            return self._apply_debug_artifacts(rule, relative_path, content, rule_id)
        if rule_type == "trailing-whitespace":
            return self._apply_trailing_whitespace(rule, relative_path, content, rule_id)
        if rule_type == "final-newline":
            return self._apply_final_newline(rule, relative_path, content, rule_id)
        if rule_type == "python-syntax":
            return self._apply_python_syntax(rule, relative_path, content, rule_id, repo_context)
        if rule_type in AST_ANALYZERS:
            return self._apply_ast_rule(rule, relative_path, content, rule_id, repo_context, rule_type)
        return []

    def _python_ast(
        self,
        relative_path: str,
        content: str | None,
        repo_context: dict[str, Any] | None,
    ) -> Any:
        if content is None or not relative_path.endswith(".py"):
            return None
        cache = repo_context.setdefault("ast_cache", {}) if repo_context is not None else {}
        if relative_path in cache:
            return cache[relative_path]
        tree, _ = parse_module(content)
        cache[relative_path] = tree
        return tree

    def _apply_ast_rule(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
        repo_context: dict[str, Any] | None,
        rule_type: str,
    ) -> list[Violation]:
        if content is None or not relative_path.endswith(".py"):
            return []
        tree = self._python_ast(relative_path, content, repo_context)
        if tree is None:
            return []
        analyzer = AST_ANALYZERS[rule_type]
        findings = analyzer(rule, tree, relative_path)
        return [
            Violation(rule_id=rule_id, path=relative_path, line=line, message=message)
            for line, message in findings
        ]

    def _apply_python_syntax(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
        repo_context: dict[str, Any] | None,
    ) -> list[Violation]:
        del rule
        if content is None or not relative_path.endswith(".py"):
            return []
        tree, error = parse_module(content)
        if repo_context is not None:
            repo_context.setdefault("ast_cache", {})[relative_path] = tree
        if error is None:
            return []
        message = f"Python syntax error: {error.msg}"
        return [Violation(rule_id=rule_id, path=relative_path, line=error.lineno, message=message)]

    def _apply_trailing_whitespace(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line != line.rstrip(" \t"):
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=line_number,
                        message="trailing whitespace found",
                    )
                )
        return violations

    def _apply_final_newline(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if not content:
            return []
        if content.endswith("\n"):
            return []
        return [
            Violation(
                rule_id=rule_id,
                path=relative_path,
                line=len(content.splitlines()) or 1,
                message="file does not end with a newline",
            )
        ]

    def _apply_merge_conflict_markers(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        # Conflict markers are a fixed length run of a single character; building
        # the patterns dynamically keeps this very source file from matching itself.
        marker_specs = [
            ("<" * 7, "start"),
            ("|" * 7, "base"),
            (">" * 7, "end"),
        ]
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            for marker, position in marker_specs:
                if line.startswith(marker) and (len(line) == len(marker) or line[len(marker)] in {" ", "\t"}):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=line_number,
                            message=f"unresolved git merge conflict marker ({position}) found",
                        )
                    )
                    break
        return violations

    def _apply_secret_scan(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern, label in _SECRET_PATTERNS:
                if pattern.search(line):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=line_number,
                            message=f"possible committed secret detected ({label})",
                        )
                    )
                    break
        return violations

    def _apply_debug_artifacts(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        if content is None:
            return []
        suffix = Path(relative_path).suffix.lower()
        selected: tuple[tuple[re.Pattern[str], str], ...] = ()
        for suffixes, entries in _DEBUG_ARTIFACT_PATTERNS:
            if suffix in suffixes:
                selected = entries
                break
        if not selected:
            return []
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern, label in selected:
                if pattern.search(stripped):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=line_number,
                            message=f"debug artifact left in source ({label})",
                        )
                    )
                    break
        return violations

    def _apply_dynamic_config(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        if not self._is_dynamic_config_candidate(relative_path):
            return []

        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern, label in _DYNAMIC_CONFIG_PATTERNS:
                if pattern.search(stripped):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=line_number,
                            message=f"hard-coded {label} found: {stripped}",
                        )
                    )
                    break
        return violations

    def _is_dynamic_config_candidate(self, relative_path: str) -> bool:
        suffixes = {
            ".py",
            ".json",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".yml",
            ".yaml",
            ".toml",
            ".ini",
            ".cfg",
            ".sh",
            ".txt",
            ".md",
            ".html",
            ".css",
            ".vue",
            ".cjs",
            ".mjs",
            ".rb",
            ".go",
            ".java",
            ".php",
            ".swift",
            ".kt",
            ".rs",
        }
        path = Path(relative_path)
        if path.suffix.lower() in suffixes:
            return True
        return path.name.lower() in {"dockerfile", "makefile", "procfile", "readme"}

    def _apply_source_loadable(
        self,
        rule: dict[str, Any],
        repo_root: Path,
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        rules = payload.get("rules")
        if not isinstance(rules, list):
            return []

        violations: list[Violation] = []
        for index, candidate in enumerate(rules):
            if not isinstance(candidate, dict):
                continue
            rule_name = str(candidate.get("id") or candidate.get("type") or f"rule-{index + 1}")
            source_refs = candidate.get("source_refs")
            if not isinstance(source_refs, list):
                continue
            for ref_index, source_ref in enumerate(source_refs):
                if not isinstance(source_ref, dict):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=None,
                            message=f"rule '{rule_name}' has an invalid source ref entry at position {ref_index + 1}",
                        )
                    )
                    continue
                path_value = str(source_ref.get("path") or "").strip()
                if not path_value:
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=None,
                            message=f"rule '{rule_name}' has an empty source ref entry at position {ref_index + 1}",
                        )
                    )
                    continue
                target_path = Path(path_value).expanduser()
                if not target_path.is_absolute():
                    target_path = (repo_root / target_path).resolve()
                else:
                    target_path = target_path.resolve()
                try:
                    target_path.relative_to(repo_root)
                except ValueError:
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=None,
                            message=f"rule '{rule_name}' points to a source ref outside the repository: {path_value}",
                        )
                    )
                    continue
                if not target_path.exists() or not target_path.is_file():
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=None,
                            message=f"rule '{rule_name}' points to a missing file: {path_value}",
                        )
                    )
                    continue
                try:
                    target_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    violations.append(
                        Violation(
                            rule_id=rule_id,
                            path=relative_path,
                            line=None,
                            message=f"rule '{rule_name}' points to an unreadable file: {path_value}",
                        )
                    )
        return violations

    def _apply_fully_defined_rules(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None:
            return []
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        rules = payload.get("rules")
        if not isinstance(rules, list):
            return []
        violations: list[Violation] = []
        for index, candidate in enumerate(rules):
            if not isinstance(candidate, dict):
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=None,
                        message=f"rule {index + 1} is not a valid object",
                    )
                )
                continue
            rule_name = str(candidate.get("id") or candidate.get("type") or f"rule-{index + 1}")
            missing_fields: list[str] = []
            for field in ("description", "what", "why"):
                value = candidate.get(field)
                if not isinstance(value, str) or not value.strip():
                    missing_fields.append(field)
            source_refs = candidate.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                missing_fields.append("source_refs")
            else:
                valid_refs = []
                for ref in source_refs:
                    if isinstance(ref, dict) and isinstance(ref.get("path"), str) and str(ref.get("path", "")).strip():
                        valid_refs.append(ref)
                if len(valid_refs) != len(source_refs):
                    missing_fields.append("source_refs")
            if missing_fields:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=None,
                        message=(
                            f"rule '{rule_name}' is missing required definition fields: "
                            f"{', '.join(missing_fields)}"
                        ),
                    )
                )
        return violations

    def _apply_placeholder_comments(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        if content is None:
            return []
        patterns = self._collect_patterns(rule)
        if not patterns:
            return []
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            comment_body = self._strip_comment_prefix(stripped)
            if comment_body is None:
                continue
            comment_text = comment_body.lower()
            if any(self._matches_pattern(comment_text, pattern, rule, case_sensitive=False) for pattern in patterns):
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=line_number,
                        message=f"placeholder comment found: {stripped}",
                    )
                )
        return violations

    def _apply_marker_spam(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        if content is None:
            return []
        if self._should_skip_text_rule(relative_path):
            return []
        patterns = self._collect_patterns(rule, fallback=["TBD", "NOTE", "REVIEW"])
        threshold = int(rule.get("threshold", 3))
        total_count = 0
        for line in content.splitlines():
            for pattern in patterns:
                total_count += self._count_pattern_matches(line, pattern, rule)
        if total_count >= threshold:
            return [
                Violation(
                    rule_id=rule_id,
                    path=relative_path,
                    line=None,
                    message=f"marker spam detected with {total_count} occurrences (threshold {threshold})",
                )
            ]
        return []

    def _apply_empty_files(
        self,
        rule: dict[str, Any],
        relative_path: str,
        file_size: int,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if file_size == 0:
            return [Violation(rule_id=rule_id, path=relative_path, line=None, message="file is empty")]
        return []

    def _apply_long_lines(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        if content is None:
            return []
        if self._should_skip_text_rule(relative_path):
            return []
        max_length = int(rule.get("max_length", 120))
        patterns = self._collect_patterns(rule)
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if patterns and not any(
                self._matches_pattern(line, pattern, rule, case_sensitive=True)
                for pattern in patterns
            ):
                continue
            if len(line) > max_length:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=line_number,
                        message=f"line length {len(line)} exceeds {max_length}",
                    )
                )
        return violations

    def _apply_file_size(
        self,
        rule: dict[str, Any],
        relative_path: str,
        file_size: int,
        rule_id: str,
    ) -> list[Violation]:
        max_bytes = int(rule.get("max_bytes", 1024 * 1024))
        if file_size > max_bytes:
            return [
                Violation(
                    rule_id=rule_id,
                    path=relative_path,
                    line=None,
                    message=f"file size {file_size} exceeds {max_bytes} bytes",
                )
            ]
        return []

    def _apply_button_actions(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None or not self._should_scan_ui_markup(relative_path):
            return []
        violations: list[Violation] = []
        for match in re.finditer(r"<button\b([^>]*)>", content, re.IGNORECASE):
            attributes = match.group(1)
            if re.search(r"\bdata-action\s*=", attributes, re.IGNORECASE):
                continue
            if re.search(r"\bonclick\s*=", attributes, re.IGNORECASE):
                continue
            violations.append(
                Violation(
                    rule_id=rule_id,
                    path=relative_path,
                    line=self._line_number_for_offset(content, match.start()),
                    message="button is missing an explicit action hook",
                )
            )
        return violations

    def _apply_button_types(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None or not self._should_scan_ui_markup(relative_path):
            return []
        violations: list[Violation] = []
        for match in re.finditer(r"<button\b([^>]*)>", content, re.IGNORECASE):
            attributes = match.group(1)
            type_match = re.search(r"\btype\s*=\s*['\"]?([^'\"\s>]+)", attributes, re.IGNORECASE)
            if not type_match:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=self._line_number_for_offset(content, match.start()),
                        message="button is missing an explicit type attribute",
                    )
                )
                continue
            explicit_type = type_match.group(1).lower()
            if explicit_type not in {"button", "submit", "reset"}:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=self._line_number_for_offset(content, match.start()),
                        message=f"button type '{explicit_type}' is not a safe explicit type",
                    )
                )
        return violations

    def _apply_form_labels(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        del rule
        if content is None or not self._should_scan_ui_markup(relative_path):
            return []
        violations: list[Violation] = []
        controls = re.finditer(r"<(input|textarea|select)\b([^>]*)>", content, re.IGNORECASE)
        for match in controls:
            attributes = match.group(2)
            if re.search(r"\b(?:aria-label|aria-labelledby|title)\s*=", attributes, re.IGNORECASE):
                continue
            if re.search(r"\btype\s*=\s*['\"]?(?:hidden|button|submit|reset)", attributes, re.IGNORECASE):
                continue
            control_id = self._extract_attribute(attributes, "id")
            if control_id and re.search(
                rf"<label\b[^>]*\bfor\s*=\s*['\"]{re.escape(control_id)}['\"]",
                content,
                re.IGNORECASE,
            ):
                continue
            violations.append(
                Violation(
                    rule_id=rule_id,
                    path=relative_path,
                    line=self._line_number_for_offset(content, match.start()),
                    message="form control is missing an explicit label or accessible name",
                )
            )
        return violations

    def _apply_asset_links(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
        repo_context: dict[str, Any] | None = None,
    ) -> list[Violation]:
        del rule
        if content is None or not relative_path.endswith((".html", ".htm")):
            return []
        actions = re.findall(r"\bdata-action\s*=\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
        if not actions:
            return []
        files = repo_context.get("files", {}) if repo_context else {}
        script_content = "\n".join(
            script
            for path, script in files.items()
            if isinstance(script, str)
            and path.endswith((".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"))
        )
        if not script_content:
            return []
        violations: list[Violation] = []
        for action_name in sorted(set(actions)):
            if not re.search(rf"['\"]{re.escape(action_name)}['\"]", script_content, re.IGNORECASE):
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        path=relative_path,
                        line=None,
                        message=f"front-end action '{action_name}' is not linked from client-side script",
                    )
                )
        return violations

    def _should_scan_ui_markup(self, relative_path: str) -> bool:
        suffix = Path(relative_path).suffix.lower()
        return suffix in {".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}

    def _should_skip_text_rule(self, relative_path: str) -> bool:
        suffix = Path(relative_path).suffix.lower()
        return suffix in {
            ".css",
            ".cfg",
            ".html",
            ".htm",
            ".ini",
            ".json",
            ".md",
            ".markdown",
            ".toml",
            ".txt",
            ".yaml",
            ".yml",
        }

    def _line_number_for_offset(self, content: str, offset: int) -> int:
        return content.count("\n", 0, offset) + 1

    def _extract_attribute(self, attributes: str, attribute_name: str) -> str | None:
        pattern = rf"\b{re.escape(attribute_name)}\s*=\s*['\"]?([^'\"\s>]+)"
        match = re.search(pattern, attributes, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _collect_patterns(self, rule: dict[str, Any], fallback: list[str] | None = None) -> list[str]:
        patterns = rule.get("patterns")
        if patterns is None:
            pattern = rule.get("pattern")
            if pattern is None:
                return fallback or []
            patterns = [pattern]
        if isinstance(patterns, str):
            return [patterns]
        return [str(pattern) for pattern in patterns if pattern is not None]

    def _matches_pattern(self, text: str, pattern: str, rule: dict[str, Any], case_sensitive: bool) -> bool:
        if not pattern:
            return False
        if self._is_regex_rule(rule):
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return bool(re.search(pattern, text, flags))
            except re.error:
                return False
        if not case_sensitive:
            text = text.lower()
            pattern = pattern.lower()
        return pattern in text

    def _count_pattern_matches(self, text: str, pattern: str, rule: dict[str, Any]) -> int:
        if not pattern:
            return 0
        if self._is_regex_rule(rule):
            try:
                return len(re.findall(pattern, text, re.IGNORECASE))
            except re.error:
                return 0
        return text.upper().count(pattern.upper())

    def _is_regex_rule(self, rule: dict[str, Any]) -> bool:
        match_mode = rule.get("match_mode") or rule.get("pattern_type") or rule.get("mode")
        return str(match_mode).lower() == "regex"

    def _strip_comment_prefix(self, text: str) -> str | None:
        prefixes = ("//", "/*", "*", "*/", "#", "<!--", ";")
        for prefix in prefixes:
            if text.startswith(prefix):
                if prefix == "#" and text.startswith("##"):
                    return None
                return text[len(prefix) :].strip()
        return None
