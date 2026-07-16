from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parent
_BUNDLED_DATA = _PACKAGE_ROOT / "data"
_CHECKOUT_ROOT = _PACKAGE_ROOT.parents[1]


def _default_data_path(repo_filename: str, bundled_filename: str) -> Path:
    checkout_copy = _CHECKOUT_ROOT / repo_filename
    if checkout_copy.is_file():
        return checkout_copy
    return _BUNDLED_DATA / bundled_filename


def resolve_manifest_path(path: str | Path | None = None, repo_root: str | Path | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            if repo_root is not None:
                candidate = (Path(repo_root).expanduser() / candidate).resolve()
            else:
                candidate = candidate.resolve()
        return candidate.resolve()
    return _default_data_path("sbg_manifest.json", "default_manifest.json")


def resolve_concepts_path(path: str | Path | None = None, repo_root: str | Path | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            if repo_root is not None:
                candidate = (Path(repo_root).expanduser() / candidate).resolve()
            else:
                candidate = candidate.resolve()
        return candidate.resolve()
    return _default_data_path("sbg_concepts.json", "concepts.json")


def resolve_bundled_docs_path() -> Path | None:
    for candidate in (_CHECKOUT_ROOT / "docs" / "hygiene-rules.md", _BUNDLED_DATA / "hygiene-rules.md"):
        if candidate.is_file():
            return candidate
    return None


def load_manifest(path: str | Path | None = None, repo_root: str | Path | None = None) -> dict[str, Any]:
    manifest_path = resolve_manifest_path(path, repo_root=repo_root)
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_manifest(path: str | Path, manifest: dict[str, Any], repo_root: str | Path | None = None) -> Path:
    manifest_path = resolve_manifest_path(path, repo_root=repo_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest_path


def load_concepts(path: str | Path | None = None, repo_root: str | Path | None = None) -> list[dict[str, Any]]:
    concepts_path = resolve_concepts_path(path, repo_root=repo_root)
    with concepts_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        concepts = payload.get("concepts")
        if isinstance(concepts, list):
            return [dict(item) for item in concepts]
    return []
