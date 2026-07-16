from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def resolve_default_repo_root() -> Path:
    configured_repo = os.environ.get("SBG_DASHBOARD_REPO_ROOT")
    if configured_repo:
        candidate = Path(configured_repo).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        return candidate

    current_dir = Path.cwd().resolve()
    for candidate in [current_dir, *current_dir.parents]:
        git_marker = candidate / ".git"
        if git_marker.exists():
            return candidate

    return REPO_ROOT.resolve()


from sbg.engine import RuleEngine, validate_manifest
from sbg.manifest import load_concepts, resolve_manifest_path, write_manifest
from sbg.script_maps import build_script_map


_SUGGESTION_TABLE: list[tuple[tuple[str, ...], dict[str, Any]]] = [
    (
        ("todo", "fixme", "marker", "note"),
        {
            "id": "suggested-marker-spam",
            "type": "marker-spam",
            "enabled": True,
            "pattern": "TO" + "DO",
            "threshold": 3,
            "match_mode": "plain_text",
        },
    ),
    (
        ("placeholder", "boilerplate", "sample", "lorem"),
        {
            "id": "suggested-placeholder",
            "type": "placeholder-comments",
            "enabled": True,
            "pattern": "placeholder",
            "match_mode": "plain_text",
        },
    ),
    (
        ("line length", "long line", "wrap", "readability"),
        {"id": "suggested-long-lines", "type": "long-lines", "enabled": True, "max_length": 120},
    ),
    (
        ("empty file", "blank file", "stub"),
        {"id": "suggested-empty-files", "type": "empty-files", "enabled": True},
    ),
    (
        ("large file", "oversized", "big file"),
        {"id": "suggested-file-size", "type": "file-size", "enabled": True, "max_bytes": 1048576},
    ),
    (
        ("secret", "credential", "api key", "token", "password"),
        {"id": "suggested-secret-scan", "type": "secret-scan", "enabled": True},
    ),
    (
        ("except", "eval", "exec", "mutable default", "ast", "complexity", "nesting"),
        {"id": "suggested-python-bare-except", "type": "python-bare-except", "enabled": True},
    ),
    (
        ("dynamic", "hard coded", "absolute path", "environment", "config", "portable"),
        {"id": "suggested-dynamic-config", "type": "dynamic-config", "enabled": True},
    ),
    (
        ("combine", "composite", "both", "either", "all of", "any of", "scoped", "group of"),
        {
            "id": "suggested-composite",
            "type": "composite",
            "enabled": True,
            "match": ["src/**/*.py"],
            "rules": [
                {"type": "long-lines", "max_length": 120},
                {"type": "placeholder-comments", "patterns": ["placeholder"]},
            ],
        },
    ),
]

_DEFAULT_SUGGESTION: dict[str, Any] = {
    "id": "suggested-placeholder",
    "type": "placeholder-comments",
    "enabled": True,
    "pattern": "placeholder",
    "match_mode": "plain_text",
}


