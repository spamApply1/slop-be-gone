# Slop Be Gone

Slop Be Gone is a local-first hygiene framework for agentic codebases. It is
meant for anyone who wants a lightweight, repository-friendly way to keep
AI-assisted changes from drifting into slop. It uses manifest-driven rules to
flag common hygiene failures such as placeholder comments, TODO/FIXME/XXX
spam, empty files, overly long lines, and oversized files.

The project is inspired by the manifest-driven spirit of idud-hygiene, but it
is intentionally opinionated for the agentic-only workflow where quality gates
must fail loudly and early. This repository uses SBG to police itself with a
self-hygiene manifest and a pre-commit hook loop.

## What it does

- Scans a repository with a default manifest in `sbg_manifest.json`
- Prints clear violations and exits non-zero when damage is detected
- Supports staged-file checks with `sbg check --staged`
- Installs a pre-commit hook with `sbg install-hooks`
- Supports one-command installer scripts for other repositories
- Produces a human-readable report with `sbg report`
- Supports JSON output for automation and CI
- Ships with a lightweight local web dashboard in `web/` for scanning repositories and reviewing findings
- Can generate repeatable script/bridge maps with `sbg script-map` so UI
  relationships and handler wiring stay inspectable
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

To enforce hygiene on staged changes before a commit:

```bash
./sbg install-hooks
./sbg check --staged .
```

To get a grouped summary with suggestions:

```bash
./sbg report .
```

To launch the local dashboard, run:

```bash
./scripts/start-dashboard.sh
```

You can also run `python3 web/server.py` directly if you want to customize the host or port.

To generate a repeatable script map for the current repository (or a target path), run:

```bash
./sbg script-map . --output ./script-map.json
```

That JSON graph is used by the dashboard to surface bridge context and
related assets when you inspect a rule, violation, or source file.

Then open the dashboard URL shown by the server in your browser. The
repository field starts filled with the current git repository root, so the
dashboard defaults to the repo you launched it from.

## Self-policing workflow

This repository uses `sbg_self_manifest.json` as its self-hygiene policy and
installs a pre-commit hook that runs SBG against staged changes before each
commit. The same pattern is reusable for other repositories:

```bash
python3 -m pip install -e .
./sbg install-hooks --manifest ./sbg_self_manifest.json .
./sbg check --staged --manifest ./sbg_self_manifest.json .
```

See [docs/self-hygiene.md](docs/self-hygiene.md) for the full hook-based
commit loop and the intended enterprise rollout.

## Install SBG into another repository

If you want to bring SBG to a different git repository, run one of the
installer scripts in this checkout:

```bash
./scripts/install-sbg-hook.sh /path/to/target-repo
./scripts/install-sbg-hook.sh /path/to/target-repo ./path/to/manifest.json
```

For PowerShell:

```powershell
pwsh -File .\scripts\install-sbg-hook.ps1 -TargetRepo C:\path\to\target-repo
pwsh -File .\scripts\install-sbg-hook.ps1 -TargetRepo C:\path\to\target-repo -ManifestPath .\path\to\manifest.json
```

The scripts install SBG in editable mode into the current Python environment and
then install a pre-commit hook into the target repository. The optional manifest
path is passed through to SBG's hook installer. See
[docs/hygiene-rules.md](docs/hygiene-rules.md) for a human-readable guide to the
default rule set.

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
