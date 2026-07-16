from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .engine import RuleEngine, validate_manifest
from .manifest import resolve_bundled_docs_path, resolve_manifest_path
from .script_maps import build_script_map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sbg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("repo_root", help="repository root to scan")
    check_parser.add_argument(
        "--manifest",
        dest="manifest",
        default=None,
        help="path to a custom manifest",
    )
    check_parser.add_argument("--json", action="store_true", help="emit violations as JSON")
    check_parser.add_argument(
        "--staged",
        action="store_true",
        help="scan only staged files from git diff --cached --name-only",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warning-severity violations as failures too",
    )
    check_parser.add_argument(
        "--fix",
        action="store_true",
        help="auto-fix violations that support it (trailing whitespace, final newline) before reporting",
    )

    install_parser = subparsers.add_parser("install-hooks")
    install_parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="repository root to install the hook into",
    )
    install_parser.add_argument(
        "--manifest",
        dest="manifest",
        default=None,
        help="path to a custom manifest",
    )

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("repo_root", help="repository root to scan")
    report_parser.add_argument("--manifest", dest="manifest", default=None, help="path to a custom manifest")

    script_map_parser = subparsers.add_parser("script-map")
    script_map_parser.add_argument("repo_root", nargs="?", default=".", help="repository root to analyze")
    script_map_parser.add_argument("--output", dest="output", default=None, help="write the script map JSON to a file")

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="repository root whose manifest should be validated",
    )
    validate_parser.add_argument("--manifest", dest="manifest", default=None, help="path to a custom manifest")

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="repository root to scaffold an SBG manifest into",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing sbg_manifest.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return run_check(args, parser)
    if args.command == "install-hooks":
        return install_hooks(args.repo_root, args.manifest)
    if args.command == "report":
        return run_report(args)
    if args.command == "script-map":
        return run_script_map(args)
    if args.command == "validate":
        return run_validate(args)
    if args.command == "init":
        return run_init(args)

    parser.error("unsupported command")


def resolve_scan_manifest(manifest: str | Path | None, repo_root: Path) -> Path:
    if manifest is not None:
        return resolve_manifest_path(manifest, repo_root=repo_root)
    repo_manifest = (repo_root / "sbg_manifest.json").resolve()
    if repo_manifest.is_file():
        return repo_manifest
    return resolve_manifest_path(None)


