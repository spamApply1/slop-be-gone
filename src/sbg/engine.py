from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import load_manifest


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


@dataclass(frozen=True)
class Violation:
    rule_id: str
    path: str
    line: int | None
    message: str

    def format(self) -> str:
        location = self.path
        if self.line is not None:
            location = f"{location}:{self.line}"
        return f"{location}: [{self.rule_id}] {self.message}"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"rule_id": self.rule_id, "path": self.path, "message": self.message}
        if self.line is not None:
            payload["line"] = self.line
        return payload


class RuleEngine:
    def __init__(self, manifest: dict[str, Any] | None = None):
        self.manifest = manifest or {"rules": []}

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
        repo_context = self._build_repo_context(repo_root, file_paths)

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
            file_size = candidate.stat().st_size
            content = self._read_text(candidate)
            for rule in rules:
                violations.extend(
                    self._apply_rule(
                        rule,
                        repo_root,
                        candidate,
                        relative_path,
                        content,
                        file_size,
                        repo_context,
                    )
                )

        return sorted(violations, key=lambda violation: (violation.path, violation.line or 0, violation.rule_id))

    def scan_staged_files(self, repo_root: str | Path) -> list[Violation]:
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
            return []

        staged_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return self.scan_paths(git_root, staged_paths)

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
        return []

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

        patterns = [
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
        ]

        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern, label in patterns:
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