def suggest_rule_for_prompt(prompt: str) -> dict[str, Any]:
    """Map a free-text prompt to a starter rule using a keyword lookup table."""

    prompt_lower = prompt.lower()
    template = _DEFAULT_SUGGESTION
    for tokens, candidate in _SUGGESTION_TABLE:
        if any(token in prompt_lower for token in tokens):
            template = candidate
            break
    rule = {key: (list(value) if isinstance(value, list) else value) for key, value in template.items()}
    if rule.get("type") == "composite":
        rule["logic"] = "any" if ("either" in prompt_lower or "any of" in prompt_lower) else "all"
    rule["description"] = f"Suggested from prompt: {prompt}"
    return rule


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_response(status=204, payload=None, content_type="text/plain; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_request(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/manifest":
            self._serve_manifest(parsed.query)
            return
        if path == "/api/manifest-save":
            self._serve_manifest_save()
            return
        if path == "/api/manifest-validate":
            self._serve_manifest_validate()
            return
        if path == "/api/concepts":
            self._serve_concepts()
            return
        if path == "/api/asset-map":
            self._serve_asset_map()
            return
        if path == "/api/source-view":
            self._serve_source_view()
            return
        if path == "/api/rule-suggest":
            self._serve_rule_suggest()
            return
        if path == "/api/scan":
            self._scan_repository()
            return
        if path == "/api/violation-context":
            self._serve_violation_context()
            return
        if path == "/api/pattern-preview":
            self._serve_pattern_preview()
            return
        if path == "/api/pattern-save":
            self._serve_pattern_save()
            return
        if path in {"/", "/index.html"}:
            self._serve_static_asset("index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._serve_static_asset("styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._serve_static_asset("app.js", "application/javascript; charset=utf-8")
            return
        self._serve_not_found()

    def _serve_manifest(self, query_string: str) -> None:
        params = parse_qs(query_string)
        manifest_path_value = params.get("manifest", [None])[0]
        if manifest_path_value:
            manifest_path = resolve_manifest_path(manifest_path_value)
        else:
            manifest_path = resolve_manifest_path(None)
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = {
            "manifest_path": str(manifest_path),
            "manifest": manifest_data,
            "default_repo_root": str(resolve_default_repo_root()),
            "concepts": load_concepts(),
        }
        self._send_json(payload)

    def _serve_concepts(self) -> None:
        payload = {
            "concepts": load_concepts(),
            "default_repo_root": str(resolve_default_repo_root()),
        }
        self._send_json(payload)

    def _serve_asset_map(self) -> None:
        repo_root = resolve_default_repo_root()
        asset_graph = self._build_asset_graph(repo_root)
        self._send_json(asset_graph)

    def _serve_source_view(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        source_path = payload.get("path")
        if not source_path:
            self._send_json({"error": "path is required"})
            return
        manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        resolved_path = self._resolve_source_path(repo_root, manifest_path, source_path)
        if resolved_path is None:
            self._send_json({"error": "source file not found"})
            return
        try:
            content = resolved_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = resolved_path.read_text(encoding="utf-8", errors="replace")
        relative_path = self._display_path_for(resolved_path, repo_root, manifest_path)
        self._send_json({
            "path": relative_path,
            "content": content,
            "line_count": len(content.splitlines()),
        })

    def _build_asset_graph(self, repo_root: Path) -> dict[str, Any]:
        web_root = repo_root / "web"
        scope_path = web_root if web_root.exists() else repo_root
        return build_script_map(repo_root, scope_path=scope_path)

    def _serve_manifest_save(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        manifest_payload = payload.get("manifest")
        if isinstance(manifest_payload, str):
            try:
                manifest_payload = json.loads(manifest_payload)
            except json.JSONDecodeError as exc:
                self._send_json({"error": f"invalid manifest JSON: {exc.msg}"})
                return
        if not isinstance(manifest_payload, dict):
            self._send_json({"error": "manifest payload must be an object"})
            return
        manifest_path = write_manifest(manifest_path, manifest_payload, repo_root=repo_root)
        self._send_json({
            "manifest_path": str(manifest_path),
            "manifest": manifest_payload,
        })

    def _serve_manifest_validate(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        manifest_payload = payload.get("manifest")
        if isinstance(manifest_payload, str):
            try:
                manifest_payload = json.loads(manifest_payload)
            except json.JSONDecodeError as exc:
                self._send_json({"valid": False, "errors": [f"invalid manifest JSON: {exc.msg}"]})
                return
        if manifest_payload is None:
            manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
            try:
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                self._send_json({"valid": False, "errors": [f"could not load manifest: {exc}"]})
                return
        errors = validate_manifest(manifest_payload)
        self._send_json({
            "valid": not errors,
            "errors": errors,
            "rule_count": len(manifest_payload.get("rules", [])) if isinstance(manifest_payload, dict) else 0,
        })

    def _serve_rule_suggest(self) -> None:
        payload = self._read_json_payload()
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            self._send_json({"error": "prompt is required"})
            return
        rule = suggest_rule_for_prompt(prompt)
        self._send_json({"prompt": prompt, "rule": rule})

    def _scan_repository(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        manifest_target = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)

        engine = RuleEngine.from_manifest_path(manifest_target)
        violations = engine.scan_repository(repo_root)

        summary = {
            "total": len(violations),
            "by_rule": dict(sorted(Counter(violation.rule_id for violation in violations).items())),
            "by_severity": dict(sorted(Counter(violation.severity for violation in violations).items())),
        }
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(manifest_target),
            "violation_count": len(violations),
            "summary": summary,
            "violations": [violation.as_dict() for violation in violations],
        }
        self._send_json(response_payload)

    def _serve_violation_context(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        violation = payload.get("violation") or {}
        if not isinstance(violation, dict):
            self._send_json({"error": "violation payload must be an object"})
            return

        relative_path = violation.get("path")
        if not relative_path:
            self._send_json({"path": None, "line": None, "lines": []})
            return

        file_path = self._resolve_file_path(repo_root, relative_path)
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"path": relative_path, "line": None, "lines": []})
            return

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        line_number = violation.get("line")
        if line_number is not None:
            try:
                line_number = int(line_number)
            except (TypeError, ValueError):
                line_number = None

        if line_number is None or line_number < 1:
            start_index = 0
            end_index = min(len(lines), 8)
        else:
            start_index = max(0, line_number - 3)
            end_index = min(len(lines), line_number + 2)

        context_lines = [
            {"line": index + 1, "text": lines[index] if index < len(lines) else ""}
            for index in range(start_index, end_index)
        ]
        response_payload = {
            "path": relative_path,
            "line": line_number,
            "line_count": len(lines),
            "lines": context_lines,
            "violation": violation,
        }
        self._send_json(response_payload)

    def _serve_pattern_preview(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        base_manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        rule = self._build_rule_payload(payload)
        manifest = self._load_manifest(base_manifest_path)
        preview_manifest = {"rules": [*manifest.get("rules", []), rule]}
        engine = RuleEngine(preview_manifest)
        violations = engine.scan_repository(repo_root)
        pattern_violations = [violation for violation in violations if violation.rule_id == rule["id"]]
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(base_manifest_path),
            "rule": rule,
            "preview_violation_count": len(pattern_violations),
            "violations": [violation.as_dict() for violation in pattern_violations],
        }
        self._send_json(response_payload)

    def _serve_pattern_save(self) -> None:
        payload = self._read_json_payload()
        repo_root = self._resolve_repo_root(payload.get("repo_root"))
        base_manifest_path = self._resolve_manifest_path(payload.get("manifest_path"), repo_root=repo_root)
        target_manifest_path = (
            payload.get("output_manifest_path")
            or payload.get("target_manifest_path")
            or payload.get("manifest_path")
        )
        target_manifest_path = self._resolve_manifest_path(target_manifest_path, repo_root=repo_root)
        rule = self._build_rule_payload(payload)
        manifest = self._load_manifest(base_manifest_path)
        rules = list(manifest.get("rules", []))
        if not any(existing.get("id") == rule["id"] for existing in rules):
            rules.append(rule)
        else:
            rules = [existing if existing.get("id") != rule["id"] else rule for existing in rules]
        manifest["rules"] = rules
        manifest_path = write_manifest(target_manifest_path, manifest, repo_root=repo_root)
        preview_manifest = {"rules": rules}
        engine = RuleEngine(preview_manifest)
        violations = engine.scan_repository(repo_root)
        pattern_violations = [violation for violation in violations if violation.rule_id == rule["id"]]
        response_payload = {
            "repo_root": str(repo_root),
            "manifest_path": str(manifest_path),
            "rule": rule,
            "saved_rule_count": len(rules),
            "preview_violation_count": len(pattern_violations),
            "violations": [violation.as_dict() for violation in pattern_violations],
            "manifest": manifest,
        }
        self._send_json(response_payload)

    def _build_rule_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        pattern_name = str(payload.get("pattern_name") or "").strip()
        if not pattern_name:
            raise ValueError("pattern_name is required")
        pattern_text = str(payload.get("pattern_text") or "").strip()
        rule_kind = str(payload.get("rule_kind") or "placeholder-comments")
        pattern_type = str(payload.get("pattern_type") or payload.get("match_mode") or "plain_text")
        rule: dict[str, Any] = {
            "id": pattern_name,
            "type": rule_kind,
            "enabled": True,
            "match_mode": pattern_type,
        }
        if pattern_text:
            rule["pattern"] = pattern_text
        if rule_kind == "marker-spam":
            rule["threshold"] = int(payload.get("threshold") or 1)
        if rule_kind == "long-lines":
            rule["max_length"] = int(payload.get("max_length") or 120)
        if rule_kind == "file-size":
            rule["max_bytes"] = int(payload.get("max_bytes") or 1024 * 1024)
        if rule_kind in {"placeholder-comments", "marker-spam"}:
            if pattern_text:
                rule["patterns"] = [pattern_text]
        if payload.get("description"):
            rule["description"] = str(payload.get("description"))
        return rule

    def _load_manifest(self, path: Path) -> dict[str, Any]:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"rules": []}

    def _resolve_repo_root(self, repo_root: str | Path | None) -> Path:
        if repo_root:
            resolved_repo = Path(repo_root).expanduser()
            if not resolved_repo.is_absolute():
                resolved_repo = (Path.cwd() / resolved_repo).resolve()
            return resolved_repo.resolve()
        return resolve_default_repo_root()

    def _resolve_manifest_path(self, manifest_path: str | Path | None, repo_root: str | Path | None = None) -> Path:
        if manifest_path:
            return resolve_manifest_path(manifest_path, repo_root=repo_root)
        return resolve_manifest_path(None, repo_root=repo_root)

    def _resolve_file_path(self, repo_root: Path, relative_path: str | Path) -> Path:
        candidate = Path(relative_path).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate.resolve()

    def _resolve_source_path(self, repo_root: Path, manifest_path: Path | None, source_path: str | Path) -> Path | None:
        candidate = Path(source_path).expanduser()
        if candidate.is_absolute():
            candidate = candidate.resolve()
            if candidate.exists() and candidate.is_file() and self._is_path_within(candidate, repo_root, manifest_path):
                return candidate
            return None

        repo_candidate = (repo_root / candidate).resolve()
        if repo_candidate.exists() and repo_candidate.is_file():
            return repo_candidate

        if manifest_path is not None:
            manifest_candidate = (manifest_path.parent / candidate).resolve()
            if manifest_candidate.exists() and manifest_candidate.is_file():
                return manifest_candidate

        return None

    def _display_path_for(self, resolved_path: Path, repo_root: Path, manifest_path: Path | None) -> str:
        for base in [repo_root.resolve(), manifest_path.parent.resolve() if manifest_path is not None else None]:
            if base is None:
                continue
            try:
                return resolved_path.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved_path.as_posix()

    def _is_path_within(self, candidate: Path, repo_root: Path, manifest_path: Path | None) -> bool:
        for base in [repo_root.resolve(), manifest_path.parent.resolve() if manifest_path is not None else None]:
            if base is None:
                continue
            try:
                candidate.relative_to(base)
                return True
            except ValueError:
                continue
        return False

    def _read_json_payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"invalid JSON: {exc.msg}"})
            raise ValueError("invalid JSON") from exc
        if not isinstance(payload, dict):
            self._send_json({"error": "request body must be a JSON object"})
            raise ValueError("request body must be a JSON object")
        return payload

    def _serve_static_asset(self, asset_name: str, content_type: str) -> None:
        asset_path = self._resolve_static_path(asset_name)
        if asset_path is None:
            self._serve_not_found()
            return
        self._send_response(status=200, payload=asset_path.read_bytes(), content_type=content_type)

    def _resolve_static_path(self, asset_name: str) -> Path | None:
        candidate = (WEB_ROOT / asset_name).resolve()
        if not candidate.exists() or not candidate.is_file():
            return None
        try:
            candidate.relative_to(WEB_ROOT)
        except ValueError:
            return None
        return candidate

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_response(status=200, payload=body, content_type="application/json; charset=utf-8")

    def _send_response(self, status: int, payload: bytes | None, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(0 if payload is None else len(payload)))
        self.end_headers()
        if payload is not None:
            self.wfile.write(payload)

    def _serve_not_found(self) -> None:
        body = b"Not Found"
        self._send_response(status=404, payload=body, content_type="text/plain; charset=utf-8")


def create_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    bind_host = host.strip() if host else "0.0.0.0"
    if bind_host not in {"0.0.0.0", "127.0.0.1", "localhost", "::", "::1"}:
        try:
            socket.inet_aton(bind_host)
        except OSError:
            bind_host = "127.0.0.1"
    return ThreadingHTTPServer((bind_host, port), DashboardHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the SBG dashboard locally")
    parser.add_argument("--host", default=os.environ.get("SBG_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SBG_WEB_PORT", "8000")))
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"Serving SBG dashboard at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