def run_check(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = resolve_scan_manifest(args.manifest, repo_root)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Manifest is not valid JSON ({manifest_path}): {exc.msg}", file=sys.stderr)
        return 1

    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        print(f"Manifest {manifest_path} is invalid; refusing to scan with broken policy:", file=sys.stderr)
        for error in manifest_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    engine = RuleEngine(manifest)
    if args.fix:
        if args.staged:
            fixed = engine.autofix_staged_files(repo_root)
        else:
            fixed = engine.autofix_repository(repo_root)
        if not args.json:
            for fixed_path in fixed:
                print(f"fixed {fixed_path}")
            if fixed:
                print(f"Auto-fixed {len(fixed)} file(s).")

    if args.staged:
        violations = engine.scan_staged_files(repo_root)
    else:
        violations = engine.scan_repository(repo_root)

    if args.json:
        print(json.dumps([violation.as_dict() for violation in violations]))
    else:
        for violation in violations:
            print(violation.format())

    blocking = [v for v in violations if v.severity == "error" or args.strict]
    warnings = [v for v in violations if v.severity == "warning"]
    if blocking:
        return 1
    if not args.json:
        if warnings:
            print(f"No blocking violations found ({len(warnings)} warning(s)).")
        else:
            print("No violations found.")
    return 0


def install_hooks(repo_root: str | Path, manifest: str | Path | None = None) -> int:
    repo_root = Path(repo_root).expanduser().resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        print(f"Not a git repository: {repo_root}", file=sys.stderr)
        return 1

    git_root = Path(result.stdout.strip()).expanduser().resolve()
    try:
        hooks_result = subprocess.run(
            ["git", "-C", str(git_root), "rev-parse", "--git-path", "hooks"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        print(f"Unable to resolve hooks directory for {git_root}", file=sys.stderr)
        return 1

    hooks_dir = Path(hooks_result.stdout.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = git_root / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)

    selected_manifest = None
    if manifest is not None:
        selected_manifest = Path(manifest).expanduser()
        if not selected_manifest.is_absolute():
            selected_manifest = (repo_root / selected_manifest).resolve()

    hook_path = hooks_dir / "pre-commit"
    python_executable = shlex.quote(sys.executable)
    command = f'exec {python_executable} -m sbg.cli check --staged "$repo_root"'
    if selected_manifest is not None:
        command += f" --manifest {shlex.quote(str(selected_manifest))}"

    pythonpath_export = ""
    src_dir = git_root / "src"
    if src_dir.exists():
        pythonpath_export = (
            f'export PYTHONPATH={shlex.quote(str(src_dir))}${{PYTHONPATH:+:${{PYTHONPATH}}}}\n'
        )

    hook_script = f"""#!/usr/bin/env bash
set -euo pipefail
repo_root={shlex.quote(str(git_root))}
{pythonpath_export}{command}
"""
    hook_path.write_text(hook_script, encoding="utf-8")
    hook_path.chmod(0o755)
    print(f"Installed pre-commit hook at {hook_path}")
    return 0


def run_report(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = resolve_scan_manifest(args.manifest, repo_root)
    engine = RuleEngine.from_manifest_path(manifest_path)
    violations = engine.scan_repository(repo_root)
    if not violations:
        print("No violations found.")
        return 0

    grouped: dict[str, list[Any]] = {}
    for violation in violations:
        grouped.setdefault(violation.rule_id, []).append(violation)

    print(f"Hygiene report for {repo_root}")
    for rule_id in sorted(grouped):
        rule_violations = grouped[rule_id]
        print(f"{rule_id} ({len(rule_violations)})")
        for violation in rule_violations:
            location = violation.path
            if violation.line is not None:
                location = f"{location}:{violation.line}"
            print(f"  - {location}: {violation.message}")
        print(f"  Suggestion: {suggestion_for_rule(rule_id)}")
    return 1


def run_script_map(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    payload = build_script_map(repo_root)
    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_path).resolve()
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote script map to {output_path}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


def run_validate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = resolve_scan_manifest(args.manifest, repo_root)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Manifest is not valid JSON ({manifest_path}): {exc.msg}", file=sys.stderr)
        return 1

    errors = validate_manifest(manifest)
    if errors:
        print(f"Manifest {manifest_path} has {len(errors)} problem(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    rule_count = len(manifest.get("rules", []))
    print(f"Manifest {manifest_path} is valid ({rule_count} rule(s)).")
    return 0


def run_init(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    bundled_manifest = resolve_manifest_path(None)
    target_manifest = repo_root / "sbg_manifest.json"

    if target_manifest.exists() and not args.force:
        print(
            f"Refusing to overwrite existing {target_manifest}; pass --force to replace it.",
            file=sys.stderr,
        )
        return 1

    try:
        manifest_text = bundled_manifest.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Bundled manifest not found at {bundled_manifest}", file=sys.stderr)
        return 1

    repo_root.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(manifest_text, encoding="utf-8")
    written = [target_manifest]

    bundled_docs = resolve_bundled_docs_path()
    if bundled_docs is not None:
        target_docs = repo_root / "docs" / "hygiene-rules.md"
        if not target_docs.exists() or args.force:
            target_docs.parent.mkdir(parents=True, exist_ok=True)
            target_docs.write_text(bundled_docs.read_text(encoding="utf-8"), encoding="utf-8")
            written.append(target_docs)

    for path in written:
        print(f"Wrote {path}")
    print("Next: run './sbg install-hooks .' then './sbg check .' to enforce hygiene.")
    return 0


def suggestion_for_rule(rule_id: str) -> str:
    suggestions = {
        "placeholder-comments": "Remove placeholder comments or sample content before committing.",
        "marker-spam": "Replace marker spam with actionable notes and clear follow-ups.",
        "empty-files": "Delete empty files or add meaningful content before committing.",
        "long-lines": "Wrap or refactor long lines to keep the codebase readable.",
        "file-size": "Split large files or move generated content elsewhere.",
        "merge-conflict-markers": "Resolve the git conflict and remove all conflict markers before committing.",
        "secret-scan": "Remove the credential, rotate it, and load it from the environment instead.",
        "debug-artifacts": "Remove debugger/console/breakpoint statements left over from debugging.",
        "trailing-whitespace": "Strip trailing spaces and tabs from the flagged lines.",
        "final-newline": "Add a single trailing newline at the end of the file.",
    }
    return suggestions.get(rule_id, "Review these findings and fix the underlying issue before committing.")


if __name__ == "__main__":
    sys.exit(main())
