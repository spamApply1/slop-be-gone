#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/install-sbg-hook.sh [target-repo] [manifest-path]

Installs SBG in editable mode into the current Python environment, then installs
an SBG pre-commit hook into the target repository. If a manifest path is
provided, the hook will use that manifest for staged checks.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 2 ]]; then
  usage >&2
  exit 1
fi

target_repo="${1:-.}"
manifest_path="${2:-}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sbg_repo_root="$(cd "${script_dir}/.." && pwd)"

if [[ -x "${sbg_repo_root}/.venv/bin/python" ]]; then
  python_bin="${sbg_repo_root}/.venv/bin/python"
elif [[ -x "${sbg_repo_root}/.venv/Scripts/python.exe" ]]; then
  python_bin="${sbg_repo_root}/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  echo "Python 3 is required to install SBG." >&2
  exit 1
fi

if [[ ! -d "${target_repo}" ]]; then
  echo "Target repository not found: ${target_repo}" >&2
  exit 1
fi

target_repo_path="$(cd "${target_repo}" && pwd)"

echo "Installing SBG from ${sbg_repo_root}..."
pip_args=(--quiet --disable-pip-version-check)
if [[ "${python_bin}" != "${sbg_repo_root}/.venv/"* ]]; then
  pip_args+=(--user)
fi
"${python_bin}" -m pip install "${pip_args[@]}" -e "${sbg_repo_root}"

echo "Installing SBG hook into ${target_repo_path}..."
if [[ -n "${manifest_path}" ]]; then
  "${python_bin}" -m sbg.cli install-hooks "${target_repo_path}" --manifest "${manifest_path}"
else
  "${python_bin}" -m sbg.cli install-hooks "${target_repo_path}"
fi
