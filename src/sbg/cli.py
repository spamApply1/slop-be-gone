from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import RuleEngine
from .manifest import resolve_manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sbg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("repo_root", help="repository root to scan")
    check_parser.add_argument("--manifest", dest="manifest", default=None, help="path to a custom manifest")
    check_parser.add_argument("--json", action="store_true", help="emit violations as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "check":
        parser.error("unsupported command")

    manifest_path = resolve_manifest_path(args.manifest)
    engine = RuleEngine.from_manifest_path(manifest_path)
    violations = engine.scan_repository(Path(args.repo_root))

    if violations:
        if args.json:
            print(json.dumps([violation.as_dict() for violation in violations]))
        else:
            for violation in violations:
                print(violation.format())
        return 1

    if args.json:
        print("[]")
    else:
        print("No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
