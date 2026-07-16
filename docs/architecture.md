# Architecture note

## Slop Be Gone vision

Slop Be Gone is an opinionated framework for reducing repository churn and
cleanup overhead without depending on centralized infrastructure. The core idea
is to let developers declare lightweight manifests that describe how their
workspace should be kept tidy, then run local automation to enforce those
rules.

The first implementation is intentionally simple: it scans a repository,
applies a default manifest, and fails fast on obvious hygiene violations. That
makes it useful both for local development and for CI pipelines that need to
refuse noisy or low-quality AI output.

## Design goals

- Keep the default experience local-first so contributors can iterate quickly without network dependencies.
- Make policies explicit through manifest files that can be reviewed, tested, and versioned.
- Favor automation-friendly primitives that can be reused in scripts, CI jobs, and developer tooling.
- Treat repository hygiene as a contract that can be enforced by humans and AI agents alike.

## Current structure

- `src/sbg/engine.py` owns the rule engine, violation model, and repository scanning loop.
- `src/sbg/manifest.py` loads the JSON manifest used by the engine.
- `src/sbg/cli.py` provides the user-facing CLI with text and JSON output.
- `sbg_manifest.json` is the default rule set for the current release.
- `tests/` contains the fixture-based and CLI tests that keep the rules honest.
