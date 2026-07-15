from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_manifest_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "sbg_manifest.json"


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = resolve_manifest_path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
