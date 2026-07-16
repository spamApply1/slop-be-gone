from __future__ import annotations

import os
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
        return self.scan_paths(repo_root, (path for path, _ in files))

    def scan_paths(
        self,
        repo_root: str | Path,
        file_paths: list[str | Path] | tuple[str | Path, ...] | set[str | Path],
    ) -> list[Violation]:
        repo_root = Path(repo_root).expanduser().resolve()
        violations: list[Violation] = []
        rules = [rule for rule in self.manifest.get("rules", []) if rule.get("enabled", True)]

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
                violations.extend(self._apply_rule(rule, repo_root, candidate, relative_path, content, file_size))

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

    def _apply_rule(
        self,
        rule: dict[str, Any],
        repo_root: Path,
        file_path: Path,
        relative_path: str,
        content: str | None,
        file_size: int,
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
        return []

    def _apply_placeholder_comments(
        self,
        rule: dict[str, Any],
        relative_path: str,
        content: str | None,
        rule_id: str,
    ) -> list[Violation]:
        if content is None:
            return []
        patterns = [pattern.lower() for pattern in rule.get("patterns", [])]
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
            if any(pattern in comment_text for pattern in patterns):
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
        markers = [marker.upper() for marker in rule.get("patterns", ["TODO", "FIXME", "XXX"])]
        threshold = int(rule.get("threshold", 3))
        total_count = 0
        for line in content.splitlines():
            upper_line = line.upper()
            for marker in markers:
                total_count += upper_line.count(marker)
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
        max_length = int(rule.get("max_length", 120))
        violations: list[Violation] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
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

    def _strip_comment_prefix(self, text: str) -> str | None:
        prefixes = ("//", "/*", "*", "*/", "#", "<!--", ";")
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix) :].strip()
        return None
