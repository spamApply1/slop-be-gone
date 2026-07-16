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


def build_script_map(repo_root: str | Path, scope_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    files = discover_source_files(root, scope_path=scope_path)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_index: dict[str, str] = {}

    def add_node(node_id: str, label: str, kind: str) -> str:
        if node_id in node_index:
            return node_id
        node_index[node_id] = node_id
        nodes.append({"id": node_id, "label": label, "kind": kind})
        return node_id

    def add_edge(source: str, target: str, kind: str) -> None:
        if source == target:
            return
        edges.append({"from": source, "to": target, "kind": kind})

    file_nodes: list[str] = []
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        file_node_id = add_node(f"file:{relative_path}", path.name, "file")
        file_nodes.append(file_node_id)

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        file_node_id = add_node(f"file:{relative_path}", path.name, "file")
        content = path.read_text(encoding="utf-8", errors="ignore")
        suffix = path.suffix.lower()

        if suffix in {".html", ".htm"}:
            action_names = sorted(
                set(re.findall(r"\bdata-action\s*=\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE))
            )
            for action_name in action_names:
                action_node_id = add_node(f"action:{action_name}", action_name, "action")
                add_edge(file_node_id, action_node_id, "declares")
                for other_path in files:
                    if other_path.suffix.lower() not in {".js", ".ts", ".tsx", ".jsx"}:
                        continue
                    other_content = other_path.read_text(encoding="utf-8", errors="ignore")
                    if re.search(rf"['\"]{re.escape(action_name)}['\"]", other_content, re.IGNORECASE):
                        handler_node_id = add_node(f"handler:{action_name}", action_name, "handler")
                        add_edge(action_node_id, handler_node_id, "dispatches")
            class_names = sorted(
                set(re.findall(r"\bclass\s*=\s*['\"][^'\"]*\b([A-Za-z0-9_-]+)\b", content, re.IGNORECASE))
            )
            for class_name in class_names:
                class_node_id = add_node(f"class:{class_name}", class_name, "class")
                add_edge(file_node_id, class_node_id, "uses-class")
            element_ids = sorted(
                set(re.findall(r"\bid\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", content, re.IGNORECASE))
            )
            for element_id in element_ids:
                id_node_id = add_node(f"id:{element_id}", element_id, "id")
                add_edge(file_node_id, id_node_id, "uses-id")

        if suffix in {".css"}:
            selectors = sorted(set(re.findall(r"(?:^|[\s,>+~])([.#][A-Za-z0-9_-]+)", content)))
            for selector in selectors:
                style_node_id = add_node(f"style:{selector}", selector, "style")
                add_edge(file_node_id, style_node_id, "styles")

        if suffix in {".js", ".ts", ".tsx", ".jsx"}:
            function_names = sorted(
                set(
                    re.findall(
                        r"\b(?:function|const|let|var)\s+([A-Za-z0-9_]+)\s*(?:=|\()",
                        content,
                    )
                )
            )
            for function_name in function_names:
                function_node_id = add_node(f"function:{function_name}", function_name, "function")
                add_edge(file_node_id, function_node_id, "defines")

        if suffix == ".py":
            function_names = sorted(
                set(re.findall(r"^def\s+([A-Za-z0-9_]+)\s*\(", content, flags=re.MULTILINE))
            )
            class_names = sorted(set(re.findall(r"^class\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)))
            for function_name in function_names:
                function_node_id = add_node(f"function:{function_name}", function_name, "function")
                add_edge(file_node_id, function_node_id, "defines")
            for class_name in class_names:
                class_node_id = add_node(f"class:{class_name}", class_name, "class")
                add_edge(file_node_id, class_node_id, "defines")

    return {
        "repo_root": str(root),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }
