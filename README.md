# slop-be-gone (sbg)

**Make AI slop fail at the gate before it fossilizes in your repo.**

`slop-be-gone` is a local-first code hygiene framework for agentic codebases:
repos where agents generate enough code that review becomes damage control. The
fix is not another dashboard full of vibes. It is executable standards, a
manifest, and a CLI that fails loudly before generated cruft becomes architecture.

## ⚡ Quickstart

```bash
python3 -m pip install -e .
PYTHONPATH="$PWD/src" ./sbg check docs --manifest "$PWD/sbg_self_manifest.json" \
  --json --strict
```

Clean JSON is the sound of a gate doing its job:

```json
[]
```

Scan the whole repository with the self policy:

```bash
PYTHONPATH="$PWD/src" ./sbg check . --manifest ./sbg_self_manifest.json
# No blocking violations found (warnings may still be printed).
```

Wire it into commits:

```bash
PYTHONPATH="$PWD/src" ./sbg install-hooks --manifest ./sbg_self_manifest.json .
PYTHONPATH="$PWD/src" ./sbg check --staged . --manifest ./sbg_self_manifest.json
```

Use the shared automation contract in CI or a harness:

```bash
./sbg check . --manifest ./sbg_manifest.json --json --strict
```

## 🧱 What it enforces

The bundled manifest is intentionally opinionated. It is still just JSON, so you
can disable rules, scope them with `include` and `exclude`, or lower them to
`warning` while rolling out.

| Rule family | Rule IDs | What fails |
| --- | --- | --- |
| Text hygiene | `placeholder-comments`<br>`marker-spam`<br>`long-lines` | Scaffold leftovers and dense lines. |
| File shape | `empty-files`<br>`file-size`<br>`trailing-whitespace`<br>`final-newline` | Empty, huge, or noisy files. |
| UI integrity | `button-actions`<br>`button-types`<br>`form-labels`<br>`asset-links` | Unclear or unwired UI. |
| Policy quality | `fully-defined-rules`<br>`source-loadable`<br>`dynamic-config` | Opaque or brittle policy. |
| Repo hazards | `merge-conflict-markers`<br>`secret-scan`<br>`debug-artifacts` | Broken merges and leaks. |
| Python AST checks | `python-syntax`<br>`python-bare-except`<br>`python-broad-except` | Parse and exception traps. |
| Python design checks | `python-mutable-default`<br>`python-eval-exec` | State leaks and dynamic execution. |
| Python complexity | `python-function-args`<br>`python-function-length`<br>`python-nesting-depth` | Complexity. |
| Composition | `composite` | Multiple checks bundled into one higher-level policy idea. |

## 🧠 How it works

- `sbg check` resolves a manifest, validates it, scans files, prints violations,
  and exits non-zero when blocking rules fire.
- `--json` emits machine-readable violations for CI, agents, and scripts.
- `--strict` treats warning-severity findings as blocking, useful once a repo is
  ready to make the policy hard.
- `--staged` scans only `git diff --cached --name-only`, which is what the
  installed pre-commit hook uses.
- `--fix` safely repairs trailing whitespace and missing final newlines before
  reporting anything else.
- Python checks parse real ASTs for syntax, exception, mutable-default,
  dynamic-execution, argument-count, function-length, and nesting rules.
- `sbg report` groups findings with suggestions. `sbg script-map` builds a JSON
  map of scripts, UI actions, and bridge relationships for inspection tooling.
- The optional `web/` dashboard runs locally for browsing scans and bridge
  context. The CLI does not require a hosted service.

## 🧬 Part of the be-gone ecosystem

The family is a set of small, composable enforcement gates for codebases where
AI agents generate large chunks of the tree:

- [slop-be-gone](https://github.com/spamApply1/slop-be-gone) — code hygiene:
  comments, file shape, Python traps, secrets, debug leftovers, and more.
- [design-be-gone](https://github.com/spamApply1/design-be-gone) — design
  standards: markup shape, heading discipline, filename case, and exports.
- [chaos-be-gone](https://github.com/spamApply1/chaos-be-gone) — workflow
  sanity: CI, hooks, ignore files, README presence, and workflow secret checks.

Together, they are the quality backstop for local AI code factories: let agents
move fast, then make the standards executable enough to push back.

## 🧾 Manifest-driven by design

A manifest is a JSON object with rules:

```json
{
  "rules": [
    { "id": "readability", "type": "long-lines", "max_length": 120 },
    { "id": "python-ast", "type": "python-syntax", "enabled": true }
  ]
}
```

Each rule can carry `id`, `type`, `enabled`, `severity`, `include`, `exclude`,
and rule-specific thresholds. Invalid manifests fail validation before a scan so
broken policy does not silently pass.

## 🛠 Common commands

```bash
./sbg init path/to/repo
./sbg validate . --manifest ./sbg_manifest.json
./sbg check . --fix
./sbg report .
./sbg script-map . --output ./script-map.json
./scripts/start-dashboard.sh
```

Installer scripts are included for bringing SBG to another repository:

```bash
./scripts/install-sbg-hook.sh path/to/repo
./scripts/install-sbg-hook.sh path/to/repo path/to/manifest.json
```

PowerShell users can run `scripts/install-sbg-hook.ps1` with `-TargetRepo` and
an optional `-ManifestPath`.

## 🧪 Development

```bash
PYTHONPATH="$PWD/src" python3 -m unittest discover -s tests -v
PYTHONPATH="$PWD/src" ./sbg validate . --manifest ./sbg_self_manifest.json
PYTHONPATH="$PWD/src" ./sbg check . --manifest ./sbg_self_manifest.json
```

Project map:

- `src/sbg/engine.py` — rule engine and violation model.
- `src/sbg/ast_analysis.py` — AST-based Python analyzers.
- `src/sbg/manifest.py` — manifest loading and bundled policy resolution.
- `src/sbg/cli.py` — CLI entry point.
- `src/sbg/data/` — bundled manifest, concepts, and rule guide.
- `web/` — local dashboard assets.
- `tests/` — CLI, engine, AST, packaging, script-map, and web UI coverage.

## 🧭 Philosophy

The north star is brutally simple: define reality with standards and intent.
Push enforcement outward until there is one canonical way for each thing to
exist, then let humans and local agents move fast inside that rail.

If that makes your inner build-system gremlin happy, ⭐ star the repo, try it on
a codebase that an agent has been enthusiastically "helping," and compose a
manifest that encodes your taste.
