# Self-hygiene manifest and hook loop

SBG is meant for anyone who wants a lightweight, local-first guardrail for
AI-assisted changes. This repository uses a dedicated manifest,
`sbg_self_manifest.json`, so the tool can police itself before changes reach
the main branch.

## How this repository uses SBG

- `sbg_self_manifest.json` is the repository-specific policy for this
  project.
- `./sbg install-hooks --manifest ./sbg_self_manifest.json .` installs a
  pre-commit hook that runs SBG against staged files before each commit.
- `./sbg check --staged --manifest ./sbg_self_manifest.json .` is the manual
  equivalent for local validation.
- `./sbg report --manifest ./sbg_self_manifest.json .` produces a grouped
  summary of what still needs cleanup.

## Install the git hook loop

1. Install the package in editable mode:
   ```bash
   python3 -m pip install -e .
   ```
2. Install the repository hook:
   ```bash
   ./sbg install-hooks --manifest ./sbg_self_manifest.json .
   ```
3. Stage your changes and commit normally. The pre-commit hook will run
   `sbg check --staged` using the self-hygiene manifest.
4. If you want to reproduce the same check manually, run:
   ```bash
   ./sbg check --staged --manifest ./sbg_self_manifest.json .
   ```

## Apply the same workflow to other repositories

1. Copy `sbg_self_manifest.json` into the target repository, or create a new
   manifest with rules that fit that repository's language, conventions, and
   risk profile.
2. Tune the rule set to match the repository's expectations. A small
   repository can start with a lightweight manifest; larger teams can add
   stricter rules for generated code, tests, or docs.
3. Install the hook with the repository's manifest:
   ```bash
   ./sbg install-hooks --manifest path/to/manifest.json .
   ```
4. Keep the policy versioned alongside the repository so changes to the
   hygiene rules are reviewed like any other change.
5. For an enterprise rollout, use the same manifest template across
   repositories, document the onboarding path, and make the hook part of the
   default development workflow. That keeps standards consistent without
   forcing every team to invent its own process from scratch.
