from __future__ import annotations

import re
from pathlib import Path
from typing import Any


DEFAULT_IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
}

DEFAULT_EXTENSIONS = {".html", ".htm", ".js", ".ts", ".tsx", ".jsx", ".css", ".py", ".sh", ".json"}

_SCRIPT_SUFFIXES = {".js", ".ts", ".tsx", ".jsx"}


def discover_source_files(repo_root: str | Path, scope_path: str | Path | None = None) -> list[Path]:
    root = Path(repo_root).expanduser().resolve()
    if scope_path is not None:
        candidate = Path(scope_path).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if candidate.exists() and candidate.is_dir():
            root = candidate
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in DEFAULT_IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue
        files.append(path)
    files.sort()
    return files


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _unique_sorted(matches: list[str]) -> list[str]:
    return sorted(set(matches))


class _ScriptMapBuilder:
    """Accumulates the node/edge graph for :func:`build_script_map`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self._node_index: dict[str, str] = {}

    def add_node(self, node_id: str, label: str, kind: str) -> str:
        if node_id not in self._node_index:
            self._node_index[node_id] = node_id
            self.nodes.append({"id": node_id, "label": label, "kind": kind})
        return node_id

    def add_edge(self, source: str, target: str, kind: str) -> None:
        if source != target:
            self.edges.append({"from": source, "to": target, "kind": kind})

    def map_file(self, path: Path, files: list[Path]) -> None:
        relative_path = path.relative_to(self.root).as_posix()
        file_node_id = self.add_node(f"file:{relative_path}", path.name, "file")
        content = _read(path)
        suffix = path.suffix.lower()
        if suffix in {".html", ".htm"}:
            self._map_html(file_node_id, content, files)
        elif suffix == ".css":
            self._map_css(file_node_id, content)
        elif suffix in _SCRIPT_SUFFIXES:
            self._map_script(file_node_id, content)
        elif suffix == ".py":
            self._map_python(file_node_id, content)

    def _map_html(self, file_node_id: str, content: str, files: list[Path]) -> None:
        for action_name in _unique_sorted(
            re.findall(r"\bdata-action\s*=\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
        ):
            action_node_id = self.add_node(f"action:{action_name}", action_name, "action")
            self.add_edge(file_node_id, action_node_id, "declares")
            self._link_handlers(action_node_id, action_name, files)
        for class_name in _unique_sorted(
            re.findall(r"\bclass\s*=\s*['\"][^'\"]*\b([A-Za-z0-9_-]+)\b", content, re.IGNORECASE)
        ):
            class_node_id = self.add_node(f"class:{class_name}", class_name, "class")
            self.add_edge(file_node_id, class_node_id, "uses-class")
        for element_id in _unique_sorted(
            re.findall(r"\bid\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", content, re.IGNORECASE)
        ):
            id_node_id = self.add_node(f"id:{element_id}", element_id, "id")
            self.add_edge(file_node_id, id_node_id, "uses-id")

    def _link_handlers(self, action_node_id: str, action_name: str, files: list[Path]) -> None:
        for other_path in files:
            if other_path.suffix.lower() not in _SCRIPT_SUFFIXES:
                continue
            if re.search(rf"['\"]{re.escape(action_name)}['\"]", _read(other_path), re.IGNORECASE):
                handler_node_id = self.add_node(f"handler:{action_name}", action_name, "handler")
                self.add_edge(action_node_id, handler_node_id, "dispatches")

    def _map_css(self, file_node_id: str, content: str) -> None:
        for selector in _unique_sorted(re.findall(r"(?:^|[\s,>+~])([.#][A-Za-z0-9_-]+)", content)):
            style_node_id = self.add_node(f"style:{selector}", selector, "style")
            self.add_edge(file_node_id, style_node_id, "styles")

    def _map_script(self, file_node_id: str, content: str) -> None:
        for function_name in _unique_sorted(
            re.findall(r"\b(?:function|const|let|var)\s+([A-Za-z0-9_]+)\s*(?:=|\()", content)
        ):
            function_node_id = self.add_node(f"function:{function_name}", function_name, "function")
            self.add_edge(file_node_id, function_node_id, "defines")

    def _map_python(self, file_node_id: str, content: str) -> None:
        for function_name in _unique_sorted(re.findall(r"^def\s+([A-Za-z0-9_]+)\s*\(", content, flags=re.MULTILINE)):
            function_node_id = self.add_node(f"function:{function_name}", function_name, "function")
            self.add_edge(file_node_id, function_node_id, "defines")
        for class_name in _unique_sorted(re.findall(r"^class\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)):
            class_node_id = self.add_node(f"class:{class_name}", class_name, "class")
            self.add_edge(file_node_id, class_node_id, "defines")


def build_script_map(repo_root: str | Path, scope_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    files = discover_source_files(root, scope_path=scope_path)
    builder = _ScriptMapBuilder(root)

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        builder.add_node(f"file:{relative_path}", path.name, "file")

    for path in files:
        builder.map_file(path, files)

    return {
        "repo_root": str(root),
        "nodes": builder.nodes,
        "edges": builder.edges,
        "summary": {
            "node_count": len(builder.nodes),
            "edge_count": len(builder.edges),
        },
    }
