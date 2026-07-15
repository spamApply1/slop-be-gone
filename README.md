# Slop Be Gone

Slop Be Gone is a local-first hygiene framework for agentic codebases. It uses manifest-driven rules to flag slop patterns that tend to show up when AI-generated patches are allowed to drift: placeholder comments, TODO/FIXME/XXX spam, empty files, overly long lines, and oversized files.

The project is inspired by the manifest-driven spirit of idud-hygiene, but it is intentionally opinionated for the agentic-only workflow where quality gates must fail loudly and early.

## What it does

- Scans a repository with a default manifest in `sbg_manifest.json`
- Prints clear violations and exits non-zero when damage is detected
- Supports JSON output for automation and CI
- Keeps the rule set easy to review, test, and extend

## Quick start

```bash
python3 -m pip install -e .
./sbg check .
```

For automation-friendly output:

```bash
./sbg check . --json
```

## Project layout

- `src/sbg/engine.py` contains the rule engine and violation model
- `src/sbg/manifest.py` loads the JSON manifest
- `src/sbg/cli.py` provides the CLI entry point
- `sbg_manifest.json` holds the default rules
- `tests/` contains fixture-based and CLI tests

## Development

```bash
python3 -m unittest discover -s tests -v
```
